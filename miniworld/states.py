from types import SimpleNamespace
import re
from collections import Counter, defaultdict

import numpy as np
from scipy.optimize import minimize

from interface.script import blocks, body, read, scalar
from . import GAME, countries, timed
from .geography import hops, partition, split

NEAREST=5


@timed
def model(vanilla):
    definitions={tag:block for tag,block in read(GAME,'common/country_definitions') if scalar(block,'country_type')=='recognized'}
    cultures={tag:set(countries.cultures(block,vanilla.get(tag,''))) for tag,block in definitions.items()}
    known=dict(read(GAME,'common/cultures'))
    default={key:scalar(block,'religion') for key,block in known.items()}
    held=defaultdict(Counter)
    believers=defaultdict(Counter)
    for _,block in read(GAME,'common/history/pops'):
        for state,inner in blocks(body(block)):
            for region,group in blocks(body(inner)):
                tag=region.split(':',1)[1]
                for _,pop in blocks(body(group)):
                    culture=scalar(pop,'culture')
                    believers[state,tag,culture][scalar(pop,'religion') or default[culture]]+=int(scalar(pop,'size'))
                    if tag in cultures: held[tag,state[2:]][culture]+=int(scalar(pop,'size'))
    found=SimpleNamespace()
    found.faith=defaultdict(list)
    for (_,_,culture),faiths in sorted(believers.items()):
        if sum(faiths.values()): found.faith[culture].append(({r:n/sum(faiths.values()) for r,n in faiths.items()},sum(faiths.values())))
    found.heritage={key:scalar(block,'heritage') for key,block in known.items()}
    kin=Counter()
    grouped=defaultdict(list)
    for (tag,state),sizes in sorted(held.items()):
        total=sum(sizes.values())
        foreign={c:n for c,n in sizes.items() if c not in cultures[tag] and n>0}
        heritage={found.heritage[c] for c in cultures[tag]}
        for c,n in foreign.items(): kin[found.heritage[c] in heritage]+=n
        if sum(foreign.values())<total: grouped[tag].append((total,sorted(foreign.values(),reverse=True)))
    found.templates=[[(sum(foreign)/total,[n/sum(foreign) for n in foreign]) for total,foreign in sorted(kept,key=lambda t:-t[0])] for _,kept in sorted(grouped.items())]
    found.sizes=np.log([len(kept) for kept in found.templates])
    found.kin=kin[True]/sum(kin.values())
    homes={}
    claimed={}
    for _,top in read(GAME,'common/history/states'):
        for state,inner in blocks(body(top)):
            homes[state[2:]]=set(re.findall(r'add_homeland\s*=\s*cu:(\w+)',inner))
            claimed[state[2:]]=set(re.findall(r'\badd_claim\s*=\s*c:(\w+)',inner))
    mixes=defaultdict(Counter)
    for (tag,state),sizes in held.items(): mixes[state].update(sizes)
    rows=[(np.log(n/sum(m.values())),c in homes.get(s,())) for s,m in mixes.items() for c,n in m.items() if n]
    x=np.array([r[0] for r in rows]);y=np.array([r[1] for r in rows],float)
    loss=lambda w:np.sum(np.logaddexp(0,-(w[0]+w[1]*x))*y+np.logaddexp(0,w[0]+w[1]*x)*(1-y))
    found.homeland=tuple(minimize(loss,[0.,1.]).x)
    created=countries.incorporation()
    owners=defaultdict(set)
    for tag,made in created.items():
        for state,_ in made: owners[state].add(tag)
    pairs=[(state,tag) for state in owners for tag in cultures if tag not in owners[state] and homes.get(state,set())&cultures[tag]]
    found.claim=sum(tag in claimed[state] for state,tag in pairs)/len(pairs)
    rows=[(len(created[tag]),sum(u for s,u in created[tag] if s!=scalar(block,'capital'))) for tag,block in definitions.items() if len(created[tag])>1]
    found.held=np.log([n for n,_ in rows])
    found.unincorporated=np.array([u for _,u in rows],float)
    found.others=np.array([n-1 for n,_ in rows],float)
    found.capital=[]
    for tag,block in definitions.items():
        states={state:sum(sizes.values()) for (t,state),sizes in held.items() if t==tag and sum(sizes.values())>0}
        capital=scalar(block,'capital')
        if len(states)>1 and capital in states:
            ranked=sorted(states,key=lambda s:-states[s])
            found.capital.append(ranked.index(capital)/(len(ranked)-1))
    return found


@timed
def owners(rng,world,described,tags,concentration):
    shares=rng.dirichlet(np.full(len(tags),1/concentration))
    targets=split(len(world.states)-len(tags),shares)+1
    inland=defaultdict(list)
    for s,k in landmasses(world).items():
        if 'port' not in described[s]['hubs']: inland[k].append(s)
    first=[int(rng.choice(inland[k])) for k in sorted(inland,key=lambda k:(-len(inland[k]),k))[:len(tags)]]
    return dict(zip(tags,partition(rng,range(len(world.states)),world.reachable,list(targets),first)))


@timed
def landmasses(world):
    component={}
    for s in range(len(world.states)):
        if s not in component: component.update(dict.fromkeys(hops(range(len(world.states)),world.joined,[s]),s))
    return component


@timed
def settle(world,described,owned):
    component=landmasses(world)
    owner={s:tag for tag,members in owned.items() for s in members}
    home={tag:Counter(component[s] for s in members).most_common(1)[0][0] for tag,members in owned.items()}
    for tag,members in owned.items():
        away={s for s in members if component[s]!=home[tag]}
        while away:
            cluster=set(hops(away,world.joined,[min(away)]))
            away-=cluster
            if all('port' in described[s]['hubs'] for s in cluster): continue
            others=Counter(owner[o] for s in sorted(cluster) for o in sorted(world.joined[s]) if owner[o]!=tag and home[owner[o]]==component[s])
            if others: owner.update(dict.fromkeys(cluster,others.most_common(1)[0][0]))
    return {tag:sorted(s for s in owner if owner[s]==tag) for tag in owned},home,component


