from functools import cache, cached_property

import numpy as np
import pandas as pd

from interface.common import DEFAULT_GAME, timed, timed_often
from interface.recording.spec import TABLE
from interface.script import read
from ...catalogue import ENTITIES, RECORDED_PARAMS, SITED
from ...data.features import CATEGORIES, History, INSTITUTIONS, NUMBERS, PRICES, SITE, TARIFFS, TAXES, LiveLookup, Versions, categories, located
from . import diplomacy

PARAMETERS={name:list(params) for name,params in RECORDED_PARAMS.items()}
ENTITY={kind:('formation' if kind=='military_formation' else kind) for kind in ENTITIES}
OMIT={'first_name_key','last_name_key','name_key','localized_name_key','company_name_key','dynamic_name_key','dynamic_adjective_key',
      'map_color_override','color_red','color_green','color_blue','power_bloc_map_texture','trends_initialized'}
STATE=NUMBERS+PRICES+INSTITUTIONS+TARIFFS+TAXES
PLAYER_FIELDS=STATE+CATEGORIES+diplomacy.PLAYER_NUMERIC+diplomacy.PLAYER_CATEGORICAL
MISSING='<missing>'
ABSENT='<not-applicable>'
TRAITS=sorted(name for name,_ in read(DEFAULT_GAME/'game','common/character_traits'))
STATE_TRAITS=sorted(name for name,_ in read(DEFAULT_GAME/'game','common/state_traits'))
STATE_REPORTS={'state_economy_report':['market_access'],'state_status_report':['is_incorporated']}
SITE_ACTIONS=frozenset(SITED)|{'raise_subsidies','lower_subsidies','raise_subsidies_statewide','lower_subsidies_statewide',
                             'nationalise_building','withdraw_building_from_sale','offer_building_for_sale','buy_out_statewide','expropriate_statewide',
                             'cancel_queued_construction','raise_building_priority','lower_building_priority','halt_construction_sector','restart_construction_sector',
                             'raise_state_decrees','lower_state_decrees','raise_incorporation','lower_incorporation',
                             'relocate_national_capital','relocate_market_capital','grant_charter_for_region','revoke_charter_for_region',
                             'establish_colony','resume_colony','pause_colony','give_up_colony','stake_colonial_claim',
                             'demand_for_state','add_demand_for_state','add_state_article_demand','propose_state_article',
                             'sway_with_state','sway_with_state_war_goal','sway_with_state_article','grant_state_to_subject','take_state_from_subject',
                             'ask_overlord_for_state','give_state_in_trade','ask_state_in_trade','raise_regular_army','call_up_conscripts'}


@cache
@timed_often
def columns(table):
    return [column for column in TABLE[table+'_history'].columns if column.name not in OMIT]


@cache
@timed_often
def identities(table):
    return [column for column in columns(table) if column.vocabulary or column.enum] if table+'_history' in TABLE else []


@timed_often
def categorical(column):
    return bool(column.vocabulary or column.enum or column.check or column.kind=='text')


@timed_often
def fields():
    numeric=list(STATE)+diplomacy.PLAYER_NUMERIC+diplomacy.COUNTERPART_NUMERIC
    categories=list(CATEGORIES)+['action']+diplomacy.PLAYER_CATEGORICAL+diplomacy.COUNTERPART_CATEGORICAL
    for param,kind in sorted({pair for pairs in PARAMETERS.values() for pair in pairs}):
        prefix=f'parameter.{param}.{kind}'
        if kind=='int':
            numeric.append(prefix)
        elif kind not in ENTITY:
            categories.append(prefix)
        else:
            table=ENTITY[kind]
            for column in columns(table):
                name=f'{prefix}.{column.name}'
                if column.entity:
                    categories.extend(f'{name}.{field.name}' for field in identities(column.entity))
                else:
                    (categories if categorical(column) else numeric).append(name)
    numeric.extend(f'target_character.trait.{trait}' for trait in TRAITS)
    numeric.extend(SITE)
    numeric.extend(f'site.{name}' for names in STATE_REPORTS.values() for name in names)
    categories.extend(f'site.trait.{trait}' for trait in STATE_TRAITS)
    return numeric,categories


NUMERIC,CATEGORICAL=fields()


class Historical:
    @timed
    def __init__(self,connection,runs):
        self.state=History(connection,runs)
        self.diplomacy=diplomacy.Historical(connection,runs)
        tables=set(ENTITY.values())
        tables.update(column.entity for table in list(tables) for column in columns(table) if column.entity and identities(column.entity))
        self.tables={table:Versions(connection,table+'_history',[table],[column.name for column in columns(table)],runs) for table in tables}
        self.reports={table:Versions(connection,table,['state'],names,runs) for table,names in STATE_REPORTS.items()}
        self.state_traits=Versions(connection,'state_region_trait',['state_region','state_trait'],[],runs)
        self.traits=Versions(connection,'character_assigned_trait',['character','character_trait'],[],runs)
        self.trait_keys={}
        for run,keys in self.traits.by_run.items():
            for character,trait in keys:
                self.trait_keys.setdefault((run,character),[]).append(trait)

    @timed_often
    def at(self,run,seq):
        return HistoricalPoint(self,run,seq)


