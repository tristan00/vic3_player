import collections
import itertools
import math

from ..common import timed

ONSETS=['b','c','d','f','g','h','j','k','l','m','n','p','r','s','t','v','w','z','br','dr','gr','kr','tr','st','sh','th','ch','vl','sk','pr']
VOWELS=['a','e','i','o','u','ai','ei','ou','ia','y','ae','io']
CODAS=['','','','n','r','l','s','m','th','rd','nd','sk','x','k','t']
ENDINGS=['ia','an','or','ar','en','is','ad','um','ea','ost']
SPECIAL={'building_trade_center','building_government_administration','building_construction_sector','building_barrack','building_naval_administration'}
COASTAL={'building_fishing_wharf','building_whaling_station','building_shipyard','building_naval_fortification','building_port','building_naval_administration'}
GOODS={'building_wheat_farm':'grain','building_rye_farm':'grain','building_rice_farm':'grain','building_maize_farm':'grain','building_millet_farm':'grain',
       'building_livestock_ranch':'meat','building_logging_camp':'wood','building_fishing_wharf':'fish','building_whaling_station':'oil',
       'building_iron_mine':'iron','building_coal_mine':'coal','building_lead_mine':'lead','building_sulfur_mine':'sulfur','building_gold_mine':'gold',
       'building_textile_mill':'clothes','building_furniture_manufactory':'furniture','building_tooling_workshop':'tools','building_glassworks':'glass',
       'building_paper_mill':'paper','building_food_industry':'groceries','building_cotton_plantation':'fabric','building_tobacco_plantation':'tobacco',
       'building_tea_plantation':'tea','building_coffee_plantation':'coffee','building_sugar_plantation':'sugar','building_silk_plantation':'silk',
       'building_dye_plantation':'dye','building_opium_plantation':'opium','building_vineyard':'wine','building_banana_plantation':'fruit'}
FLAG_COLORS=['red','white','blue','yellow','green','black']
TIERS=[(1,'principality'),(3,'grand_principality'),(7,'kingdom'),(10**6,'empire')]


def sounds(rng):
    return {'onsets':rng.sample(ONSETS,12),'vowels':rng.sample(VOWELS,6),'codas':rng.sample(CODAS,6),'endings':rng.sample(ENDINGS,3)}


GENERIC={'onsets':ONSETS,'vowels':VOWELS,'codas':CODAS,'endings':ENDINGS}


def word(rng,used=None,phonology=GENERIC,syllables=(2,3),ending=True):
    while True:
        text=''.join(rng.choice(phonology['onsets'])+rng.choice(phonology['vowels'])+rng.choice(phonology['codas']) for _ in range(rng.randint(*syllables)))
        text=(text+rng.choice(phonology['endings']) if ending else text).capitalize()
        if used is None or text not in used:
            if used is not None:
                used.add(text)
            return text


def _names(rng,phonology,count,used):
    return [word(rng,used,phonology,(1,2),False) for _ in range(count)]


def _rgb(rng):
    return ' '.join(str(rng.randrange(40,230)) for _ in range(3))


def _pick(rng,pool,key):
    return rng.choice(pool)[key]


def _ownership(tag,owner,levels,state):
    if owner=='country':
        return f'country = {{ country = "c:{tag}" levels = {levels} }}'
    return f'building = {{ type = "{owner}" country = "c:{tag}" levels = {levels} region = "{state}" }}'


def _create(tag,kind,levels,owner,state):
    return f'create_building = {{ building = "{kind}" add_ownership = {{ {_ownership(tag,owner,levels,state)} }} reserves = 1 }}'


def _religions(rng,data,count,used):
    religions=[]
    for i in range(count):
        template=rng.choice(data['religions'])
        key=f'religion_interface_{i+1}'
        taboos=f'taboos = {{ {" ".join(template["taboos"])} }}' if template['taboos'] else ''
        religions.append({'key':key,'name':word(rng,used),'heritage':template['heritage'],
                          'text':f'{key} = {{ icon = "{template["icon"]}" heritage = {template["heritage"]} '
                                 f'color = {{ {" ".join(f"{rng.random():.2f}" for _ in range(3))} }} {taboos} }}'})
    return religions


