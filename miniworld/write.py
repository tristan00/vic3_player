import json
import re
import shutil
import struct

import numpy as np
from PIL import Image

from interface.common import write_json
from interface.script import blocks, body, clean, scalar
from . import GAME, heightmap, timed, timed_often

FIXED=['map_data/state_regions','common/strategic_regions','common/strait_definitions','common/geographic_regions']
HUBS={'city':0,'farm':1,'mine':2,'port':3,'wood':4}
HARBOR=1<<23
SHORE=3
ROAD,LANE,DOCK=0,2,3


@timed_often
def color(value):
    return f'x{int(value):06X}'


@timed_often
def text(path,content,encoding='utf-8-sig'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content,encoding=encoding)


@timed
def images(mod,world):
    data=mod/'map_data'
    data.mkdir(parents=True,exist_ok=True)
    rgb=world.colors[world.grid]
    Image.fromarray(np.stack([rgb>>16,(rgb>>8)&255,rgb&255],2).astype(np.uint8),'RGB').save(data/'provinces.png')
    heightmap.write(data,world.heights)
    with Image.open(GAME/'map_data/rivers.png') as source:
        palette=source.getpalette()
    rivers=Image.fromarray(np.where(world.grid<world.land_count,254,255).astype(np.uint8),'P')
    rivers.putpalette(palette)
    rivers.save(data/'rivers.png')


@timed
def canals(mod,world,states):
    content=clean(GAME/'common/buildings/10_canals.txt')
    rows=[]
    definitions=[]
    for name,block in blocks(content):
        key=scalar(block,'strait')
        site=world.canals.get(key)
        made=block
        for part,inner in blocks(body(block)):
            if part=='potential': made=made.replace(inner,f'potential = {{ state_region = s:{states[site[0]]["key"]} }}' if site else 'potential = { always = no }',1)
            if part=='possible': made=made.replace(inner,f'possible = {{ owner = {{ owns_entire_state_region = {states[site[0]]["key"]} }} }}' if site else 'possible = { always = no }',1)
        if site:
            s,a,b,x,y=site
            (y0,x0),(y1,x1)=world.centre[a].astype(int),world.centre[b].astype(int)
            rows.append(f'{color(world.colors[x])};{color(world.colors[y])};{key};-1;{x0};{world.shape[0]-1-y0};{x1};{world.shape[0]-1-y1};;\n')
            definitions.append(f'{key} = {{\n\ttype = artificial\n\tfirst_land_endpoint = {color(world.colors[a])}\n\tsecond_land_endpoint = {color(world.colors[b])}\n'
                               f'\tfirst_sea_endpoint = {color(world.colors[x])}\n\tsecond_sea_endpoint = {color(world.colors[y])}\n}}\n')
        else:
            made=re.sub(r'\n\s*strait\s*=\s*\w+','',made,count=1)
        content=content.replace(block,made,1)
    text(mod/'common/buildings/10_canals.txt',content)
    text(mod/'common/strait_definitions/miniworld.txt',''.join(definitions))
    return ''.join(rows)


