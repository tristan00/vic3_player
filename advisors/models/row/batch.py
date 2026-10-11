from collections import defaultdict
import logging

import numpy as np
import pandas as pd

from interface.common import evidence, timed
from interface.recording.spec import TABLE
from ...catalogue import NAVAL
from ...data.features import PEOPLE, SITE
from .features import ABSENT, CATEGORICAL, ENTITY, MISSING, NUMERIC, PARAMETERS, SITE_ACTIONS, STATE_REPORTS, categorical

LOG=logging.getLogger('tuning')


@timed
def entities(connection,table,requests,fields,presence=True):
    columns=[field.name for field in fields]
    source=table+'_history' if table+'_history' in TABLE else table
    key=TABLE[source].owner
    keys=['run','seq','ident']
    unique=requests[keys].drop_duplicates(ignore_index=True)
    unique['request']=np.arange(len(unique))
    order=requests.merge(unique,on=keys,how='left',sort=False)
    projected=[f'v{i}.name as {field.name}' if field.vocabulary else 'h.'+field.name for i,field in enumerate(fields)]
    joins=[f'left join {field.vocabulary} v{i} on v{i}.{field.vocabulary}=h.{field.name}' for i,field in enumerate(fields) if field.vocabulary]
    query=f'''select q.position,h.present,{','.join(projected)}
from unnest(%s::integer[],%s::integer[],%s::integer[],%s::integer[]) q(position,run_id,seq,ident)
left join lateral (
    select {'present' if presence else 'true as present'},{','.join(columns)} from {source}
    where run_id=q.run_id and {key}=q.ident and seq<=q.seq order by seq desc limit 1
) h on true {' '.join(joins)} order by q.position'''
    arguments=[unique['request'].tolist(),*[unique[name].tolist() for name in keys]]
    rows=connection.execute(query,arguments).fetchall()
    found=pd.DataFrame(rows,columns=['position','present',*columns],dtype=object).set_index('position')
    found.loc[found['present']!=True,columns]=None
    found=found.loc[order['request'],columns]
    found.index=requests['position']
    LOG.info('batch %s columns %d requests %d distinct %d',source,len(columns),len(requests),len(unique))
    return found


@timed
def parameters(connection,actions,selection):
    selected=[name for name in selection.names if name.startswith('parameter.')]
    numeric=set(NUMERIC)
    result={name:np.full(len(actions),np.nan,np.float32) if name in numeric else np.empty(len(actions),object) for name in selected}
    for name in set(selected)-numeric:
        result[name].fill(ABSENT)
    grouped=defaultdict(list)
    for position,(run,seq,hours,name,params) in enumerate(actions):
        expected=PARAMETERS[name]
        if set(params)!={param for param,kind in expected}:
            raise ValueError(evidence(name=name,params=sorted(params),expected=expected))
        for param,kind in expected:
            prefix=f'parameter.{param}.{kind}'
            if selection.parameters.get(prefix) or prefix in result:
                grouped[prefix].append((position,run,seq,hours,params[param]))
    for prefix,rows in grouped.items():
        requests=pd.DataFrame(rows,columns=['position','run','seq','hours','ident'],dtype=object)
        indices=requests['position'].to_numpy(dtype=np.int64)
        kind=prefix.split('.')[2]
        if kind not in ENTITY:
            result[prefix][indices]=requests['ident'].to_numpy(dtype=np.float32) if kind=='int' else requests['ident'].astype(str).to_numpy()
            continue
        specs=selection.parameters[prefix]
        found=entities(connection,ENTITY[kind],requests,[field for field,related in specs])
        hours=requests.set_index('position')['hours']
        for field,related in specs:
            column=found[field.name]
            key=f'{prefix}.{field.name}'
            if field.entity:
                present=column.notna()
                related_requests=requests.set_index('position').loc[present].reset_index()
                related_requests['ident']=column.loc[present].to_numpy()
                if len(related_requests):
                    values=entities(connection,field.entity,related_requests,related)
                for target in related:
                    result[f'{key}.{target.name}'][indices]=MISSING
                    if len(related_requests):
                        result[f'{key}.{target.name}'][values.index.to_numpy(dtype=np.int64)]=values[target.name].where(values[target.name].notna(),MISSING).astype(str).to_numpy()
            elif categorical(field):
                result[key][indices]=column.where(column.notna(),MISSING).astype(str).to_numpy()
            else:
                values=column.to_numpy(dtype=np.float64,na_value=np.nan)
                if field.kind=='game_hours':
                    values=(hours.to_numpy(dtype=np.float64)-values)/24
                result[key][indices]=values
    for name in set(selected)&set(CATEGORICAL):
        result[name]=pd.Categorical(result[name])
    return pd.DataFrame(result,index=range(len(actions)),copy=False)