def _cultures(rng,data,count,religions,used,names):
    obsessions=sorted({g for c in data['cultures'] for g in c['obsessions'] if g in data['goods']})
    cultures=[]
    for i in range(count):
        template=rng.choice(data['cultures'])
        phonology=sounds(rng)
        key=f'culture_interface_{i+1}'
        lists={kind:_names(rng,phonology,n,names) for kind,n in [('male',30),('female',30),('common',40),('noble',15)]}
        block=lambda keys:'{ '+' '.join('nm_'+k for k in keys)+' }'
        chosen=rng.sample(obsessions,rng.randint(0,2))
        religion=rng.choice(religions)
        cultures.append({'key':key,'name':word(rng,used,phonology),'phonology':phonology,'religion':religion['key'],'lists':lists,
                         'text':f'{key} = {{ color = rgb{{ {_rgb(rng)} }} religion = {religion["key"]} heritage = {template["heritage"]} '
                                f'language = {template["language"]} traditions = {{ {" ".join(template["traditions"])} }} obsessions = {{ {" ".join(chosen)} }} '
                                f'male_common_first_names = {block(lists["male"])} female_common_first_names = {block(lists["female"])} '
                                f'noble_last_names = {block(lists["noble"])} common_last_names = {block(lists["common"])} '
                                f'male_regal_first_names = {block(lists["male"][:10])} female_regal_first_names = {block(lists["female"][:10])} '
                                f'graphics = {template["graphics"]} {template["ethnicities"]} }}'})
    return cultures


def _tags(count,taken):
    letters='ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    tags=[t for t in ('X'+a+b for a,b in itertools.product(letters,repeat=2)) if t not in taken]
    if count>len(tags):
        raise ValueError(f'At most {len(tags)} countries are supported')
    return tags[:count]


def _permitted(law,laws,rules,techs):
    disallowing,unlocking,needs=rules[law]
    return needs<=techs and (not unlocking or unlocking&set(laws)) and not disallowing&set(laws) and not any(law in rules[other][0] for other in laws)


def _laws(rng,pool,rules,techs):
    laws=[]
    for group in rng.sample(sorted({g for p in pool for g in p['laws']}),len({g for p in pool for g in p['laws']})):
        law=rng.choice(pool)['laws'].get(group)
        if law and _permitted(law,laws,rules,techs):
            laws.append(law)
    return laws


FLAGS={'ruler':'ruler = yes','heir':'heir = yes','general':'is_general = yes','admiral':'is_admiral = yes','ig_leader':'ig_leader = yes'}


def _character(rng,tag,index,culture,record,interest_group):
    lists=culture['lists']
    key=f'{tag}_character_{index}'
    first=rng.choice(lists['female' if record['female'] else 'male'])
    last=rng.choice(lists['noble' if record['role'] in ('ruler','heir') else 'common'])
    born=f'birth_date = {1836-record["age"]}.{rng.randint(1,12)}.{rng.randint(1,28)} ' if record['age'] is not None else ''
    ideology=f'ideology = {record["ideology"]} ' if record['ideology'] else ''
    text=(f'{key} = {{ first_name = nm_{first} last_name = nm_{last} culture = cu:{culture["key"]} female = {"yes" if record["female"] else "no"} '
          f'{born}{"interest_group = "+interest_group+" " if interest_group else ""}{FLAGS[record["role"]]} {"ig_leader = yes " if record.get("leads") else ""}{ideology}traits = {{ {" ".join(record["traits"])} }} }}')
    return key,text


def _scale(state):
    return state['arable_land']/state['source']['arable_land']


def level(value,low,mean,top):
    return low+2*value*(mean-low) if value<=.5 else mean+(value-.5)*2*(top-mean)


def _techs(rng,base,count,requires):
    techs=set(base)
    while len(techs)<count:
        reachable=sorted(tech for tech,needs in requires.items() if tech not in techs and needs<=techs)
        if not reachable:
            raise ValueError(f'Only {len(techs)} technologies are reachable, {count} requested')
        techs.add(rng.choice(reachable))
    while len(techs)>count:
        techs.remove(rng.choice(sorted(tech for tech in techs if not any(tech in requires.get(other,()) for other in techs))))
    return techs


def _pops(rng,state,culture,candidates,religions,mix,factor):
    total=int(state['source']['population']*_scale(state)*factor)
    shares=[[culture,None,mix['primary']]]+[[other,None,part] for other,part in zip(candidates,mix['others'])]
    shares[0][2]+=1-sum(part for _,_,part in shares)
    if mix['faith']:
        largest=max(shares,key=lambda share:share[2])
        part=min(mix['faith'],largest[2])
        largest[2]-=part
        shares.append([largest[0],rng.choice([r['key'] for r in religions if r['key']!=largest[0]['religion']]),part])
    shares=[(c['key'],r,part) for c,r,part in shares]
    pops=' '.join(f'create_pop = {{ culture = {c} {"religion = "+r if r else ""} size = {int(total*s)} }}' for c,r,s in shares if int(total*s)>0)
    homelands=list(dict.fromkeys(c for c,_,s in shares if s>.1))
    return total,pops,homelands


