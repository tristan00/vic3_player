import collections
from functools import lru_cache
import re
import warnings

import numpy as np
from PIL import Image
from scipy import ndimage

from ..common import timed
from ..script import blocks, body, clean, entries, keys, read, scalar, script_files


COUNTRY_HISTORY=['countries','population','characters','military_formations','governments','government_setup','production_methods','ai','political_movements']


GLOBAL_HISTORY=['global','conscription','cultures']


FOREIGN=r'\b(?:c:[A-Z0-9]{3}|STATE_\w+|sr:\w+)'


BANDS={'1':0,'2':0,'3':1,'4':1,'5':2,'6':3,'7':3}


TRIM=.1


MILITARY={'building_barrack':'barracks','building_naval_administration':'naval'}


POLICIES={'set_institution_investment_level','set_import_tariff_level','set_export_tariff_level'}


def _foreign(value):
    return re.search(FOREIGN+r'(?!\s*\?=)',value) or 'journal_entry' in value or 'can_form_nation' in value


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


def _profiles(game):
    types={tag:scalar(value,'country_type') for tag,value in read(game,'common/country_definitions')}
    population={key:value for _,key,value in entries(game,'common/history/population')}
    groups={key:scalar(value,'group') for key,value in read(game,'common/laws')}
    generic={key for key,value in read(game,'common/amendments') if not re.search(r'\bc:[A-Z0-9]{3}\b|was_formed_from|STATE_|has_template',value)}
    profiles=[];bands={};amendments=[]
    for _,tag,value in entries(game,'common/history/countries'):
        tier=re.search(r'effect_starting_technology_tier_(\d)_tech',value)
        politics=re.search(r'effect_starting_politics_(\w+?)\s*=\s*yes',value)
        if not tier or not politics or types.get(tag) not in {'recognized','unrecognized'} or politics[1]=='princely_state':
            continue
        bands[tag]=BANDS[tier[1]]
        people=population.get(tag,'')
        laws={}
        for law in re.findall(r'activate_law\s*=\s*law_type:(\w+)',value):
            if law in groups:
                laws[groups[law]]=law
        policies=[text for key,text in blocks(body(value)) if key in POLICIES]
        amendments+=[(laws[key.split(':')[1]],text) for key,text in blocks(body(value))
                     if key.startswith('active_law:') and scalar(text,'type') in generic and key.split(':')[1] in laws and not _foreign(text)]
        policies+=re.findall(r'add_taxed_goods\s*=\s*g:\w+',value)
        profiles.append({'band':BANDS[tier[1]],'tier':int(tier[1]),'politics':politics[1],'type':types[tag],'laws':laws,
                         'policies':[text for text in policies if not _foreign(text)],
                         'ruling':sorted(set(re.findall(r'ig:(\w+)\s*\??=\s*\{\s*add_ruling_interest_group\s*=\s*yes',value))),
                         'tax':scalar(value,'set_tax_level'),
                         'wealth':next(iter(re.findall(r'effect_starting_pop_wealth_(\w+?)\s*=',people)),None),
                         'literacy':next(iter(re.findall(r'effect_starting_pop_literacy_(\w+?)\s*=',people)),None)})
    return profiles,groups,bands,amendments


@timed
def _economy(game,bands):
    unique={key for key,value in read(game,'common/buildings') if re.search(r'\bunique\s*=\s*yes',value)}
    states={};allowed={};owners=collections.defaultdict(collections.Counter)
    for _,state,value in entries(game,'common/history/buildings'):
        record=states.setdefault(state,{'buildings':collections.Counter(),'population':0})
        for owner,inner in blocks(body(value)):
            for kind,building in blocks(body(inner)):
                name=scalar(building,'building')
                if kind=='create_building' and name not in unique:
                    record['buildings'][name]+=sum(map(int,re.findall(r'\blevels\s*=\s*(\d+)',building)))
                    kinds=re.findall(r'\btype\s*=\s*"?(building_\w+)',building)
                    owners[name][kinds[0] if kinds else 'country']+=1
                    if owner.split(':')[-1] in bands:
                        allowed.setdefault(bands[owner.split(':')[-1]],set()).add(name)
    for _,state,value in entries(game,'common/history/pops'):
        states.setdefault(state,{'buildings':collections.Counter(),'population':0})['population']+=sum(map(int,re.findall(r'\bsize\s*=\s*(\d+)',value)))
    return states,allowed,{name:sorted(counts.items()) for name,counts in owners.items()}


