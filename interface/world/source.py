import collections
import re

from ..common import timed, timed_often
from ..script import blocks, body, fields, read, scalar


@timed
def reference(game,templates,rules):
    history={}
    roots={}
    for folder in sorted((game/'common/history').iterdir()):
        if not folder.is_dir():
            continue
        records=collections.defaultdict(list)
        for root,text in read(game,'common/history/'+folder.name):
            roots[folder.name]=root
            for key,value in blocks(body(text)):
                records[key].append(body(value))
        history[folder.name]=dict(records)
    definitions=dict(read(game,'common/country_definitions'))
    religions={key:scalar(value,'religion') for key,value in read(game,'common/cultures')}
    tech_eras={key:scalar(value,'era') for key,value in read(game,'common/technology/technologies')}
    countries={}
    for key,records in history['countries'].items():
        if not key.startswith('c:'):
            continue
        tag=key[2:]
        text=' '.join(records)
        tiers=re.findall(r'effect_starting_technology_tier_(\d+)_tech\s*=',text)
        techs=set().union(*(rules['tier_techs'][int(t)] for t in tiers))
        techs.update(re.findall(r'add_technology_researched\s*=\s*(\w+)',text))
        eras=set(re.findall(r'add_era_researched\s*=\s*(\w+)',text))
        techs.update(k for k,v in tech_eras.items() if v in eras)
        cultures=dict(fields(body(definitions[tag]))).get('cultures',[])
        for record in records:
            for kind,value in fields(record):
                if kind=='add_primary_culture' and value[0] not in cultures:
                    cultures.append(value[0].removeprefix('cu:'))
                elif kind=='remove_primary_culture':
                    cultures=[culture for culture in cultures if culture!=value[0].removeprefix('cu:')]
        countries[tag]={'definition':definitions[tag],'techs':techs,
                        'type':scalar(definitions[tag],'country_type'),
                        'cultures':cultures}
    from .military import units

    unit_profiles=units({'history':history})
    state_definitions=dict(read(game,'map_data/state_regions'))
    for state in templates:
        key='s:'+state['key']
        pops=[]
        owners=collections.Counter()
        for text in history['pops'].get(key,[]):
            for owner,record in blocks(text):
                for kind,pop in blocks(body(record)):
                    if kind=='create_pop':
                        if scalar(pop,'religion') is None:
                            pop=pop[:pop.rfind('}')]+f' religion = {religions[scalar(pop,"culture")]} }}'
                        owners[owner.split(':')[-1]]+=int(scalar(pop,'size'))
                        pops.append(pop)
        buildings=[record for text in history['buildings'].get(key,[]) for _,owned in blocks(text)
                   for kind,record in blocks(body(owned)) if kind=='create_building']
        implicit=sum(unit_profiles[state['key']].values())
        if implicit:
            buildings.append(f'create_building = {{ building = building_barrack add_ownership = {{ country = {{ country = c:{owners.most_common(1)[0][0]} levels = {implicit} }} }} }}')
        state.update(pop_records=pops,building_records=buildings,owner=owners.most_common(1)[0][0],
                     state_history=' '.join(history['states'].get(key,[])),
                     trade_history=' '.join(body(v) for text in history['trade'].get(key,[]) for _,v in blocks(text)),
                     coastal='port' in dict(fields(body(state_definitions[state['key']]))))
    population=collections.Counter()
    for state in templates:
        for record in state['pop_records']:
            population[scalar(record,'culture')]+=int(scalar(record,'size'))
    return {'history':history,'history_roots':roots,'source_countries':countries,'culture_population':dict(population)}


@timed_often
def select_groups(rng,data,count,pool):
    available=collections.defaultdict(list)
    for state in data['templates']:
        available[data['source_group_by_state'][state['key']]].append(state)
    if pool is not None:
        if len(set(pool))!=len(pool) or set(pool)-available.keys():
            raise ValueError('Source group pool must contain distinct populated vanilla source groups')
        available={key:available[key] for key in pool}
    return {key:available[key] for key in rng.sample(sorted(available),count)}


@timed_often
def select_countries(data,pool):
    available=sorted(tag for tag,source in data['source_countries'].items() if source['type']!='decentralized')
    if pool is None:
        return available
    if not pool or len(set(pool))!=len(pool) or set(pool)-set(available):
        raise ValueError('Country pool must contain distinct centralized vanilla country tags')
    return sorted(pool)


@timed_often
def integer_counts(values):
    counts=[int(v) for v in values]
    for index in sorted(range(len(values)),key=lambda i:values[i]-counts[i],reverse=True)[:round(sum(values))-sum(counts)]:
        counts[index]+=1
    return counts


@timed_often
def assignments(rng,groups,sources):
    keys=list(sources)
    destinations={key:[] for key in keys}
    centers=[r['states'][0]['center'] for r in groups]
    for group in groups:
        for state in group['states']:
            distances=[float(sum((state['center']-center)**2))**.5 for center in centers]
            scale=max(1,sum(distances)/len(distances))
            weights=[(4 if key==group['source_group'] else 1)/(1+d/scale)**2 for key,d in zip(keys,distances)]
            eligible=[key for key in keys if state['coastal'] or any(not s['coastal'] for s in sources[key])]
            if not eligible:
                raise ValueError('These source groups have no inland state templates for this map')
            origin=group['source_group'] if state is group['states'][0] and group['source_group'] in eligible else rng.choices(eligible,[weights[keys.index(k)] for k in eligible])[0]
            destinations[origin].append(state)
    for origin,states in destinations.items():
        capacity=sum(s['coastal'] for s in states)
        remaining=[]
        chosen=[]
        for _ in states:
            available=[s for s in remaining if capacity or not s['coastal']]
            if not available:
                remaining=list(sources[origin])
                available=[s for s in remaining if capacity or not s['coastal']]
            source=rng.choice(available)
            remaining.remove(source)
            chosen.append(source)
            capacity-=source['coastal']
        rng.shuffle(states)
        states.sort(key=lambda s:s['coastal'],reverse=True)
        chosen.sort(key=lambda s:s['coastal'],reverse=True)
        for state,source in zip(states,chosen):
            state['source']=source
            state['source_group']=origin