def _buildings(rng,tag,state,band,capital,overseas,population,center,military,allowed,owners,buildable):
    key=state['key']
    lines=[]
    produced=[]
    _building=lambda tag,kind,levels,state:_create(tag,kind,levels,rng.choices(*zip(*owners[kind]))[0],state) if buildable(kind) else ''
    if capital:
        lines.append(_building(tag,'building_government_administration',1+(band<=1)+(population>1500000),key))
        if band<=2:
            lines.append(_building(tag,'building_construction_sector',max(1,3-band-rng.randint(0,1)),key))
    elif population>800000 and band<=2:
        lines.append(_building(tag,'building_government_administration',1,key))
    if center:
        lines.append(_building(tag,'building_trade_center',center,key))
    local=set(state['arable_resources'])
    levels={kind:level for kind,level in military.items() if level}
    lines+=[_building(tag,kind,level,key) for kind,level in levels.items()]
    for kind,amount in sorted(state['source']['buildings'].items()):
        if kind in SPECIAL or not amount or (kind in COASTAL and not state['coastal']) or kind not in local|allowed or not buildable(kind):
            continue
        levels[kind]=min(max(1,round(amount*_scale(state))),state['capped'].get(kind,amount*2))
        lines.append(_building(tag,kind,levels[kind],key))
        produced.append(kind)
    if overseas and state['coastal'] and 'building_port' not in levels:
        lines.append(_building(tag,'building_port',1,key))
    return lines,produced,levels


def _allot(total,weights,cap):
    counts=[0]*len(weights)
    for _ in range(min(total,cap*len(weights))):
        i=min((i for i in range(len(weights)) if counts[i]<cap),key=lambda i:(counts[i]+1)/weights[i])
        counts[i]+=1
    return counts


def _trade_profile(rng,profiles,states,tier):
    matching=[p for p in profiles if p['tier']==tier]
    gap=min(abs(p['states']-states) for p in matching)
    return rng.choice([p for p in matching if abs(p['states']-states)==gap])