def _cultures(game):
    cultures=[]
    for key,value in read(game,'common/cultures'):
        inner=dict(blocks(body(value)))
        if 'ethnicities' not in inner or not scalar(value,'graphics'):
            continue
        cultures.append({'heritage':scalar(value,'heritage'),'language':scalar(value,'language'),'graphics':scalar(value,'graphics'),
                         'ethnicities':inner['ethnicities'],'traditions':re.findall(r'\w+',body(inner.get('traditions','{}'))),
                         'obsessions':re.findall(r'\w+',body(inner.get('obsessions','{}')))})
    religions=[]
    for key,value in read(game,'common/religions'):
        inner=dict(blocks(body(value)))
        religions.append({'key':key,'heritage':scalar(value,'heritage'),'icon':scalar(value,'icon'),
                          'taboos':re.findall(r'\w+',body(inner.get('taboos','{}')))})
    return cultures,religions


@timed
def _mixes(game,bands):
    religion={key:scalar(value,'religion') for key,value in read(game,'common/cultures')}
    primary={tag:set(re.findall(r'\w+',body(dict(blocks(body(value))).get('cultures','{}')))) for tag,value in read(game,'common/country_definitions')}
    colonial={(state,scalar(block,'country').split(':')[-1]) for _,state,value in entries(game,'common/history/states')
              for kind,block in blocks(body(value)) if kind=='create_state' and scalar(block,'state_type')=='unincorporated'}
    started={tag for _,tag,_ in entries(game,'common/history/countries')}
    mixes={'incorporated':{band:[] for band in set(bands.values())},'unincorporated':[]}
    found=collections.Counter()
    for _,state,value in entries(game,'common/history/pops'):
        for owner,inner in blocks(body(value)):
            tag=owner.split(':')[-1]
            sizes=collections.Counter();faith=0
            for kind,pop in blocks(body(inner)):
                if kind=='create_pop':
                    culture=scalar(pop,'culture').split(':')[-1];size=int(scalar(pop,'size'))
                    sizes[culture]+=size
                    believer=scalar(pop,'religion')
                    faith+=size if believer and believer.split(':')[-1]!=religion[culture] else 0
            found.update(sizes)
            total=sum(sizes.values())
            if tag in bands and total:
                (mixes['unincorporated'] if (state,tag) in colonial else mixes['incorporated'][bands[tag]]).append(
                    {'primary':sum(s for c,s in sizes.items() if c in primary[tag])/total,
                     'others':sorted((s/total for c,s in sizes.items() if c not in primary[tag]),reverse=True),'faith':faith/total})
    owned=set().union(*(primary[tag] for tag in bands))
    return {'mixes':mixes,'primary_cultures':len(found.keys()&owned)/len(bands),'stateless_cultures':len(found.keys()-set().union(*(primary.get(tag,set()) for tag in started)))/len(bands)}


ROLES=[('ruler','ruler'),('heir','heir'),('is_general','general'),('is_admiral','admiral'),('ig_leader','ig_leader')]


def _walk(text,key):
    for kind,block in blocks(text):
        if kind==key:
            yield block
        else:
            yield from _walk(body(block),key)


@timed
def _characters(game):
    templates=dict(read(game,'common/character_templates'))
    politics={tag:found[1] for _,tag,value in entries(game,'common/history/countries') if (found:=re.search(r'effect_starting_politics_(\w+?)\s*=\s*yes',value))}
    groups={key:scalar(value,'group') for key,value in read(game,'common/laws')}
    defaults=_politics_laws(game,groups)
    laws={}
    for _,tag,value in entries(game,'common/history/countries'):
        laws[tag]=dict(defaults.get(politics.get(tag),{}))
        laws[tag].update({groups.get(law):law for law in re.findall(r'activate_law\s*=\s*law_type:(\w+)',value)})
    elective=set()
    rulers=collections.defaultdict(list);casts=collections.defaultdict(list)
    for folder in ('characters','military_formations'):
        for _,tag,value in entries(game,'common/history/'+folder):
            for block in _walk(body(value),'create_character'):
                source=templates[scalar(block,'template')] if scalar(block,'template') else block
                role=next((name for flag,name in ROLES if re.search(r'\b'+flag+r'\s*=\s*yes',source)),None)
                traits=dict(blocks(body(source))).get('traits','{}')
                record={'role':role,'female':bool(re.search(r'\bfemale\s*=\s*yes',source)),'age':1836-int(scalar(source,'birth_date').split('.')[0]) if scalar(source,'birth_date') else None,
                        'traits':re.findall(r'\w+',body(traits)),'interest_group':scalar(source,'interest_group'),'ideology':scalar(source,'ideology')}
                if role=='ruler' and tag in politics:
                    rulers[politics[tag]].append(record)
                    if 'republic' in laws[tag].get('lawgroup_governance_principles','') and re.search(r'\big_leader\s*=\s*yes',source):
                        elective.add(laws[tag]['lawgroup_distribution_of_power'])
                elif role and role!='ruler':
                    casts[tag].append(record)
    return {'rulers':dict(rulers),'casts':dict(casts),'elective_laws':elective}


