import collections
import re
import warnings

import numpy as np
from PIL import Image
from scipy import ndimage

from ..common import timed, timed_often
from ..script import blocks, body, clean, entries, fields, keys, read, scalar, script_files
from .source import reference


@timed_often
def _templates(game):
    templates=[]
    for key,value in read(game,'map_data/state_regions'):
        if not scalar(value,'arable_land'):
            continue
        parts=list(blocks(body(value)))
        inner=dict(parts)
        templates.append({'key':key,'provinces':[p.lower() for p in re.findall(r'x[0-9A-Fa-f]{6}',inner['provinces'])],
                          'subsistence':scalar(value,'subsistence_building'),
                          'traits':re.findall(r'\w+',body(inner['traits'])) if 'traits' in inner else [],
                          'arable_land':int(scalar(value,'arable_land')),
                          'arable_resources':re.findall(r'\w+',body(inner.get('arable_resources','{}'))),
                          'capped':{k:int(v) for k,v in re.findall(r'(\w+)\s*=\s*(\d+)',body(inner.get('capped_resources','{}')))},
                          'resources':[text for kind,text in parts if kind=='resource']})
    return templates


@timed_often
def _military_buildings(game):
    parents={key:scalar(value,'parent_group') for key,value in read(game,'common/building_groups')}
    def military(group):
        return group=='bg_military' or (group is not None and military(parents[group]))
    return {key for key,value in read(game,'common/buildings') if military(scalar(value,'building_group'))}


@timed_often
def _politics_laws(game,groups):
    defaults={}
    for key,value in read(game,'common/scripted_effects'):
        if key.startswith('effect_starting_politics_'):
            laws=defaults[key.removeprefix('effect_starting_politics_')]={}
            for law in re.findall(r'law_type:(\w+)',value):
                laws[groups.get(law)]=law
    return defaults


@timed_often
def _relations(game):
    subject_types=set()
    subject_rules={}
    for key,value in read(game,'common/subject_types'):
        subject_types.add(key.removeprefix('subject_type_'))
        rule=dict(fields(body(value)))
        if (rule['overlord_must_be_higher_rank']==['yes'] and rule['join_overlord_wars']==['yes'] and
                {'minor_power','unrecognized_regional_power'}&set(rule['valid_overlord_ranks'])):
            subject_rules[key.removeprefix('subject_type_')]=(set(rule['valid_overlord_country_types']),set(rule['valid_subject_country_types']))
    bloc_principles=collections.defaultdict(list)
    for _,value in read(game,'common/power_bloc_principle_groups'):
        if scalar(value,'primary_for_identity'):
            bloc_principles[scalar(value,'primary_for_identity')].append(dict(fields(body(value)))['levels'][0])
    return {'subject_types':subject_types,'subject_rules':subject_rules,'bloc_principles':dict(bloc_principles)}


@timed_often
def _law_rules(game):
    listed=lambda value,key:set(re.findall(r'\w+',body(dict(blocks(body(value))).get(key,'{}'))))
    techs={key:(scalar(value,'era'),listed(value,'unlocking_technologies')) for key,value in read(game,'common/technology/technologies')}
    tiers={}
    for key,value in read(game,'common/scripted_effects'):
        found=re.fullmatch(r'effect_starting_technology_tier_(\d)_tech',key)
        if found:
            eras=set(re.findall(r'add_era_researched\s*=\s*(\w+)',value))
            tiers[int(found[1])]={tech for tech,(era,_) in techs.items() if era in eras}|set(re.findall(r'add_technology_researched\s*=\s*(\w+)',value))
    buildings={key:listed(value,'unlocking_technologies') for key,value in read(game,'common/buildings')}
    parents={key:scalar(value,'parent') for key,value in read(game,'common/laws') if scalar(value,'parent')}
    laws={key:(listed(value,'disallowing_laws'),listed(value,'unlocking_laws'),listed(value,'unlocking_technologies')) for key,value in read(game,'common/laws')}
    modifier=lambda value,name:sum(map(float,re.findall(r'\b'+name+r'\s*=\s*(-?[\d.]+)',value)))
    administration={key:(modifier(value,'state_bureaucracy_population_base_cost_factor_mult'),modifier(value,'country_bureaucracy_investment_cost_factor_mult'),scalar(value,'institution'))
                    for key,value in read(game,'common/laws')}
    defines=' '.join(text for _,text in read(game,'common/defines'))
    costs={name:float(scalar(defines,name)) for name in ('STATE_BUREAUCRACY_BASE_COST','STATE_BUREAUCRACY_POP_BASE_COST','STATE_BUREAUCRACY_POP_MULTIPLE')}
    return {'law_rules':laws,'law_parents':parents,'tier_techs':tiers,'building_techs':buildings,'tech_requires':{tech:needs for tech,(_,needs) in techs.items()},
            'law_administration':administration,'administration_costs':costs}