def _army(band,units):
    kinds=[['combat_unit_type_line_infantry','combat_unit_type_cannon_artillery','combat_unit_type_hussars'],
           ['combat_unit_type_line_infantry','combat_unit_type_cannon_artillery','combat_unit_type_dragoons'],
           ['combat_unit_type_line_infantry','combat_unit_type_irregular_infantry','combat_unit_type_hussars'],
           ['combat_unit_type_irregular_infantry','combat_unit_type_irregular_infantry','combat_unit_type_lancers']][band]
    lines=[]
    for state,count in units:
        split=[count-count//3-count//4,count//3,count//4]
        for kind,n in zip(kinds,split):
            if n:
                lines.append(f'combat_unit = {{ type = unit_type:{kind} state_region = s:{state} count = {n} }}')
    return ' '.join(lines)


@timed
def nations(rng,data,regions,groups,capitals,state_neighbours,strategic,tech,pop):
    low,mean,top=data['tech_range']
    target=level(tech,low,mean,top)
    tech_count=lambda base:round(low+(len(base)-low)*(target-low)/(mean-low)) if target<mean else round(len(base)+target-mean)
    factor=level(pop,*data['province_population_range'])*sum(len(s['province_codes']) for s in regions)/sum(s['source']['population']*_scale(s) for s in regions)
    used=set();names=set()
    by_id={s['id']:s for s in regions}
    region_of={s['id']:r['key'] for r in strategic for s in r['states']}
    count=len(groups)
    religions=_religions(rng,data,max(2,min(len(data['religions']),count//3+1)),used)
    native=max(1,round(count*data['primary_cultures']))
    cultures=_cultures(rng,data,native+int(count*data['stateless_cultures']+rng.random()),religions,used,names)
    homes={}
    for culture in cultures[native:]:
        home=rng.choice(sorted(by_id))
        homes[culture['key']]={home,*state_neighbours[home]}
    tags=_tags(count,data['tags'])
    owner_of={sid:i for i,members in enumerate(groups) for sid in members}
    neighbours=[set() for _ in range(count)]
    for sid,others in state_neighbours.items():
        for other in others:
            if owner_of[other]!=owner_of[sid]:
                neighbours[owner_of[sid]].add(owner_of[other])
    primary=[None]*count
    for i in range(count):
        fresh=[c for c in cultures[:native] if c not in primary]
        primary[i]=fresh[0] if fresh else rng.choice([primary[j] for j in neighbours[i] if primary[j]] or cultures[:native])
    band_weights={b:sum(p['band']==b for p in data['profiles']) for b in range(4)}
    countries=[]
    files={}
    localization=[]
    history={folder:list(data['universal'].get(folder,[])) for folder in data['roots']}
    for folder in ['diplomacy','diplomatic_plays','military_deployments','power_blocs','treaties','lobbies','trade','states','pops','buildings']:
        history.setdefault(folder,[])
    definitions=[];templates=[]
    natives={i for i in range(count) if rng.random()<data['native_share']}
    if len(natives)==count:
        natives.discard(max(range(count),key=lambda i:len(groups[i])))
    for i,(tag,members) in enumerate(zip(tags,groups)):
        band=rng.choices(list(band_weights),weights=list(band_weights.values()))[0]
        pool=[p for p in data['profiles'] if p['band']==band]
        culture=primary[i]
        states=[by_id[s] for s in members]
        capital=by_id[capitals[i]]
        name=word(rng,used,culture['phonology'])
        tier=next(t for limit,t in TIERS if len(states)<=limit)
        country_type='decentralized' if i in natives else _pick(rng,pool,'type')
        politics=_pick(rng,pool,'politics')
        ruling=rng.choice([p['ruling'] for p in pool if p['ruling']])
        tax,wealth,literacy=(_pick(rng,pool,k) for k in ('tax','wealth','literacy'))
        technology=_pick(rng,pool,'tier')
        base=data['tier_techs'][technology]
        techs=_techs(rng,base,tech_count(base),data['tech_requires'])
        laws=_laws(rng,pool,data['law_rules'],techs)
        color=_rgb(rng)
        definitions.append(f'{tag} = {{ color = {{ {color} }} country_type = {country_type} tier = {tier} cultures = {{ {culture["key"]} }} capital = {capital["key"]} }}')
        one,two,three=rng.sample(FLAG_COLORS,3)
        files[f'common/coat_of_arms/coat_of_arms/{tag}.txt']=(f'{tag} = {{ pattern = "{rng.choice(data["patterns"])}" color1 = "{one}" color2 = "{two}" '
            f'colored_emblem = {{ texture = "{rng.choice(data["emblems"])}" color1 = "{three}" color2 = "{one}" instance = {{ position = {{ 0.5 0.5 }} scale = {{ 0.6 0.6 }} }} }} }}')
        localization+=[f' {tag}: "{name}"',f' {tag}_ADJ: "{name}"']
        if i in natives:
            countries.append(_native(rng,data,tag,name,culture,states,capital,[c for c in cultures if c is not culture],religions,band,factor,history,color))
            continue
        lines=[f'add_technology_researched = {name}' for name in sorted(techs)]+[f'effect_starting_politics_{politics} = yes']
        lines+=[f'set_tax_level = {tax}'] if tax else []
        lines+=[f'activate_law = law_type:{law}' for law in laws]
        lines+=[f'ig:{ig} ?= {{ add_ruling_interest_group = yes }}' for ig in ruling]
        lines+=_pick(rng,pool,'policies')
        history['countries'].append(f'c:{tag} ?= {{ {" ".join(lines)} }}')
        people=[f'effect_starting_pop_wealth_{wealth} = yes'] if wealth else []
        people+=[f'effect_starting_pop_literacy_{literacy} = yes'] if literacy else []
        history['population'].append(f'c:{tag} ?= {{ {" ".join(people)} }}')
        coastal=[s for s in states if s['coastal']]
        reachable={capital['id']}
        stack=[capital['id']]
        while stack:
            for other in state_neighbours[stack.pop()]:
                if other in members and other not in reachable:
                    reachable.add(other);stack.append(other)
        units=[];produced={};holdings=[]
        trade=_trade_profile(rng,data['trade'],len(states),technology)
        buildable=lambda kind:data['building_techs'].get(kind,set())<=techs
        ranked=[capital]+sorted((s for s in states if s is not capital),key=lambda s:-s['arable_land'])
        centers={s['id']:level for s,level in zip(ranked,trade['centers'])}
        populations=[]
        for state in states:
            local=[c for c in cultures if c is not culture and (any(c is primary[j] for j in neighbours[i]) or state['id'] in homes.get(c['key'],()))]
            rest=[c for c in cultures if c is not culture and c not in local]
            mix=rng.choice(data['mixes']['incorporated'][band] if state['id'] in reachable else data['mixes']['unincorporated'])
            populations.append(_pops(rng,state,culture,rng.sample(local,len(local))+rng.sample(rest,len(rest)),religions,mix,factor))
        army_law=next((law for law in laws if law in data['barracks_cap']),data['politics_army'][politics])
        if not _permitted(army_law,laws,data['law_rules'],techs):
            army_law=next(law for law in data['barracks_cap'] if _permitted(law,laws,data['law_rules'],techs))
        weights=[size for size,_,_ in populations]
        garrison=_allot(trade['barracks'] if buildable('building_barrack') else 0,weights,data['barracks_cap'][army_law])
        troops_by_state=_allot(trade['units'],weights,data['barracks_cap'][army_law])
        naval_home=max(coastal,key=lambda s:(s is capital,s['arable_land'])) if coastal else None
        navy=trade['ships'] if naval_home and trade['naval'] and buildable('building_naval_administration') else 0
        for state,(size,pops,homelands),troops,regiments in zip(states,populations,garrison,troops_by_state):
            state['country']=tag
            state_type='incorporated' if state['id'] in reachable else 'unincorporated'
            history['states'].append(f's:{state["key"]} = {{ create_state = {{ country = c:{tag} state_type = {state_type} '
                                     f'owned_provinces = {{ {" ".join(state["province_codes"])} }} }} {" ".join("add_homeland = cu:"+h for h in homelands)} }}')
            history['pops'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {pops} }} }}')
            military={'building_barrack':troops,'building_naval_administration':trade['naval'] if state is naval_home and buildable('building_naval_administration') else 0}
            buildings,made,levels=_buildings(rng,tag,state,band,state is capital,state['id'] not in reachable,size,centers.get(state['id']),military,data['allowed'][band],data['owners'],buildable)
            history['buildings'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {" ".join(buildings)} }} }}')
            holdings+=[(level,kind,state['key']) for kind,level in levels.items()]
            if regiments:
                units.append((state['key'],regiments))
            for building in made:
                if building in GOODS and GOODS[building] in data['goods']:
                    produced.setdefault(GOODS[building],state['key'])
        held=lambda group:next((law for law in laws if data['law_groups'].get(law)==group),data['politics_laws'][politics].get(group,''))
        governance=held('lawgroup_governance_principles')
        vanilla_cast=data['casts'].get(trade['tag'],[])
        ruler=dict(rng.choice(data['rulers'][politics]),leads='republic' in governance and held('lawgroup_distribution_of_power') in data['elective_laws'])
        leaders={r['interest_group']:r for r in vanilla_cast if r['role']=='ig_leader' and not (ruler['leads'] and r['interest_group']==ruling[0])}
        chosen=([(ruler,ruling[0])]
                +[(r,r['interest_group']) for r in vanilla_cast if r['role']=='heir' and 'republic' not in governance][:1]
                +[(r,group) for group,r in leaders.items()]
                +[(r,r['interest_group']) for r in vanilla_cast if r['role']=='general' or (r['role']=='admiral' and navy)])
        cast=[];commanders=[];monarchs=[]
        for index,(record,group) in enumerate(chosen,1):
            key,text=_character(rng,tag,index,culture,record,group)
            templates.append(text)
            if record['role'] in ('general','admiral'):
                commanders.append((key,'army' if record['role']=='general' else 'fleet'))
            else:
                cast.append(key)
            if record['role'] in ('ruler','heir'):
                monarchs.append(key)
        formations=[f'create_military_formation = {{ type = army hq_region = sr:{region_of[capital["id"]]} save_scope_as = army_{tag} {_army(band,units)} }}'] if units else []
        if navy:
            ship='ship_type_ship_of_the_line' if band==0 else 'ship_type_frigate'
            formations.append(f'create_military_formation = {{ type = fleet hq_region = sr:{region_of[naval_home["id"]]} save_scope_as = fleet_{tag} ship = {{ type = ship_type:{ship} count = {navy} }} }}')
        for key,branch in commanders:
            formations.append(f'create_character = {{ template = {key} save_scope_as = {key} }}')
            if branch=='fleet' or units:
                formations.append(f'scope:{key} = {{ transfer_to_formation = scope:{branch}_{tag} }}')
        history['military_formations'].append(f'c:{tag} ?= {{ {" ".join(formations)} }}')
        history['characters']+=[f'c:{tag} ?= {{ create_character = {{ template = {key} }} }}' for key in cast]
        if band==0:
            history['production_methods'].append(f'c:{tag} ?= {{ activate_production_method = {{ building_type = building_urban_center production_method = pm_market_squares }} }}')
        strategies=[rng.choices(list(options),weights=list(options.values()))[0] for options in data['strategies'].values()]
        history['ai'].append(f'c:{tag} ?= {{ {" ".join("set_strategy = "+s for s in strategies)} }}')
        countries.append({'tag':tag,'name':name,'states':[s['key'] for s in states],'capital':capital['key'],'culture':culture['key'],
                          'religion':culture['religion'],'color':[int(c) for c in color.split()],'band':band,'technology_tier':technology,
                          'country_type':country_type,'tier':tier,'politics':politics,'laws':laws,'ruling':ruling,'produced':produced,'trade':trade,'holdings':holdings,'armed':bool(units),'army':sum(count for _,count in units),'navy':navy,'monarchs':monarchs,'situations':0,
                          'provinces':[p for s in states for p in s['province_codes']]})
    _diplomacy(rng,data,countries,neighbours,history,localization)
    _claims(rng,data,regions,state_neighbours,history,{c['tag'] for c in countries if c['country_type']=='decentralized'})
    _companies(rng,data,countries,history)
    _amendments(rng,data,countries,history)
    for culture in cultures:
        history['cultures'].append(f'cu:{culture["key"]} = {{ set_fervor = {rng.randint(5,40)} }}')
        localization.append(f' {culture["key"]}: "{culture["name"]}"')
        localization+=[f' nm_{n}: "{n}"' for n in itertools.chain(*culture['lists'].values())]
    for religion in religions:
        localization+=[f' {religion["key"]}: "{religion["name"]}"',f' {religion["key"]}_ADJ: "{religion["name"]}"']
    roots=dict(data['roots'],diplomacy='DIPLOMACY',diplomatic_plays='DIPLOMATIC_PLAYS',military_deployments='MILITARY_DEPLOYMENTS',power_blocs='POWER_BLOCS',treaties='TREATIES',lobbies='LOBBIES',trade='TRADE',
               states='STATES',pops='POPS',buildings='BUILDINGS')
    for folder,lines in history.items():
        files[f'common/history/{folder}/interface.txt']=roots[folder]+' = {\n'+'\n'.join(lines)+'\n}'
    files['common/country_definitions/interface.txt']='\n'.join(definitions)
    files['common/character_templates/interface.txt']='\n'.join(templates)
    files['common/cultures/interface.txt']='\n'.join(c['text'] for c in cultures)
    files['common/religions/interface.txt']='\n'.join(r['text'] for r in religions)
    modifiers=[]
    kinds=[('standard_of_living','state_{}_standard_of_living_add'),('cultural_acceptance','country_{}_cultural_acceptance_add'),('fervor_target','country_fervor_target_{}_add')]
    for key,used in [(c['key'],kinds) for c in cultures]+[(r['key'],kinds[:1]) for r in religions]:
        for kind,modifier in used:
            for sign in ['positive','negative']:
                modifiers.append(f'{key}_{kind}_modifier_{sign} = {{ icon = "gfx/interface/icons/timed_modifier_icons/modifier_flag_{sign}.dds" {modifier.format(key)} = 1 }}')
    files['common/static_modifiers/interface.txt']='\n'.join(modifiers)
    types=[kind.format(key) for key,used in [(c['key'],kinds) for c in cultures]+[(r['key'],kinds[:1]) for r in religions] for _,kind in used]
    files['common/modifier_type_definitions/interface.txt']='\n'.join(f'{t} = {{ decimals = 1 color = good game_data = {{ ai_value = 0 }} }}' for t in types)
    return {'countries':countries,'files':files,'localization':localization}


