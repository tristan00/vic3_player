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
        countries[tag]={'tag':tag,'definition':definitions[tag],'techs':techs,
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
def select_regions(rng,data,count,requested=None):
    available=collections.defaultdict(list)
    for state in data['templates']:
        available[data['regions'][state['key']]].append(state)
    selected=list(requested) if requested is not None else rng.sample(sorted(available),count)
    if len(selected)!=count or len(set(selected))!=count or set(selected)-available.keys():
        raise ValueError('Source regions must be distinct populated vanilla strategic regions')
    return {key:available[key] for key in selected}


@timed_often
def moments(values):
    mean=sum(values)/len(values)
    return mean,(sum((v-mean)**2 for v in values)/len(values))**.5


@timed_often
def spread(values,amount,center=None,lower=0,upper=None):
    mean,_=moments(values)
    center=mean if center is None else center
    shifted=[center+amount*(value-mean) for value in values]
    negative=min(shifted)
    positive=max(shifted)
    scale=1.0
    if negative<lower:
        scale=min(scale,(center-lower)/(center-negative))
    if upper is not None and positive>upper:
        scale=min(scale,(upper-center)/(positive-center))
    result=[max(lower,center+(value-center)*scale) for value in shifted]
    return result if upper is None else [min(upper,value) for value in result]


@timed_often
def integer_counts(values):
    counts=[int(v) for v in values]
    for index in sorted(range(len(values)),key=lambda i:values[i]-counts[i],reverse=True)[:round(sum(values))-sum(counts)]:
        counts[index]+=1
    return counts


@timed_often
def assignments(rng,regions,sources):
    keys=list(sources)
    destinations={key:[] for key in keys}
    centers=[r['states'][0]['center'] for r in regions]
    for region in regions:
        for state in region['states']:
            distances=[float(sum((state['center']-center)**2))**.5 for center in centers]
            scale=max(1,sum(distances)/len(distances))
            weights=[(4 if key==region['source_region'] else 1)/(1+d/scale)**2 for key,d in zip(keys,distances)]
            eligible=[key for key in keys if state.get('coastal',True) or any(not s['coastal'] for s in sources[key])]
            if not eligible:
                raise ValueError('These source regions have no inland state templates for this map')
            origin=region['source_region'] if state is region['states'][0] and region['source_region'] in eligible else rng.choices(eligible,[weights[keys.index(k)] for k in eligible])[0]
            destinations[origin].append(state)
    for origin,states in destinations.items():
        capacity=sum(s.get('coastal',True) for s in states)
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
        states.sort(key=lambda s:s.get('coastal',True),reverse=True)
        chosen.sort(key=lambda s:s['coastal'],reverse=True)
        for state,source in zip(states,chosen):
            state['source']=source
            state['source_region']=origin


@timed
def development(rng,states,groups,country_economy,local_economy):
    by_id={s['id']:s for s in states}
    drawn=lambda value:rng.uniform(*value) if isinstance(value,(tuple,list)) else value
    countries=[]
    for group in groups:
        countries.append(drawn(country_economy))
        for index in group:
            state=by_id[index]
            source=state['source']
            limits=[cap/source['buildings'][kind] for kind,cap in source['capped'].items() if source['buildings'].get(kind)]
            farms=sum(source['buildings'].get(kind,0) for kind in source['arable_resources'])
            if farms:
                limits.append(source['arable_land']/farms)
            state['local_economy']=drawn(local_economy)
            state['economic_scale']=min([countries[-1]*state['local_economy'],*limits])
    return countries
