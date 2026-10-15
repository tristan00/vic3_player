from collections import Counter

import numpy as np

from . import timed, timed_often

HUBS=('city','farm','mine','wood')


@timed_often
def nearest(world,options,target):
    return min(options,key=lambda p:float(((world.centre[p]-target)**2).sum()))


@timed
def describe(rng,terrains,found,world):
    seas={p:i for i,p in enumerate(world.seas)}
    out=[]
    for index,members in enumerate(world.states):
        dominant=next(kind for kind,_ in Counter(world.terrain[p] for p in members).most_common() if kind in terrains)
        weight=world.area[members].astype(float)
        size=np.sqrt(weight.sum())
        middle=(world.centre[members]*weight[:,None]).sum(0)/weight.sum()
        open_=[p for p in members if p not in world.impassable]
        away=lambda p,target,goal:abs(float(np.hypot(*(world.centre[p]-target)))/size-goal)
        offset,spread=rng.choice(found.offsets),rng.choice(found.spreads)
        city=min(open_,key=lambda p:away(p,middle,offset))
        chosen=[city]+sorted((p for p in open_ if p!=city),key=lambda p:away(p,world.centre[city],spread))
        state={'key':f'STATE_MW_{index+1}','id':index+1,'provinces':members,'terrain':dominant,'hubs':{hub:chosen[i%len(chosen)] for i,hub in enumerate(HUBS)},
               'impassable':[p for p in members if p in world.impassable]}
        shore=[p for p in open_ if world.neighbours[p]&seas.keys()]
        if shore:
            port=nearest(world,shore,world.centre[city])
            coast=Counter(o for p in shore for o in world.neighbours[p]&seas.keys())
            state['hubs']['port']=port
            state['naval_exit']=3000+seas[max(sorted(world.neighbours[port]&seas.keys()),key=lambda o:coast[o])]
        out.append(state)
    return out