def _native(rng,data,tag,name,culture,states,capital,others,religions,band,factor,history,color):
    profile=rng.choice(data['natives'])
    history['countries'].append(f'c:{tag} ?= {{ {profile["history"]} }}')
    history['population'].append(f'c:{tag} ?= {{ {profile["population"]} }}')
    for state in states:
        _,pops,homelands=_pops(rng,state,culture,rng.sample(others,len(others)),religions,rng.choice(data['mixes']['incorporated'][band]),factor)
        state['country']=tag
        history['states'].append(f's:{state["key"]} = {{ create_state = {{ country = c:{tag} owned_provinces = {{ {" ".join(state["province_codes"])} }} }} '
                                 f'{" ".join("add_homeland = cu:"+h for h in homelands)} }}')
        history['pops'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {pops} }} }}')
        history['buildings'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ }} }}')
    return {'tag':tag,'name':name,'states':[s['key'] for s in states],'capital':capital['key'],'culture':culture['key'],'religion':culture['religion'],
            'color':[int(c) for c in color.split()],'band':band,'country_type':'decentralized','laws':[],'ruling':[],'produced':{},'holdings':[],
            'armed':False,'army':0,'navy':0,'monarchs':[],'situations':0,'provinces':[p for s in states for p in s['province_codes']]}


