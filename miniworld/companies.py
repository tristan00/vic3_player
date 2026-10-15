from types import SimpleNamespace
import re

from interface.script import blocks, body, clean, read, scalar
from . import GAME, timed, timed_often

FOUNDED='1830.1.1'


@timed
def model():
    found=SimpleNamespace()
    found.kinds={}
    for key,block in read(GAME,'common/company_types'):
        if scalar(block,'flavored_company')!='no': continue
        possible=next(text for name,text in blocks(body(block)) if name=='possible')
        found.kinds[key]=(set(re.findall(r'is_building_type\s*=\s*(\w+)',possible)),int(re.search(r'level\s*>=\s*(\d+)',possible)[1]),
                          set(re.findall(r'\w+',re.search(r'building_types\s*=\s*\{([^}]*)\}',block)[1])))
    recognized={tag for tag,block in read(GAME,'common/country_definitions') if scalar(block,'country_type')=='recognized'}
    owners={tag for _,top in read(GAME,'common/history/states') for tag in re.findall(r'country\s*=\s*c:(\w+)',top)}&recognized
    founding={key[2:] for path in sorted((GAME/'common/history/countries').glob('*.txt')) for _,top in blocks(clean(path))
              for key,inner in blocks(body(top)) if 'add_company' in inner}
    found.share=len(founding&owners)/len(owners)
    return found


@timed_often
def eligible(found,placed):
    return sorted(kind for kind,(needed,level,_) in found.kinds.items() if any(levels.get(b,0)>=level for levels in placed for b in needed))


@timed
def found_companies(rng,found,owned,placed,described,copied):
    out=dict(copied)
    for tag,states in owned.items():
        options=eligible(found,[placed[s] for s in states])
        if not options or rng.random()>=found.share: continue
        kind=str(rng.choice(options))
        home=max(states,key=lambda s:sum(placed[s].get(b,0) for b in found.kinds[kind][2]))
        out[tag]=copied[tag]+(f'\nadd_company = company_type:{kind}\ncompany:{kind} = {{\n\tset_company_establishment_date = {FOUNDED}\n'
                               f'\tset_company_state_region = s:{described[home]["key"]}\n}}')
    return out