@timed
def memberships(connection,table,requests,owner,member,selected,vocabulary=False):
    keys=['run','seq','ident']
    unique=requests[keys].drop_duplicates(ignore_index=True)
    unique['request']=np.arange(len(unique))
    order=requests.merge(unique,on=keys,how='left',sort=False)
    joined=f'join {owner} o on o.name=q.ident' if vocabulary else ''
    ident=f'o.{owner}' if vocabulary else 'q.ident'
    query=f'''select q.position,v.name from unnest(%s::integer[],%s::integer[],%s::integer[],%s::{'text' if vocabulary else 'integer'}[]) q(position,run_id,seq,ident)
{joined} join lateral (
    select distinct on ({member}) {member},present from {table}
    where run_id=q.run_id and {owner}={ident} and seq<=q.seq order by {member},seq desc
) h on h.present join {member} v on v.{member}=h.{member} where v.name=any(%s)'''
    arguments=[unique['request'].tolist(),*[unique[name].tolist() for name in keys],selected]
    rows=connection.execute(query,arguments).fetchall()
    found=pd.DataFrame(rows,columns=['request','trait'])
    return order[['position','request']].merge(found,on='request',how='inner')[['position','trait']]


@timed
def characters(connection,actions,selection):
    result={f'target_character.trait.{trait}':np.full(len(actions),np.nan,np.float32) for trait in selection.traits}
    if not result:
        return pd.DataFrame(result,index=range(len(actions)),copy=False)
    rows=[]
    for position,(run,seq,hours,name,params) in enumerate(actions):
        for param,kind in PARAMETERS[name]:
            if kind in ('character','interest_group'):
                rows.append((len(rows),position,run,seq,params[param],kind))
    requests=pd.DataFrame(rows,columns=['position','action','run','seq','ident','kind'],dtype=object)
    grouped=requests['kind']=='interest_group'
    if grouped.any():
        fields=[field for field in TABLE['interest_group_history'].columns if field.name=='leader']
        found=entities(connection,'interest_group',requests.loc[grouped],fields)
        requests.loc[grouped,'ident']=found['leader'].to_numpy()
    requests=requests.loc[requests['ident'].notna()].drop_duplicates('action',keep='last')
    if not requests.empty:
        requests['position']=requests['action']
        indices=requests['position'].to_numpy(dtype=np.int64)
        for values in result.values():
            values[indices]=0
        found=memberships(connection,'character_assigned_trait',requests,'character','character_trait',selection.traits)
        for trait,rows in found.groupby('trait',sort=False):
            result[f'target_character.trait.{trait}'][rows['position'].to_numpy(dtype=np.int64)]=1
    return pd.DataFrame(result,index=range(len(actions)),copy=False)


@timed
def building_levels(connection,requests):
    runs=sorted(set(requests['run']))
    query='select run_id,building,seq,present,state,building_type,levels from building_history where run_id=any(%s) order by run_id,building,seq'
    events=pd.DataFrame(connection.execute(query,(runs,)).fetchall(),columns=['run','building','seq','present','state','kind','levels'])
    result=pd.Series(np.where(requests['kind'].notna(),0.,np.nan),index=requests['position'])
    if events.empty:
        return result
    events.loc[~events['present'],'levels']=0
    keys=['state','kind','levels']
    previous=events[['run','seq',*keys]].copy()
    previous[keys]=events.groupby(['run','building'],sort=False)[keys].shift()
    previous['levels']=-previous['levels']
    changes=pd.concat([events[['run','seq',*keys]],previous],ignore_index=True).dropna(subset=['kind','levels'])
    changes['state']=changes['state'].fillna(np.iinfo(np.int64).min)
    changes=changes.loc[changes['levels']!=0]
    totals=changes.groupby(['run','state','kind','seq'],sort=True)['levels'].sum().reset_index()
    if totals.empty:
        return result
    totals['levels']=totals.groupby(['run','state','kind'],sort=False)['levels'].cumsum()
    kinds=dict(connection.execute('select name,building_type from building_type').fetchall())
    selected=requests[['position','run','seq','ident','kind']].rename(columns={'ident':'state'}).copy()
    selected['kind']=selected['kind'].map(kinds)
    selected=selected.dropna(subset=['kind'])
    selected['state']=selected['state'].fillna(np.iinfo(np.int64).min)
    for frame in (selected,totals):
        for key in ('run','state','kind','seq'):
            frame[key]=frame[key].astype(np.int64)
    found=pd.merge_asof(selected.sort_values('seq'),totals.sort_values('seq'),on='seq',by=['run','state','kind'])
    result.loc[found['position']]=found['levels'].fillna(0).to_numpy()
    return result


