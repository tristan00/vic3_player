from functools import cache, cached_property

import numpy as np
import pandas as pd

from interface.common import DEFAULT_GAME, evidence, timed, timed_often
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
STATE_PARTS=((NUMBERS,'numbers'),(PRICES,'prices'),(INSTITUTIONS,'institutions'),(TARIFFS,'tariffs'),(TAXES,'taxes'),(CATEGORIES[:-1],'laws'))
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


@cache
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


class Selection:
    @timed
    def __init__(self,selected=NUMERIC+CATEGORICAL):
        self.names=set(selected)
        self.parameters={}
        for param,kind in {pair for pairs in PARAMETERS.values() for pair in pairs}:
            prefix=f'parameter.{param}.{kind}'
            if kind in ENTITY:
                found=[]
                for column in columns(ENTITY[kind]):
                    key=f'{prefix}.{column.name}'
                    related=[field for field in identities(column.entity) if f'{key}.{field.name}' in self.names] if column.entity else []
                    if key in self.names or related:
                        found.append((column,related))
                self.parameters[prefix]=found
        self.traits=[trait for trait in TRAITS if f'target_character.trait.{trait}' in self.names]
        self.site=bool(self.names.intersection(SITE+[f'site.{field}' for fields in STATE_REPORTS.values() for field in fields]))
        self.site_traits=[trait for trait in STATE_TRAITS if f'site.trait.{trait}' in self.names]
        self.state=[(attribute,len(names),[i for i,name in enumerate(names) if name in self.names],[name for name in names if name in self.names])
                    for names,attribute in STATE_PARTS if self.names.intersection(names)]
        self.player=[name for name in diplomacy.PLAYER_NUMERIC+diplomacy.PLAYER_CATEGORICAL if name in self.names]
        self.diplomacy=bool(self.names.intersection(diplomacy.COUNTERPART_NUMERIC+diplomacy.COUNTERPART_CATEGORICAL))
        self.history={'hours','treasury','population','politics'}
        for names,required in (
            (NUMBERS,{'legitimacy','budget','interest','sol','construction','gdp','government','queue','military','wars','army','infamy','groups','group_stats','policy','enactments','law_rows','battles','sliders'}),
            (PRICES,{'markets','goods','world'}),(INSTITUTIONS,{'institution_rows'}),(TARIFFS,{'tariff_rows'}),(TAXES,{'taxed'}),
            (CATEGORIES[:-1],{'law_rows'}),(['player.country_rank'],{'countries'})):
            if self.names.intersection(names):
                self.history.update(required)
        if self.site:
            self.history.update(('buildings','people','living','literate','shares'))
        if self.site_traits or self.diplomacy:
            self.history.update(('states','buildings'))


ALL=Selection()


class Historical:
    @timed
    def __init__(self,connection,runs,selection=ALL):
        self.state=History(connection,runs,selection.history)
        if selection.diplomacy or selection.names.intersection(diplomacy.PLAYER_NUMERIC+diplomacy.PLAYER_CATEGORICAL):
            self.diplomacy=diplomacy.Historical(connection,runs)
        tables={ENTITY[prefix.split('.')[2]] for prefix,specs in selection.parameters.items() if specs}
        if selection.diplomacy:
            tables.update(('treaty','war','diplomatic_play'))
        if selection.traits:
            tables.update(('character','interest_group'))
            self.traits=Versions(connection,'character_assigned_trait',['character','character_trait'],[],runs)
            self.trait_keys={}
            for run,keys in self.traits.by_run.items():
                for character,trait in keys:
                    self.trait_keys.setdefault((run,character),[]).append(trait)
        tables.update(column.entity for table in list(tables) for column in columns(table) if column.entity and identities(column.entity))
        self.tables={table:Versions(connection,table+'_history',[table],[column.name for column in columns(table)],runs) for table in tables}
        self.reports={table:Versions(connection,table,['state'],names,runs) for table,names in STATE_REPORTS.items()
                      if any(f'site.{name}' in selection.names for name in names)}
        if selection.site_traits:
            self.state_traits=Versions(connection,'state_region_trait',['state_region','state_trait'],[],runs)

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
def context(point,selection=ALL):
    state=point.state
    found={}
    for attribute,size,indices,names in selection.state:
        values=getattr(state,attribute)
        if values is None:
            raise ValueError(evidence(attribute=attribute))
        found.update(zip(names,values if len(names)==size else [values[i] for i in indices]))
    if 'player.country_rank' in selection.names:
        rank=state.country(state.player)
        found['player.country_rank']='none' if rank is None else rank
    if selection.player:
        overview=point.diplomacy.overview
        found.update((name,overview[name]) for name in selection.player)
    return found