def _chance(data,count):
    return count/len(data['trade'])


def _picked(rng,data,count,total,eligible):
    chosen=[x for x in eligible if rng.random()<min(1,_chance(data,count)*total/len(eligible))] if eligible else []
    if eligible and not chosen:
        chosen=[rng.choice(eligible)]
    return rng.sample(chosen,len(chosen))


def _situation(*countries):
    for country in countries:
        country['situations']+=1


def _claims(rng,data,regions,state_neighbours,history,natives):
    owner={s['id']:s['country'] for s in regions}
    for state in regions:
        rivals=sorted({owner[n] for n in state_neighbours[state['id']]}-{state['country']}-natives)
        if rivals and rng.random()<data['claims_per_state']:
            history['states'].append(f's:{state["key"]} = {{ add_claim = c:{rng.choice(rivals)} }}')


def _companies(rng,data,countries,history):
    options=lambda country:sorted(((level,company,state) for level,kind,state in country['holdings'] for company,kinds in data['companies'].items()
                                   if kind in kinds and company not in taken),reverse=True)
    taken=set()
    for country in _picked(rng,data,data['company_count'],len(countries),[c for c in countries if options(c)]):
        if options(country):
            _,company,state=options(country)[0];taken.add(company)
            _situation(country)
            history['countries'].append(f'c:{country["tag"]} ?= {{ add_company = company_type:{company} company:{company} = {{ set_company_establishment_date = 1830.1.1 set_company_state_region = s:{state} }} }}')


