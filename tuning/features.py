from collections import Counter

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix

from advisors.catalogue import RECORDED_PARAMS
from advisors.data import features as state
from advisors.data import histograms as hist
from advisors.models.row import features as row
from interface.common import evidence, timed, timed_often


FINANCE=['treasury','debt','interest','balance','balance_gdp','government_spending','government_spending_gdp']
SOCIETY=['population','standard_of_living','radicals_percent']
STANDING=['bureaucracy_available','infamy','government_legitimacy']
GOODS=len(state.GOODS)
BINS={hist.BUILDINGS:[4,8,16,32,0],hist.METHODS:[8,16,32,64,0],hist.ROLES:[2,4,0],hist.IDEOLOGIES:[4,8,16,0],hist.PEOPLE:[]}


@timed_often
def share(part,whole):
    return np.divide(part,whole,out=np.full(np.shape(part),np.nan),where=whole>0)


@timed_often
def politics(block):
    clout,approval,ruling=block[:,0::3],block[:,1::3],block[:,2::3]
    held=clout*ruling
    return [np.nansum(held,1),share(np.nansum(clout*approval,1),np.nansum(clout,1)),share(np.nansum(held*approval,1),np.nansum(held,1)),np.nansum(ruling,1)]


@timed_often
def premiums(block):
    level,above=block[:,:GOODS],block[:,GOODS:]
    premium=share(above,level-above)
    return [share(np.nansum(premium,1),(~np.isnan(premium)).sum(1)),(above>0).sum(1),(~np.isnan(above)).sum(1)]


@timed_often
def invested(block):
    return [block.sum(1),(block>0).sum(1)]


@timed_often
def duties(block):
    return [block.mean(1),(block>state.NO_DUTY).sum(1),(block<state.NO_DUTY).sum(1)]


@timed_often
def taxed(block):
    return [block.sum(1)]


@timed_often
def ratios(block):
    used,capacity,government,private,treasury,debt,population=block.T
    return [share(used,capacity),share(government,capacity),share(private,capacity),share(treasury,population),share(debt,population)]


DERIVED={'summary.interest_groups':(state.GROUP_FEATURES,['government_clout','approval','government_approval','in_government'],politics),
         'summary.prices':(state.PRICES,['premium','above_world','traded'],premiums),
         'summary.institutions':(state.INSTITUTIONS,['total','present'],invested),
         'summary.tariffs.import':(state.TARIFFS[:GOODS],['mean','tariffed','subsidised'],duties),
         'summary.tariffs.export':(state.TARIFFS[GOODS:],['mean','tariffed','subsidised'],duties),
         'summary.consumption_taxes':(state.TAXES,['taxed'],taxed),
         'context.ratios':(['construction_used','construction_capacity','government_queue_left','private_queue_left','treasury','debt','population'],
                           ['construction_used','government_queue','private_queue','treasury_per_capita','debt_per_capita'],ratios)}


@timed_often
def context_groups():
    groups={'context.finance':FINANCE,'context.society':SOCIETY,'context.standing':STANDING,'context.construction':state.CONSTRUCTION,'context.military':state.MILITARY,
            **{'context.interest_groups.'+metric:[column for column in state.GROUP_FEATURES if column.endswith('.'+metric)] for metric in state.GROUP_METRICS},
            'context.policy':state.POLICY,'context.law_enactment':state.ENACTMENT,'context.war':state.WAR,'context.world':state.WORLD,
            'context.prices.level':state.PRICES[:GOODS],'context.prices.above_world':state.PRICES[GOODS:],'context.institutions':state.INSTITUTIONS,
            'context.tariffs.import':state.TARIFFS[:GOODS],'context.tariffs.export':state.TARIFFS[GOODS:],
            'context.consumption_taxes':state.TAXES,'context.laws':state.LAWS,'context.rank':['player.country_rank']}
    found=[column for columns in groups.values() for column in columns]
    if sorted(found)!=sorted(row.STATE+state.CATEGORIES):
        raise ValueError(evidence(found=len(found),differing=set(found)^set(row.STATE+state.CATEGORIES)))
    return {name:list(columns) for name,columns in groups.items()}