class HistoricalPoint:
    @timed_often
    def __init__(self,history,run,seq):
        self.history,self.run,self.seq=history,run,seq
        self.state=history.state.at(run,seq)
        self.hours=history.state.hours.at(run,seq)[0]
        self.entities={}

    @timed_often
    def entity(self,table,ident):
        key=(table,ident)
        if key not in self.entities:
            found=self.history.tables[table].at(self.run,(ident,),self.seq)
            self.entities[key]=None if found is None else dict(zip([column.name for column in columns(table)],found))
        return self.entities[key]

    @timed_often
    def traits(self,character):
        return sorted(trait for trait in self.history.trait_keys.get((self.run,character),[]) if self.history.traits.at(self.run,(character,trait),self.seq) is not None)

    @timed_often
    def report(self,table,state):
        return self.history.reports[table].at(self.run,(state,),self.seq)

    @cached_property
    @timed_often
    def diplomacy(self):
        return self.history.diplomacy.at(self.state.player,self.hours,self.run,self.seq)

    @cached_property
    @timed_often
    def state_traits(self):
        found={}
        history=self.history.state_traits
        for region,trait in history.by_run.get(self.run,[]):
            if history.at(self.run,(region,trait),self.seq) is not None:
                found.setdefault(region,set()).add(trait)
        return found


class Live:
    @timed_often
    def __init__(self,snapshot):
        self.snapshot=snapshot
        self.state=LiveLookup(snapshot)
        self.hours=snapshot.hours
        self.tables={}

    @timed_often
    def entity(self,table,ident):
        if table not in self.tables:
            names=[column.name for column in columns(table)]
            self.tables[table]={key:dict(zip(names,values)) for key,*values in self.snapshot.rows(table,','.join([table,*names]))}
        return self.tables[table].get(ident)

    @timed_often
    def traits(self,character):
        return sorted(trait for owner,trait in self.snapshot.rows('character_assigned_trait','character,character_trait') if owner==character)

    @timed_often
    def report(self,table,state):
        if table not in self.tables:
            self.tables[table]={key:values for key,*values in self.snapshot.rows(table,','.join(['state',*STATE_REPORTS[table]]))}
        return self.tables[table].get(state)

    @cached_property
    @timed_often
    def diplomacy(self):
        return diplomacy.live(self.snapshot)

    @cached_property
    @timed_often
    def state_traits(self):
        found={}
        for region,trait in self.snapshot.rows('state_region_trait','state_region,state_trait'):
            found.setdefault(region,set()).add(trait)
        return found


@timed_often
def context(point):
    state=point.state
    if state.numbers is None:
        raise ValueError('The starting snapshot lacks required player state')
    return {**dict(zip(STATE,state.numbers+state.prices+state.institutions+state.tariffs+state.taxes)),**dict(zip(CATEGORIES,categories(state))),
            **point.diplomacy.overview}


@timed_often
def action_features(name,params,point):
    found={'action':name}
    expected=dict(PARAMETERS[name])
    if set(params)!=set(expected):
        raise ValueError(f'{name} parameters differ from the catalogue: {set(params)^set(expected)}')
    for param,kind in expected.items():
        value=params[param]
        prefix=f'parameter.{param}.{kind}'
        if kind=='int':
            found[prefix]=float(value)
        elif kind not in ENTITY:
            found[prefix]=str(value)
        else:
            table=ENTITY[kind]
            target=point.entity(table,value)
            for column in columns(table):
                key=f'{prefix}.{column.name}'
                item=None if target is None else target[column.name]
                if column.entity:
                    related=point.entity(column.entity,item) if item is not None and identities(column.entity) else None
                    for field in identities(column.entity):
                        raw=None if related is None else related[field.name]
                        found[f'{key}.{field.name}']=MISSING if raw is None else str(raw)
                elif categorical(column):
                    found[key]=MISSING if item is None else str(item)
                else:
                    found[key]=np.nan if item is None else (point.hours-item)/24 if column.kind=='game_hours' else float(item)
            if table in ('character','interest_group'):
                character=value if table=='character' else None if target is None else target['leader']
                if character is not None:
                    traits=set(point.traits(character))
                    found.update({f'target_character.trait.{trait}':float(trait in traits) for trait in TRAITS})
    if name in SITE_ACTIONS:
        state,kind=located(name,params,point.state)
        found.update(zip(SITE,point.state.site(state,kind)))
        for table,names in STATE_REPORTS.items():
            values=point.report(table,state)
            found.update({f'site.{field}':np.nan if values is None or values[i] is None else float(values[i]) for i,field in enumerate(names)})
        region,_=point.state.state(state)
        traits=point.state_traits.get(region,set())
        found.update({f'site.trait.{trait}':MISSING if region is None else str(trait in traits) for trait in STATE_TRAITS})
    found.update(point.diplomacy.target(diplomacy.counterpart(name,params,point)))
    return found


@timed
def frame(rows):
    values=pd.DataFrame(rows)
    numeric=values.reindex(columns=NUMERIC).astype(np.float32)
    categories=values.reindex(columns=CATEGORICAL).fillna(ABSENT).astype(str).astype('category')
    return pd.concat([numeric,categories],axis=1)


@timed
def live(snapshot,actions):
    point=Live(snapshot)
    state=context(point)
    return frame([{**state,**action_features(name,params,point)} for name,params in actions])
