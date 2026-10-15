from types import SimpleNamespace
import re
from collections import Counter

import numpy as np

from interface.script import blocks, body, read, scalar
from . import GAME, countries, timed, timed_often


@timed_often
def needs(block):
    found=re.search(r'unlocking_technologies\s*=\s*\{([^}]*)\}',block)
    return set(found[1].split()) if found else set()


@timed
def model(people):
    recognized={tag for tag,block in read(GAME,'common/country_definitions') if scalar(block,'country_type')=='recognized'}
    shores={key for key,block in read(GAME,'map_data/state_regions') if scalar(block,'port') is not None}
    pop=countries.held(people)
    seaside=set()
    for _,top in read(GAME,'common/history/states'):
        for state,inner in blocks(body(top)):
            if state[2:] in shores: seaside.update(re.findall(r'country\s*=\s*c:(\w+)',inner))
    sizes={'army':Counter(),'fleet':Counter()}
    types={'army':Counter(),'fleet':Counter()}
    for _,top in read(GAME,'common/history/military_formations'):
        for key,inner in blocks(body(top)):
            tag=key[2:]
            if tag not in recognized: continue
            for kind,made in blocks(body(inner)):
                if kind=='create_ship':
                    sizes['fleet'][tag]+=1
                    types['fleet'][scalar(made,'type').split(':')[1]]+=1
                if kind!='create_military_formation': continue
                for part,unit in blocks(body(made)):
                    if part in ('combat_unit','ship'):
                        n=int(scalar(unit,'count') or 1)
                        branch='army' if part=='combat_unit' else 'fleet'
                        sizes[branch][tag]+=n
                        types[branch][scalar(unit,'type').split(':')[1]]+=n
    out={}
    for branch,found in sizes.items():
        eligible=[t for t in recognized if pop[t] and (branch=='army' or t in seaside)]
        holders=[t for t in eligible if found[t]]
        force=SimpleNamespace()
        force.share=len(holders)/len(eligible)
        x=np.log([pop[t] for t in holders])
        y=np.log([found[t] for t in holders])
        force.slope,force.intercept=np.polyfit(x,y,1)
        force.spread=float(np.std(y-(force.intercept+force.slope*x)))
        force.types=types[branch]
        out[branch]=force
    folders={'army':'common/combat_unit_types','fleet':'common/ship_types'}
    for branch,folder in folders.items():
        out[branch].needs={key:needs(block) for key,block in read(GAME,folder)}
    return out


@timed_often
def draw(rng,force,pop,techs):
    if rng.random()>=force.share: return Counter()
    total=int(round(np.exp(force.intercept+force.slope*np.log(pop)+rng.normal(0,force.spread))))
    allowed=sorted(t for t in force.types if force.needs[t]<=techs)
    if not allowed or total<1: return Counter()
    weights=np.array([force.types[t] for t in allowed],float)
    return Counter(dict(zip(allowed,rng.multinomial(total,weights/weights.sum()))))


@timed
def history(rng,forces,described,owned,sizes,capitals,region_of,techs):
    lines=[]
    fleets=set()
    for tag,states in owned.items():
        pop=sum(sizes[s] for s in states)
        made=[]
        army=draw(rng,forces['army'],pop,techs[tag])
        if army:
            weights=np.array([sizes[s] for s in states])/pop
            units=''
            for unit,count in sorted(army.items()):
                for s,n in zip(states,rng.multinomial(count,weights)):
                    if n: units+=f'\t\t\tcombat_unit = {{\n\t\t\t\ttype = unit_type:{unit}\n\t\t\t\tstate_region = s:{described[s]["key"]}\n\t\t\t\tcount = {n}\n\t\t\t}}\n'
            made.append(f'\t\tcreate_military_formation = {{\n\t\t\ttype = army\n\t\t\thq_region = sr:{region_of[capitals[tag]]}\n{units}\t\t}}\n')
        shore=[s for s in states if 'port' in described[s]['hubs']]
        fleet=draw(rng,forces['fleet'],pop,techs[tag]) if shore else Counter()
        if fleet:
            fleets.add(tag)
            home=capitals[tag] if capitals[tag] in shore else shore[0]
            ships=''.join(f'\t\t\tship = {{\n\t\t\t\ttype = ship_type:{ship}\n\t\t\t\tcount = {n}\n\t\t\t}}\n' for ship,n in sorted(fleet.items()) if n)
            made.append(f'\t\tcreate_military_formation = {{\n\t\t\ttype = fleet\n\t\t\thq_region = sr:{region_of[home]}\n{ships}\t\t}}\n')
        if made: lines.append(f'\tc:{tag} ?= {{\n{"".join(made)}\t}}\n')
    return 'MILITARY_FORMATIONS = {\n'+''.join(lines)+'}\n',fleets