@timed
def taxonomy(model):
    groups={name:{'kind':'columns','role':'context','columns':columns} for name,columns in context_groups().items()}
    groups.update({name:{'kind':'columns','role':'context','columns':[f'{name}.{output}' for output in outputs],'sources':list(sources)}
                   for name,(sources,outputs,_) in DERIVED.items()})
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
        found=[column for group in groups.values() if 'sources' not in group for column in group['columns']]
        if len(found)!=len(set(found)) or set(found)!=set(row.NUMERIC+row.CATEGORICAL):
            raise ValueError(evidence(found=len(found),distinct=len(set(found)),differing=set(found)^set(row.NUMERIC+row.CATEGORICAL)))
    elif model in ('histogram','size'):
        groups['option.batch_size']={'kind':'columns','role':'option','columns':['batch_size']}
        actions=set()
        if model=='histogram':
            actions={hist.ACTION,*hist.ANSWER,*hist.QUEUE,*hist.PLAY,*hist.PLAY_CONTEXT,*hist.PLAY_PACTS,*hist.LEADERS,*state.SITE}
            actions.update(f'{action}.{param}' for action,params in RECORDED_PARAMS.items() for param,_ in params)
        for name in sorted(actions):
            groups['option.'+name]={'kind':'histogram','role':'option','source':'actions','family':name,'forms':['count','share'],'bins':[8,32,128,0]}
        for name,bins in BINS.items():
            groups['holdings.'+name]={'kind':'histogram','role':'context','source':'held','family':name,'forms':['count','share'] if bins else ['count'],'bins':bins}
    else:
        raise ValueError(evidence(model=model))
    return groups


@timed_often
def selected_columns(groups,config):
    return [column for name,group in groups.items() if config['feature.'+name]!='off' and group['kind']=='columns' for column in group['columns']]


@timed_often
def loaded_columns(groups,config):
    chosen=[group for name,group in groups.items() if config['feature.'+name]!='off' and group['kind']=='columns']
    return list(dict.fromkeys(column for group in chosen for column in (group['sources'] if 'sources' in group else group['columns'])))


@timed_often
def selected_families(groups,config):
    return {source:{group['family'] for name,group in groups.items() if group['kind']=='histogram' and group['source']==source and config['feature.'+name]!='off'}
            for source in ('actions','held')}


