from types import SimpleNamespace
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

from interface.script import blocks, body, building_methods, production_methods, read, scalar
from . import GAME, countries, timed, timed_often

CALIBRATION=Path(__file__).with_name('calibration.json')
SMOOTHING=.01
NEIGHBOURS=15
ADMIN='building_government_administration'
LEVEL=re.compile(r'set_institution_investment_level\s*=\s*\{[^}]*institution\s*=\s*(\w+)[^}]*level\s*=\s*(\d+)')
COMMANDER=re.compile(r'\bis_general\s*=\s*yes|\bis_admiral\s*=\s*yes|\bhq\s*=')
EXOTIC={'unlocking_production_methods','unlocking_principles','unlocking_identity','unlocking_company_categories','unlocking_geographic_regions',
        'unlocking_religions','disallowing_religions','unlocking_global_technologies','required_input_goods'}


@timed
def methods(techs,laws):
    groups=defaultdict(dict)
    for building,group,method in building_methods(GAME):
        groups[building].setdefault(group,[]).append(method)
    gates={name:entry for name,entry in production_methods(GAME)}
    usage=defaultdict(Counter)
    situations=defaultdict(Counter)
    for _,top in read(GAME,'common/history/buildings'):
        for _,inner in blocks(body(top)):
            for region,group in blocks(body(inner)):
                tag=region[13:] if region.startswith('region_state:') else None
                for _,made in blocks(body(group)):
                    active=re.search(r'activate_production_methods\s*=\s*\{([^}]*)\}',made)
                    chosen=set(re.findall(r'\w+',active[1])) if active else set()
                    building=scalar(made,'building')
                    for method in chosen: usage[building][method]+=1
                    if tag not in techs: continue
                    for options in groups[building].values():
                        open_=tuple(m for m in options if allowed(gates[m],techs[tag],laws[tag]))
                        for method in chosen&set(options): situations[building,open_][method]+=1
    return groups,gates,usage,situations


@timed_often
def allowed(entry,techs,laws):
    if set(entry)&EXOTIC: return False
    if not set(entry.get('unlocking_technologies',[]))<=techs: return False
    if entry.get('unlocking_laws') and not set(entry['unlocking_laws'])&laws: return False
    return not set(entry.get('disallowing_laws',[]))&laws


@timed_often
def choose(rng,known,building,techs,laws,preferred=()):
    groups,gates,usage,situations=known
    out=[]
    for options in groups[building].values():
        open_=tuple(m for m in options if allowed(gates[m],techs,laws))
        matched=[m for m in open_ if m in preferred]
        if matched:
            out.append(matched[0])
            continue
        weighted=[(m,situations[building,open_][m]+SMOOTHING*usage[building][m]) for m in open_ if usage[building][m]]
        if weighted:
            names=[m for m,_ in weighted]
            weights=np.array([w for _,w in weighted],float)
            out.append(str(rng.choice(names,p=weights/weights.sum())))
    return out