def _ai(game):
    kinds={key:scalar(value,'type') for key,value in read(game,'common/ai_strategies')}
    text='\n'.join(value for _,_,value in entries(game,'common/history/ai'))
    counts=collections.Counter(re.findall(r'set_strategy\s*=\s*(\w+)',text))
    strategies={}
    for key,count in counts.items():
        if count>=3 and 'subject' not in key and kinds.get(key) in {'administrative','diplomatic','political'}:
            strategies.setdefault(kinds[key],{})[key]=count
    goals=collections.Counter(re.findall(r'(?<!\w)secret_goal\s*=\s*(\w+)',text))
    return strategies,{goal:count for goal,count in goals.items() if goal!='none'}


@timed
def _trade(game,bands):
    found={}
    for _,_,value in entries(game,'common/history/buildings'):
        for key,inner in blocks(body(value)):
            record=found.setdefault(key.split(':')[-1],{'states':0,'centers':[],'exports':[],'imports':[],'barracks':0,'naval':0,'units':0,'ships':0})
            record['states']+=1
            for kind,building in blocks(body(inner)):
                name=scalar(building,'building')
                levels=sum(map(int,re.findall(r'\blevels\s*=\s*(\d+)',building)))
                if kind=='create_building' and name=='building_trade_center':
                    record['centers'].append(levels)
                if kind=='create_building' and name in MILITARY:
                    record[MILITARY[name]]+=levels
    for _,tag,value in entries(game,'common/history/military_formations'):
        for kind,formation in blocks(body(value)):
            if kind=='create_military_formation' and tag in found:
                found[tag]['units']+=sum(int(c) for c in re.findall(r'combat_unit\s*=\s*\{[^{}]*?count\s*=\s*(\d+)',formation))
                found[tag]['ships']+=sum(int(c) for c in re.findall(r'\bship\s*=\s*\{[^{}]*?count\s*=\s*(\d+)',formation))
    for _,_,value in entries(game,'common/history/trade'):
        for key,inner in blocks(body(value)):
            record=found.get(key.split(':')[-1])
            for flow,amount in re.findall(r'add_(exports|imports)\s*=\s*(\d+)',inner):
                if record:
                    record[flow].append(int(amount))
    tiers={tag:int(tier[1]) for _,tag,value in entries(game,'common/history/countries') if (tier:=re.search(r'effect_starting_technology_tier_(\d)_tech',value))}
    return [dict(r,tag=tag,tier=tiers[tag],centers=sorted(r['centers'],reverse=True)) for tag,r in found.items() if tag in bands]


def _armies(game,groups):
    caps={key:int(found[1]) for key,value in read(game,'common/laws') if (found:=re.search(r'state_building_barrack_max_level_add\s*=\s*(\d+)',value))}
    politics={key.removeprefix('effect_starting_politics_'):next(law for law in re.findall(r'law_type:(\w+)',value) if law in caps)
              for key,value in read(game,'common/scripted_effects') if key.startswith('effect_starting_politics_')}
    return {'barracks_cap':caps,'politics_army':politics,'politics_laws':_politics_laws(game,groups)}


def _politics_laws(game,groups):
    defaults={}
    for key,value in read(game,'common/scripted_effects'):
        if key.startswith('effect_starting_politics_'):
            laws=defaults[key.removeprefix('effect_starting_politics_')]={}
            for law in re.findall(r'law_type:(\w+)',value):
                laws.setdefault(groups.get(law),law)
    return defaults


