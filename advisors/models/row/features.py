from functools import cache

import numpy as np
import pandas as pd

from interface.common import DEFAULT_GAME, timed, timed_often
from interface.recording.spec import TABLE
from interface.script import read
from ...catalogue import ENTITIES, PARAMS, SITED
from ...data.features import CATEGORIES, History, INSTITUTIONS, NUMBERS, PRICES, SITE, TARIFFS, TAXES, LiveLookup, Versions, categories, located

PARAMETERS={name:list(params) for name,params in PARAMS.items()}
ENTITY={kind:('formation' if kind=='military_formation' else kind) for kind in ENTITIES}
OMIT={'first_name_key','last_name_key','name_key','localized_name_key','company_name_key','dynamic_name_key','dynamic_adjective_key',
      'map_color_override','color_red','color_green','color_blue','power_bloc_map_texture','trends_initialized'}
STATE=NUMBERS+PRICES+INSTITUTIONS+TARIFFS+TAXES
MISSING='<missing>'
ABSENT='<not-applicable>'
TRAITS=sorted(name for name,_ in read(DEFAULT_GAME/'game','common/character_traits'))


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
    numeric=list(STATE)
    categories=list(CATEGORIES)+['action']
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
    return numeric,categories


NUMERIC,CATEGORICAL=fields()


class Historical:
    @timed
    def __init__(self,connection,runs):
        self.state=History(connection,runs)
        tables=set(ENTITY.values())
        tables.update(column.entity for table in list(tables) for column in columns(table) if column.entity and identities(column.entity))
        self.tables={table:Versions(connection,table+'_history',[table],[column.name for column in columns(table)],runs) for table in tables}
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
def context(point):
    state=point.state
    if state.numbers is None:
        raise ValueError('The starting snapshot lacks required player state')
    return {**dict(zip(STATE,state.numbers+state.prices+state.institutions+state.tariffs+state.taxes)),**dict(zip(CATEGORIES,categories(state)))}


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
    if name in SITED:
        found.update(zip(SITE,point.state.site(*located(name,params,point.state))))
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