@timed
def administration(people):
    calibration=json.loads(CALIBRATION.read_text(encoding='utf-8'))
    recognized={tag for tag,block in read(GAME,'common/country_definitions') if scalar(block,'country_type')=='recognized'}
    defines=(GAME/'common/defines/00_defines.txt').read_text(encoding='utf-8-sig')
    constant=lambda name:float(re.search(name+r'\s*=\s*([\d.]+)',defines)[1])
    found=SimpleNamespace()
    found.state_cost=constant('STATE_BUREAUCRACY_BASE_COST')
    found.pop_cost=constant('STATE_BUREAUCRACY_POP_BASE_COST')/constant('STATE_BUREAUCRACY_POP_MULTIPLE')
    found.outputs={name:float(m[1]) for name,text in read(GAME,'common/production_methods') if (m:=re.search(r'country_bureaucracy_add\s*=\s*(-?[\d.]+)',text))}
    found.needs=set(re.findall(r'\w+',re.search(r'unlocking_technologies\s*=\s*\{([^}]*)\}',dict(read(GAME,'common/buildings'))[ADMIN])[1]))
    outside=Counter(tag for tag,made in countries.incorporation().items() for _,unincorporated in made if unincorporated)
    pops=defaultdict(list)
    for (_,tag),n in sorted(people.items()): pops[tag].append(n)
    found.creates={key:scalar(block,'institution') for key,block in read(GAME,'common/laws') if scalar(block,'institution')}
    found.floor,found.ceiling=constant('MIN_INSTITUTION_INVESTMENT'),constant('MAX_INSTITUTION_INVESTMENT')
    ranks={key:(scalar(block,'rank_value'),-float(m[1])) for key,block in read(GAME,'common/commander_ranks') if (m:=re.search(r'country_bureaucracy_add\s*=\s*(-?[\d.]+)',block))}
    found.ranks={key:cost for key,(_,cost) in ranks.items()}|{value:cost for value,cost in ranks.values()}
    found.ranks['default']=found.ranks[str(int(constant('COMMANDER_START_RANK')))]
    found.templates=dict(read(GAME,'common/character_templates'))
    produced=Counter()
    levels=Counter()
    for _,top in read(GAME,'common/history/buildings'):
        for state,inner in blocks(body(top)):
            for region,group in blocks(body(inner)):
                if not region.startswith('region_state:'): continue
                for _,made in blocks(body(group)):
                    if scalar(made,'building')!=ADMIN: continue
                    active=re.search(r'activate_production_methods\s*=\s*\{([^}]*)\}',made)
                    each=sum(found.outputs.get(m,0) for m in re.findall(r'\w+',active[1] if active else ''))
                    count=sum(int(n) for n in re.findall(r'levels\s*=\s*(\d+)',made))
                    produced[region[13:]]+=each*count
                    levels[region[13:],state]+=count
    found.most=max(levels.values())
    found.modifiers={key:(sum(float(n) for n in re.findall(r'state_bureaucracy_population_base_cost_factor_mult\s*=\s*(-?[\d.]+)',block)),
                          sum(float(n) for n in re.findall(r'country_bureaucracy_investment_cost_factor_mult\s*=\s*(-?[\d.]+)',block)))
                     for key,block in read(GAME,'common/laws')}
    vanilla=calibration['vanilla']
    tags=[tag for tag in sorted(recognized) if tag in vanilla and pops[tag]]
    donors=countries.everyone()
    _,characters=countries.copied('characters',set(tags))
    laws={tag:set(found) for tag,found in calibration['laws'].items()}
    rows=[(pops[tag],len(pops[tag])-outside[tag],invested(found,donors[tag],laws[tag]),laws[tag],commanders(found,characters.get(tag,'')),vanilla[tag]['spending_bureaucracy_expenses'])
          for tag in tags]
    rows+=[(row['pops'],row['incorporated'],row['invested'],laws[row['tag']],row['commanders'],row['expenses']) for row in calibration['generated']]
    x=np.array([features(found,p,n,i,set(l),c) for p,n,i,l,c,_ in rows])
    spent=np.array([e for *_,e in rows])
    free=np.zeros(x.shape[1])
    free[-1]=-np.inf
    found.expenses=lsq_linear(x/spent[:,None],np.ones(len(rows)),bounds=(free,np.inf)).x
    held=countries.held(people)
    found.ratios=sorted((np.log(held[tag]),vanilla[tag]['spending_bureaucracy_income']/vanilla[tag]['spending_bureaucracy_expenses']) for tag in tags)
    found.base=float(np.median([vanilla[tag]['spending_bureaucracy_income'] for tag in tags if not produced[tag]]))
    return found


@timed_often
def features(found,pops,incorporated,invested,laws,commanders):
    population,investment=(sum(found.modifiers[law][i] for law in laws if law in found.modifiers) for i in (0,1))
    total=sum(pops)*found.pop_cost
    return [found.state_cost*incorporated,total*(1+population),invested*total*(1+investment),invested,commanders,1.]


@timed_often
def invested(found,text,laws):
    levels=dict(LEVEL.findall(text))
    return sum(min(found.ceiling,max(found.floor,float(levels.get(made,found.floor)))) for made in {found.creates[law] for law in laws if law in found.creates})