def _relations(game):
    text=lambda folder:'\n'.join(clean(path) for path in script_files(game,'common/history/'+folder))
    counts=collections.Counter(re.findall(r'\bcountry\s*=\s*c:(\w+)',text('states')))
    subject_types={key.removeprefix('subject_type_') for key,_ in read(game,'common/subject_types')}
    pacts=[(scalar(block,'type'),tag,scalar(block,'country').removeprefix('c:')) for _,tag,value in entries(game,'common/history/diplomacy')
           for kind,block in blocks(body(value)) if kind=='create_diplomatic_pact']
    subjects={b for kind,_,b in pacts if kind in subject_types}
    treaties=[];total=0
    treaty_text=text('treaties')
    for found in re.finditer(r'\bcreate_treaty\s*=',treaty_text):
        total+=1
        _,treaty=next(blocks(treaty_text[found.start():]))
        first,second=(scalar(treaty,key).removeprefix('c:') for key in ('first_country','second_country'))
        articles=[]
        for _,articles_block in blocks(body(treaty)):
            for article in re.findall(r'\{([^{}]*)\}',body(articles_block)):
                entry=dict(re.findall(r'(\w+)\s*=\s*(\S+)',article))
                articles.append(None if set(entry)-{'article','source_country','target_country'} else
                                (entry['article'],entry['source_country']=='c:'+first if 'source_country' in entry else None))
        if articles and None not in articles and counts[first] and counts[second]:
            treaties.append({'articles':articles,'years':int(re.search(r'years\s*=\s*(\d+)',treaty)[1]),
                             'sizes':(counts[first],counts[second]),'subjects':(first in subjects,second in subjects)})
    blocs=[(scalar(block,'identity'),scalar(block,'principle'),len(re.findall(r'\bmember\s*=',block)))
           for block in re.findall(r'create_power_bloc\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}',text('power_blocs'))]
    return {'pacts':[(kind,counts[a],counts[b]) for kind,a,b in pacts if counts[a] and counts[b]],'subject_types':subject_types,
            'treaties':treaties,'treaty_count':total,
            'relation_values':[int(v) for v in re.findall(r'set_relations\s*=\s*\{[^}]*?value\s*=\s*(-?\d+)',text('diplomacy'))],
            'lobbies':[(scalar(block,'type'),scalar(block,'add_interest_group').removeprefix('ig:'))
                       for block in re.findall(r'create_political_lobby\s*=\s*\{([^{}]*)\}',text('lobbies'))],
            'blocs':blocs}


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
    laws={key:(listed(value,'disallowing_laws'),listed(value,'unlocking_laws'),listed(value,'unlocking_technologies')) for key,value in read(game,'common/laws')}
    return {'law_rules':laws,'tier_techs':tiers,'building_techs':buildings,'tech_requires':{tech:needs for tech,(_,needs) in techs.items()}}


def _companies(game):
    return {key:re.findall(r'building_\w+',body(dict(blocks(body(value)))['building_types']))
            for key,value in read(game,'common/company_types') if re.search(r'flavored_company\s*=\s*no',value)}


def _natives(game):
    types={tag:scalar(value,'country_type') for tag,value in read(game,'common/country_definitions')}
    owners=set()
    for _,_,value in entries(game,'common/history/states'):
        owners|=set(re.findall(r'country\s*=\s*c:(\w+)',value))
    counted=[types.get(tag) for tag in owners if types.get(tag) in ('recognized','unrecognized','decentralized')]
    population={tag:' '.join(body(value).split()) for _,tag,value in entries(game,'common/history/population')}
    natives=[{'history':' '.join(body(value).split()),'population':population.get(tag,'')} for _,tag,value in entries(game,'common/history/countries')
             if types.get(tag)=='decentralized' and tag in owners and not _foreign(body(value))]
    return {'natives':natives,'native_share':counted.count('decentralized')/len(counted)}


def _rates(game):
    states=history=0
    for _,_,value in entries(game,'common/history/states'):
        states+=1;history+=len(re.findall(r'\badd_claim\s*=',value))
    plays=sum(len(re.findall(r'\bcreate_diplomatic_play\s*=',clean(path))) for path in script_files(game,'common/history/diplomatic_plays'))
    companies=sum(len(re.findall(r'\badd_company\s*=',clean(path))) for path in script_files(game,'common/history/countries'))
    return {'claims_per_state':history/states,'plays':plays,'company_count':companies}


