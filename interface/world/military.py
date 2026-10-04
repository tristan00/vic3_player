import collections
import re

from ..common import timed, timed_often
from ..script import blocks, body, scalar


@timed
def units(data):
    profiles=collections.defaultdict(collections.Counter)
    for records in data['history']['military_formations'].values():
        for text in records:
            for key,formation in blocks(text):
                if key!='create_military_formation':
                    continue
                for kind,unit in blocks(body(formation)):
                    if kind=='combat_unit' and scalar(unit,'service_type')!='conscript':
                        state=scalar(unit,'state_region').removeprefix('s:')
                        profiles[state][scalar(unit,'type')]+=int(scalar(unit,'count') or 1)
    return profiles


@timed_often
def military(data,donor,tag,states,regions):
    from .project import commands

    output=[]
    coast=[s for s in states if s.get('coastal',s['source']['coastal'])]
    text=' '.join(data['history']['military_formations'].get('c:'+donor,[]))
    removed=set()
    extra=[]
    for key,op,value in commands(text):
        if key!='create_military_formation':
            extra.append((key,op,value))
            continue
        scope=scalar(value,'save_scope_as')
        if scalar(value,'type')=='army':
            if scope:
                removed.add(scope)
        elif coast:
            value=re.sub(r'\bhq_region\s*=\s*sr:\w+',f'hq_region = sr:{regions[coast[0]["id"]]}',value)
            value=re.sub(r'\bSTATE_\w+',coast[0]['key'],value)
            output.append(f'{key} {op} {value}')
        elif scope:
            removed.add(scope)
    for key,op,value in extra:
        if set(re.findall(r'\bscope:(\w+)',key+' '+value)) & removed:
            continue
        if key=='activate_production_method':
            continue
        command=f'{key} {op} {value}'
        if re.search(r'\b(?:STATE_\w+|sr:\w+|p:x[0-9A-Fa-f]+|c:[A-Z0-9]{3})',command):
            continue
        output.append(command)
    return '\n'.join(output)
