from collections import Counter
import csv
import io
import math
import re

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from interface.common import timed, timed_often


@timed
def map_geometry(files,identities):
    settings=bytes(files['default.map']).decode('utf-8-sig')
    wrap=re.search(r'(?m)^\s*wrap_x\s*=\s*(yes|no)\b',settings)
    if wrap is None:
        raise ValueError('Recorded map must specify horizontal wrapping')
    with Image.open(io.BytesIO(files['provinces.png'])) as image:
        rgb=np.asarray(image.convert('RGB'),dtype=np.int32)
    colors=(rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
    unique,inverse=np.unique(colors,return_inverse=True)
    values=np.array([identities.get(int(color),-1) for color in unique],np.int32)
    raster=values[inverse].reshape(colors.shape)
    crossings=[]
    rows=csv.reader(io.StringIO(bytes(files['adjacencies.csv']).decode('utf-8-sig')),delimiter=';')
    next(rows)
    for row in rows:
        if not row or not row[0].strip() or row[0].lstrip().startswith('#') or row[0].strip()=='-1':
            continue
        endpoints=[]
        for color in (row[0],row[1],row[3]):
            color=color.strip()
            if color=='-1':
                endpoints.append(None)
            else:
                key=int(color[1:],16) if color.lower().startswith('x') else int(color)
                if key not in identities:
                    raise ValueError(f'Crossing references unrecorded province color {color}')
                endpoints.append(identities[key])
        if endpoints[0] is None or endpoints[1] is None:
            raise ValueError('Geographic crossing lacks an endpoint')
        crossings.append({'first':endpoints[0],'second':endpoints[1],'through':endpoints[2],
                          'type':row[2].strip(),'positions':[float(v) for v in row[4:8]]})
    height,width=raster.shape
    seam=Counter()
    centres={}
    segments=[]
    endpoints=[]
    axes=[]
    for vertical,first,second in ((True,raster[:,:-1],raster[:,1:]),(False,raster[:-1],raster[1:])):
        yy,xx=np.nonzero((first!=second)&(first>=0)&(second>=0))
        segments.append(np.column_stack((xx+(1 if vertical else .5),height-yy-(.5 if vertical else 1))))
        endpoints.append(np.column_stack((first[yy,xx],second[yy,xx])))
        axes.append(np.full(len(xx),int(vertical),np.int8))
    if wrap[1]=='yes':
        angles=2*math.pi*(np.arange(width)+.5)/width
        sine=np.bincount(inverse.ravel(),weights=np.broadcast_to(np.sin(angles),raster.shape).ravel())
        cosine=np.bincount(inverse.ravel(),weights=np.broadcast_to(np.cos(angles),raster.shape).ravel())
        centres={int(province):float(math.atan2(s,c)%(2*math.pi)*width/(2*math.pi)) for province,s,c in zip(values,sine,cosine) if province>=0}
        for left,right in zip(raster[:,0],raster[:,-1]):
            if left>=0 and right>=0 and left!=right:
                seam[tuple(sorted((int(left),int(right))))]+=1
        yy=np.flatnonzero((raster[:,0]!=raster[:,-1])&(raster[:,0]>=0)&(raster[:,-1]>=0))
        segments.append(np.column_stack((np.zeros(len(yy)),height-yy-.5)))
        endpoints.append(np.column_stack((raster[yy,-1],raster[yy,0])))
        axes.append(np.ones(len(yy),np.int8))
    return {'raster':raster,'width':width,'height':height,'wrap_x':wrap[1]=='yes',
            'crossings':crossings,'seam':[(a,b,n) for (a,b),n in sorted(seam.items())],
            'border_centres':np.concatenate(segments),'border_provinces':np.concatenate(endpoints),
            'border_axes':np.concatenate(axes),
            'circular_centres':centres,'unmapped_pixels':int((raster<0).sum()),'coordinate_frame':'game_xy_bottom_left'}


def point(x,y,geometry):
    if x is None or y is None:
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError('Nonfinite spatial coordinate')
    width,height=geometry['width'],geometry['height']
    if geometry['wrap_x']:
        x=x%width
    if not 0<=x<width or not 0<=y<height:
        return None
    return float(x),float(y)


def displacement(first,second,geometry):
    dx,dy=second[0]-first[0],second[1]-first[1]
    width=geometry['width']
    if geometry['wrap_x']:
        if dx>width/2:
            dx-=width
        elif dx<-width/2:
            dx+=width
    distance=math.hypot(dx,dy)
    return {'dx':dx/width,'dy':dy/geometry['height'],
            'distance':distance/math.hypot(width,geometry['height']),
            'distance_pixels':distance,'direction_x':dx/distance if distance else 0.,
            'direction_y':dy/distance if distance else 0.,'coincident':float(distance==0)}


@timed
def border_distances(builder,raw,seq,hour,positions,geography):
    geometry=geography['map']
    provinces=geometry['border_provinces']
    terrain={p:t for p,r,t,a,x,y in geography['provinces']}
    unique,inverse=np.unique(provinces,return_inverse=True)
    water=np.asarray([terrain.get(int(p)) in ('ocean','lakes') for p in unique],bool)[inverse].reshape(-1,2)
    owners=[raw['province'].get(int(p),{}).get('state') for p in unique]
    states=np.asarray(owners,object)[inverse].reshape(-1,2)
    countries=np.asarray([raw['state'].get(s,{}).get('country') for s in owners],object)[inverse].reshape(-1,2)
    valid=(states[:,0]!=None)&(states[:,1]!=None)&~water.any(1)
    masks={'coast':water[:,0]!=water[:,1],
           'state_border':valid&(states[:,0]!=states[:,1]),
           'country_border':valid&(countries[:,0]!=None)&(countries[:,1]!=None)&(countries[:,0]!=countries[:,1])}
    counts={}
    for kind,mask in masks.items():
        selected=np.flatnonzero(mask)
        counts[kind]=0
        if not len(selected):
            continue
        centres=geometry['border_centres'][selected]
        if geometry['wrap_x']:
            centres=np.concatenate((centres,centres+[geometry['width'],0],centres-[geometry['width'],0]))
            selected=np.tile(selected,3)
        tree=cKDTree(centres)
        for (group,formation),origin in positions.items():
            if group!='formation':
                continue
            distance,_=tree.query(origin)
            near=np.asarray(tree.query_ball_point(origin,distance+.5000001),np.int64)
            points=centres[near].copy()
            axis=geometry['border_axes'][selected[near]]
            row=np.arange(len(near))
            points[row,axis]+=np.clip(np.asarray(origin)[axis]-points[row,axis],-.5,.5)
            distances=np.linalg.norm(points-origin,axis=1)
            nearest=np.flatnonzero(np.isclose(distances,distances.min(),rtol=0,atol=1e-7))
            seen=set()
            for index in nearest:
                a,b=map(int,provinces[selected[near[index]]])
                x,y=map(float,points[index])
                if geometry['wrap_x']:
                    x%=geometry['width']
                key=(formation,a,b,x,y)
                if key in seen:
                    continue
                seen.add(key)
                attrs=displacement(origin,(x,y),geometry)
                attrs.update({'border_x':x/geometry['width'],'border_y':y/geometry['height']})
                node=builder.node('spatial.nearest_'+kind,key,seq,hour,attrs)
                builder.edge(builder.find(seq,'formation',formation),node,'spatial.origin')
                for role,province in (('first',a),('second',b)):
                    target=builder.endpoint('province',province,seq,hour,'spatial.border',role,node)
                    builder.edge(node,target,'spatial.border.'+role)
                counts[kind]+=1
    return counts


@timed
def add_spatial(builder,raw,seq,hour,geography):
    geometry=geography['map']
    width,height=geometry['width'],geometry['height']
    if geometry['coordinate_frame']!='game_xy_bottom_left' or geometry['raster'].shape!=(height,width):
        raise ValueError('Invalid world coordinate geometry')
    positions={}
    regions={}
    members_by_state={}
    located={}
    status={r['formation']:r for r in builder.data['states'][seq]['formation_status']}
    audit={'seq':seq,'formations':len(raw['formation']),'located_formations':0,'located_fronts':0,
           'missing_positions':[],'outside_map':[],'unmapped_positions':[],
           'recorded_province_disagreements':[],'pairs':Counter()}
    for province,region,terrain,area,x,y in geography['provinces']:
        node=builder.find(seq,'province',province)
        if node is not None:
            positions['province',province]=(geometry['circular_centres'].get(province,float(x)+.5),height-float(y)-.5)
            regions[province]=raw['province'].get(province,{}).get('state')
            members_by_state.setdefault(regions[province],[]).append((province,area))
    for state,row in raw['state'].items():
        members=members_by_state.get(state,[])
        if members:
            total=sum(area for _,area in members)
            if geometry['wrap_x']:
                sine=sum(math.sin(2*math.pi*positions['province',p][0]/width)*area for p,area in members)
                cosine=sum(math.cos(2*math.pi*positions['province',p][0]/width)*area for p,area in members)
                x=math.atan2(sine,cosine)%(2*math.pi)*width/(2*math.pi)
            else:
                x=sum(positions['province',p][0]*area for p,area in members)/total
            y=sum(positions['province',p][1]*area for p,area in members)/total
            positions['state',state]=(x,y)
    for kind,rows in (('formation',status),('front',raw['front'])):
        for key,row in rows.items():
            if key not in raw[kind]:
                continue
            node=builder.find(seq,kind,key)
            position=point(row['x'],row['y'],geometry)
            if position is None:
                reason='missing_positions' if row['x'] is None or row['y'] is None else 'outside_map'
                audit[reason].append({'kind':kind,'key':key,'x':row['x'],'y':row['y']})
                continue
            positions[kind,key]=position
            x,y=position
            province=int(geometry['raster'][height-1-math.floor(y),math.floor(x)])
            if province<0:
                audit['unmapped_positions'].append({'kind':kind,'key':key,'x':x,'y':y})
                continue
            target=builder.endpoint('province',province,seq,hour,'spatial',kind,node)
            builder.edge(node,target,f'spatial.{kind}.in_province')
            state=raw['province'].get(province,{}).get('state')
            if state is not None:
                builder.edge(node,builder.endpoint('state',state,seq,hour,'spatial',kind,node),f'spatial.{kind}.in_state')
            located[kind,key]=province
            audit['located_formations' if kind=='formation' else 'located_fronts']+=1
            observed=row.get('province')
            if observed is not None and observed!=65535:
                builder.nodes[node]['attrs']['spatial.recorded_province_agrees']=float(observed==province)
                if observed!=province:
                    audit['recorded_province_disagreements'].append({'kind':kind,'key':key,'recorded':observed,'coordinate':province})
    for key in raw['formation'].keys()-status.keys():
        audit['missing_positions'].append({'kind':'formation','key':key,'x':None,'y':None})
    for (kind,key),(x,y) in positions.items():
        node=builder.find(seq,kind,key)
        builder.nodes[node]['attrs'].update({'spatial.x':x/width,'spatial.y':y/height})
        builder.nodes[node]['position']={'x':x,'y':y,'units':'map_pixels','coordinate_frame':geometry['coordinate_frame'],
                                         'basis':'area_centroid' if kind in ('province','state') else 'recorded_position'}
    for kind in ('formation','state','front'):
        targets=[(key,value) for (group,key),value in positions.items() if group==kind]
        for (group,first),origin in list(positions.items()):
            if group!='formation':
                continue
            for second,destination in targets:
                if kind=='formation' and first==second:
                    continue
                attrs=displacement(origin,destination,geometry)
                owner=raw[kind][second].get('country')
                if owner is not None:
                    attrs['same_country']=float(raw['formation'][first]['country']==owner)
                pair=builder.node('spatial.formation_to_'+kind,(first,second),seq,hour,attrs)
                builder.edge(builder.find(seq,'formation',first),pair,'spatial.origin')
                builder.edge(pair,builder.find(seq,kind,second),'spatial.target')
                audit['pairs'][kind]+=1
    for index,crossing in enumerate(geometry['crossings']):
        attrs={'type':crossing['type']}
        if all(v>=0 for v in crossing['positions']):
            x,y,u,v=crossing['positions']
            attrs.update({'start_x':x/width,'start_y':y/height,'end_x':u/width,'end_y':v/height})
            attrs.update(displacement((x,y),(u,v),geometry))
        node=builder.node('spatial.crossing',index,seq,hour,attrs)
        for role in ('first','second','through'):
            if crossing[role] is not None:
                target=builder.endpoint('province',crossing[role],seq,hour,'spatial.crossing',role,node)
                builder.edge(node,target,'spatial.crossing.'+role)
    audit['pairs']=dict(audit['pairs'])
    audit['nearest_borders']=border_distances(builder,raw,seq,hour,positions,geography)
    audit['crossings']=len(geometry['crossings'])
    return audit
