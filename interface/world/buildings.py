import collections
import re

from ..common import slot, timed, timed_often
from ..script import blocks, body, scalar
from .source import integer_counts


@timed_often
def levels(record):
    return int(scalar(record,'level') or 0)+sum(map(int,re.findall(r'\blevels\s*=\s*(\d+)',record)))


@timed_often
def expected(records,factor,scales):
    counts=collections.Counter()
    for record in records:
        kind=scalar(record,'building')
        scale=scales.get(kind,factor)
        counts[kind]+=int(scalar(record,'level') or 0)
        for key,ownership in blocks(body(record)):
            if key=='add_ownership':
                counts[kind]+=sum(integer_counts([int(scalar(owner,'levels'))*scale for _,owner in blocks(body(ownership))]))
    return {kind:count for kind,count in counts.items() if count}


@timed_often
def project(records,tag,state,tags,states,owners,factor,scales,companies):
    from .project import commands

    groups=collections.defaultdict(list)
    for record in records:
        groups[scalar(record,'building')].append(record)
    output=[]
    for kind,group in groups.items():
        ownership=collections.Counter()
        scale=scales.get(kind,factor)
        direct=sum(int(scalar(record,'level') or 0) for record in group)
        representative=max(group,key=levels)
        fields=[f'{key} {op} {value}' for key,op,value in commands(body(representative)) if key not in ('add_ownership','level')]
        for record in group:
            for key,value in blocks(body(record)):
                if key!='add_ownership':
                    continue
                entries=list(blocks(body(value)))
                counts=integer_counts([int(scalar(owner,'levels'))*scale for _,owner in entries])
                for (owner_kind,owner),count in zip(entries,counts):
                    if not count:
                        continue
                    source=(scalar(owner,'country') or 'c:'+tag).removeprefix('c:')
                    if owner_kind=='building':
                        origin=scalar(owner,'region')
                        destination=states[origin] if origin in states else state
                        fields_owner=f'type = "{scalar(owner,"type")}" country = "c:{owners[destination]}" region = "{destination}"'
                    elif owner_kind=='company':
                        fields_owner=f'type = {scalar(owner,"type")} country = "c:{companies[scalar(owner,"type")]}"'
                    else:
                        owner_kind='country'
                        target=tag if kind in scales else tags[source] if source in tags else tag
                        fields_owner=f'country = "c:{target}"'
                    ownership[owner_kind,fields_owner]+=count
        if direct:
            fields.append(f'level = {direct}')
        if ownership:
            fields.append('add_ownership = { '+' '.join(f'{owner_kind} = {{ {fields_owner} levels = {count} }}'
                                                      for (owner_kind,fields_owner),count in ownership.items())+' }')
        if direct or ownership:
            output.append('create_building = { '+' '.join(fields)+' }')
    return output


@timed
def compare(manifest,actual):
    wanted={(s['country'],s['key'],kind):count for s in manifest['states'] for kind,count in s['buildings'].items()}
    found=collections.Counter()
    for tag,state,kind,count in actual:
        found[tag,state,kind]+=int(count)
    differences=[{'country':tag,'state':state,'building':kind,'expected':count,'actual':found[tag,state,kind]}
                 for (tag,state,kind),count in wanted.items() if found[tag,state,kind]!=count]
    return {'excluded_levels':sum(v['levels'] for s in manifest['states'] for v in s.get('excluded_buildings',{}).values()),
            'expected_levels':sum(wanted.values()),'actual_levels':sum(found[key] for key in wanted),
            'expected_buildings':len(wanted),'differences':differences}


@timed
def loaded(reader,manifest):
    countries,_=reader.table('country')
    states,_=reader.table('state')
    buildings,_=reader.table('building')
    label=lambda token:reader.names[int(token)-1][1] if token else None
    tags={slot(ident):label(kind) for ident,kind in zip(countries['id'],countries['country_definition'])}
    locations={slot(ident):(tags[slot(country)],label(region)) for ident,country,region in
               zip(states['id'],states['country'],states['state_region'])}
    return compare(manifest,((*locations[slot(state)],label(kind),count) for state,kind,count,dead in
                             zip(buildings['state'],buildings['building'],buildings['levels'],buildings['dead']) if not dead))