@timed
def map_text(mod,world,states):
    seas=' '.join(color(world.colors[p]) for p in world.seas)
    lakes=' '.join(color(world.colors[p]) for p in world.lakes)
    text(mod/'map_data/default.map',f'provinces = "provinces.png"\ntopology = "heightmap.heightmap"\nrivers = "rivers.png"\nadjacencies = "adjacencies.csv"\nwrap_x = no\n\n'
         f'sea_starts = {{\n\t{seas}\n}}\nlakes = {{\n\t{lakes}\n}}\n','utf-8')
    text(mod/'map_data/adjacencies.csv','From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment\n'
         +''.join(f'{color(world.colors[a])};{color(world.colors[b])};sea;-1;{x0};{world.shape[0]-1-y0};{x1};{world.shape[0]-1-y1};;\n'
                  for a,b,(y0,x0),(y1,x1) in world.crossings)+canals(mod,world,states),'utf-8')
    text(mod/'common/geographic_regions/miniworld.txt',''.join(f'{key} = {{\n'+(f'\tshort_key = "{short}"\n' if short else '')+'\tstate_regions = { '
                                                             +' '.join([f'STATE_MW_{s+1}' for s in states]+[f'STATE_MW_SEA_{i+1}' for i in seas])+' }\n}\n'
                                                             for key,(short,states,seas) in world.geographic.items()))
    text(mod/'map_data/province_terrains.txt',''.join(f'{color(world.colors[p])}="{world.terrain[p]}"\n' for p in range(world.count)),'utf-8')
    height,width=world.shape
    text(mod/'common/defines/miniworld.txt',f'NJominiMap = {{\n\tWORLD_EXTENTS_X = {width}\n\tWORLD_EXTENTS_Z = {height-1}\n}}\n'
         f'NEconomy = {{\n\tWORLD_MARKET_LOCATION = "{color(world.colors[world.market])}"\n}}\n')
    lines=[]
    for state in states:
        hubs=''.join(f'\t{hub} = "{color(world.colors[p])}"\n' for hub,p in state['hubs'].items())
        capped=''.join(f'\t\t{b} = {n}\n' for b,n in state['capped'].items())
        resources=''.join(f'\tresource = {{\n\t\ttype = "{kind}"\n'+(f'\t\tdepleted_type = "{depleted}"\n' if depleted else '')+f'\t\tundiscovered_amount = {amount}\n\t}}\n'
                          for kind,depleted,amount in state['resources'])
        lines.append(f"{state['key']} = {{\n\tid = {state['id']}\n\tsubsistence_building = \"{state['subsistence']}\"\n"
                     f"\tprovinces = {{ {' '.join(chr(34)+color(world.colors[p])+chr(34) for p in state['provinces'])} }}\n"
                     +(f"\timpassable = {{ {' '.join(chr(34)+color(world.colors[p])+chr(34) for p in state['impassable'])} }}\n" if state['impassable'] else '')
                     +(f"\ttraits = {{ {' '.join(chr(34)+t+chr(34) for t in state['traits'])} }}\n" if state['traits'] else '')+hubs+
                     f"\tarable_land = {state['arable_land']}\n\tarable_resources = {{ {' '.join(chr(34)+b+chr(34) for b in state['arable_resources'])} }}\n"
                     +(f'\tcapped_resources = {{\n{capped}\t}}\n' if capped else '')+resources
                     +(f"\tnaval_exit_id = {state['naval_exit']}\n" if 'naval_exit' in state else '')+'}\n')
    for index,sea in enumerate(world.seas):
        lines.append(f'STATE_MW_SEA_{index+1} = {{\n\tid = {3000+index}\n\tprovinces = {{ "{color(world.colors[sea])}" }}\n}}\n')
    text(mod/'map_data/state_regions/miniworld.txt','\n'.join(lines))
    regions=[]
    for index,members in enumerate(world.regions):
        middle=np.mean([world.centre[states[s]['hubs']['city']] for s in members],0)
        capital=min((states[s]['hubs']['city'] for s in members),key=lambda p:float(((world.centre[p]-middle)**2).sum()))
        regions.append(f'region_mw_{index+1} = {{\n\tcapital_province = {color(world.colors[capital])}\n\tmap_color = {{ {" ".join(map(str,world.tints[index]))} }}\n'
                       f'\tstates = {{ {" ".join(states[s]["key"] for s in members)} }}\n}}\n')
    regions+=[f'region_mw_sea_{index+1} = {{\n\tstates = {{ STATE_MW_SEA_{index+1} }}\n}}\n' for index in range(len(world.seas))]
    text(mod/'common/strategic_regions/miniworld.txt','\n'.join(regions))


@timed_often
def locator(name,layer,instances,clamp):
    body=''.join(f'\t\t{{\n\t\t\tid={i}\n\t\t\tposition={{ {x:.6f} 0.000000 {z:.6f} }}\n\t\t\trotation={{ 0.000000 0.000000 0.000000 1.000000 }}\n\t\t\tscale={{ 1.000000 1.000000 1.000000 }}\n\t\t}}\n'
                 for i,x,z in instances)
    return (f'game_object_locator={{\n\tname="{name}"\n\tclamp_to_water_level={clamp}\n\trender_under_water=no\n\tgenerated_content=no\n'
            f'\tlayer="{layer}"\n\tinstances={{\n{body}\t}}\n}}\n')


@timed
def graphics(mod,world,states):
    folder=mod/'gfx/map/map_object_data'
    for hub in ('city','farm','mine','wood','port'):
        instances=[(s['id'],world.centre[s['hubs'][hub]][1],world.shape[0]-world.centre[s['hubs'][hub]][0]) for s in states if hub in s['hubs']]
        text(folder/f'generated_map_object_locators_{hub}.txt',locator(hub,'locators',instances,'no'))
    text(folder/'fortification_locators.txt',locator('fortification','fortifications',[],'yes'))
    spline=mod/'gfx/map/spline_network/spline_network.splnet'
    spline.parent.mkdir(parents=True,exist_ok=True)
    spline.write_bytes(network(world,states))


@timed_often
def water(world,start,sea):
    target=world.inside[sea]
    step=(target-start)/max(1.,float(np.abs(target-start).max()))
    point=np.array(start,float)
    while world.grid[int(point[0]),int(point[1])]!=sea: point+=step
    return point+step*SHORE