@timed
def sites(connection,actions,selection):
    selected=selection.names.intersection(SITE+[f'site.{name}' for names in STATE_REPORTS.values() for name in names])
    result={name:np.full(len(actions),np.nan,np.float32) for name in selected}
    result.update({f'site.trait.{trait}':np.full(len(actions),1,np.int8) for trait in selection.site_traits})
    if not result:
        return pd.DataFrame(result,index=range(len(actions)),copy=False)
    rows=[(position,run,seq,params.get('state'),params.get('building_type',NAVAL.get(name)),params.get('building'))
          for position,(run,seq,hours,name,params) in enumerate(actions) if name in SITE_ACTIONS]
    requests=pd.DataFrame(rows,columns=['position','run','seq','ident','kind','building'],dtype=object)
    if requests.empty:
        return pd.DataFrame({name:pd.Categorical.from_codes(values,[MISSING,ABSENT,'False','True']).remove_unused_categories() if name.startswith('site.trait.') else values for name,values in result.items()},index=range(len(actions)),copy=False)
    placed=requests['building'].notna()
    if placed.any():
        buildings=requests.loc[placed].copy()
        buildings['ident']=buildings['building']
        fields=[field for field in TABLE['building_history'].columns if field.name in ('state','building_type')]
        found=entities(connection,'building',buildings,fields)
        requests.loc[placed,'ident']=found['state'].to_numpy()
        requests.loc[placed,'kind']=found['building_type'].to_numpy()
    indices=requests['position'].to_numpy(dtype=np.int64)
    if selected.intersection(('site.unemployed','site.peasants','site.population')):
        fields=[field for field in TABLE['state_population'].columns if field.name in PEOPLE]
        found=entities(connection,'state_population',requests,fields,presence=False)
        if 'site.unemployed' in selected:
            result['site.unemployed'][indices]=found['unemployed_workforce'].to_numpy(dtype=np.float64,na_value=np.nan)
        if 'site.peasants' in selected:
            result['site.peasants'][indices]=found['subsisting_workforce'].to_numpy(dtype=np.float64,na_value=np.nan)
        if 'site.population' in selected:
            result['site.population'][indices]=found[['lower_strata','middle_strata','upper_strata']].to_numpy(dtype=np.float64,na_value=np.nan).sum(axis=1)
    reports=[('state_standard_of_living_report','average_standard_of_living_all','site.standard_of_living'),
             ('state_population_report','literacy','site.literacy'),('state_economy_report','gdp_contribution_percentage','site.gdp_share'),
             *[(table,name,f'site.{name}') for table,names in STATE_REPORTS.items() for name in names]]
    for table,column,name in reports:
        if name in selected:
            fields=[field for field in TABLE[table].columns if field.name==column]
            found=entities(connection,table,requests,fields)
            result[name][indices]=found[column].to_numpy(dtype=np.float64,na_value=np.nan)
    if 'site.buildings_of_type' in selected:
        result['site.buildings_of_type'][indices]=building_levels(connection,requests).to_numpy()
    if selection.site_traits:
        fields=[field for field in TABLE['state_history'].columns if field.name=='state_region']
        regions=entities(connection,'state',requests,fields)
        requests['ident']=regions['state_region'].to_numpy()
        present=requests['ident'].notna()
        located=requests.loc[present]
        resolved=located['position'].to_numpy(dtype=np.int64)
        for trait in selection.site_traits:
            values=result[f'site.trait.{trait}']
            values[indices]=0
            values[resolved]=2
        if not located.empty:
            found=memberships(connection,'state_region_trait',located,'state_region','state_trait',selection.site_traits,True)
            for trait,rows in found.groupby('trait',sort=False):
                result[f'site.trait.{trait}'][rows['position'].to_numpy(dtype=np.int64)]=3
        for trait in selection.site_traits:
            name=f'site.trait.{trait}'
            result[name]=pd.Categorical.from_codes(result[name],[MISSING,ABSENT,'False','True']).remove_unused_categories()
    return pd.DataFrame(result,index=range(len(actions)),copy=False)
