import random
import re

from ..common import timed, timed_often
from ..script import blocks, body, scalar
from .nations import _rgb, _tags, _techs, word
from .source import select_countries
from .buildings import expected, project
from .military import military as formations
from .international import connect, conquests, found, members, opening_war, pacts, split
from .cultures import population


TYPES={'recognized':.9,'company':.1}


@timed_often
def commands(text):
    tokens=list(re.finditer(r'"(?:\\.|[^"\\])*"|\?=|[{}]|[^\s{}=?]+|=',text))
    result=[]
    i=0
    while i+2<len(tokens):
        key,operator=tokens[i][0],tokens[i+1][0]
        if operator not in ('=','?='):
            i+=1
            continue
        start=i+2
        end=start
        if tokens[start][0]=='{':
            depth=1
            while depth:
                end+=1
                depth+=(tokens[end][0]=='{')-(tokens[end][0]=='}')
        result.append((key,operator,text[tokens[start].start():tokens[end].end()]))
        i=end+1
    return result


@timed_often
def remap(text,tags,states,group_map):
    text=re.sub(r'\b(c|region_state):([A-Z0-9]{3})\b',lambda m:m[1]+':'+tags.get(m[2],m[2]),text)
    text=re.sub(r'\bSTATE_\w+',lambda m:states.get(m[0],m[0]),text)
    return re.sub(r'\bsr:(\w+)',lambda m:'sr:'+group_map.get(m[1],m[1]),text)


@timed_often
def history_text(text,tags,states,group_map):
    text=re.sub(r'\bhome_region\s*=\s*(?:s:)?STATE_\w+','home_region = random',text)
    output=[]
    dropped_branch=False
    for key,operator,value in commands(text):
        heading=key+' '+value
        refs=set(re.findall(r'\b(?:c|region_state):([A-Z0-9]{3})\b',heading))-tags.keys()
        missing=set(re.findall(r'\bSTATE_\w+',heading))-states.keys()
        absent_groups=set(re.findall(r'\bsr:(\w+)',heading))-group_map.keys()
        provinces=re.findall(r'\bp:x[0-9A-Fa-f]+',heading)
        invalid=bool(refs or missing or absent_groups or provinces)
        if key=='limit' and invalid:
            return ''
        if key not in ('else','else_if'):
            dropped_branch=False
        if key in ('else','else_if') and dropped_branch:
            continue
        head_invalid=(set(re.findall(r'\b(?:c|region_state):([A-Z0-9]{3})\b',key))-tags.keys() or set(re.findall(r'\bSTATE_\w+',key))-states.keys())
        if head_invalid:
            continue
        wrapper=key in ('if','else_if','else') or key.startswith(('c:','s:','cu:','company:','every_','random_'))
        if wrapper:
            inner=history_text(body(value),tags,states,group_map)
            if not inner:
                dropped_branch=key in ('if','else_if')
                continue
            output.append(f'{remap(key,tags,states,group_map)} {operator} {{ {inner} }}')
        elif not invalid:
            output.append(remap(f'{key} {operator} {value}',tags,states,group_map))
    return '\n'.join(output)


@timed_often
def starting_history(data,source,techs):
    text=' '.join(data['history']['countries'].get('c:'+source,[]))
    kept=[f'{key} {operator} {value}' for key,operator,value in commands(text)
          if not re.fullmatch(r'effect_starting_technology_tier_\d+_tech',key) and key not in ('add_technology_researched','add_era_researched')]
    return '\n'.join([*(f'add_technology_researched = {t}' for t in sorted(techs)),*kept])


@timed_often
def politics(text,data,techs,capacity):
    def base(law):
        while law in data['law_parents']:
            law=data['law_parents'][law]
        return law

    records=[]
    for key,op,value in commands(text):
        if key.startswith('effect_starting_politics_'):
            records.extend(('activate_law','=',f'law_type:{law}') for law in data['politics_laws'][key.removeprefix('effect_starting_politics_')].values())
        else:
            records.append((key,op,value))
    laws={}
    remaining=[]
    setup=[]
    for key,op,value in records:
        if key=='activate_law':
            law=base(value.removeprefix('law_type:'))
            laws[data['law_groups'][law]]=law
        elif key=='add_technology_researched':
            setup.append(f'{key} {op} {value}')
        elif key=='set_institution_investment_level':
            remaining.append(f'if = {{ limit = {{ has_institution = {scalar(value,"institution")} }} {key} {op} {value} }}')
        else:
            remaining.append(f'{key} {op} {value}')
    choices={law for law in data['law_rules'] if law not in data['law_parents'] and law!='law_chiefdom'}
    laws.setdefault('lawgroup_army_model','law_peasant_levies')
    for group,wanted in list(laws.items()):
        eligible=[law for law in choices if data['law_groups'][law]==group and data['law_rules'][law][2]<=techs
                  and (group!='lawgroup_army_model' or data['barracks_cap'][law]>=capacity)]
        if not eligible:
            raise ValueError(f'No researched law supports {group} with {capacity} barracks in one state')
        laws[group]=min(eligible,key=lambda law:(abs(data['law_progress'][law]-data['law_progress'][wanted]),law!=wanted,law))
    setup.extend(f'activate_law = law_type:{law}' for law in laws.values())
    return '\n'.join(setup+remaining)