@timed
def _crossings(game):
    return sum(1 for line in (game/'map_data/adjacencies.csv').read_text(encoding='utf-8-sig').splitlines() if line.split(';')[2:3]==['sea'])


def _straits(game):
    crossings=_crossings(game)
    natural=sum(len(re.findall(r'type\s*=\s*natural',clean(path))) for path in script_files(game,'common/strait_definitions'))
    return natural/crossings


@timed
def _seas(game):
    text=(game/'map_data/default.map').read_text(encoding='utf-8-sig')
    return len(re.findall(r'x[0-9A-Fa-f]{6}',re.search(r'sea_starts\s*=\s*\{([^}]*)\}',text)[1]))


@timed
def vanilla(game):
    roots={};universal={}
    for folder in COUNTRY_HISTORY+GLOBAL_HISTORY:
        for root,key,value in entries(game,'common/history/'+folder):
            roots[folder]=root
            if (folder in GLOBAL_HISTORY or key=='every_country') and not _foreign(value) and not re.match(r'(?:cu|c):',value):
                universal.setdefault(folder,[]).append(value)
    profiles,groups,bands,amendments=_profiles(game)
    economy,allowed,owners=_economy(game,bands)
    cultures,religions=_cultures(game)
    strategies,goals=_ai(game)
    terrains={k.lower():v for k,v in re.findall(r'(x[0-9A-Fa-f]{6})\s*=\s*"([^"]+)"',(game/'map_data/province_terrains.txt').read_text(encoding='utf-8-sig'))}
    regions={state:key for key,value in read(game,'common/strategic_regions') for state in re.findall(r'STATE_\w+',value)}
    every=_templates(game)
    templates=[dict(t,**economy[t['key']]) for t in every if economy.get(t['key'],{}).get('population')]
    trade=_trade(game,bands)
    rules=_law_rules(game)
    counts=[len(rules['tier_techs'][p['tier']]) for p in profiles]
    density=np.sort(np.repeat([t['population']/len(t['provinces']) for t in templates],[len(t['provinces']) for t in templates]))
    return {'templates':templates,'seas_per_state':_seas(game)/len(every),'straits_per_crossing':_straits(game),'crossings_per_state':_crossings(game)/len(every),'trade':trade,'profiles':profiles,'amendments':amendments,'allowed':allowed,'owners':owners,'law_groups':groups,'cultures':cultures,'religions':religions,
            'companies':_companies(game),**_rates(game),**_natives(game),**_mixes(game,bands),**_characters(game),**_armies(game,groups),**rules,**_relations(game),
            'tech_range':(min(counts),sum(counts)/len(counts),max(counts)),
            'province_population_range':(float(density[int(len(density)*TRIM)]),float(density.mean()),float(density[len(density)-1-int(len(density)*TRIM)])),
            'strategies':strategies,'goals':goals,'roots':roots,'universal':universal,'terrains':terrains,'regions':regions,
            'tags':set(keys(game,'common/country_definitions')),
            'goods':set(keys(game,'common/goods')),
            'patterns':sorted(p.name for p in (game/'gfx/coat_of_arms/patterns').iterdir()),
            'emblems':sorted(p.name for p in (game/'gfx/coat_of_arms/colored_emblems').glob('ce_*.dds'))}


@lru_cache(maxsize=1)
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


@lru_cache(maxsize=1)
@timed
def boxes(game):
    provinces=rasters(game)['provinces']
    colors=np.flatnonzero(np.bincount(provinces.ravel(),minlength=1<<24))
    lookup=np.zeros(1<<24,dtype=np.int32)
    lookup[colors]=np.arange(1,len(colors)+1)
    return {f'x{int(c):06x}':box for c,box in zip(colors,ndimage.find_objects(lookup[provinces]))}


@timed
def textures(game,provinces,u,v):
    source=rasters(game)
    spans=[boxes(game)[p] for p in provinces]
    box=tuple(slice(min(s[axis].start for s in spans),max(s[axis].stop for s in spans)) for axis in range(2))
    mask=np.isin(source['provinces'][box],[int(p[1:],16) for p in provinces])
    nearest=ndimage.distance_transform_edt(~mask,return_distances=False,return_indices=True)
    sy,sx=nearest[:,(v*mask.shape[0]).astype(int),(u*mask.shape[1]).astype(int)]
    return {key:image[box][sy,sx] for key,image in source.items()}