def _amendments(rng,data,countries,history):
    for country in _picked(rng,data,len(data['amendments']),len(countries),[c for c in countries if any(law in c['laws'] for law,_ in data['amendments'])]):
        options=[text for law,text in data['amendments'] if law in country['laws']]
        if options:
            _situation(country)
            history['countries'].append(f'c:{country["tag"]} ?= {{ {rng.choice(options)} }}')


def _partner(rng,size,i,candidates,ratio):
    fits=[j for j in candidates if j!=i and (abs(math.log(ratio))<math.log(1.5) or (size[i]>size[j])==(ratio>1))]
    return min(fits,key=lambda j:(abs(math.log(size[i]/size[j])-math.log(ratio)),rng.random())) if fits else None


def _diplomacy(rng,data,countries,neighbours,history,localization):
    n=len(countries);size=[len(c['states']) for c in countries];tags=[c['tag'] for c in countries]
    natives={i for i,c in enumerate(countries) if c['country_type']=='decentralized'}
    active=[i for i in range(n) if i not in natives]
    neighbours=[set() if i in natives else set(others)-natives for i,others in enumerate(neighbours)]
    say=lambda folder,i,text:history[folder].append(f'c:{tags[i]} ?= {{ {text} }}')
    situation=lambda *indices:_situation(*(countries[i] for i in indices))
    pacts=collections.defaultdict(list)
    for kind,first,second in data['pacts']:
        pacts[kind].append(first/second)
    overlord={}
    kinds=[kind for kind in sorted(pacts) if kind in data['subject_types']]
    subjects=sum(len(pacts[kind]) for kind in kinds)
    for j in _picked(rng,data,subjects,n,[j for j in active if size[j]<max(size)]):
        if j in overlord.values():
            continue
        kind=rng.choices(kinds,weights=[len(pacts[k]) for k in kinds])[0]
        i=_partner(rng,size,j,[i for i in active if i not in overlord],1/rng.choice(pacts[kind]))
        if i is not None:
            overlord[j]=i
            situation(i,j)
            say('diplomacy',i,f'create_diplomatic_pact = {{ country = c:{tags[j]} type = {kind} }}')
            if kind=='personal_union':
                history['characters']=[line for line in history['characters'] if not any(f'template = {key} ' in line for key in countries[j]['monarchs'])]
    relation={}
    for i in active:
        count=len(data['relation_values'])/len(data['trade'])
        for j in rng.sample(sorted(neighbours[i]),min(len(neighbours[i]),int(count)+(rng.random()<count%1))):
            relation[(i,j)]=relation[(j,i)]=rng.choice(data['relation_values'])
            say('diplomacy',i,f'set_relations = {{ country = c:{tags[j]} value = {relation[(i,j)]} }}')
    free=lambda i:i not in overlord and i not in natives
    feeling=lambda i,j:relation.get((i,j),0)
    for kind,ratios in sorted(pacts.items()):
        if kind in data['subject_types'] or kind not in ('rivalry','embargo'):
            continue
        for i in _picked(rng,data,len(ratios),n,[i for i in range(n) if free(i) and any(free(j) for j in neighbours[i])]):
                j=_partner(rng,size,i,[j for j in neighbours[i] if free(j)],rng.choice(ratios))
                if j is not None:
                    situation(i,j)
                    say('diplomacy',i,f'create_diplomatic_pact = {{ country = c:{tags[j]} type = {kind} }}')
    for kind,ratios in sorted(pacts.items()):
        if kind in data['subject_types'] or kind in ('rivalry','embargo'):
            continue
        for j,i in overlord.items():
            if rng.random()<len(ratios)/subjects:
                say('diplomacy',i,f'create_diplomatic_pact = {{ country = c:{tags[j]} type = {kind} }}')
    targets={'protect':lambda i:[j for j in range(n) if overlord.get(j)==i] or [j for j in neighbours[i] if size[j]<size[i]],
             'conquer':lambda i:sorted(neighbours[i]),
             'befriend':lambda i:[j for j in neighbours[i] if feeling(i,j)>0] or sorted(neighbours[i]),
             'reconcile':lambda i:[j for j in neighbours[i] if feeling(i,j)<0],
             'antagonize':lambda i:[j for j in neighbours[i] if feeling(i,j)<0] or sorted(neighbours[i]),
             'defy':lambda i:[overlord[i]] if i in overlord else []}
    for goal,count in sorted(data['goals'].items()):
        for i in _picked(rng,data,count,n,[i for i in active if goal in targets and targets[goal](i)]):
            say('ai',i,f'set_secret_goal = {{ country = c:{tags[rng.choice(sorted(targets[goal](i)))]} secret_goal = {goal} }}')
    lobbies=collections.defaultdict(list)
    for kind,group in data['lobbies']:
        lobbies[kind].append(group)
    aim={'lobby_anti_country':lambda i:min(neighbours[i],key=lambda j:(feeling(i,j),tags[j])) if neighbours[i] else None,
         'lobby_pro_country':lambda i:max(neighbours[i],key=lambda j:(feeling(i,j),tags[j])) if neighbours[i] else None,
         'lobby_anti_overlord':lambda i:overlord.get(i),'lobby_pro_overlord':lambda i:overlord.get(i)}
    for kind,groups in sorted(lobbies.items()):
        rate=len(groups)/subjects if kind.endswith('overlord') else _chance(data,len(groups))
        for i in active:
            j=aim[kind](i)
            if j is not None and rng.random()<rate:
                say('lobbies',i,f'create_political_lobby = {{ type = {kind} target = c:{tags[j]} add_interest_group = ig:{rng.choice(groups)} }}')
    for _ in range(max(1,int(n*data['treaty_count']/len(data['trade']))+(rng.random()<n*data['treaty_count']/len(data['trade'])%1))):
        for treaty in rng.sample(data['treaties'],len(data['treaties'])):
            first,second=treaty['sizes']
            stronger=lambda i,j:all(countries[a]['army']>countries[b]['army'] for kind,forward in treaty['articles'] if kind=='military_assistance' and forward is not None
                                    for a,b in [(i,j) if forward else (j,i)])
            pairs=[(i,j) for i in active for j in active if i!=j and (size[i]>size[j])==(first>second) and (size[i]<size[j])==(first<second)
                   and (i in overlord,j in overlord)==treaty['subjects'] and overlord.get(i)!=j and overlord.get(j)!=i and stronger(i,j)]
            if pairs:
                break
        else:
            break
        i,j=max(pairs,key=lambda p:(feeling(*p),rng.random()))
        situation(i,j)
        ends=lambda forward:f'source_country = c:{tags[i if forward else j]} target_country = c:{tags[j if forward else i]}'
        articles=' '.join(f'{{ article = {kind} {"" if forward is None else ends(forward)} }}' for kind,forward in treaty['articles'])
        history['treaties'].append(f'create_treaty = {{ first_country = c:{tags[i]} second_country = c:{tags[j]} is_draft = no '
                                   f'entered_into_force_on = 1830.{rng.randint(1,12)}.1 binding_period = {{ years = {treaty["years"]} }} articles_to_create = {{ {articles} }} }}')
    fighting=set()
    armed=lambda i:free(i) and countries[i]['armed']
    for i in _picked(rng,data,data['plays'],n,[i for i in range(n) if armed(i) and any(armed(j) for j in neighbours[i])]):
            options=[j for j in neighbours[i] if armed(j) and j not in fighting] if i not in fighting else []
            if options:
                j=min(options,key=lambda j:(feeling(i,j),tags[j]));fighting|={i,j}
                situation(i,j)
                say('diplomatic_plays',i,f'create_diplomatic_play = {{ target_state = c:{tags[j]}.capital war = yes type = dp_annex_war '
                                          f'add_war_goal = {{ holder = c:{tags[j]} type = revoke_all_claims target_country = c:{tags[i]} }} }}')
                for k in (i,j):
                    say('military_deployments',k,'every_military_formation = { limit = { is_army = yes } fully_mobilize_army = yes }')
    leaders=sorted((i for i in range(n) if free(i) and countries[i]['country_type']=='recognized'),key=lambda i:(-size[i],tags[i]))
    members=set()
    for i in _picked(rng,data,len(data['blocs']),n,leaders):
        if i not in members:
            identity,principle,count=rng.choice(data['blocs'])
            joined=[j for j in sorted(neighbours[i],key=lambda j:-feeling(i,j)) if free(j) and j not in members and j not in leaders and feeling(i,j)>0][:count]
            members|=set(joined)|{i}
            situation(i,*joined)
            history['power_blocs'].append(f'c:{tags[i]} ?= {{ create_power_bloc = {{ name = POWER_BLOC_{tags[i]} map_color = {{ {_rgb(rng)} }} founding_date = 1820.1.1 '
                                          f'identity = {identity} principle = {principle} {" ".join("member = c:"+tags[j] for j in joined)} }} }}')
            localization.append(f' POWER_BLOC_{tags[i]}: "{countries[i]["name"]} Bloc"')
    for country in (countries[i] for i in active):
        tag=country['tag']
        for good,amount in zip(rng.sample(sorted(country['produced']),len(country['produced'])),country['trade']['exports']):
            history['trade'].append(f's:{country["produced"][good]} = {{ region_state:{tag} = {{ sg:{good} = {{ add_exports = {amount} }} }} }}')
        wanted=sorted({g for g in GOODS.values() if g in data['goods'] and g not in country['produced']})
        for good,amount in zip(rng.sample(wanted,len(wanted)),country['trade']['imports']):
            history['trade'].append(f's:{country["capital"]} = {{ region_state:{tag} = {{ sg:{good} = {{ add_imports = {amount} }} }} }}')
