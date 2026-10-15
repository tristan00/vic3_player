from types import SimpleNamespace
import heapq
import re
from collections import Counter, deque

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

from interface.script import blocks, clean, read, scalar
from interface.timing import evidence
from . import GAME, textures, timed, timed_often
from .names import label

WATER=4751
LIFT={'plains':500,'forest':700,'wetland':150,'jungle':500,'desert':900,'savanna':600,'tundra':500,'snow':2200,'hills':3200,'mountain':8000}
COLD=('snow','tundra')
HOT=('desert','jungle','savanna')
RUGGED=('mountain','hills')
COMPACT=6
SMALLEST=384
SPREAD=8

Image.MAX_IMAGE_PIXELS=None


@timed
def profile():
    rgb=np.asarray(Image.open(GAME/'map_data/provinces.png').convert('RGB')).astype(np.int32)
    code=(rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
    colors,inverse,area=np.unique(code,return_inverse=True,return_counts=True)
    inverse=inverse.ravel()
    centre=np.stack([np.bincount(inverse,np.repeat(np.arange(code.shape[0]),code.shape[1])),np.bincount(inverse,np.tile(np.arange(code.shape[1]),code.shape[0]))],1)/area[:,None]
    position={c:i for i,c in enumerate(colors.tolist())}
    areas=dict(zip(colors.tolist(),area.tolist()))
    text=(GAME/'map_data/default.map').read_text(encoding='utf-8-sig')
    seas=[int(c,16) for c in re.findall(r'x([0-9A-Fa-f]{6})',text.split('sea_starts')[1].split('}')[0])]
    lakes=[int(c,16) for c in re.findall(r'x([0-9A-Fa-f]{6})',text.split('lakes')[1].split('}')[0])]
    terrain={int(c,16):k for c,k in re.findall(r'x([0-9A-Fa-f]{6})\s*=\s*"(\w+)"',(GAME/'map_data/province_terrains.txt').read_text(encoding='utf-8-sig'))}
    counts=[]
    land=[]
    impassable=set()
    state_of={}
    offsets=[]
    spreads=[]
    places={}
    waters={}
    for key,block in read(GAME,'map_data/state_regions'):
        provinces=[int(c,16) for c in re.findall(r'x([0-9A-Fa-f]{6})',re.search(r'provinces\s*=\s*\{([^}]*)\}',block)[1])]
        if int(scalar(block,'id'))>=3000:
            waters[key]=provinces
            continue
        places[key]=provinces
        blocked=re.search(r'impassable\s*=\s*\{([^}]*)\}',block)
        impassable.update(int(c,16) for c in re.findall(r'x([0-9A-Fa-f]{6})',blocked[1] if blocked else ''))
        state_of.update(dict.fromkeys(provinces,len(counts)))
        if len(provinces)>=SPREAD and np.ptp([centre[position[c]][1] for c in provinces])<code.shape[1]/2:
            index=[position[c] for c in provinces]
            weight=area[index].astype(float)
            middle=(centre[index]*weight[:,None]).sum(0)/weight.sum()
            city,*hubs=(centre[position[int(scalar(block,h).strip('"')[1:],16)]] for h in ('city','farm','mine','wood'))
            offsets.append(np.hypot(*(middle-city))/np.sqrt(weight.sum()))
            spreads.append(np.mean([np.hypot(*(h-city)) for h in hubs])/np.sqrt(weight.sum()))
        counts.append(len(provinces))
        land+=provinces
    pairs=set()
    for a,b in ((code[:,:-1],code[:,1:]),(code[:-1],code[1:]),(code[:,-1],code[:,0])):
        edge=a!=b
        pairs.update((key>>24,key&0xFFFFFF) for key in np.unique(a[edge].astype(np.int64)<<24|b[edge]).tolist())
    touching={c:set() for c in seas}
    for x,y in pairs:
        if x in touching and y in state_of: touching[x].add(state_of[y])
        if y in touching and x in state_of: touching[y].add(state_of[x])
    market=int(re.search(r'WORLD_MARKET_LOCATION\s*=\s*"x([0-9A-Fa-f]{6})"',(GAME/'common/defines/00_defines.txt').read_text(encoding='utf-8-sig'))[1],16)
    found=SimpleNamespace()
    found.textures=textures.profile(colors,inverse,code.shape,terrain,impassable)
    found.offsets=offsets
    found.spreads=spreads
    found.harsh={key for key,block in read(GAME,'common/terrain') if re.search(r'\blabel\s*=\s*label_travel_harsh_environment\b',block)}
    found.coastal_seas=[areas[c] for c in seas if touching[c]]
    found.market_rank=float(np.mean([len(touching[c])>len(touching[market]) for c in seas]))
    logs=np.log(counts)
    found.count_mu,found.count_sd=float(logs.mean()),float(logs.std())
    found.land_area=float(np.median([areas[c] for c in land]))
    found.sea_ratio=sum(areas[c] for c in seas)/sum(areas[c] for c in land)
    found.lake_rate=len(lakes)/len(land)
    kinds=Counter(terrain[c] for c in land)
    found.terrain={k:n/len(land) for k,n in kinds.items()}
    found.impassable={k:sum(1 for c in land if terrain[c]==k and c in impassable)/n for k,n in kinds.items()}
    near={c:set() for c in impassable}
    for x,y in pairs:
        if x in near and y in near: near[x].add(y);near[y].add(x)
    rows=[line.split(';') for line in (GAME/'map_data/adjacencies.csv').read_text(encoding='utf-8-sig').splitlines()]
    found.crossing=float(np.quantile([np.hypot(float(r[4])-float(r[6]),float(r[5])-float(r[7])) for r in rows if len(r)>7 and r[2]=='sea' and '-1' not in (r[4],r[6])],.9))
    found.canals=sorted(key for key,block in read(GAME,'common/strait_definitions') if scalar(block,'type')=='artificial')
    found.canal=max(np.hypot(float(r[4])-float(r[6]),float(r[5])-float(r[7])) for r in rows if len(r)>7 and r[2] in found.canals)
    found.masses=[]
    while near:
        reached=hops(near,near,[next(iter(near))])
        found.masses.append(len(reached))
        for c in reached: del near[c]
    regions=sum(1 for path in (GAME/'common/strategic_regions').glob('*.txt') if path.name!='water_strategic_regions.txt'
                for _ in blocks(clean(path)))
    found.states_per_region=len(counts)/regions
    found.kinds=sorted(kinds)
    coast={c for pair in pairs for c,o in (pair,pair[::-1]) if c in state_of and o in touching}
    shapes={key:character(found.kinds,[terrain[c] for c in provinces],any(c in coast for c in provinces)) for key,provinces in places.items()}
    found.shapes=shapes
    found.land_keys=sorted(shapes)
    names=list(places)
    near={key:sorted({names[s] for c in provinces for s in touching[c]}) for key,provinces in waters.items()}
    found.sea_keys=sorted(key for key in near if near[key])
    found.sea_shapes=np.array([np.mean([shapes[s] for s in near[key]],0) for key in found.sea_keys])
    strategic={key:set(re.findall(r'\bSTATE_\w+',block)) for key,block in read(GAME,'common/strategic_regions')}
    found.regions={key:sorted(members&shapes.keys()) for key,members in strategic.items() if members&shapes.keys()}
    found.region_of={s:key for key,members in found.regions.items() for s in members}
    found.geographic={}
    for key,block in read(GAME,'common/geographic_regions'):
        listed=re.search(r'\bstate_regions\s*=\s*\{([^}]*)\}',block)
        found.geographic[key]=(scalar(block,'short_key'),set(re.findall(r'\bSTATE_\w+',listed[1]) if listed else ())|{s for r in re.findall(r'\bsr:(\w+)',block) for s in strategic[r]})
    return found


@timed_often
def character(kinds,terrains,coastal):
    counted=Counter(terrains)
    return [counted[k]/len(terrains) for k in kinds]+[float(coastal)]


@timed
def geographic(world,found):
    seas=set(world.seas)
    shapes=np.array([character(found.kinds,[world.terrain[p] for p in members],any(world.neighbours[p]&seas for p in members)) for members in world.states])
    nearest=lambda shape,keys:keys[int(((np.array([found.shapes[k] for k in keys])-shape)**2).sum(1).argmin())]
    land={}
    for members in world.regions:
        votes=Counter(found.region_of[nearest(shapes[s],found.land_keys)] for s in members)
        region=max(sorted(votes),key=lambda key:votes[key])
        land.update({s:nearest(shapes[s],found.regions[region]) for s in members})
    near={p:sorted({int(world.state_of[o]) for o in world.neighbours[p] if o<world.land_count}) for p in world.seas}
    water={p:found.sea_keys[int(np.argmin(((found.sea_shapes-shapes[near[p]].mean(0))**2).sum(1)))] for p in world.seas if near[p]}
    coastal=sorted(water)
    for p in world.seas:
        if not near[p]:
            reached=hops(seas,world.neighbours,[p])
            water[p]=water[min((q for q in coastal if q in reached),key=lambda q:(reached[q],q))]
    return {key:(short,[s for s in range(len(world.states)) if land[s] in members],[i for i,p in enumerate(world.seas) if water[p] in members])
            for key,(short,members) in found.geographic.items()}


@timed_often
def smooth(rng,shape,sigma):
    factor=max(1,int(sigma/3))
    coarse=(-(-shape[0]//factor),-(-shape[1]//factor))
    field=ndimage.gaussian_filter(rng.standard_normal(coarse),sigma/factor,mode='wrap')
    field=ndimage.zoom(field,factor,order=1)[:shape[0],:shape[1]]
    return (field-field.mean())/field.std()


@timed
def canvas(area):
    width=max(SMALLEST,int(np.ceil(np.sqrt(2*area)/32))*32)
    return int(np.ceil(width/2/32))*32,width


@timed
def cells(rng,shape,step):
    ys,xs=np.mgrid[step/2:shape[0]:step,step/2:shape[1]:step]
    points=np.stack([ys.ravel(),xs.ravel()],1)+rng.uniform(-.4*step,.4*step,(ys.size,2))
    yy,xx=np.indices(shape)
    warp=step*.45
    coords=np.stack([(yy+warp*smooth(rng,shape,step)).ravel(),(xx+warp*smooth(rng,shape,step)).ravel()],1)
    _,found=cKDTree(points).query(coords,workers=1)
    found=found.reshape(shape).astype(np.int32)
    stray=np.zeros(shape,bool)
    for index,box in enumerate(ndimage.find_objects(found+1)):
        if box is None: continue
        parts,count=ndimage.label(found[box]==index)
        if count>1:
            keep=np.argmax(np.bincount(parts.ravel())[1:])+1
            stray[box]|=(parts>0)&(parts!=keep)
    if stray.any():
        _,(iy,ix)=ndimage.distance_transform_edt(stray,return_indices=True)
        found=found[iy,ix]
    _,dense=np.unique(found,return_inverse=True)
    return dense.reshape(shape).astype(np.int32)


@timed
def adjacency(grid,diagonal=False):
    pairs=[]
    count=int(grid.max())+1
    sides=[(grid[:,:-1],grid[:,1:]),(grid[:-1],grid[1:])]+([(grid[:-1,:-1],grid[1:,1:]),(grid[:-1,1:],grid[1:,:-1])] if diagonal else [])
    for first,second in sides:
        differ=first!=second
        first,second=first[differ],second[differ]
        pairs.append(np.minimum(first,second).astype(np.int64)*count+np.maximum(first,second))
    edges=np.unique(np.concatenate(pairs))
    neighbours=[set() for _ in range(count)]
    for edge in edges.tolist():
        a,b=divmod(edge,count)
        neighbours[a].add(b)
        neighbours[b].add(a)
    return neighbours


@timed
def centres(grid):
    count=grid.max()+1
    yy,xx=np.indices(grid.shape)
    size=np.bincount(grid.ravel(),minlength=count)
    return np.stack([np.bincount(grid.ravel(),yy.ravel(),count)/size,np.bincount(grid.ravel(),xx.ravel(),count)/size],1),size


@timed_often
def hops(nodes,neighbours,sources):
    distance=dict.fromkeys(sources,0)
    queue=deque(sources)
    while queue:
        node=queue.popleft()
        for other in neighbours[node]:
            if other in nodes and other not in distance:
                distance[other]=distance[node]+1
                queue.append(other)
    return distance


@timed
def spread(rng,nodes,neighbours,count,first):
    ordered=sorted(nodes)
    seeds=list(first) or [ordered[rng.integers(len(ordered))]]
    nearest=hops(nodes,neighbours,seeds)
    if len(nearest)<len(nodes): raise RuntimeError(evidence(reached=len(nearest),nodes=len(nodes)))
    while len(seeds)<count:
        seed=max(ordered,key=lambda n:(nearest[n],-n))
        seeds.append(seed)
        nearest[seed]=0
        queue=deque([seed])
        while queue:
            node=queue.popleft()
            distance=nearest[node]+1
            for other in neighbours[node]:
                if other in nodes and distance<nearest[other]:
                    nearest[other]=distance
                    queue.append(other)
    return seeds


@timed
def partition(rng,nodes,neighbours,targets,first=()):
    nodes=set(nodes)
    seeds=spread(rng,nodes,neighbours,len(targets),first)
    owner={seed:group for group,seed in enumerate(seeds)}
    members=[{seed} for seed in seeds]
    frontier=[{n for n in neighbours[seed] if n in nodes} for seed in seeds]
    while len(owner)<len(nodes):
        for group in sorted(range(len(targets)),key=lambda g:len(members[g])/targets[g]):
            frontier[group]={n for n in frontier[group] if n not in owner}
            if frontier[group]: break
        options=sorted(frontier[group])
        best=max(len(neighbours[n]&members[group]) for n in options)
        node=rng.choice([n for n in options if len(neighbours[n]&members[group])==best])
        owner[node]=group
        members[group].add(node)
        frontier[group]|={n for n in neighbours[node] if n in nodes and n not in owner}
    return [sorted(group) for group in members]


@timed
def split(total,shares):
    raw=np.asarray(shares,float)/sum(shares)*total
    out=np.floor(raw).astype(int)
    out[np.argsort(raw-out)[::-1][:total-out.sum()]]+=1
    return out


@timed
def landmasses(rng,grid,neighbours,touching,centre,total,count,spacing,compact):
    height,width=grid.shape
    border=set(np.unique(np.concatenate([grid[0],grid[-1],grid[:,0],grid[:,-1]])).tolist())
    field=smooth(rng,grid.shape,width/10)
    score=field[centre[:,0].astype(int),centre[:,1].astype(int)]
    margin={o for n in border for o in neighbours[n]}|border
    margin|={o for n in margin for o in neighbours[n]}
    inner=[n for n in range(len(neighbours)) if n not in margin and all(o not in margin for o in neighbours[n])]
    picked=rng.choice(inner,count,replace=False)
    edge=lambda n:min(centre[n][0],centre[n][1],height-centre[n][0],width-centre[n][1])
    starts=[max(inner,key=edge) if count==1 else int(picked[0])]
    while len(starts)<count:
        starts.append(max(inner,key=lambda n:min(min(np.sqrt(((centre[n]-centre[s])**2).sum()) for s in starts),2*edge(n))))
    quotas=split(total,rng.dirichlet(np.full(count,3.)))
    mass={}
    members=[set() for _ in range(count)]
    heaps=[[(0.,s)] for s in starts]
    active=set(range(count))
    while active:
        k=min(active,key=lambda m:len(members[m])/max(quotas[m],1))
        if len(members[k])>=quotas[k] or not heaps[k]:
            active.discard(k)
            if not heaps[k] and len(members[k])<quotas[k]:
                spare=quotas[k]-len(members[k])
                quotas[k]=len(members[k])
                others=sorted(active,key=lambda m:len(members[m]))
                if others: quotas[others[0]]+=spare
            continue
        _,node=heapq.heappop(heaps[k])
        if node in mass or node in margin or any(mass.get(o,k)!=k for o in touching[node]): continue
        mass[node]=k
        members[k].add(node)
        for other in neighbours[node]:
            if other not in mass:
                reach=np.sqrt(((centre[other]-centre[starts[k]])**2).sum()/max(quotas[k],1))/spacing
                heapq.heappush(heaps[k],(-score[other]+rng.normal(0,.3)+compact*reach,other))
    outside=set(border)
    queue=deque(border)
    while queue:
        node=queue.popleft()
        for other in neighbours[node]:
            if other not in mass and other not in outside:
                outside.add(other)
                queue.append(other)
    holes={n for n in range(len(neighbours)) if n not in mass and n not in outside}
    pockets=[]
    while holes:
        component={min(holes)}
        queue=deque(component)
        while queue:
            for other in neighbours[queue.popleft()]:
                if other in holes and other not in component:
                    component.add(other)
                    queue.append(other)
        holes-=component
        around={mass[o] for n in component for o in touching[n] if o in mass}
        if len(around)==1:
            mass.update((n,next(iter(around))) for n in component)
        else:
            pockets+=sorted(component)
    return mass,pockets


@timed
def lakes(rng,mass,neighbours,count):
    chosen=[]
    candidates=[n for n,k in mass.items() if all(mass.get(o)==k for o in neighbours[n])]
    for node in rng.permutation(candidates):
        if len(chosen)>=count: break
        node=int(node)
        if any(o in chosen for o in neighbours[node]): continue
        rest={n for n,k in mass.items() if k==mass[node] and n!=node and n not in chosen}
        if len(hops(rest,neighbours,[next(iter(rest))]))==len(rest): chosen.append(node)
    return chosen


@timed
def shares(profile,climate,relief):
    target=dict(profile.terrain)
    for kind in COLD: target[kind]*=2*(1-climate)
    for kind in HOT: target[kind]*=2*climate
    for kind in RUGGED: target[kind]*=relief
    total=sum(target.values())
    return {k:v/total for k,v in target.items()}


@timed
def terrain(rng,grid,centre,land,target):
    count=len(land)
    at=lambda field:field[centre[land,0].astype(int),centre[land,1].astype(int)]
    height=at(smooth(rng,grid.shape,grid.shape[1]/32))+.5*at(smooth(rng,grid.shape,grid.shape[1]/90))
    moisture=at(smooth(rng,grid.shape,grid.shape[1]/24))+.5*at(smooth(rng,grid.shape,grid.shape[1]/70))
    warmth=rng.choice([-1,1])*(centre[land,0]/grid.shape[0]-.5)*2+.6*at(smooth(rng,grid.shape,grid.shape[1]/10))
    kinds=np.array(['plains']*count,dtype=object)
    free=np.ones(count,bool)

    @timed_often
    def take(kind,score):
        n=int(round(target.get(kind,0)*count))
        order=[i for i in np.argsort(-score) if free[i]][:n]
        kinds[order]=kind
        free[order]=False
    take('mountain',height)
    take('hills',height)
    take('snow',-warmth-.3*height)
    take('tundra',-warmth)
    take('desert',warmth-moisture)
    take('jungle',warmth+moisture)
    take('savanna',warmth)
    take('wetland',moisture-.5*height)
    take('forest',moisture)
    return list(kinds),height


@timed
def blocked(rng,world,kinds,elevation,found):
    owner=world.state_of.tolist()
    seas=set(world.seas)
    open_=[set(members) for members in world.states]
    shore=[{p for p in members if world.neighbours[p]&seas} for members in world.states]
    links=Counter(frozenset((owner[p],owner[o])) for p in range(len(kinds)) for o in world.neighbours[p] if p<o<len(kinds) and owner[o]!=owner[p])
    kind=np.array(kinds)
    quota=Counter({k:int(round(found.impassable[k]*n)) for k,n in Counter(kinds).items()})
    free=np.array([found.impassable[k] if quota[k] else 0 for k in kinds])
    total=sum(quota.values())
    sizes=np.array(found.masses,float)
    out=set()
    while len(out)<total and free.any():
        size=min(total-len(out),int(rng.choice(sizes,p=sizes/sizes.sum())))
        frontier=[(0.,0.,int(rng.choice(len(kinds),p=free/free.sum())))]
        grown=0
        while frontier and grown<size:
            *_,p=heapq.heappop(frontier)
            if not free[p]: continue
            free[p]=0
            s=owner[p]
            rest=open_[s]-{p}
            if not rest or shore[s] and not shore[s]&rest or len(hops(rest,world.neighbours,[min(rest)]))<len(rest): continue
            lost=Counter(owner[o] for o in world.neighbours[p] if o<len(kinds) and owner[o]!=s and o in open_[owner[o]])
            if any(links[frozenset((s,t))]<=n for t,n in lost.items()): continue
            for t,n in lost.items(): links[frozenset((s,t))]-=n
            open_[s]=rest
            out.add(p)
            grown+=1
            quota[kinds[p]]-=1
            if not quota[kinds[p]]: free[kind==kinds[p]]=0
            for o in world.neighbours[p]:
                if o<len(kinds) and free[o]: heapq.heappush(frontier,(-free[o]*(1+len(world.neighbours[o]&out)),-elevation[o],o))
    return out


@timed
def crossings(world,limit):
    mass=np.array(world.mass+[-1]*(world.count-world.land_count))[world.grid]
    out=[]
    for k in sorted(set(world.mass)):
        distance,(rows,cols)=ndimage.distance_transform_edt(mass!=k,return_indices=True)
        for o in sorted(set(world.mass)-set(range(k+1))):
            at=np.unravel_index(np.argmin(np.where(mass==o,distance,np.inf)),mass.shape)
            if distance[at]<=limit:
                near=(rows[at],cols[at])
                out.append((int(world.grid[near]),int(world.grid[at]),near,at))
    return out


@timed
def canals(world,found):
    seas=set(world.seas)
    out=[]
    for s,members in enumerate(world.states):
        open_={p for p in members if p not in world.impassable}
        coast={}
        for p in sorted(open_):
            for x in world.neighbours[p]&seas: coast.setdefault(x,[]).append(p)
        for x in sorted(coast):
            for y in sorted(coast):
                if x<y and y not in world.neighbours[x]:
                    if coast[x]==coast[y] and len(coast[x])==1: continue
                    d,a,b=min((float(np.hypot(*(world.centre[a]-world.centre[b]))),a,b) for a in coast[x] for b in coast[y] if a!=b)
                    if d<=found.canal: out.append((d,s,a,b,x,y))
    picked={}
    for _,s,a,b,x,y in sorted(out):
        if len(picked)>=len(found.canals): break
        if any(s==t or (x,y)==(u,v) for t,_,_,u,v in picked.values()): continue
        picked[found.canals[len(picked)]]=(s,a,b,x,y)
    return picked


@timed
def regions(rng,world,size):
    left=set(range(len(world.states)))
    parts=[]
    while left:
        part=sorted(hops(left,world.joined,[min(left)]))
        left-=set(part)
        parts.append(part)
    middle=[world.centre[group].mean(0) for group in world.states]
    out=[]
    for part in sorted(parts,key=lambda part:(-len(part),part[0])):
        count=int(round(len(part)/size))
        if count or not out:
            out+=partition(rng,part,world.joined,[1]*max(1,count))
        else:
            _,index=min((float(np.hypot(*(middle[s]-middle[o]))),index) for index,group in enumerate(out) for o in group for s in part)
            out[index]=sorted(out[index]+part)
    return out


@timed
def heights(rng,grid,land_count,kinds,impassable):
    land=grid<land_count
    lift=np.array([LIFT.get(kind,0)+(3000 if p in impassable else 0) for p,kind in enumerate(kinds)],float)[grid]
    inland=ndimage.distance_transform_edt(land)
    offshore=ndimage.distance_transform_edt(~land)
    rough=(smooth(rng,grid.shape,5)+.3*smooth(rng,grid.shape,2))*(150+.25*lift)
    raised=ndimage.gaussian_filter(np.minimum(inland*120,lift),3)+rough
    out=np.where(land,WATER+150+np.maximum(raised,0),WATER-300-np.minimum(offshore*80,4000))
    big=ndimage.zoom(out,2,order=1)
    coast=np.repeat(np.repeat(land,2,0),2,1)
    big=np.where(coast,np.maximum(big,WATER+150),np.minimum(big,WATER-300))
    return np.clip(big,0,65535).astype(np.uint16)


@timed
def colors(rng,count):
    picked=set()
    while len(picked)<count:
        picked.update(int(c) for c in rng.integers(1,0xFFFFFF,count-len(picked)))
    return np.array(sorted(picked)[:count])[rng.permutation(count)]


@timed
def generate(rng,found,knobs):
    world=SimpleNamespace()
    counts=np.maximum(1,np.round(np.exp(rng.normal(found.count_mu,found.count_sd,knobs['states'])))).astype(int)
    lake_count=int(rng.binomial(counts.sum(),found.lake_rate))
    land_cells=int(counts.sum())+lake_count
    world.shape=canvas(land_cells*found.land_area*(1+found.sea_ratio))
    fine=cells(rng,world.shape,np.sqrt(found.land_area))
    fine_neighbours=adjacency(fine)
    fine_centre,_=centres(fine)
    mass,pockets=landmasses(rng,fine,fine_neighbours,adjacency(fine,True),fine_centre,land_cells,knobs["landmasses"],np.sqrt(found.land_area),COMPACT)
    inland=lakes(rng,mass,fine_neighbours,lake_count)
    for node in inland: del mass[node]
    lake_cells=list(inland)+pockets
    sea=[n for n in range(len(fine_neighbours)) if n not in mass and n not in lake_cells]
    zones=partition(rng,sea,fine_neighbours,[1]*max(1,int(round(np.bincount(fine.ravel(),minlength=len(fine_neighbours))[sea].sum()/np.median(found.coastal_seas)))))
    land=sorted(mass)
    mapping=np.empty(len(fine_neighbours),np.int32)
    mapping[land]=np.arange(len(land))
    mapping[lake_cells]=len(land)+np.arange(len(lake_cells))
    for index,group in enumerate(zones): mapping[group]=len(land)+len(lake_cells)+index
    world.grid=mapping[fine]
    world.land_count=len(land)
    world.lakes=list(range(len(land),len(land)+len(lake_cells)))
    world.seas=list(range(len(land)+len(lake_cells),len(land)+len(lake_cells)+len(zones)))
    world.neighbours=adjacency(world.grid)
    world.centre,world.area=centres(world.grid)
    world.inside={p:inside(world.grid==p) for p in world.seas}
    world.count=len(world.neighbours)
    world.colors=colors(rng,world.count)
    world.mass=[mass[n] for n in land]
    target=shares(found,knobs['climate'],knobs['relief'])
    kinds,elevation=terrain(rng,world.grid,world.centre,np.arange(world.land_count),target)
    world.terrain=kinds+['lakes']*len(lake_cells)+['ocean']*len(zones)
    world.states=states(rng,world,counts)
    world.state_of=np.full(world.count,-1)
    for index,members in enumerate(world.states): world.state_of[members]=index
    world.impassable=blocked(rng.spawn(1)[0],world,kinds,elevation,found)
    world.heights=heights(rng,world.grid,world.land_count,world.terrain,world.impassable)
    world.state_neighbours=[set() for _ in world.states]
    seas=set(world.seas)
    shore={}
    for province in range(world.land_count):
        for other in world.neighbours[province]:
            if other<world.land_count and world.state_of[other]!=world.state_of[province]:
                world.state_neighbours[world.state_of[province]].add(int(world.state_of[other]))
            if other in seas: shore.setdefault(other,set()).add(int(world.state_of[province]))
    world.crossings=crossings(world,found.crossing)
    world.canals=canals(world,found)
    world.joined=[set(n) for n in world.state_neighbours]
    for a,b,*_ in world.crossings:
        world.joined[world.state_of[a]].add(int(world.state_of[b]))
        world.joined[world.state_of[b]].add(int(world.state_of[a]))
    world.reachable=[set(n) for n in world.joined]
    for touching in shore.values():
        for s in touching: world.reachable[s]|=touching-{s}
    bridge(world,{s for touching in shore.values() for s in touching})
    touched=Counter({p:len(touching) for p,touching in shore.items()})
    rank={p:float(np.mean([touched[o]>touched[p] for o in world.seas])) for p in sorted(shore)}
    world.market=min(rank,key=lambda p:abs(rank[p]-found.market_rank))
    world.regions=regions(rng,world,found.states_per_region)
    world.geographic=geographic(world,found)
    world.labels,world.tints=label(rng.spawn(1)[0],world)
    return world


@timed_often
def inside(mask):
    rows,cols=np.nonzero(mask)
    top,left=rows.min()-1,cols.min()-1
    crop=np.zeros((rows.max()-top+2,cols.max()-left+2),bool)
    crop[rows-top,cols-left]=True
    depth=ndimage.distance_transform_edt(crop)
    r,c=np.unravel_index(np.argmax(depth),depth.shape)
    return np.array([r+top,c+left],float)


@timed
def bridge(world,coastal):
    middle=[world.centre[group].mean(0) for group in world.states]
    mass=[world.mass[group[0]] for group in world.states]
    joined={k:k for k in set(mass)}
    find=lambda k:k if joined[k]==k else find(joined[k])
    pairs=sorted((float(((middle[a]-middle[b])**2).sum()),a,b) for a in coastal for b in coastal if mass[a]<mass[b])
    for _,a,b in pairs:
        if find(mass[a])!=find(mass[b]):
            joined[find(mass[a])]=find(mass[b])
            world.reachable[a].add(b)
            world.reachable[b].add(a)


@timed
def states(rng,world,counts):
    masses=sorted(set(world.mass))
    room={k:sum(1 for m in world.mass if m==k) for k in masses}
    placed={k:[] for k in masses}
    ordered=sorted(counts,reverse=True)
    for k,n in zip(sorted(masses,key=lambda m:-room[m]),ordered):
        placed[k].append(int(n))
    for n in ordered[len(masses):]:
        k=max(masses,key=lambda m:room[m]-sum(placed[m]))
        placed[k].append(int(n))
    out=[]
    for k in masses:
        members=[p for p in range(world.land_count) if world.mass[p]==k]
        out+=partition(rng,members,world.neighbours,list(split(len(members)-len(placed[k]),placed[k])+1))
    return out
