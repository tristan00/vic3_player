from types import SimpleNamespace
import re
from collections import Counter

import numpy as np

from interface.script import blocks, body, read, scalar
from . import GAME, timed, timed_often

FRIENDLY=('befriend','protect')
HOSTILE=('antagonize','dominate','conquer')
SUBJECT_SHARE=.6
RIVAL_SHARE=.5
DISTANT=.3
LARGER=2
SIMILAR=3


@timed_often
def listed(block,key):
    found=re.search(key+r'\s*=\s*\{([^}]*)\}',block)
    return set(found[1].split()) if found else set()


@timed
def model():
    found=SimpleNamespace()
    allowed={key.removeprefix('subject_type_') for key,block in read(GAME,'common/subject_types')
             if 'recognized' in listed(block,'valid_subject_country_types') and 'recognized' in listed(block,'valid_overlord_country_types')}
    pacts=Counter()
    for _,top in read(GAME,'common/history/diplomacy'):
        for _,inner in blocks(body(top)):
            for kind,pact in blocks(body(inner)):
                if kind=='create_diplomatic_pact' and scalar(pact,'type') in allowed: pacts[scalar(pact,'type')]+=1
    found.subjects=pacts
    actions=dict(read(GAME,'common/diplomatic_actions'))
    monarchy=set(re.findall(r'law_type:(\w+)',dict(read(GAME,'common/scripted_triggers'))['country_has_monarchy_law']))
    found.ruler={key.removeprefix('subject_type_') for key,block in read(GAME,'common/subject_types') if scalar(block,'use_overlord_ruler')=='yes'}
    found.needs={kind:(monarchy,set(re.findall(r'NOT\s*=\s*\{\s*has_law\s*=\s*law_type:(\w+)',actions[kind]))) for kind in pacts if 'country_has_monarchy_law' in actions[kind]}
    found.blocs=[(scalar(made,'identity'),scalar(made,'principle'),1+len(re.findall(r'member\s*=',made))) for _,top in read(GAME,'common/history/power_blocs')
                 for _,inner in blocks(body(top)) for kind,made in blocks(body(inner)) if kind=='create_power_bloc']
    pairs={}
    for _,top in read(GAME,'common/history/diplomacy'):
        for tag,inner in blocks(body(top)):
            for other,value in re.findall(r'set_relations\s*=\s*\{\s*country\s*=\s*c:(\w+)\s*value\s*=\s*(-?\d+)',inner):
                pairs[frozenset((tag[2:],other))]=int(value)
    found.relations=float(np.std(list(pairs.values())))
    members=[pairs[key] for _,top in read(GAME,'common/history/power_blocs') for leader,inner in blocks(body(top))
             for member in re.findall(r'member\s*=\s*c:(\w+)',inner) if (key:=frozenset((leader[2:],member))) in pairs]
    found.bloc=int(np.median(members))
    defines=(GAME/'common/defines/00_defines.txt').read_text(encoding='utf-8-sig')
    prestige={name.lower():int(value) for name,value in re.findall(r'COUNTRY_TIER_(\w+)_PRESTIGE\s*=\s*(\d+)',defines)}
    found.order=sorted(prestige,key=prestige.get)
    return found


@timed
def neighbours(world,owned):
    owner={s:tag for tag,members in owned.items() for s in members}
    out={tag:set() for tag in owned}
    for s,others in enumerate(world.reachable):
        for o in others:
            if owner[o]!=owner[s]: out[owner[s]].add(owner[o])
    return out


@timed
def interests(world,owned):
    region={s:index for index,members in enumerate(world.regions) for s in members}
    return {tag:{region[s] for s in members} for tag,members in owned.items()}


@timed_often
def fitting(found,kind,laws,ruled):
    if kind in found.ruler and not (ruled[0] and not ruled[1]): return False
    if kind not in found.needs: return True
    required,forbidden=found.needs[kind]
    return all(found_laws&required and not found_laws&forbidden for found_laws in laws)