@timed
def capitals(rng,found,owned,totals,home,component):
    out={}
    for tag,states in owned.items():
        ranked=sorted((s for s in states if component[s]==home[tag]),key=lambda s:-totals[s])
        out[tag]=ranked[int(round(rng.choice(found.capital)*(len(ranked)-1)))]
    return out


@timed
def homelands(rng,found,mixes):
    out=[]
    for mix in mixes:
        total=sum(n for _,n in mix)
        out.append({c for c,n in mix if rng.random()<1/(1+np.exp(-(found.homeland[0]+found.homeland[1]*np.log(n/total))))})
    return out


@timed
def unincorporated(rng,found,world,owned,capitals):
    out=set()
    for tag,members in owned.items():
        rest=[s for s in members if s!=capitals[tag]]
        if not rest: continue
        distance=np.abs(found.held-np.log(len(members)))
        near=np.flatnonzero(distance<=np.sort(distance)[NEAREST-1])
        reach=hops(set(members),world.joined,[capitals[tag]])
        far=sorted(rest,key=lambda s:(-reach.get(s,len(world.states)),s))
        out.update(far[:rng.binomial(len(rest),found.unincorporated[near].sum()/found.others[near].sum())])
    return out


@timed
def claims(rng,found,owned,homes,cultures):
    return {s:[t for t in sorted(owned) if s not in owned[t] and homes[s]&set(cultures[t]) and rng.random()<found.claim] for members in owned.values() for s in members}


@timed
def history(world,described,owned,homes,colors,unincorporated,claimed):
    lines=[]
    for tag,states in owned.items():
        for s in states:
            provinces=' '.join(colors(world.colors[p]) for p in described[s]['provinces'])
            added=''.join(f'\t\tadd_homeland = cu:{c}\n' for c in sorted(homes[s]))+''.join(f'\t\tadd_claim = c:{t}\n' for t in claimed[s])
            kind='\t\t\tstate_type = unincorporated\n' if s in unincorporated else ''
            lines.append(f"\ts:{described[s]['key']} = {{\n\t\tcreate_state = {{\n\t\t\tcountry = c:{tag}\n\t\t\towned_provinces = {{ {provinces} }}\n{kind}\t\t}}\n{added}\t}}\n")
    return 'STATES = {\n'+''.join(lines)+'}\n'


@timed
def mix(rng,found,world,owner,cultures,totals,diversity):
    out=[]
    rank={}
    choices={}
    tags=sorted(set(owner.values()))
    neighbours={tag:set() for tag in tags}
    for s,others in enumerate(world.reachable): neighbours[owner[s]].update(owner[o] for o in others if owner[o]!=owner[s])
    for tag in tags:
        mine=sorted((s for s in range(len(owner)) if owner[s]==tag),key=lambda s:-totals[s])
        distance=np.abs(found.sizes-np.log(len(mine)))
        reference=found.templates[rng.choice(np.flatnonzero(distance<=np.sort(distance)[NEAREST-1]))]
        rank.update({s:(r,len(mine),reference) for r,s in enumerate(mine)})
        own=set(cultures[tag])
        heritage={found.heritage[c] for c in own}
        near=sorted({c for o in neighbours[tag] for c in cultures[o]}-own)
        kin=sorted({c for c in found.faith if found.heritage[c] in heritage}-own)
        weights=Counter({c:found.kin/len(kin) for c in kin})
        weights.update({c:(1-found.kin)/len(near) for c in near})
        choices[tag]=weights
    for s in range(len(owner)):
        tag=owner[s]
        weights=choices[tag]
        names=sorted(weights)
        r,n,reference=rank[s]
        share,parts=reference[0 if r==0 else min(len(reference)-1,int((r+rng.random())/n*len(reference)))]
        held=min(len(parts),len(names))
        parts=parts[:held-1]+[sum(parts[held-1:])] if held else []
        minority=1-(1-share)**diversity if parts else 0.
        made=list(zip(cultures[tag],rng.dirichlet(np.ones(len(cultures[tag])))*(1-minority)))
        if parts:
            chances=np.array([weights[c] for c in names])
            chosen=rng.choice(names,len(parts),replace=False,p=chances/chances.sum())
            made+=list(zip(chosen.tolist(),np.array(parts)/sum(parts)*minority))
        merged=Counter()
        for c,part in made: merged[c]+=int(totals[s]*part)
        out.append([(c,n) for c,n in merged.items() if n>0])
    return out


@timed
def pops(rng,found,described,owner,mixes):
    lines=[]
    for s,state in enumerate(described):
        made=[]
        for c,n in mixes[s]:
            weights=np.array([w for _,w in found.faith[c]],float)
            shares,_=found.faith[c][rng.choice(len(weights),p=weights/weights.sum())]
            made+=[(c,r,int(n*share)) for r,share in sorted(shares.items()) if int(n*share)>0]
        entries=''.join(f'\t\t\tcreate_pop = {{\n\t\t\t\tculture = {c}\n\t\t\t\treligion = {r}\n\t\t\t\tsize = {n}\n\t\t\t}}\n' for c,r,n in made)
        lines.append(f"\ts:{state['key']} = {{\n\t\tregion_state:{owner[s]} = {{\n{entries}\t\t}}\n\t}}\n")
    return 'POPS = {\n'+''.join(lines)+'}\n'