@timed_often
def action_features(name,params,point,selection=ALL):
    found={'action':name} if 'action' in selection.names else {}
    expected=dict(PARAMETERS[name])
    if set(params)!=set(expected):
        raise ValueError(evidence(name=name,differing=set(params)^set(expected)))
    for param,kind in expected.items():
        value=params[param]
        prefix=f'parameter.{param}.{kind}'
        if kind=='int':
            if prefix in selection.names:
                found[prefix]=float(value)
        elif kind not in ENTITY:
            if prefix in selection.names:
                found[prefix]=str(value)
        else:
            table=ENTITY[kind]
            selected=selection.parameters[prefix]
            traits=selection.traits and table in ('character','interest_group')
            if not selected and not traits:
                continue
            target=point.entity(table,value)
            for column,related_fields in selected:
                key=f'{prefix}.{column.name}'
                item=None if target is None else target[column.name]
                if column.entity:
                    related=point.entity(column.entity,item) if item is not None else None
                    for field in related_fields:
                        raw=None if related is None else related[field.name]
                        found[f'{key}.{field.name}']=MISSING if raw is None else str(raw)
                elif categorical(column):
                    found[key]=MISSING if item is None else str(item)
                else:
                    found[key]=np.nan if item is None else (point.hours-item)/24 if column.kind=='game_hours' else float(item)
            if traits:
                character=value if table=='character' else None if target is None else target['leader']
                if character is not None:
                    traits=set(point.traits(character))
                    found.update({f'target_character.trait.{trait}':float(trait in traits) for trait in selection.traits})
    if name in SITE_ACTIONS and (selection.site or selection.site_traits):
        state,kind=located(name,params,point.state)
        if selection.site:
            found.update((key,value) for key,value in zip(SITE,point.state.site(state,kind)) if key in selection.names)
            for table,names in STATE_REPORTS.items():
                if any(f'site.{field}' in selection.names for field in names):
                    values=point.report(table,state)
                    found.update({f'site.{field}':np.nan if values is None or values[i] is None else float(values[i]) for i,field in enumerate(names) if f'site.{field}' in selection.names})
        if selection.site_traits:
            region,_=point.state.state(state)
            traits=point.state_traits.get(region,set())
            found.update({f'site.trait.{trait}':MISSING if region is None else str(trait in traits) for trait in selection.site_traits})
    if selection.diplomacy:
        found.update((key,value) for key,value in point.diplomacy.target(diplomacy.counterpart(name,params,point)).items() if key in selection.names)
    return found


@timed
def frame(rows,columns=NUMERIC+CATEGORICAL):
    found={name:([],[]) for name in columns}
    keys=tuple(rows[0]) if len(rows) else ()
    if keys and all(tuple(row)==keys for row in rows):
        every=range(len(rows))
        for name,values in zip(keys,zip(*(row.values() for row in rows))):
            if name in found:
                found[name]=(every,values)
    else:
        for i,row in enumerate(rows):
            for name,value in row.items():
                if name in found:
                    indices,values=found[name]
                    indices.append(i)
                    values.append(value)
    result={}
    numeric=set(NUMERIC)
    for name,(indices,values) in found.items():
        if name in numeric:
            column=np.full(len(rows),np.nan,np.float32)
            column[indices]=values
        else:
            selected=pd.Categorical(pd.Series(values,dtype=object).fillna(ABSENT).astype(str))
            if len(indices)==len(rows):
                column=selected
            else:
                categories=selected.categories.union([ABSENT]).sort_values()
                codes=np.full(len(rows),categories.get_loc(ABSENT),np.int32)
                codes[indices]=categories.get_indexer(selected.categories)[selected.codes]
                column=pd.Categorical.from_codes(codes,categories)
        result[name]=column
    return pd.DataFrame(result,index=range(len(rows)),copy=False)


@timed
def described(snapshot,actions):
    point=Live(snapshot)
    state=context(point)
    return [{**state,**action_features(name,params,point)} for name,params in actions]


@timed
def live(snapshot,actions):
    return frame(described(snapshot,actions))