@timed
def network(world,states):
    height=world.shape[0]
    place=lambda point:(float(point[1]),float(height-point[0]))
    anchors={}
    for s in states:
        for hub,p in s['hubs'].items():
            anchors[s['id']*100+HUBS[hub]]=place(world.centre[p])
    links=[(s['id']*100,s['id']*100+HUBS[hub],ROAD) for s in states for hub in s['hubs'] if hub!='city']
    links+=[(states[a]['id']*100,states[b]['id']*100,ROAD) for a,others in enumerate(world.state_neighbours) for b in sorted(others) if a<b]
    seas={p:3000+index for index,p in enumerate(world.seas)}
    for p,sea in seas.items(): anchors[HARBOR+sea*100]=place(world.inside[p])
    for s in states:
        if 'port' in s['hubs']:
            sea=world.seas[s['naval_exit']-3000]
            anchors[HARBOR+s['id']*100]=place(water(world,world.centre[s['hubs']['port']],sea))
            links.append((HARBOR+s['id']*100,HARBOR+s['naval_exit']*100,DOCK))
    links+=[(HARBOR+seas[p]*100,HARBOR+seas[o]*100,LANE) for p in world.seas for o in sorted(world.neighbours[p]) if o in seas and seas[p]<seas[o]]
    links+=[(HARBOR+seas[x]*100,HARBOR+seas[y]*100,LANE) for _,_,_,x,y in world.canals.values()]
    group=lambda body:b'\x03\x00'+body+b'\x04\x00'
    out=struct.pack('<HHHi',0xee,1,0x0c,4)+struct.pack('<HH',0x45a,1)+group(struct.pack('<HiHiHi',0x0c,len(anchors),0x0c,len(links),0x0c,len(links)))
    out+=struct.pack('<HH',0x5f4,1)+group(b''.join(group(struct.pack('<HHHI',0x0b,1,0x14,key)+struct.pack('<HH',0x4c,1)+group(struct.pack('<HfHf',0x0d,x,0x0d,z)))
                                                    for key,(x,z) in sorted(anchors.items())))
    out+=struct.pack('<HH',0x5f5,1)+group(b''.join(group(struct.pack('<HHHQ',0x0b,1,0x29c,index)+struct.pack('<HH',0x5f7,1)+group(struct.pack('<HIHI',0x14,a,0x14,b)))
                                                    for index,(a,b,_) in enumerate(links)))
    out+=struct.pack('<HH',0x5f6,1)+group(b''.join(group(struct.pack('<HHHQ',0x0b,1,0x29c,key)+struct.pack('<HH',0x5f5,1)+group(struct.pack('<HQ',0x29c,index)))
                                                    for key,index in sorted(((b<<35)|(a<<6)|kind,index) for index,(a,b,kind) in enumerate(links))))
    return out


@timed
def localization(mod,labels):
    text(mod/'localization/english/miniworld_l_english.yml','l_english:\n'+''.join(f' {key}:0 "{value}"\n' for key,value in labels.items()))


@timed
def metadata(mod,replaced):
    mod.joinpath('.metadata').mkdir(parents=True,exist_ok=True)
    mod.joinpath('.metadata/metadata.json').write_text(json.dumps({'name':'Miniworld','id':'local.miniworld','version':'1','supported_game_version':'1.13.*',
        'short_description':'Generated miniworld','tags':[],'relationships':[],'game_custom_data':{'multiplayer_synchronized':True,'replace_paths':replaced}},indent=2),encoding='utf-8')


@timed
def manifest(out,mod,seed,knobs,world,states,owned,totals,capitals,labels,names,relations,tiers):
    owner={s:tag for tag,members in owned.items() for s in members}
    value={'seed':seed,'knobs':knobs,'mod':str(mod.resolve()),'width':world.shape[1],'height':world.shape[0],'population':int(sum(totals)),
           'provinces':{'land':world.land_count,'lakes':len(world.lakes),'sea':len(world.seas)},
           'countries':[{'tag':tag,'name':names[tag],'tier':tiers[tag],'capital':states[capitals[tag]]['key'],'states':[states[s]['key'] for s in members],
                         'population':int(sum(totals[s] for s in members))} for tag,members in owned.items()],
           'states':[{'key':state['key'],'name':labels[state['key']],'country':owner[s],'population':int(totals[s]),'terrain':state['terrain'],
                      'coastal':'port' in state['hubs'],'provinces':[color(world.colors[p]) for p in state['provinces']]} for s,state in enumerate(states)],
           'subjects':[{'overlord':a,'subject':b,'type':kind} for a,b,kind in relations.subjects],
           'rivals':[{'country':a,'rival':b} for a,b in relations.rivals],
           'blocs':[{'leader':leader,'members':members,'identity':identity} for leader,members,identity,_,_ in relations.blocs],
           'relations':[{'country':a,'with':b,'value':v} for (a,b),v in relations.relations.items()]}
    write_json(out/'manifest.json',value)


@timed
def reset(mod):
    if mod.exists(): shutil.rmtree(mod)
    mod.mkdir(parents=True)
