from collections import Counter

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix

from advisors.catalogue import RECORDED_PARAMS
from advisors.data import features as state
from advisors.data import histograms as hist
from advisors.models.row import features as row
from interface.common import evidence, timed, timed_often


@timed_often
def context_groups():
    split={'context.construction':state.CONSTRUCTION,'context.military':state.MILITARY,'context.interest_groups':state.GROUP_FEATURES,'context.policy':state.POLICY,
           'context.law_enactment':state.ENACTMENT,'context.war':state.WAR,'context.world':state.WORLD}
    taken={column for columns in split.values() for column in columns}
    return {'context.economy':[column for column in state.NUMBERS if column not in taken],**{name:list(columns) for name,columns in split.items()},
            'context.prices':list(state.PRICES),
            'context.institutions':list(state.INSTITUTIONS),'context.tariffs':list(state.TARIFFS),
            'context.consumption_taxes':list(state.TAXES),'context.laws':list(state.LAWS),
            'context.rank':['player.country_rank']}


@timed
def taxonomy(model):
    groups={name:{'kind':'columns','role':'context','columns':columns} for name,columns in context_groups().items()}
    if model=='row':
        groups['context.diplomacy']={'kind':'columns','role':'context','columns':row.diplomacy.PLAYER_NUMERIC+row.diplomacy.PLAYER_CATEGORICAL}
        groups['option.action']={'kind':'columns','role':'option','columns':['action']}
        groups['option.diplomacy']={'kind':'columns','role':'option','columns':row.diplomacy.COUNTERPART_NUMERIC+row.diplomacy.COUNTERPART_CATEGORICAL}
        groups['option.character_traits']={'kind':'columns','role':'option','columns':[f'target_character.trait.{trait}' for trait in row.TRAITS]}
        groups['option.site']={'kind':'columns','role':'option','columns':state.SITE+[f'site.{field}' for fields in row.STATE_REPORTS.values() for field in fields]}
        groups['option.site_traits']={'kind':'columns','role':'option','columns':[f'site.trait.{trait}' for trait in row.STATE_TRAITS]}
        for param,kind in sorted({pair for pairs in RECORDED_PARAMS.values() for pair in pairs}):
            prefix=f'parameter.{param}.{kind}'
            for dtype,columns in [('numeric',row.NUMERIC),('categorical',row.CATEGORICAL)]:
                selected=[name for name in columns if name==prefix or name.startswith(prefix+'.')]
                if selected:
                    groups[f'option.{prefix}.{dtype}']={'kind':'columns','role':'option','columns':selected}
        found=[column for group in groups.values() for column in group['columns']]
        if len(found)!=len(set(found)) or set(found)!=set(row.NUMERIC+row.CATEGORICAL):
            raise ValueError(evidence(found=len(found),distinct=len(set(found)),differing=set(found)^set(row.NUMERIC+row.CATEGORICAL)))
    elif model=='histogram':
        groups['option.batch_size']={'kind':'columns','role':'option','columns':['batch_size']}
        actions={hist.ACTION,*hist.ANSWER,*hist.QUEUE,*hist.PLAY,*hist.PLAY_CONTEXT,*hist.PLAY_PACTS,*hist.LEADERS,*state.SITE}
        actions.update(f'{action}.{param}' for action,params in RECORDED_PARAMS.items() for param,_ in params)
        for name in sorted(actions):
            groups['option.'+name]={'kind':'histogram','role':'option','source':'actions','family':name}
        for name in [hist.BUILDINGS,hist.METHODS,*hist.COUNTRY]:
            groups['holdings.'+name]={'kind':'histogram','role':'context','source':'held','family':name}
    else:
        raise ValueError(evidence(model=model))
    return groups


@timed_often
def selected_columns(groups,config):
    return [column for name,group in groups.items() if config['feature.'+name]!='off' and group['kind']=='columns' for column in group['columns']]


@timed_often
def selected_families(groups,config):
    return {source:{group['family'] for name,group in groups.items() if group['kind']=='histogram' and group['source']==source and config['feature.'+name]!='off'}
            for source in ('actions','held')}


class Encoder:
    @timed
    def __init__(self,model,config,groups):
        self.model,self.config,self.groups=model,config,groups
        self.columns=selected_columns(groups,config)
        self.vocabulary={}

    @timed
    def fit(self,records):
        if self.model=='histogram':
            frequencies={}
            for record in records:
                for source in ('actions','held'):
                    for family,value in {(family,value) for family,value,_ in record[source]}:
                        frequencies.setdefault((source,family),Counter())[value]+=1
            for name,group in self.groups.items():
                if group['kind']!='histogram' or self.config['feature.'+name]=='off':
                    continue
                counts=frequencies.get((group['source'],group['family']),{})
                limit=self.config['bins.'+name]
                values=sorted(counts,key=lambda value:(-counts[value],value))
                self.vocabulary[name]=values if limit==0 else values[:limit]
        return self

    @timed
    def transform(self,records):
        if self.model=='row':
            return records.loc[:,self.columns]
        frame=pd.DataFrame([{column:record['state'][column] if column!='batch_size' else record['size'] for column in self.columns} for record in records])
        for column in set(state.CATEGORIES)&set(frame.columns):
            frame[column]=frame[column].astype('category')
        for column in set(frame.columns)-set(state.CATEGORIES):
            frame[column]=frame[column].astype(np.float32)
        mapping={}
        labels=[]
        for name,values in self.vocabulary.items():
            group=self.groups[name]
            mapping[group['source'],group['family']]=({value:len(labels)+i for i,value in enumerate(values)},len(labels)+len(values),self.config['feature.'+name]=='share')
            labels.extend(f'{name}.{position}={value}' for position,value in enumerate([*values,'<other>']))
        indices,columns,weights=[],[],[]
        for index,record in enumerate(records):
            for source in ('actions','held'):
                for family,value,weight in record[source]:
                    if (source,family) in mapping:
                        lookup,other,share=mapping[source,family]
                        indices.append(index)
                        columns.append(lookup.get(value,other))
                        weights.append(weight/record['size'] if share else weight)
        sparse=coo_matrix((weights,(indices,columns)),shape=(len(records),len(labels)),dtype=np.float32).tocsc()
        return pd.concat([frame,pd.DataFrame.sparse.from_spmatrix(sparse,columns=labels)],axis=1)

    @timed
    def live(self,snapshot,candidates):
        if self.model=='row':
            return self.transform(row.live(snapshot,candidates))
        lookup=state.LiveLookup(snapshot)
        context=dict(zip(row.STATE,lookup.numbers+lookup.prices+lookup.institutions+lookup.tariffs+lookup.taxes))
        context.update(zip(state.CATEGORIES,state.categories(lookup)))
        held=hist.live_holdings(snapshot)
        return self.transform([{'state':context,'held':held,'actions':hist.entries(batch,lookup),'size':len(batch)} for batch in candidates])