class Encoder:
    @timed
    def __init__(self,model,config,groups):
        self.model,self.config,self.groups=model,config,groups
        self.columns=selected_columns(groups,config)
        self.derived=[name for name in DERIVED if config['feature.'+name]!='off']
        self.vocabulary={}

    @timed
    def fit(self,records):
        if self.model!='row':
            frequencies={}
            for record in records:
                for source in ('actions','held'):
                    for family,value in {(family,value) for family,value,_ in record[source]}:
                        frequencies.setdefault((source,family),Counter())[value]+=1
            for name,group in self.groups.items():
                if group['kind']!='histogram' or self.config['feature.'+name]=='off':
                    continue
                counts=frequencies.get((group['source'],group['family']),{})
                limit=self.config['bins.'+name] if group['bins'] else 0
                values=sorted(counts,key=lambda value:(-counts[value],value))
                self.vocabulary[name]=values if limit==0 else values[:limit]
        return self

    @timed_often
    def summaries(self,read):
        found={}
        for name in self.derived:
            sources,outputs,compute=DERIVED[name]
            found.update((f'{name}.{output}',values.astype(np.float32)) for output,values in zip(outputs,compute(read(sources))))
        return found

    @timed
    def transform(self,records,columns=None):
        if self.model=='row':
            return records.assign(**self.summaries(lambda sources:records.loc[:,sources].to_numpy(float))).loc[:,self.columns if columns is None else columns]
        contexts,holdings={},{}
        for index,record in enumerate(records):
            contexts.setdefault(id(record['state']),(record['state'],[]))[1].append(index)
            holdings.setdefault(id(record['held']),(record['held'],[]))[1].append(index)
        states=[found for found,_ in contexts.values()]
        derived=self.summaries(lambda sources:np.array([[found[column] for column in sources] for found in states],float).reshape(len(states),len(sources)))
        named=[column for column in self.columns if column!='batch_size' and column not in derived]
        distinct=pd.DataFrame([{column:found[column] for column in named} for found in states],index=range(len(states))).assign(**derived)
        for column in set(state.CATEGORIES)&set(named):
            distinct[column]=distinct[column].astype('category')
        for column in set(named)-set(state.CATEGORIES):
            distinct[column]=distinct[column].astype(np.float32)
        places=np.empty(len(records),np.intp)
        for position,(_,members) in enumerate(contexts.values()):
            places[members]=position
        sizes=np.asarray([record['size'] for record in records],float)
        frame=pd.concat([distinct.iloc[places].reset_index(drop=True),pd.DataFrame({'batch_size':sizes.astype(np.float32)})],axis=1).loc[:,self.columns]
        mapping={}
        labels=[]
        for name,values in self.vocabulary.items():
            group=self.groups[name]
            mapping[group['source'],group['family']]=({value:len(labels)+i for i,value in enumerate(values)},len(labels)+len(values),self.config['feature.'+name]=='share')
            labels.extend(f'{name}.{position}={value}' for position,value in enumerate([*values,'<other>']))
            if group['source']=='held' and self.config['feature.'+name]=='share':
                labels.append(name+'.total')
        indices,columns,weights=[],[],[]
        for index,record in enumerate(records):
            for family,value,weight in record['actions']:
                found=mapping.get(('actions',family))
                if found is not None:
                    indices.append(index)
                    columns.append(found[0].get(value,found[1]))
                    weights.append(weight/record['size'] if found[2] else weight)
        parts=[(np.asarray(indices,np.intp),np.asarray(columns,np.intp),np.asarray(weights,float))]
        for held,members in holdings.values():
            totals=Counter()
            for family,_,weight in held:
                totals[family]+=weight
            found=[(lookup.get(value,other),weight/totals[family] if share else weight) for family,value,weight in held if ('held',family) in mapping
                   for lookup,other,share in [mapping['held',family]]]
            found+=[(mapping['held',family][1]+1,total) for family,total in totals.items() if ('held',family) in mapping and mapping['held',family][2]]
            if found:
                column,weight=(np.asarray(values) for values in zip(*found))
                parts.append((np.repeat(members,len(found)),np.tile(column,len(members)),np.tile(weight.astype(float),len(members))))
        sparse=coo_matrix((np.concatenate([part[2] for part in parts]),(np.concatenate([part[0] for part in parts]),np.concatenate([part[1] for part in parts]))),
                          shape=(len(records),len(labels)),dtype=np.float32).tocsc()
        return pd.concat([frame,pd.DataFrame.sparse.from_spmatrix(sparse,columns=labels)],axis=1)

    @timed
    def live(self,snapshot,candidates):
        if self.model=='row':
            return self.transform(row.live(snapshot,candidates))
        lookup=state.LiveLookup(snapshot)
        context=dict(zip(row.STATE,lookup.numbers+lookup.prices+lookup.institutions+lookup.tariffs+lookup.taxes))
        context.update(zip(state.CATEGORIES,state.categories(lookup)))
        held=hist.live_holdings(snapshot)
        if self.model=='size':
            return self.transform([{'state':context,'held':held,'actions':[],'size':length} for length in candidates])
        return self.transform([{'state':context,'held':held,'actions':hist.entries(batch,lookup),'size':len(batch)} for batch in candidates])