@timed_often
def commanders(found,text):
    total=0.
    for key,statement in countries.statements(text):
        if key!='create_character' or not statement.endswith('}'): continue
        inner=body(statement)
        template=found.templates.get(scalar(inner,'template'),'')
        if COMMANDER.search(inner) or COMMANDER.search(template):
            total+=found.ranks[scalar(inner,'commander_rank') or scalar(template,'commander_rank') or 'default']
    return total


@timed_often
def ratio(rng,found,population):
    logs=np.array([p for p,_ in found.ratios])
    middle=int(np.searchsorted(logs,np.log(population)))
    window=found.ratios[max(0,middle-NEIGHBOURS//2):max(0,middle-NEIGHBOURS//2)+NEIGHBOURS]
    return window[rng.integers(len(window))][1]


@timed_often
def best(found,known,chosen,techs,laws):
    groups,gates,_,_=known
    for options in groups[ADMIN].values():
        ladder=sorted((m for m in options if found.outputs.get(m,0)>0 and allowed(gates[m],techs,laws)),key=lambda m:found.outputs[m])
        chosen=[ladder[-1] if m in options and ladder else m for m in chosen]
    return chosen


@timed_often
def fill(rng,total,weights,most):
    out=np.minimum(most,rng.multinomial(total,weights/weights.sum()))
    for index in np.argsort(-weights):
        extra=min(most-out[index],total-out.sum())
        out[index]+=extra
    return out


@timed
def administer(rng,found,known,owned,sizes,techs,laws,copied,characters,unincorporated):
    out={}
    for tag,members in owned.items():
        states=[s for s in members if s not in unincorporated]
        expenses=float(np.dot(found.expenses,features(found,[sizes[s] for s in members],len(states),invested(found,copied[tag],laws[tag]),laws[tag],
                                                      commanders(found,characters.get(tag,'')))))
        needed=expenses*ratio(rng,found,sum(sizes[s] for s in members))-found.base
        if needed<=0 or not found.needs<=techs[tag]: continue
        capacity=found.most*len(states)
        chosen=best(found,known,choose(rng,known,ADMIN,techs[tag],laws[tag]),techs[tag],laws[tag])
        total=min(capacity,int(np.ceil(needed/sum(found.outputs.get(m,0) for m in chosen))))
        for s,n in zip(states,fill(rng,total,np.array([sizes[s] for s in states]),found.most)):
            if n: out[s]=(int(n),chosen)
    return out


@timed
def history(rng,owners,known,described,owner,placed,techs,laws,admin):
    lines=[]
    every=[]
    for s,state in enumerate(described):
        tag=owner[s]
        made=[]
        found=dict(placed[s])
        if s in admin: found[ADMIN]=admin[s][0]
        every.append(found)
        for building,level in sorted(found.items()):
            names=sorted(owners[building]) if building!=ADMIN else ['country']
            weights=np.array([owners[building][n] for n in names],float) if building!=ADMIN else np.ones(1)
            holder=str(rng.choice(names,p=weights/weights.sum()))
            if holder=='country':
                ownership=f'country={{ country="c:{tag}" levels={level} }}'
            else:
                ownership=f'building={{ type="{building if holder=="self" else holder}" country="c:{tag}" levels={level} region="{state["key"]}" }}'
            chosen=' '.join(f'"{m}"' for m in (admin[s][1] if building==ADMIN else choose(rng,known,building,techs[tag],laws[tag],state['methods'].get(building,()))))
            made.append(f'\t\t\tcreate_building={{\n\t\t\t\tbuilding="{building}"\n\t\t\t\tadd_ownership={{ {ownership} }}\n\t\t\t\treserves=1\n'
                        f'\t\t\t\tactivate_production_methods={{ {chosen} }}\n\t\t\t}}\n')
        lines.append(f"\ts:{state['key']}={{\n\t\tregion_state:{tag}={{\n{''.join(made)}\t\t}}\n\t}}\n")
    return 'BUILDINGS={\n'+''.join(lines)+'}\n',every
