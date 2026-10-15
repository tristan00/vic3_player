import re
from collections import Counter, defaultdict
from types import SimpleNamespace

import numpy as np

from interface.script import blocks, body, read, scalar
from . import GAME, countries, timed, timed_often

ADMIN='building_government_administration'
TRADE='building_trade_center'
NEAREST=25
COASTAL={'building_fishing_wharf','building_whaling_station','building_port','building_naval_base','building_shipyards','building_military_shipyards'}


@timed
def templates(people):
    types={tag:scalar(block,'country_type') for tag,block in read(GAME,'common/country_definitions')}
    held=defaultdict(set)
    for _,top in read(GAME,'common/history/states'):
        for state,inner in blocks(body(top)):
            held[state[2:]]|={types.get(tag) for tag in re.findall(r'country\s*=\s*c:(\w+)',inner)}
    definitions=dict(read(GAME,'common/buildings'))
    excluded={key for key,block in definitions.items() if scalar(block,'unique')=='yes' or 'monuments' in (scalar(block,'building_group') or '')}|{ADMIN}
    found=SimpleNamespace()
    found.needs={key:set(re.findall(r'\w+',m[1])) if (m:=re.search(r'unlocking_technologies\s*=\s*\{([^}]*)\}',block)) else set() for key,block in definitions.items()}
    pops=Counter()
    for (state,_),n in people.items(): pops[state]+=n
    owned=countries.held(people)
    found.floor=min(owned[tag] for tag,kind in types.items() if kind=='recognized' and owned[tag])
    levels=defaultdict(Counter)
    methods=defaultdict(lambda:defaultdict(Counter))
    traders=Counter()
    found.owners=defaultdict(Counter)
    for _,top in read(GAME,'common/history/buildings'):
        for state,inner in blocks(body(top)):
            for region,group in blocks(body(inner)):
                if not region.startswith('region_state:'): continue
                for key,made in blocks(body(group)):
                    if key!='create_building': continue
                    building=scalar(made,'building')
                    active=re.search(r'activate_production_methods\s*=\s*\{([^}]*)\}',made)
                    chosen=tuple(re.findall(r'\w+',active[1])) if active else ()
                    for part,owned in blocks(body(made)):
                        if part!='add_ownership': continue
                        for kind,share in blocks(body(owned)):
                            n=int(scalar(share,'levels'))
                            if building not in excluded: levels[state[2:]][building]+=n
                            methods[state[2:]][building][chosen]+=n
                            if building==TRADE: traders[region[13:]]+=n
                            name=kind if kind!='building' else scalar(share,'type')
                            found.owners[building]['country' if name=='company' else 'self' if name==building else name]+=n
    populations=countries.held(people)
    recognized=[tag for tag,kind in types.items() if kind=='recognized' and populations[tag]]
    found.trade_floor=max(populations[tag] for tag in recognized if not traders[tag])
    found.trade_templates=np.array([(np.log(populations[tag]),traders[tag]/populations[tag]) for tag in recognized if traders[tag]])
    terrain={c.upper():k for c,k in re.findall(r'(x[0-9A-Fa-f]{6})\s*=\s*"(\w+)"',(GAME/'map_data/province_terrains.txt').read_text(encoding='utf-8-sig'))}
    found.templates=defaultdict(list)
    for key,block in read(GAME,'map_data/state_regions'):
        if int(scalar(block,'id'))>=3000 or not pops[key] or not held[key]-{'decentralized',None}: continue
        provinces=re.findall(r'x[0-9A-Fa-f]{6}',re.search(r'provinces\s*=\s*\{([^}]*)\}',block)[1])
        arable=re.search(r'arable_resources\s*=\s*\{([^}]*)\}',block)
        capped=re.search(r'capped_resources\s*=\s*\{([^}]*)\}',block)
        made=SimpleNamespace(key=key,recognized=held[key]=={'recognized'},provinces=len(provinces),coastal=scalar(block,'port') is not None,population=pops[key],
                             arable_land=int(scalar(block,'arable_land') or 0),subsistence=scalar(block,'subsistence_building'),
                             arable_resources=re.findall(r'building_\w+',arable[1]) if arable else [],
                             capped={b:int(n) for b,n in re.findall(r'(building_\w+)\s*=\s*(\d+)',capped[1])} if capped else {},
                             resources=[(scalar(inner,'type'),scalar(inner,'depleted_type'),int(scalar(inner,'undiscovered_amount') or 0)+int(scalar(inner,'discovered_amount') or 0))
                                        for name,inner in blocks(body(block)) if name=='resource'],
                             buildings=dict(levels[key]),methods={b:counts.most_common(1)[0][0] for b,counts in methods[key].items()},
                             traits=re.findall(r'state_trait_\w+',traits[1]) if (traits:=re.search(r'traits\s*=\s*\{([^}]*)\}',block)) else [])
        made.density=made.population/made.provinces
        found.templates[Counter(terrain[p.upper()] for p in provinces).most_common(1)[0][0]].append(made)
    return found


@timed_often
def pick(rng,found,state,density,alone):
    options=found.templates[state['terrain']]
    options=[t for t in options if t.population>=found.floor] if alone else options
    coastal='port' in state['hubs']
    options=sorted(options,key=lambda t:(not t.recognized,t.coastal!=coastal,abs(np.log(t.provinces/len(state['provinces'])))))[:NEAREST]
    options=sorted(options,key=lambda t:t.density)
    return options[int(rng.random()**(1/density)*len(options))]


@timed_often
def apply(state,made,needs,techs):
    coastal='port' in state['hubs']
    state.update(template=made.key,arable_land=made.arable_land,subsistence=made.subsistence,arable_resources=list(made.arable_resources),
                 capped=dict(made.capped),resources=list(made.resources),traits=list(made.traits),methods=dict(made.methods))
    return float(made.population),{b:n for b,n in made.buildings.items() if needs[b]<=techs and (coastal or b not in COASTAL)}


@timed
def harbours(found,placed,described,owned,capitals,component,totals,laws):
    for tag,states in owned.items():
        population=sum(totals[s] for s in states)
        if len(owned)>1 and population>found.trade_floor and any('port' in described[s]['hubs'] for s in states) \
                and not any(placed[s].get(TRADE,0) for s in states) and not laws[tag]&{'law_isolationism','law_canton_system','law_sakoku'}:
            nearest=np.argsort(np.abs(found.trade_templates[:,0]-np.log(population)))[:countries.NEAREST]
            placed[capitals[tag]][TRADE]=max(1,int(round(population*np.median(found.trade_templates[nearest,1]))))
        parts={component[s] for s in states}
        if len(parts)==1 and not any(placed[s].get(TRADE,0) for s in states): continue
        for part in parts:
            coastal=[s for s in states if component[s]==part and 'port' in described[s]['hubs']]
            if not coastal: continue
            if not any('building_port' in placed[s] for s in coastal):
                placed[capitals[tag] if capitals[tag] in coastal else max(coastal,key=lambda s:totals[s])]['building_port']=1


@timed
def furnish(rng,found,described,owner,techs,density):
    sizes=[]
    placed=[]
    counts=Counter(owner[s] for s in range(len(described)))
    for s,state in enumerate(described):
        size,built=apply(state,pick(rng,found,state,density,counts[owner[s]]==1),found.needs,techs[owner[s]])
        sizes.append(size)
        placed.append(built)
    return sizes,placed
