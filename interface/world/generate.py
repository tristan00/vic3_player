from pathlib import Path
import math
import random
import re
import shutil
import struct

from PIL import Image
import numpy as np
from scipy import ndimage
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from ..common import DEFAULT_DATA, DEFAULT_GAME, timed, write_json, write_script, timed_often
from ..script import blocks, body, clean, read, scalar
from .vanilla import rasters, textures, vanilla
from .nations import word
from .project import nations
from .source import assignments, select_regions
from .audit import audit

MAP={'states':(20,50),'country_share':(1/8,1/5),'tech':.5,'ideology_uniformity':0,'primary_culture_share':None,'copies':0,
     'tech_variation':1,'country_economy':1,'local_economy':1,'source_regions':1}
PROVINCE_PIXELS=2000
SEA_ID=3000
NAVAL=83886
SECONDARY_SHARE=.133
HUBS=['port','city','farm','mine','wood']
HUB_INDEX={'city':0,'farm':1,'mine':2,'port':3,'wood':4}
CROSS=np.array([[0,1,0],[1,1,1],[0,1,0]])
LAND,OCEAN,LAKE=1,2,3
PLAIN={'map_data/province_terrains.txt','map_data/default.map'}


@timed_often
def _noise(nrng,shape,sigmas):
    total=np.zeros(shape)
    for sigma in sigmas:
        factor=max(1,int(sigma//4))
        coarse=ndimage.gaussian_filter(nrng.standard_normal((shape[0]//factor+2,shape[1]//factor+2)),sigma/factor)/factor
        total+=ndimage.zoom(coarse,factor,order=1)[:shape[0],:shape[1]]*sigma
    return total/total.std()


@timed_often
def _morton(x,y):
    return sum((x>>bit&1)<<2*bit|(y>>bit&1)<<2*bit+1 for bit in range(16))


@timed_often
def _spline_safe(cells):
    return all(_morton(x,y)<cells*cells for x in range(cells) for y in range((cells+1)//2))


@timed_often
def _size(rng,provinces):
    fraction=rng.uniform(.35,.55)
    cells=max(4,math.ceil(math.sqrt(provinces*PROVINCE_PIXELS/fraction/2)/64))
    while not _spline_safe(cells):
        cells+=1
    return 128*cells,64*cells,fraction


@timed
def _domains(nrng,width,height,fraction,landmasses):
    field=_noise(nrng,(height,width),[height/64,height/21,height/8,height/3.2])
    yy,xx=np.mgrid[0:height,0:width]
    edge=np.minimum.reduce([xx,yy,width-1-xx,height-1-yy])/(height*.15)
    field-=6*np.clip(1-edge,0,1)**2
    land=field>np.quantile(field,1-fraction)
    land[[0,-1],:]=False
    land[:,[0,-1]]=False
    labels,_=ndimage.label(land,CROSS)
    sizes=np.bincount(labels.ravel())
    sizes[0]=0
    keep=[i for i in np.argsort(sizes)[::-1][:landmasses] if sizes[i]>=PROVINCE_PIXELS]
    land=np.isin(labels,keep)
    water,_=ndimage.label(~land,CROSS)
    ocean=water==water[0,0]
    lakes,_=ndimage.label(~land&~ocean,CROSS)
    small=np.bincount(lakes.ravel())<PROVINCE_PIXELS
    small[0]=False
    land|=small[lakes]
    domain=np.where(land,LAND,np.where(ocean,OCEAN,LAKE)).astype(np.int8)
    return domain


@timed_often
def _seeds(points,count,nrng,density):
    seeds=points[nrng.choice(len(points),count,replace=False,p=density/density.sum())].astype(float)
    for _ in range(3):
        nearest=cKDTree(seeds).query(points)[1]
        weight=np.bincount(nearest,density,minlength=count)
        moved=np.stack([np.bincount(nearest,points[:,i]*density,count) for i in range(2)],1)
        seeds[weight>0]=moved[weight>0]/weight[weight>0,None]
    return seeds


@timed_often
def _split(counts,sizes,every=True):
    order=np.argsort(sizes)[::-1]
    result=np.zeros(len(sizes),dtype=int)
    if every and counts<=len(sizes):
        result[order[:counts]]=1
        return result
    floor=len(sizes) if every else 0
    share=np.asarray(sizes,dtype=float)/sum(sizes)*(counts-floor)
    result=int(every)+np.floor(share).astype(int)
    for i in np.argsort(share-np.floor(share))[::-1][:counts-result.sum()]:
        result[i]+=1
    return result


@timed
def _cells(domain,land_count,sea_count,nrng):
    height,width=domain.shape
    jitter=[7*_noise(nrng,domain.shape,[5,12]) for _ in range(2)]
    cells=np.zeros(domain.shape,dtype=np.int32)
    lands,count=ndimage.label(domain==LAND,CROSS)
    sizes=np.bincount(lands.ravel())[1:]
    ocean=domain==OCEAN
    lakes,lake_count=ndimage.label(domain==LAKE,CROSS)
    groups=[(lands==i+1,n) for i,n in enumerate(_split(land_count,sizes))]
    groups.append((ocean,sea_count))
    shore=ndimage.distance_transform_edt(domain!=LAND)
    groups+=[(lakes==i+1,1) for i in range(lake_count)]
    offset=0
    for mask,n in groups:
        yy,xx=np.nonzero(mask)
        points=np.stack([xx,yy],1)
        seeds=_seeds(points,n,nrng,1/(1+shore[yy,xx]/math.sqrt(len(yy)/n))**2 if mask is ocean else np.ones(len(yy)))
        moved=points+np.stack([jitter[0][yy,xx],jitter[1][yy,xx]],1)
        cells[yy,xx]=cKDTree(seeds).query(moved)[1]+offset+1
        offset+=n
    for _ in range(8):
        _contiguous(cells,domain)
        a,b,c,d=cells[:-1,:-1],cells[:-1,1:],cells[1:,:-1],cells[1:,1:]
        jy,jx=np.nonzero((a!=b)&(a!=c)&(a!=d)&(b!=c)&(b!=d)&(c!=d))
        if not len(jy):
            break
        cells[jy+1,jx+1]=cells[jy,jx+1]
        domain[jy+1,jx+1]=domain[jy,jx+1]
    else:
        raise RuntimeError('Four-way province junctions could not be removed')
    ids,cells=np.unique(cells,return_inverse=True)
    cells=cells.reshape(domain.shape).astype(np.int32)+1
    kinds=np.zeros(len(ids)+1,dtype=np.int8)
    kinds[cells.ravel()]=domain.ravel()
    return cells,kinds


_SHIFTS=((-1,0),(1,0),(0,-1),(0,1))


@timed_often
def _contiguous(cells,domain):
    while True:
        stray=np.zeros(cells.shape,dtype=bool)
        for index,box in enumerate(ndimage.find_objects(cells),1):
            if box is None:
                continue
            labels,n=ndimage.label(cells[box]==index,CROSS)
            if n>1:
                sizes=np.bincount(labels.ravel())
                sizes[0]=0
                stray[box]|=(labels>0)&(labels!=sizes.argmax())
        if not stray.any():
            return
        cells[stray]=0
        ys,xs=np.nonzero(stray)
        while len(ys):
            for dy,dx in _SHIFTS:
                sy,sx=ys+dy,xs+dx
                inside=(sy>=0)&(sy<cells.shape[0])&(sx>=0)&(sx<cells.shape[1])
                ty,tx,sy,sx=ys[inside],xs[inside],sy[inside],sx[inside]
                fill=(cells[sy,sx]>0)&(domain[ty,tx]==domain[sy,sx])
                cells[ty[fill],tx[fill]]=cells[sy[fill],sx[fill]]
                left=cells[ys,xs]==0
                ys,xs=ys[left],xs[left]


@timed_often
def _graph(cells):
    pairs=[]
    for first,second in ((cells[:,:-1],cells[:,1:]),(cells[:-1],cells[1:])):
        unequal=first!=second
        pairs.append(np.stack([np.minimum(first,second)[unequal],np.maximum(first,second)[unequal]],1))
    edges,counts=np.unique(np.concatenate(pairs),axis=0,return_counts=True)
    return {(int(a),int(b)):int(n) for (a,b),n in zip(edges,counts)}


@timed_often
def _components(nodes,neighbours):
    seen={};components=[]
    for start in nodes:
        if start in seen:
            continue
        stack=[start];seen[start]=len(components);members=[]
        while stack:
            node=stack.pop();members.append(node)
            for other in neighbours[node]:
                if other not in seen:
                    seen[other]=len(components);stack.append(other)
        components.append(members)
    return components


@timed_often
def _grow(nodes,neighbours,centers,count,weights,rng,every=True,candidates=None):
    components=sorted(_components(nodes,neighbours),key=len,reverse=True)
    seeds=[]
    pools=components if candidates is None else [[m for m in c if m in candidates] for c in components]
    pools=[p for p in pools if p]
    for members,n in zip(pools,_split(count,[len(c) for c in pools],every)):
        if n>len(members):
            raise ValueError('Not enough compatible provinces to seed the requested states')
        chosen=[rng.choice(members)] if n else []
        while len(chosen)<n:
            chosen.append(max(members,key=lambda m:min(np.hypot(*(centers[m]-centers[c])) for c in chosen)))
        seeds+=chosen
    owner={s:i for i,s in enumerate(seeds)}
    sizes=[1]*len(seeds)
    frontier=[set(neighbours[s]) for s in seeds]
    while True:
        open_=[i for i in range(len(seeds)) if frontier[i]-owner.keys()]
        if not open_:
            break
        under=[i for i in open_ if sizes[i]<weights[i]] or open_
        i=min(under,key=lambda i:sizes[i]/weights[i])
        node=min(frontier[i]-owner.keys(),key=lambda n:np.hypot(*(centers[n]-centers[seeds[i]])))
        owner[node]=i;sizes[i]+=1;frontier[i]|=set(neighbours[node])
    for node in nodes:
        if node not in owner:
            owner[node]=min(range(len(seeds)),key=lambda i:np.hypot(*(centers[node]-centers[seeds[i]])))
    return owner,seeds


@timed
def _straits(cells,kinds,neighbours,width,count):
    land=[p for p in range(1,len(kinds)) if kinds[p]==LAND]
    masses=_components(land,{p:{q for q in neighbours[p] if kinds[q]==LAND} for p in land})
    reach=max(16,width//24)
    shore=ndimage.binary_dilation(kinds[cells]!=LAND,CROSS)&(kinds[cells]==LAND)
    coasts=[]
    for members in masses:
        yy,xx=np.nonzero(shore&np.isin(cells,members))
        coasts.append((np.stack([xx,yy],1),cKDTree(np.stack([xx,yy],1))))
    sites=[]
    for i in range(len(masses)):
        for j in range(i+1,len(masses)):
            distance,index=coasts[j][1].query(coasts[i][0],distance_upper_bound=reach)
            chosen=[]
            for k in np.argsort(distance):
                if not np.isfinite(distance[k]):
                    break
                start=coasts[i][0][k]
                if all(np.hypot(*(start-other))>2*reach for other in chosen):
                    chosen.append(start);sites.append((distance[k],start,coasts[j][0][index[k]]))
    straits=[];pairs=set()
    for distance,start,stop in sorted(sites,key=lambda site:site[0]):
        pair=(int(cells[start[1],start[0]]),int(cells[stop[1],stop[0]]))
        if len(straits)<count and pair not in pairs:
            pairs.add(pair)
            middle=((start+stop)/2).astype(int)
            radius=int(distance)+3
            window=cells[max(0,middle[1]-radius):middle[1]+radius+1,max(0,middle[0]-radius):middle[0]+radius+1]
            straits.append({'from':pair[0],'to':pair[1],'start':start.tolist(),'stop':stop.tolist(),'seas':[int(s) for s in np.unique(window) if kinds[s]==OCEAN]})
    return straits


@timed
def _heightmap(mod,heights):
    height,width=heights.shape
    hm=Image.fromarray(heights).resize((width*2,height*2),Image.Resampling.NEAREST)
    hm.save(mod/'map_data/heightmap.png')
    nx,ny=width*2//64,height*2//64
    padded=np.pad(np.asarray(hm),((0,1),(0,1)),mode='edge')
    packed=np.zeros((ny*65+5,nx*65),dtype=np.uint16)
    indirection=Image.new('RGBA',(nx,ny))
    for y in range(ny):
        for x in range(nx):
            packed[y*65+5:y*65+70,x*65:x*65+65]=padded[y*64:y*64+65,x*64:x*64+65]
            indirection.putpixel((x,y),(x,ny-1-y,1,0))
    Image.fromarray(packed).save(mod/'map_data/packed_heightmap.png')
    indirection.save(mod/'map_data/indirection_heightmap.png')
    offsets=' '.join(['{ 0 0 }']+[f'{{ 0 {ny*65} }}']*4)
    write_script(mod/'map_data/heightmap.heightmap',f'heightmap_file="map_data/packed_heightmap.png"\nindirection_file="map_data/indirection_heightmap.png"\n'
        f'original_heightmap_size={{ {width*2} {height*2} }}\ntile_size=65\nshould_wrap_x=no\nlevel_offsets={{ {offsets} }}\nmax_compress_level=4\nempty_tile_offset={{ 0 0 }}\n')


@timed
def _graphics(mod,game,land,geography):
    height,width=land.shape
    materials=re.findall(r'\bid\s*=\s*"([^"]+)"',(game/'gfx/map/terrain/materials.settings').read_text())
    for key in ['detail_index','detail_intensity']:
        (mod/'gfx/map/terrain').mkdir(parents=True,exist_ok=True)
        Image.fromarray(geography[key]).save(mod/f'gfx/map/terrain/{key}.tga')
    for folder in ['gfx/map/terrain','gfx/map/masks']:
        (mod/folder).mkdir(parents=True,exist_ok=True)
        for source in (game/folder).glob('mask_*.png'):
            material=source.stem.removeprefix('mask_')
            used=geography['detail_index'][:,:,0]==materials.index(material) if folder.endswith('terrain') and material in materials else np.zeros(land.shape,dtype=bool)
            Image.fromarray((used*255).astype(np.uint8)).save(mod/folder/source.name)
    mask=Image.fromarray((land*255).astype(np.uint8))
    (mod/'gfx/map/textures').mkdir(parents=True,exist_ok=True)
    images={}
    for name,ocean,ground in [('flatmap.dds',(87,133,151,255),(209,201,158,255)),
                              ('colormap.dds',(52,91,107,255),Image.fromarray(geography['colormap'])),
                              ('land_mask.dds',(0,0,0,0),(255,255,255,255))]:
        images[name]=Image.new('RGBA',(width,height),ocean)
        images[name].paste(ground,(0,0,width,height),mask)
        images[name].save(mod/'gfx/map/textures'/name)
    (mod/'gfx/interface/minimap').mkdir(parents=True,exist_ok=True)
    images['flatmap.dds'].resize((280,132)).save(mod/'gfx/interface/minimap/minimap.dds')
    Image.new('RGBA',(width,height),(0,0,0,0)).save(mod/'gfx/map/textures/flatmap_overlay.dds')
    for source in list((game/'gfx/map/textures').glob('maptextures*.settings'))+list((game/'dlc').glob('*/gfx/map/textures/maptextures*.settings')):
        text=source.read_text(encoding='utf-8-sig')
        for key,value in [('Flatmap','flatmap.dds'),('FlatmapOverlay','flatmap_overlay.dds')]:
            text=re.sub(f'"{key}"\\s*=\\s*"[^"]+"',f'"{key}" = "{value}"',text)
        write_script(mod/'gfx/map/textures'/source.name,text)
    (mod/'gfx/map/water').mkdir(parents=True,exist_ok=True)
    for name,color in [('watercolor_rgb_waterspec_a.dds',(52,91,107,255)),('flowmap.dds',(128,128,0,255)),('foam_map.dds',(0,0,0,0))]:
        Image.new('RGBA',(width,height),color).save(mod/'gfx/map/water'/name)
    rivers=Image.fromarray(np.where(land,255,254).astype(np.uint8)).convert('P')
    rivers.putpalette(Image.open(game/'map_data/rivers.png').getpalette())
    rivers.save(mod/'map_data/rivers.png')
    (mod/'map_data/nodes.dat').write_bytes(b'')
    (mod/'gfx/map/spline_network').mkdir(parents=True,exist_ok=True)
    write_script(mod/'gfx/map/spline_network/game_road_data.txt','state_region_road_strips = { }\n')


@timed_often
def _geographic_regions(game,states,regions):
    members={}
    for state,region in regions.items():
        members.setdefault(region,set()).add(state)
    lines=[]
    for key,value in read(game,'common/geographic_regions'):
        sources=set(re.findall(r'\bSTATE_\w+',value)).union(*(members[r] for r in re.findall(r'sr:(\w+)',value)))
        inside=' '.join(s['key'] for s in states if s['template'] in sources)
        lines.append(f'{key} = {{ short_key = "{scalar(value,"short_key")}" state_regions = {{ {inside} }} }}')
    return '\n'.join(lines)


TRIGGER_TAGS=r'is_subject_of|is_direct_subject_of|this'
ARGUMENTS={'value','placement','set_company_state_region','supply_hub','move_pop','target_state','state','hq_region','strategic_region'}
ARGUMENT_BLOCKS={'combat_unit','ship','set_variable','start_national_awakening','add_involvement'}
BARE_STATE=r'owns_entire_state_region|has_state_in_state_region|country_or_subject_owns_entire_state_region|owns_treaty_port_in'
@timed_often
def _enclosing(text,position):
    depth=0
    for i in range(position-1,-1,-1):
        if text[i]=='}':
            depth+=1
        elif text[i]=='{':
            if not depth:
                found=re.search(r'([\w:.@]+)\s*\??=\s*$',text[max(0,i-200):i])
                return found[1] if found else None
            depth-=1
    return None


SKIPPED=('common/history/','common/country_definitions/','common/strategic_regions/','common/geographic_regions/','common/strait_definitions/')


@timed_often
def _absent(text,tags):
    text=re.sub(r'\bexists\s*=\s*c:([A-Z0-9]{3})(?![\w.:])',lambda m:m[0] if m[1] in tags else 'always = no',text)
    text=re.sub(r'\bwas_formed_from\s*=\s*([A-Z0-9]{3})(?![\w.:])',lambda m:m[0] if m[1] in tags else 'always = no',text)
    return re.sub(r'\bc:([A-Z0-9]{3})\s*\??=\s*(?=[\w:.])([\w:.]+)',lambda m:m[0] if m[1] in tags else 'always = no',text)


@timed
def _rewrites(game,states,strategic,regions,tags,tag_map=None):
    tag_map={} if tag_map is None else tag_map
    state_map={}
    for state in states:
        state_map.setdefault(state['template'],set()).add(state['key'])
    region_map={}
    for region in strategic:
        for state in region['states']:
            region_map.setdefault(regions.get(state['template']),set()).add(region['key'])
    def swap(found,prefix):
        def replace(m):
            block=_enclosing(m.string,m.start())
            if m[1] in ARGUMENTS or block in ARGUMENT_BLOCKS or (block or '').startswith('create_'):
                return m[0]
            return 'OR = { '+' '.join(f'{m[1]} = {prefix}{k}' for k in sorted(found[m[2]]))+' }' if m[2] in found else 'always = no'
        return replace
    files={}
    for path in sorted(list((game/'common').rglob('*.txt'))+list((game/'events').rglob('*.txt'))):
        name=path.relative_to(game).as_posix()
        if name.startswith(SKIPPED):
            continue
        original=path.read_text(encoding='utf-8-sig',errors='replace')
        if not re.search(r's:STATE_|sr:region_|\bc:[A-Z0-9]{3}\b|preferred_headquarters|home_region',original):
            continue
        cleaned=text=clean(path)
        text=re.sub(r'\bc:([A-Z0-9]{3})\b',lambda m:'c:'+tag_map.get(m[1],m[1]),text)
        text=re.sub(r'\bhome_region\s*=\s*(?:s:)?STATE_\w+','home_region = random',text)
        text=re.sub(r'\bpreferred_headquarters\s*=\s*\{([^{}]*)\}',
                    lambda m:'preferred_headquarters = { '+' '.join(sorted({key for source in re.findall(r'\bSTATE_\w+',m[1]) for key in state_map.get(source,())}))+' }',text)
        for literal,pattern,replace in (('s:STATE_',r'([\w:.@]+)\s*=\s*s:(STATE_\w+)(?![\w.:])',swap(state_map,'s:')),
                                        ('sr:region_',r'([\w:.@]+)\s*=\s*sr:(region_\w+)(?![\w.:])',swap(region_map,'sr:')),
                                        ('STATE_',r'\b('+BARE_STATE+r')\s*=\s*(STATE_\w+)(?![\w.:])',swap(state_map,'')),
                                        ('c:',r'\b('+TRIGGER_TAGS+r')\s*=\s*c:([A-Z0-9]{3})(?![\w.:])',lambda m:m[0] if m[2] in tags else 'always = no')):
            if literal in text:
                text=re.sub(pattern,replace,text)
        text=_absent(text,tags)
        for literal,pattern,replace in (('s:STATE_',r'\bs:(STATE_\w+)\s*=\s*\{',lambda m:f's:{m[1]} ?= {{'),
                                        ('sr:region_',r'\bsr:(region_\w+)\s*=\s*\{',lambda m:f'sr:{m[1]} ?= {{'),
                                        ('c:',r'\bc:([A-Z0-9]{3})\s*=\s*\{',lambda m:m[0] if m[1] in tags else f'c:{m[1]} ?= {{')):
            if literal in text:
                text=re.sub(pattern,replace,text)
        if name.startswith('common/company_types/'):
            text=_company_scopes(text,state_map)
        if text!=cleaned:
            files[name]=text
    return files


@timed_often
def _company_scopes(text,states):
    for key,record in list(blocks(text)):
        inner=_company_scopes(body(record),states)
        if key.startswith('s:STATE_'):
            targets=sorted(states.get(key[2:],()))
            replacement='OR = { '+' '.join(f's:{target} = {{ {inner} }}' for target in targets)+' }' if targets else 'always = no'
        else:
            replacement=record[:record.index('{')+1]+inner+'}'
        text=text.replace(record,replacement,1)
    return text


@timed_often
def _detach(rng,ownership,capitals,neighbours,coastal,count):
    def connected(members):
        members=set(members);start=next(iter(members));seen={start};stack=[start]
        while stack:
            for other in neighbours[stack.pop()]&members-seen:
                seen.add(other);stack.append(other)
        return seen==members
    for _ in range(count):
        owned=lambda i:[s for s in ownership if ownership[s]==i]
        options=[]
        for state in coastal-set(capitals):
            rest=[s for s in owned(ownership[state]) if s!=state]
            if not rest or not connected(rest):
                continue
            nearby={ownership[n] for n in neighbours[state]}|{ownership[state]}
            options+=[(state,i,len(owned(i))) for i in set(ownership.values())-nearby if coastal&set(owned(i))]
        if not options:
            return
        state,receiver,_=rng.choices(options,weights=[w for *_,w in options])[0]
        ownership[state]=receiver


@timed_often
def _locator(cells,province,kind,coast,taken,rng):
    inside=cells==province
    py,px=np.nonzero(inside)
    ty,tx=np.nonzero(inside&coast) if coast is not None else (py,px)
    order=np.argsort((tx-px.mean())**2+(ty-py.mean())**2)
    free=[i for i in order if (tx[i],ty[i]) not in taken]
    best=free[0] if kind in ('city','port') else rng.choice(free)
    taken.add((tx[best],ty[best]))
    return int(tx[best]),int(ty[best])


@timed_often
def _path(crop,start,stop,box,factor,spacing):
    (y0,y1),(x0,x1)=box
    h,w=-(-crop.shape[0]//factor),-(-crop.shape[1]//factor)
    pooled=np.pad(crop,((0,h*factor-crop.shape[0]),(0,w*factor-crop.shape[1])),constant_values=np.inf).reshape(h,factor,w,factor).min((1,3))
    a=((start[1]-y0)//factor,(start[0]-x0)//factor)
    b=((stop[1]-y0)//factor,(stop[0]-x0)//factor)
    pooled[a]=pooled[b]=1
    index=np.arange(h*w).reshape(h,w)
    rows,cols,weights=[],[],[]
    for dy,dx in ((0,1),(1,0),(1,1),(1,-1)):
        first=(slice(0,h-dy),slice(max(0,-dx),w-max(0,dx)))
        second=(slice(dy,h),slice(max(0,dx),w-max(0,-dx)))
        weight=(pooled[first]+pooled[second])/2*math.hypot(dy,dx)
        ok=np.isfinite(weight)
        rows.append(index[first][ok]);cols.append(index[second][ok]);weights.append(weight[ok])
    graph=csr_matrix((np.concatenate(weights),(np.concatenate(rows),np.concatenate(cols))),shape=(h*w,h*w))
    _,previous=dijkstra(graph,directed=False,indices=index[a],return_predecessors=True)
    node,chain=index[b],[]
    while node!=index[a]:
        if node<0:
            raise RuntimeError(f'No route from {start} to {stop}')
        chain.append(node);node=previous[node]
    chain=chain[::-1][:-1][spacing//factor-1::spacing//factor]
    middle=[(x0+(n%w)*factor+factor//2,y0+(n//w)*factor+factor//2) for n in chain]
    return [tuple(start)]+middle+[tuple(stop)]


@timed_often
def _splnet(anchors,strips):
    H=lambda *v:struct.pack(f'<{len(v)}H',*v)
    u=lambda v:H(0x14)+struct.pack('<I',v)
    index={}
    for sid,points in strips:
        a,b=sorted((points[0],points[-1]))
        index.setdefault(b<<35|a<<6|sid&255,[]).append(sid)
    out=[H(0xee,1,0x0c)+struct.pack('<i',4),H(0x45a,1,3)+b''.join(H(0x0c)+struct.pack('<i',n) for n in (len(anchors),len(strips),len(index)))+H(4),H(0x5f4,1,3)]
    out+=[H(3,0xb,1)+u(i)+H(0x4c,1,3,0x0d)+struct.pack('<f',x)+H(0x0d)+struct.pack('<f',y)+H(4,4) for i,(x,y) in sorted(anchors.items())]
    out+=[H(4,0x5f5,1,3)]
    out+=[H(3,0xb,1,0x29c)+struct.pack('<Q',sid)+H(0x5f7,1,3)+b''.join(u(p) for p in points)+H(4,4) for sid,points in sorted(strips)]
    out+=[H(4,0x5f6,1,3)]
    out+=[H(3,0xb,1,0x29c)+struct.pack('<Q',key)+H(0x5f5,1,3)+b''.join(H(0x29c)+struct.pack('<Q',s) for s in ids)+H(4,4) for key,ids in sorted(index.items())]
    return b''.join(out+[H(4)])


@timed
def _network(cells,kinds,points,regions,state_neighbours,seas,borders,height,rng):
    anchors={};strips=[]
    land=kinds[cells]==LAND
    slices=ndimage.find_objects(cells)
    def box(provinces,extra=(),pad=12):
        found=[slices[p-1] for p in provinces]
        ys=[s[0].start for s in found]+[y for _,y in extra];ye=[s[0].stop for s in found]+[y+1 for _,y in extra]
        xs=[s[1].start for s in found]+[x for x,_ in extra];xe=[s[1].stop for s in found]+[x+1 for x,_ in extra]
        return (max(0,min(ys)-pad),min(cells.shape[0],max(ye)+pad)),(max(0,min(xs)-pad),min(cells.shape[1],max(xe)+pad))
    def place(anchor,x,y):
        points[anchor]=(x,y);anchors[anchor]=(x+.5,height-y-.5)
    def link(a,b,cost,area,factor,spacing,kind):
        ids=[a]
        for x,y in _path(cost,points[a],points[b],area,factor,spacing)[1:-1]:
            ids.append(0x10000000+len(anchors));anchors[ids[-1]]=(x+.5,height-y-.5)
        strips.append(((len(strips)<<8)|kind,ids+[b]))
    for anchor,(x,y) in list(points.items()):
        place(anchor,x,y)
    hubs={s['id']:[a for a in points if a//100==s['id']] for s in regions}
    def crop(grid,area):
        (y0,y1),(x0,x1)=area
        return grid[y0:y1,x0:x1]
    def cost(provinces,area):
        return np.where(np.isin(crop(cells,area),provinces),1.,np.where(crop(land,area),4.,30.))
    for state in regions:
        area=box(state['provinces'])
        own=cost(state['provinces'],area)
        joined=hubs[state['id']][:1]
        while len(joined)<len(hubs[state['id']]):
            a,b=min(((a,b) for a in joined for b in hubs[state['id']] if b not in joined),key=lambda p:math.dist(points[p[0]],points[p[1]]))
            link(a,b,own,area,2,6,int(rng.random()>.39));joined.append(b)
    by_id={s['id']:s for s in regions}
    for sid,others in state_neighbours.items():
        for other in others:
            if sid<other:
                provinces=by_id[sid]['provinces']+by_id[other]['provinces']
                area=box(provinces)
                a,b=min(((a,b) for a in hubs[sid] for b in hubs[other]),key=lambda p:math.dist(points[p[0]],points[p[1]]))
                link(a,b,cost(provinces,area),area,2,6,int(rng.random()>.36))
    water=np.where(kinds[cells]==OCEAN,1.,np.inf)
    junction={}
    for sea in seas:
        depth=ndimage.distance_transform_edt(np.pad(cells==sea['province'],1))[1:-1,1:-1]
        yy,xx=np.nonzero(depth>=min(8,depth.max()))
        ports=[points[s['id']*100+3] for s in regions if s.get('naval_exit')==sea['id']]
        target=np.mean(ports,0) if ports else (xx.mean(),yy.mean())
        best=np.argmin((xx-target[0])**2+(yy-target[1])**2)
        junction[sea['id']]=(NAVAL+sea['id'])*100+8
        place(junction[sea['id']],int(xx[best]),int(yy[best]))
    sea_of={s['province']:s['id'] for s in seas}
    for p,q in borders:
        if p in sea_of and q in sea_of:
            area=box([p,q])
            link(junction[sea_of[p]],junction[sea_of[q]],crop(water,area),area,4,30,2)
    for state in [s for s in regions if s['coastal']]:
        port=points[state['id']*100+3]
        harbor=(NAVAL+state['id'])*100+8
        place(harbor,*port)
        exit_=next(s for s in seas if s['id']==state['naval_exit'])
        area=box([exit_['province']],[port])
        link(harbor,junction[exit_['id']],crop(water,area),area,4,30,3)
    return _splnet(anchors,strips)


@timed
def generate(seed,countries,states,tech=.5,ideology_uniformity=0,copies=0,tech_variation=1,country_economy=1,local_economy=1,source_regions=1,primary_culture_share=None,
             *,game_dir=DEFAULT_GAME,data_dir=DEFAULT_DATA,region_keys=None,source_data=None):
    if not 1<=countries<=states:
        raise ValueError('Need at least one country and no more countries than states')
    if not 0<=tech<=1 or not 0<=copies<=1 or any(not 0<=v<=2 for v in (tech_variation,country_economy,local_economy)):
        raise ValueError('tech/copies must be within 0..1 and variation multipliers within 0..2')
    for name,value in (('ideology_uniformity',ideology_uniformity),('primary_culture_share',primary_culture_share)):
        if value is None and name=='primary_culture_share':
            continue
        if not (0<=value<=1 if isinstance(value,(int,float)) else isinstance(value,(tuple,list)) and len(value)==2 and 0<=value[0]<=value[1]<=1):
            raise ValueError(f'{name} must be within 0..1')
    if not isinstance(source_regions,int) or not 1<=source_regions<=states:
        raise ValueError('source_regions must be an integer between one and the state count')
    game=Path(game_dir)/'game'
    out=Path(data_dir)/'worlds'/f'seed_{seed}_{countries}_{states}'
    if out.exists():
        raise FileExistsError(out)
    work=out.with_name(out.name+'.building')
    shutil.rmtree(work,ignore_errors=True)
    mod=work/'mod'
    rng=random.Random(seed)
    nrng=np.random.default_rng(seed)
    data=vanilla(game) if source_data is None else source_data[0]
    sources=select_regions(rng,data,source_regions,region_keys)
    targets=[rng.randint(5,15) for _ in range(states)]
    width,height,fraction=_size(rng,sum(targets))
    domain=_domains(nrng,width,height,fraction,states)
    cells,kinds=_cells(domain,sum(targets),max(2,round(states*data['seas_per_state'])),nrng)
    total=len(kinds)-1
    yy,xx=np.indices(cells.shape)
    area=np.bincount(cells.ravel(),minlength=total+1)
    centers=np.stack([np.bincount(cells.ravel(),xx.ravel(),total+1),np.bincount(cells.ravel(),yy.ravel(),total+1)],1)/np.maximum(area,1)[:,None]
    borders=_graph(cells)
    neighbours={p:set() for p in range(1,total+1)}
    for a,b in borders:
        neighbours[a].add(b);neighbours[b].add(a)
    straits=_straits(cells,kinds,neighbours,width,int(states*data['crossings_per_state']+rng.random()))
    land=[p for p in range(1,total+1) if kinds[p]==LAND]
    ocean=[p for p in range(1,total+1) if kinds[p]==OCEAN]
    lakes=[p for p in range(1,total+1) if kinds[p]==LAKE]
    linked={p:{q for q in neighbours[p] if kinds[q]==LAND} for p in land}
    for strait in straits:
        linked[strait['from']].add(strait['to']);linked[strait['to']].add(strait['from'])
    coast_seeds={p for p in land if any(kinds[q]==OCEAN for q in neighbours[p])} if all(s['coastal'] for pool in sources.values() for s in pool) else None
    owner,_=_grow(land,linked,centers,states,targets,rng,candidates=coast_seeds)
    regions=[{'id':i+1,'key':f'STATE_INTERFACE_{i+1}','provinces':[]} for i in range(states)]
    for p in land:
        regions[owner[p]]['provinces'].append(p)
    for state in regions:
        state['center']=centers[state['provinces']].mean(0)
        state['coastal']=any(kinds[q]==OCEAN for p in state['provinces'] for q in neighbours[p])
    state_neighbours={s['id']:set() for s in regions}
    state_of={p:s['id'] for s in regions for p in s['provinces']}
    for p in land:
        for q in linked[p]:
            if state_of[q]!=state_of[p]:
                state_neighbours[state_of[p]].add(state_of[q])
    state_centers={s['id']:s['center'] for s in regions}
    grouping,seeds=_grow(list(state_centers),state_neighbours,state_centers,source_regions,[states/source_regions]*source_regions,rng,False)
    strategic=[{'key':f'region_interface_{i+1}','source_region':key,'states':[s for s in regions if grouping[s['id']]==i],
                'name':word(rng)+' Region'} for i,key in enumerate(sources)]
    assignments(rng,strategic,sources)
    colors=np.array([(0,0,0)]+[(v>>16,(v>>8)&255,v&255) for v in rng.sample(range(0x100000,0xEFFFFF),total)],dtype=np.uint8)
    codes=['x'+bytes(c).hex().upper() for c in colors]
    (mod/'map_data').mkdir(parents=True)
    Image.fromarray(colors[cells]).save(mod/'map_data/provinces.png')
    seas=[{'id':SEA_ID+i,'key':f'STATE_INTERFACE_SEA_{i+1}','province':p} for i,p in enumerate(ocean)]
    sea_of={s['province']:s for s in seas}
    geography={}
    terrains={}
    for state in regions:
        mask=np.isin(cells,state['provinces'])
        sy,sx=np.nonzero(mask)
        fields=textures(game,state['source']['provinces'],(sx-sx.min())/(np.ptp(sx)+1),(sy-sy.min())/(np.ptp(sy)+1),
                        None if source_data is None else source_data[1:])
        origin=fields.pop('provinces')
        for key,values in fields.items():
            geography.setdefault(key,np.zeros(cells.shape+values.shape[1:],dtype=values.dtype))[sy,sx]=values
        for p in state['provinces']:
            inside=cells[sy,sx]==p
            found,counts=np.unique(origin[inside],return_counts=True)
            ranked=[data['terrains'][f'x{int(c):06x}'] for c in found[np.argsort(counts)[::-1]] if f'x{int(c):06x}' in data['terrains']]
            terrains[p]=ranked[0]
    for state in regions:
        ids=state['provinces'];source=state['source']
        coastal=[p for p in ids if any(kinds[q]==OCEAN for q in neighbours[p])]
        center=state['center']
        by_center=sorted(ids,key=lambda p:np.hypot(*(centers[p]-center)))
        hubs={'city':by_center[0]}
        others=rng.sample(by_center[1:],len(by_center)-1) or by_center
        for i,kind in enumerate(['farm','mine','wood']):
            hubs[kind]=others[i%len(others)]
        if coastal:
            hubs['port']=min(coastal,key=lambda p:np.hypot(*(centers[p]-center)))
            exits=[q for q in neighbours[hubs['port']] if kinds[q]==OCEAN]
            state['naval_exit']=sea_of[max(exits,key=lambda q:borders[(min(q,hubs['port']),max(q,hubs['port']))])]['id']
        state['coastal']=bool(coastal)
        state['hubs']={kind:codes[p] for kind,p in hubs.items()}
        state['province_ids']=ids
        state['province_codes']=[codes[p] for p in ids]
        capped=dict(source['capped'])
        state['arable_land']=source['arable_land']
        state['arable_resources']=source['arable_resources']
        state['capped']=capped
        state['resources']=source['resources']
        state['traits']=source['traits']
        state['subsistence']=source['subsistence']
        state['template']=source['key']
    weights=[rng.lognormvariate(0,.7) for _ in range(countries)]
    ownership,capitals=_grow([s['id'] for s in regions],state_neighbours,state_centers,countries,[w/sum(weights)*states for w in weights],rng,False)
    _detach(rng,ownership,capitals,state_neighbours,{s['id'] for s in regions if s['coastal']},round(states*SECONDARY_SHARE+rng.random()-.5))
    groups=[[s['id'] for s in regions if ownership[s['id']]==i] for i in range(countries)]
    world=nations(rng,data,regions,groups,capitals,strategic,sources,tech,ideology_uniformity,copies,tech_variation,country_economy,local_economy,primary_culture_share)
    used=set()
    for state in regions:
        state['name']=word(rng,used)
    for sea in seas:
        sea['name']=word(rng,used)+' Sea'
    region_lines=[]
    for state in regions:
        resources=' '.join(state['resources'])
        capped=' '.join(f'{k} = {v}' for k,v in state['capped'].items())
        hubs=' '.join(f'{kind} = "{code}"' for kind,code in state['hubs'].items())
        exit_=f'naval_exit_id = {state["naval_exit"]}' if state['coastal'] else ''
        region_lines.append(f'{state["key"]} = {{ id = {state["id"]} subsistence_building = "{state["subsistence"]}" '
            f'provinces = {{ {" ".join(chr(34)+c+chr(34) for c in state["province_codes"])} }} traits = {{ {" ".join(chr(34)+t+chr(34) for t in state["traits"])} }} '
            f'{hubs} arable_land = {state["arable_land"]} arable_resources = {{ {" ".join(chr(34)+r+chr(34) for r in state["arable_resources"])} }} '
            f'capped_resources = {{ {capped} }} {resources} {exit_} }}')
    for sea in seas:
        region_lines.append(f'{sea["key"]} = {{ id = {sea["id"]} provinces = {{ "{codes[sea["province"]]}" }} }}')
    strategic_lines=[]
    localization=['l_english:']
    for region in strategic:
        capital=region['states'][0]['hubs']['city']
        color=' '.join(f'{rng.random():.2f}' for _ in range(3))
        strategic_lines.append(f'{region["key"]} = {{ capital_province = {capital} map_color = {{ {color} }} states = {{ {" ".join(s["key"] for s in region["states"])} }} }}')
        localization.append(f' {region["key"]}: "{region["name"]}"')
    for sea in seas:
        strategic_lines.append(f'region_interface_sea_{sea["id"]} = {{ states = {{ {sea["key"]} }} }}')
        localization+=[f' {sea["key"]}: "{sea["name"]}"',f' region_interface_sea_{sea["id"]}: "{sea["name"]}"']
    locators={kind:[] for kind in HUBS}
    points={};taken=set()
    for state in regions:
        localization.append(f' {state["key"]}: "{state["name"]}"')
        for kind in sorted(state['hubs'],key=HUB_INDEX.get):
            coast=ndimage.binary_dilation(cells==next(s['province'] for s in seas if s['id']==state['naval_exit']),CROSS) if kind=='port' else None
            x,y=_locator(cells,codes.index(state['hubs'][kind]),kind,coast,taken,rng)
            points[state['id']*100+HUB_INDEX[kind]]=(x,y)
            locators[kind].append(f'{{ id = {state["id"]} position = {{ {x+.5} 0 {height-y-.5} }} rotation = {{ 0 0 0 1 }} scale = {{ 1 1 1 }} }}')
    network=_network(cells,kinds,points,regions,state_neighbours,seas,borders,height,rng)
    terrain_lines=[f'{codes[p]} = "{terrains[p]}"' for p in land]+[f'{codes[p]} = "ocean"' for p in ocean]+[f'{codes[p]} = "lakes"' for p in lakes]
    adjacency_lines=['From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment']
    strait_lines=[]
    eligible=[s for s in straits if len(s['seas'])>=2]
    chokepoints=[s for s in eligible if rng.random()<min(1,data['straits_per_crossing']*len(straits)/len(eligible))]
    for i,strait in enumerate(straits,1):
        (x0,y0),(x1,y1)=strait['start'],strait['stop']
        adjacency_lines.append(f'{codes[strait["from"]]};{codes[strait["to"]]};sea;-1;{x0};{height-y0};{x1};{height-y1};;strait_{i}')
        if strait in chokepoints:
            first,second=strait['seas'][:2]
            strait_lines.append(f'strait_interface_{i} = {{ type = natural total_block_requires_full_control = no military_block_requires_full_control = no '
                                f'first_land_endpoint = {codes[strait["from"]]} second_land_endpoint = {codes[strait["to"]]} '
                                f'first_sea_endpoint = {codes[first]} second_sea_endpoint = {codes[second]} }}')
    heights=ndimage.gaussian_filter(geography['height'].astype(np.float32),2)
    is_land=kinds[cells]==LAND
    _heightmap(mod,np.where(is_land,np.maximum(heights,11000),np.minimum(heights,9500)).astype(np.uint16))
    _graphics(mod,game,is_land,geography)
    files={
        'map_data/default.map':f'provinces = "provinces.png"\ntopology = "heightmap.heightmap"\nrivers = "rivers.png"\nadjacencies = "adjacencies.csv"\nwrap_x = no\n'
                               f'sea_starts = {{ {" ".join(codes[p] for p in ocean)} }}\nlakes = {{ {" ".join(codes[p] for p in lakes)} }}',
        'map_data/state_regions/01_interface.txt':'\n'.join(region_lines),
        'map_data/province_terrains.txt':'\n'.join(terrain_lines),
        'common/strategic_regions/interface.txt':'\n'.join(strategic_lines),
        'common/strait_definitions/interface.txt':'\n'.join(strait_lines),
        'common/geographic_regions/interface.txt':_geographic_regions(game,regions,data['regions']),
        'common/defines/interface.txt':f'NJominiMap = {{ WORLD_EXTENTS_X = {width} WORLD_EXTENTS_Y = 24 WORLD_EXTENTS_Z = {height} WATERLEVEL = 3.7 }}\n'
                                       f'NEconomy = {{ WORLD_MARKET_LOCATION = "{codes[ocean[0]]}" }}',
        'localization/english/interface_l_english.yml':'\n'.join(localization+world['localization'])}
    tags={c['tag'] for c in world['countries']}
    files.update(_rewrites(game,regions,strategic,data['regions'],tags,{c['source']:c['tag'] for c in world['countries']}))
    files.update({path:_absent(text,tags) if path.startswith('common/history/') else text for path,text in world['files'].items()})
    from .characters import scripts
    scripts(game,files)
    for source in [game/'gfx/map/map_object_data/layers.txt',*sorted((game/'gfx/map/map_object_data').glob('papermap_*.txt'))]:
        files[source.relative_to(game).as_posix()]=source.read_text(encoding='utf-8-sig')
    for kind,instances in locators.items():
        files[f'gfx/map/map_object_data/generated_map_object_locators_{kind}.txt']=(f'game_object_locator = {{ name = "{kind}" clamp_to_water_level = {"yes" if kind=="port" else "no"} '
            f'render_under_water = no generated_content = no layer = "locators" instances = {{ {" ".join(instances)} }} }}')
    for path,text in files.items():
        if path in PLAIN:
            (mod/path).write_text(text+'\n',encoding='utf-8')
        else:
            write_script(mod/path,text+'\n')
    (mod/'gfx/map/spline_network/spline_network.splnet').write_bytes(network)
    (mod/'map_data/adjacencies.csv').write_text('\n'.join(adjacency_lines))
    replace=['map_data/state_regions','common/country_definitions','common/country_creation','common/country_formation','common/strategic_regions','common/geographic_regions','common/strait_definitions',
             'gfx/map/map_object_data']+['common/history/'+p.name for p in (game/'common/history').iterdir() if p.is_dir()]
    for path in replace:
        (mod/path).mkdir(parents=True,exist_ok=True)
        if not any((mod/path).iterdir()):
            write_script(mod/path/'interface_empty.txt','')
    write_json(mod/'.metadata/metadata.json',{'name':f'Interface world {seed} {countries} {states}','id':f'local.interface.world.{seed}.{countries}.{states}','version':'1',
        'supported_game_version':'1.13.*','short_description':'Random miniature world','tags':[],'relationships':[],'game_custom_data':{'replace_paths':replace}})
    manifest={'seed':seed,'tech':tech,'ideology_uniformity':ideology_uniformity,'primary_culture_share':primary_culture_share,'copies':copies,'tech_variation':tech_variation,
              'country_economy':country_economy,'local_economy':local_economy,'source_regions':source_regions,
              'source_region_keys':list(sources),'tech_reference':world['tech_reference'],'economy_reference':world['economy_reference'],
              'strategic_regions':[{'key':r['key'],'source_region':r['source_region'],'states':[s['key'] for s in r['states']]} for r in strategic],
              'width':width,'height':height,'mod':str((out/'mod').resolve()),'countries':world['countries'],
              'states':[{'id':s['id'],'key':s['key'],'name':s['name'],'country':s['country'],'provinces':s['province_codes'],'coastal':s['coastal'],
                         'hubs':s['hubs'],'template':s['template'],'source_region':s['source_region'],
                         'economic_scale':s['economic_scale'],'buildings':s['buildings'],'excluded_buildings':s['excluded_buildings']} for s in regions],
              'seas':[{'id':s['id'],'key':s['key'],'name':s['name'],'province':codes[s['province']]} for s in seas],
              'lakes':[codes[p] for p in lakes],
              'straits':[{'from':codes[s['from']],'to':codes[s['to']]} for s in chokepoints]}
    write_json(work/'audit.json',audit(regions,files))
    write_json(work/'manifest.json',manifest)
    work.rename(out)
    return out/'manifest.json'