@timed
def nations(rng,data,states,groups,capitals,strategic,country_pool,ideology_uniformity,copies,primary_culture_share,military,interconnectedness,antagonism,war,sides):
    by_id={s['id']:s for s in states}
    group_of={s['id']:r['key'] for r in strategic for s in r['states']}
    identity_rng=random.Random(rng.getrandbits(64))
    control_rng=random.Random(rng.getrandbits(64))
    culture_rng=random.Random(rng.getrandbits(64))
    relation_rng=random.Random(rng.getrandbits(64))
    conquest_rng=random.Random(rng.getrandbits(64))
    war_rng=random.Random(rng.getrandbits(64))
    donors=rng.sample(select_countries(data,country_pool),len(groups))
    types=[kind if kind in TYPES else identity_rng.choices(list(TYPES),list(TYPES.values()))[0] for kind in (data['source_countries'][donor]['type'] for donor in donors)]
    tags=_tags(len(groups),data['tags'])
    count=round(len(groups)*copies)
    selected=identity_rng.sample(range(len(groups)),count)
    for index in selected:
        tags[index]=donors[index]
    tag_map=dict(zip(donors,tags))
    conquest_targets=conquests(conquest_rng,antagonism,tags)
    state_map={}
    for state in states:
        state_map.setdefault(state['source']['key'],state['key'])
    group_map={r['source_group']:r['key'] for r in strategic}
    counts=[len(data['source_countries'][donor]['techs']) for donor in donors]
    histories={folder:[] for folder in data['history']}
    files={}
    definitions=[]
    localization=[]
    countries=[]
    source_companies={}
    for tag,records in data['history']['countries'].items():
        for text in records:
            for key,value in blocks(text):
                if key.startswith('company:'):
                    source_companies[key.split(':')[1]]=(tag.removeprefix('c:'),value)
    state_countries={by_id[ident]['key']:tag for tag,group in zip(tags,groups) for ident in group}
    company_states={}
    for key,(_,value) in source_companies.items():
        home=scalar(value,'set_company_state_region').removeprefix('s:')
        holdings={state['key']:sum(int(scalar(owner,'levels')) for record in state['source']['building_records']
                                  for kind,ownership in blocks(body(record)) if kind=='add_ownership'
                                  for kind,owner in blocks(body(ownership)) if kind=='company' and scalar(owner,'type')==key)
                  for state in states}
        candidates=[state for state in states if state['source']['key']==home or holdings[state['key']]]
        if candidates:
            company_states[key]=min(candidates,key=lambda s:(s['source']['key']!=home,-holdings[s['key']],s['id']))['key']
    companies={key:state_countries[state] for key,state in company_states.items()}
    scales={kind:military if kind in data['military_buildings'] else 1
            for kind in data['military_buildings']|{'building_government_administration','building_construction_sector','building_trade_center'}}
    for state in states:
        state['buildings']=expected(state['source']['building_records'],scales)
    known=[]
    for donor,group,count in zip(donors,groups,counts):
        capacity=max(by_id[i]['buildings'].get('building_barrack',0) for i in group)
        required={'standing_army','military_drill'} if capacity>data['barracks_cap']['law_peasant_levies'] else set()
        known.append(_techs(rng,data['source_countries'][donor]['techs'],count,data['tech_requires'],required))
        for ident in group:
            state=by_id[ident]
            state['excluded_buildings']={kind:{'levels':amount,'missing_technologies':sorted(data['building_techs'][kind]-known[-1])}
                                         for kind,amount in state['buildings'].items() if not data['building_techs'][kind]<=known[-1]}
            state['buildings']={kind:amount for kind,amount in state['buildings'].items() if kind not in state['excluded_buildings']}
            state['eligible_records']=[r for r in state['source']['building_records'] if scalar(r,'building') in state['buildings']]
    strength=[[sum(sum(by_id[i]['buildings'].values()) for i in group),sum(by_id[i]['buildings'].get('building_barrack',0) for i in group),
               sum(int(scalar(record,'size')) for i in group for record in by_id[i]['source']['pop_records'])] for group in groups]
    if sides:
        overlords,blocs=split(relation_rng,sides,strength,types,data['subject_rules'])
    else:
        overlords,blocs=connect(relation_rng,interconnectedness,[levels for levels,_,_ in strength],types,[by_id[i]['center'] for i in capitals],data['subject_rules'])
    bloc_of={member:bloc for bloc in blocs for member in bloc['members']}
    starting_war=opening_war(war_rng,war,[i for i in range(len(tags)) if i not in overlords])
    if starting_war:
        starting_war=[{'country':tags[holder],'target':tags[owner],'state':by_id[war_rng.choice(groups[owner])]['key']}
                      for holder,owner in (starting_war,starting_war[::-1])]
        opener,reply=starting_war
        histories['diplomatic_plays'].append(f"c:{opener['country']} ?= {{ create_diplomatic_play = {{ target_state = s:{opener['state']}.region_state:{opener['target']} "
                                             f"war = yes type = dp_conquer_state add_war_goal = {{ holder = c:{reply['country']} type = conquer_state "
                                             f"target_state = s:{reply['state']}.region_state:{reply['target']} }} }} }}")
    vanilla_blocs={}
    for index,(tag,donor,group,capital_id) in enumerate(zip(tags,donors,groups,capitals)):
        source=data['source_countries'][donor]
        capital=by_id[capital_id]
        local_tags=dict(tag_map,**{donor:tag})
        local_states=dict(state_map)
        for ident in group:
            state=by_id[ident]
            local_states[state['source']['key']]=state['key']
        techs=known[index]
        country_text=starting_history(data,donor,techs)
        uniformity=control_rng.uniform(*ideology_uniformity)
        realized=population(culture_rng,data,[by_id[i] for i in group],source['cultures'],control_rng.uniform(*primary_culture_share))
        country_text+=f'\nset_variable = {{ name = interface_ideology_uniformity value = {100*uniformity:.5f} }}'
        country_text='\n'.join(f'{key} {op} {value}' for key,op,value in commands(country_text)
                               if key not in ('add_company','set_capital','set_market_capital') and not key.startswith('company:'))
        country_text=politics(country_text,data,techs,max(by_id[i]['buildings'].get('building_barrack',0) for i in group))
        country_text=history_text(country_text,local_tags,local_states,group_map)
        for key,owner in companies.items():
            if owner==tag:
                setup=source_companies[key][1]
                home=scalar(setup,'set_company_state_region').removeprefix('s:')
                country_text+=f'\nadd_company = company_type:{key}\n'+history_text(setup,local_tags,dict(local_states,**{home:company_states[key]}),group_map)
        histories['countries'].append(f'c:{tag} ?= {{ {country_text} }}')
        definition=re.sub(r'^'+donor+r'\s*=',tag+' =',source['definition'],count=1)
        definition=re.sub(r'\bcapital\s*=\s*STATE_\w+',f'capital = {capital["key"]}',definition)
        definition=re.sub(r'\bcountry_type\s*=\s*\w+',f'country_type = {types[index]}',definition)
        definitions.append(definition)
        if tag!=donor:
            name=word(identity_rng)
            localization.extend([f' {tag}: "{name}"',f' {tag}_ADJ: "{name}"'])
            files[f'common/coat_of_arms/coat_of_arms/{tag}.txt']=f'{tag} = {{ pattern = "pattern_solid.tga" color1 = rgb {{ {_rgb(identity_rng)} }} }}'
        else:
            name=donor
        for folder in histories:
            if folder in ('states','pops','buildings','trade','countries','global','cultures','conscription','military_formations','military_deployments'):
                continue
            text=' '.join(data['history'][folder].get('c:'+donor,[]))
            if folder=='diplomacy':
                mates={tags[i] for i in bloc_of[index]['members']} if index in bloc_of else set()
                text='\n'.join(f'{key} {op} {value}' for key,op,value in commands(text) if key!='add_liberty_desire' and
                               not (key=='create_diplomatic_pact' and scalar(value,'type') in data['subject_types']) and
                               not (key in ('create_diplomatic_pact','set_relations') and tag_map.get((scalar(value,'country') or '').removeprefix('c:')) in mates))
            if folder=='power_blocs':
                text=re.sub(r'\bmember\s*=\s*c:\w+','',text) if bloc_of.get(index,{'leader':index})['leader']==index else ''
            text=history_text(text,local_tags,local_states,group_map)
            if folder=='power_blocs' and 'create_power_bloc' in text:
                vanilla_blocs[index]=scalar(text,'identity')
                if index in bloc_of:
                    text=re.sub(r'create_power_bloc\s*=\s*\{',lambda start:start[0]+members(bloc_of[index],tags),text,count=1)
            if text:
                histories[folder].append(f'c:{tag} ?= {{ {text} }}')
        military_history=formations(data,donor,[by_id[i] for i in group],group_of,military)
        if military_history:
            histories['military_formations'].append(f'c:{tag} ?= {{ {military_history} }}')
        for ident in group:
            state=by_id[ident]
            original=state['source']
            state['country']=tag
            own_states=dict(local_states,**{original['key']:state['key']})
            state_effects=history_text('\n'.join(f'{k} {op} {v}' for k,op,v in commands(original['state_history']) if k!='create_state'),local_tags,own_states,group_map)
            state_effects=re.sub(r'\badd_homeland\s*=\s*(\w+)',lambda m:' '.join('add_homeland = '+culture for culture in sorted(state['culture_map'].get(m[1],{m[1]}))),state_effects)
            state_type=next((scalar(text,'state_type') for key,text in blocks(original['state_history'])
                             if key=='create_state' and scalar(text,'country')=='c:'+original['owner']),None)
            histories['states'].append(f's:{state["key"]} = {{ create_state = {{ country = c:{tag} '
                                       f'{"state_type = "+state_type if state_type else ""} owned_provinces = {{ {" ".join(state["province_codes"])} }} }} '
                                       f'{state_effects} }}')
            histories['pops'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {" ".join(state["pop_records"])} }} }}')
            buildings=project(state['eligible_records'],tag,state['key'],local_tags,own_states,state_countries,scales,companies)
            state['generated_buildings']=' '.join(buildings)
            histories['buildings'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {state["generated_buildings"]} }} }}')
            if original['trade_history']:
                histories['trade'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {history_text(original['trade_history'],local_tags,own_states,group_map)} }} }}')
        countries.append({'tag':tag,'name':name,'source':donor,'copy':donor if tag==donor else None,'country_type':types[index],
                          'states':[by_id[i]['key'] for i in group],'capital':capital['key'],'culture':source['cultures'][0],
                          'cultures':source['cultures'],'primary_culture_share':realized,'ideology_uniformity':uniformity,
                          'tech_count':len(techs),'technologies':sorted(techs),'conquest_target':conquest_targets.get(tag),
                          'starting_laws':{data['law_groups'][law]:law for law in re.findall(r'activate_law\s*=\s*law_type:(\w+)',country_text)},
                          'provinces':[p for i in group for p in by_id[i]['province_codes']]})
    for number,bloc in enumerate(blocs,1):
        if bloc['leader'] in vanilla_blocs:
            bloc['identity']=vanilla_blocs[bloc['leader']]
        else:
            text,name,bloc['identity']=found(relation_rng,number,bloc,tags,countries[bloc['leader']]['starting_laws'],data['bloc_principles'])
            histories['power_blocs'].append(text)
            localization.append(name)
    histories['diplomacy'].extend(pacts(overlords,blocs,tags))
    for index,country in enumerate(countries):
        overlord,kind=overlords.get(index,(None,None))
        country.update(overlord=None if overlord is None else tags[overlord],subject_type=kind,
                       power_bloc=tags[bloc_of[index]['leader']] if index in bloc_of else tags[index] if index in vanilla_blocs else None)
    power_blocs=[{'leader':tags[bloc['leader']],'identity':bloc['identity'],'vanilla':bloc['leader'] in vanilla_blocs,
                  'members':[tags[i] for i in bloc['members']],'independent_members':[tags[i] for i in bloc['independent']]} for bloc in blocs]
    power_blocs+=[{'leader':tags[index],'identity':identity,'vanilla':True,'members':[tags[index]],'independent_members':[]}
                  for index,identity in vanilla_blocs.items() if index not in bloc_of]
    for folder,lines in histories.items():
        if folder not in ('countries','states','pops','buildings','trade','military_formations','military_deployments'):
            for key,records in data['history'][folder].items():
                if key.startswith('c:') and folder not in ('global','cultures','conscription'):
                    continue
                if key.startswith('s:'):
                    for state in states:
                        if key=='s:'+state['source']['key']:
                            for text in records:
                                state_tags=dict(tag_map,**{t:state['country'] for t in re.findall(r'region_state:([A-Z0-9]{3})',text)})
                                projected=history_text(text,state_tags,dict(state_map,**{state['source']['key']:state['key']}),group_map)
                                if projected:
                                    lines.append(f's:{state["key"]} = {{ {projected} }}')
                else:
                    projected=history_text('\n'.join(f'{key} = {{ {text} }}' for text in records),tag_map,state_map,group_map)
                    if projected:
                        lines.append(projected)
        if folder=='ai':
            lines.extend(f'c:{tag} ?= {{ set_secret_goal = {{ country = c:{target} secret_goal = conquer }} }}' for tag,target in conquest_targets.items())
        if folder in data['history_roots']:
            files[f'common/history/{folder}/interface.txt']=data['history_roots'][folder]+' = {\n'+'\n'.join(lines)+'\n}'
    files['common/country_definitions/interface.txt']='\n'.join(definitions)
    return {'countries':countries,'files':files,'localization':localization,'power_blocs':power_blocs,'starting_war':starting_war}