@timed
def arrange(rng,found,world,owned,population,level,laws,ruled,tiers):
    tags=sorted(owned)
    tier={tag:found.order.index(tiers[tag]) for tag in tags}
    near=neighbours(world,owned)
    shared=interests(world,owned)
    pair=lambda a,b:(min(a,b),max(a,b))
    draw=lambda:int(np.clip(round(rng.normal(0,found.relations*2*level)),-100,100))
    out=SimpleNamespace()
    out.relations={}
    for a in tags:
        for b in tags:
            if a<b and rng.random()<level*(1 if b in near[a] else DISTANT):
                out.relations[a,b]=draw()
    overlord_of={}
    out.subjects=[]
    for tag in sorted(tags,key=lambda t:population[t]):
        if tag in overlord_of.values(): continue
        bigger=[o for o in sorted(near[tag]) if population[o]>=LARGER*population[tag] and tier[o]>=tier[tag] and o not in overlord_of]
        if bigger and rng.random()<SUBJECT_SHARE*level:
            master=max(bigger,key=lambda o:population[o])
            overlord_of[tag]=master
            kinds=[k for k in sorted(found.subjects) if fitting(found,k,(laws[master],laws[tag]),(master in ruled,tag in ruled))]
            weights=np.array([found.subjects[k] for k in kinds],float)
            out.subjects.append((master,tag,str(rng.choice(kinds,p=weights/weights.sum()))))
            out.relations[pair(master,tag)]=abs(out.relations.get(pair(master,tag),draw()))
    free=[t for t in tags if t not in overlord_of]
    rivals=set()
    out.rivals=[]
    for tag in free:
        options=[o for o in sorted(near[tag]) if o in free and shared[tag]&shared[o] and pair(tag,o) not in rivals
                 and population[tag]/SIMILAR<=population[o]<=population[tag]*SIMILAR and abs(tier[o]-tier[tag])<=1]
        if options and rng.random()<RIVAL_SHARE*level:
            other=min(options,key=lambda o:abs(np.log(population[o]/population[tag])))
            rivals.add(pair(tag,other))
            out.rivals.append((tag,other))
            out.relations[pair(tag,other)]=-abs(out.relations.get(pair(tag,other),draw()))
    out.blocs=[]
    joined=set()
    for leader in sorted(free,key=lambda t:-population[t])[:int(np.floor(level*len(free)/3))]:
        if leader in joined: continue
        members=[]
        for o in sorted(near[leader]):
            if o in free and o not in joined and o!=leader and population[o]*LARGER<=population[leader] and tier[o]<=tier[leader] \
                    and all(pair(o,m) not in rivals for m in [leader,*members]) \
                    and out.relations.get(pair(leader,o),0)>=0 and rng.random()<level:
                members.append(o)
        if not members: continue
        joined.update([leader,*members])
        for m in members: out.relations[pair(leader,m)]=max(out.relations.get(pair(leader,m),0),found.bloc)
        weights=np.array([n for *_,n in found.blocs],float)
        identity,principle,_=found.blocs[rng.choice(len(found.blocs),p=weights/weights.sum())]
        out.blocs.append((leader,members,identity,principle,[int(c) for c in rng.integers(40,255,3)]))
    bloc_of={m:index for index,(leader,members,*_) in enumerate(out.blocs) for m in [leader,*members]}
    out.goals=[]
    for a in tags:
        for b in sorted(near[a]):
            if rng.random()>=level: continue
            if pair(a,b) in rivals: options=HOSTILE
            elif overlord_of.get(a)==b or overlord_of.get(b)==a or (a in bloc_of and bloc_of.get(b)==bloc_of[a]): options=FRIENDLY
            else:
                mood=out.relations.get(pair(a,b),0)
                options=FRIENDLY if mood>0 else HOSTILE if mood<0 else FRIENDLY+HOSTILE
            out.goals.append((a,b,str(rng.choice(options))))
    return out


@timed
def history(made,names,labels):
    lines={}
    for (a,b),value in made.relations.items():
        lines.setdefault(a,[]).append(f'\t\tset_relations = {{ country = c:{b} value = {value} }}\n')
    for master,subject,kind in made.subjects:
        lines.setdefault(master,[]).append(f'\t\tcreate_diplomatic_pact = {{\n\t\t\tcountry = c:{subject}\n\t\t\ttype = {kind}\n\t\t}}\n')
    diplomacy='DIPLOMACY = {\n'+''.join(f'\tc:{tag} ?= {{\n{"".join(body)}\t}}\n' for tag,body in sorted(lines.items()))+'}\n'
    rivalries='mw_rivalries = {\n\teffect = {\n'+''.join(f'\t\tc:{a} ?= {{\n\t\t\tc:{b} ?= {{ save_scope_as = target_country }}\n\t\t\tif = {{\n'
                                                      f'\t\t\t\tlimit = {{ countries_are_valid_rivals = yes }}\n'
                                                      f'\t\t\t\tcreate_diplomatic_pact = {{\n\t\t\t\t\tcountry = c:{b}\n\t\t\t\t\ttype = rivalry\n\t\t\t\t}}\n'
                                                      f'\t\t\t}}\n\t\t}}\n' for a,b in made.rivals)+'\t}\n}\n'
    goals={}
    for a,b,goal in made.goals:
        goals.setdefault(a,[]).append(f'\t\tset_secret_goal = {{\n\t\t\tcountry = c:{b}\n\t\t\tsecret_goal = {goal}\n\t\t}}\n')
    ai='AI = {\n'+''.join(f'\tc:{tag} ?= {{\n{"".join(body)}\t}}\n' for tag,body in sorted(goals.items()))+'}\n'
    blocs=[]
    for index,(leader,members,identity,principle,color) in enumerate(made.blocs):
        labels[f'MW_BLOC_{index+1}']=names[leader]+' League'
        listed=''.join(f'\t\t\tmember = c:{m}\n' for m in members)
        blocs.append(f'\tc:{leader} ?= {{\n\t\tcreate_power_bloc = {{\n\t\t\tname = MW_BLOC_{index+1}\n\t\t\tmap_color = {{ {" ".join(map(str,color))} }}\n'
                     f'\t\t\tfounding_date = 1830.1.1\n\t\t\tidentity = {identity}\n\t\t\tprinciple = {principle}\n{listed}\t\t}}\n\t}}\n')
    return diplomacy,rivalries,ai,'POWER_BLOCS = {\n'+''.join(blocs)+'}\n'
