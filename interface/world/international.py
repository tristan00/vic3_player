import itertools
import math

from ..common import timed_often
from .nations import _rgb, word


IDENTITIES={'identity_trade_league':'League','identity_ideological_union':'Union','identity_military_treaty_organization':'Pact','identity_sovereign_empire':'Empire'}
RELATIONS=50


@timed_often
def conquests(rng,level,tags):
    targets={}
    if len(tags)<2:
        return targets
    for tag in tags:
        target=rng.choice([other for other in tags if other!=tag])
        if rng.random()<level:
            targets[tag]=target
    return targets


@timed_often
def opening_war(rng,level,free):
    if len(free)<2 or rng.random()>=level:
        return None
    return rng.sample(free,2)


@timed_often
def connect(rng,level,strength,types,centers,rules):
    count=len(strength)
    if count<2:
        return {},[]
    wanted=level*count
    linked=int(wanted)+(rng.random()<wanted-int(wanted))
    if linked==1:
        linked=2*(rng.random()<.5)
    if not linked:
        return {},[]
    free=list(range(count))
    seeds=[]
    for _ in range(rng.randint(1,linked//2)):
        seeds.append(rng.choices(free,[strength[i]+1 for i in free])[0])
        free.remove(seeds[-1])
    clusters={seed:[seed] for seed in seeds}
    distance=lambda i,seed:math.dist(centers[i],centers[seed])
    for seed in seeds:
        clusters[seed].append(min(free,key=lambda i:distance(i,seed)))
        free.remove(clusters[seed][-1])
    for _ in range(linked-2*len(seeds)):
        i,seed=min(((i,seed) for i in free for seed in seeds),key=lambda pair:distance(*pair))
        clusters[seed].append(i)
        free.remove(i)
    overlords={}
    blocs=[]
    for members in clusters.values():
        members.sort(key=lambda i:(-strength[i],i))
        leader=members[0]
        independent=[]
        for i in members[1:]:
            if rng.random()<level:
                overlords[i]=(leader,rng.choice(sorted(kind for kind,(over,under) in rules.items() if types[leader] in over and types[i] in under)))
            else:
                independent.append(i)
        blocs.append({'leader':leader,'members':members,'independent':independent})
    return overlords,blocs


@timed_often
def split(rng,sides,strength,types,rules):
    def equality(chosen):
        totals=[[sum(values[k] for values,side in zip(strength,chosen) if side==s) for k in range(len(strength[0]))] for s in range(sides)]
        return min(min(metric)/max(metric) if max(metric) else 1 for metric in zip(*totals))
    sizes=lambda chosen:[chosen.count(side) for side in range(sides)]
    chosen=max((c for c in itertools.product(range(sides),repeat=len(strength)) if max(sizes(c))-min(sizes(c))<2),key=equality)
    overlords={}
    blocs=[]
    for side in range(sides):
        members=sorted((i for i,found in enumerate(chosen) if found==side),key=lambda i:(-strength[i][0],i))
        for i in members[1:]:
            overlords[i]=(members[0],rng.choice(sorted(kind for kind,(over,under) in rules.items() if types[members[0]] in over and types[i] in under)))
        blocs.append({'leader':members[0],'members':members,'independent':[]})
    return overlords,blocs


@timed_often
def members(bloc,tags):
    return ''.join(f' member = c:{tags[i]}' for i in bloc['independent'])


@timed_often
def found(rng,number,bloc,tags,laws,principles):
    identities=['identity_trade_league','identity_ideological_union']
    if laws['lawgroup_army_model']!='law_national_militia':
        identities.append('identity_military_treaty_organization')
    if not bloc['independent'] and laws.get('lawgroup_governance_principles')=='law_monarchy':
        identities.append('identity_sovereign_empire')
    identity=rng.choice(identities)
    key=f'INTERFACE_BLOC_{number}'
    text=(f'c:{tags[bloc["leader"]]} ?= {{ create_power_bloc = {{ name = {key} map_color = {{ {_rgb(rng)} }} founding_date = 1830.1.1 '
          f'identity = {identity} principle = {rng.choice(principles[identity])}{members(bloc,tags)} }} }}')
    return text,f' {key}: "{word(rng)} {IDENTITIES[identity]}"',identity


@timed_often
def pacts(overlords,blocs,tags):
    lines=[f'c:{tags[over]} ?= {{ set_relations = {{ country = c:{tags[i]} value = {RELATIONS} }} create_diplomatic_pact = {{ country = c:{tags[i]} type = {kind} }} }}'
           for i,(over,kind) in sorted(overlords.items())]
    return lines+[f'c:{tags[bloc["leader"]]} ?= {{ set_relations = {{ country = c:{tags[i]} value = {RELATIONS} }} }}' for bloc in blocs for i in bloc['independent']]