@timed
def vanilla(game):
    laws=list(read(game,'common/laws'))
    groups={key:scalar(value,'group') for key,value in laws}
    every=_templates(game)
    populated={state for _,state,value in entries(game,'common/history/pops') if any(map(int,re.findall(r'\bsize\s*=\s*(\d+)',value)))}
    templates=[t for t in every if t['key'] in populated]
    rules=_law_rules(game)
    crossings=sum(line.split(';')[2:3]==['sea'] for line in (game/'map_data/adjacencies.csv').read_text(encoding='utf-8-sig').splitlines())
    natural=sum(len(re.findall(r'type\s*=\s*natural',clean(path))) for path in script_files(game,'common/strait_definitions'))
    seas=len(re.findall(r'x[0-9A-Fa-f]{6}',re.search(r'sea_starts\s*=\s*\{([^}]*)\}',(game/'map_data/default.map').read_text(encoding='utf-8-sig'))[1]))
    return {**reference(game,templates,rules),**rules,**_relations(game),'templates':templates,
            'seas_per_state':seas/len(every),'straits_per_crossing':natural/crossings,'crossings_per_state':crossings/len(every),
            'law_groups':groups,'law_progress':{key:float(scalar(value,'progressiveness')) for key,value in laws},
            'barracks_cap':{key:int(found[1]) for key,value in laws if (found:=re.search(r'state_building_barrack_max_level_add\s*=\s*(\d+)',value))},
            'politics_laws':_politics_laws(game,groups),'military_buildings':_military_buildings(game),
            'terrains':{k.lower():v for k,v in re.findall(r'(x[0-9A-Fa-f]{6})\s*=\s*"([^"]+)"',(game/'map_data/province_terrains.txt').read_text(encoding='utf-8-sig'))},
            'source_group_by_state':{state:key for key,value in read(game,'common/strategic_regions') for state in re.findall(r'STATE_\w+',value)},
            'tags':set(keys(game,'common/country_definitions'))}


@timed
def rasters(game):
    result={}
    for key,path in [('provinces','map_data/provinces.png'),('height','map_data/heightmap.png'),
                     ('detail_index','gfx/map/terrain/detail_index.tga'),('detail_intensity','gfx/map/terrain/detail_intensity.tga'),
                     ('colormap','gfx/map/textures/colormap.dds')]:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',Image.DecompressionBombWarning)
            with Image.open(game/path) as image:
                size=result['provinces'].shape[1::-1] if result else image.size
                result[key]=np.array(image if image.size==size else image.resize(size,Image.Resampling.NEAREST))
    rgb=result['provinces'].astype(np.uint32)
    result['provinces']=(rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
    return result


@timed
def boxes(provinces):
    colors=np.flatnonzero(np.bincount(provinces.ravel(),minlength=1<<24))
    lookup=np.zeros(1<<24,dtype=np.int32)
    lookup[colors]=np.arange(1,len(colors)+1)
    return {f'x{int(c):06x}':box for c,box in zip(colors,ndimage.find_objects(lookup[provinces]))}


@timed
def textures(source,bounds,provinces,u,v):
    spans=[bounds[p] for p in provinces]
    box=tuple(slice(min(s[axis].start for s in spans),max(s[axis].stop for s in spans)) for axis in range(2))
    mask=np.isin(source['provinces'][box],[int(p[1:],16) for p in provinces])
    nearest=ndimage.distance_transform_edt(~mask,return_distances=False,return_indices=True)
    sy,sx=nearest[:,(v*mask.shape[0]).astype(int),(u*mask.shape[1]).astype(int)]
    return {key:image[box][sy,sx] for key,image in source.items()}
