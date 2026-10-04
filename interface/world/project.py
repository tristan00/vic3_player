import collections
import random
import re

from ..common import timed, timed_often
from ..script import blocks, body, scalar
from .nations import _rgb, _tags, _techs, level, word
from .source import development, integer_counts, moments, spread
from .buildings import expected, project
from .military import military
from .cultures import population


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
def remap(text,tags,states,regions):
    text=re.sub(r'\b(c|region_state):([A-Z0-9]{3})\b',lambda m:m[1]+':'+tags.get(m[2],m[2]),text)
    text=re.sub(r'\bSTATE_\w+',lambda m:states.get(m[0],m[0]),text)
    return re.sub(r'\bsr:(\w+)',lambda m:'sr:'+regions.get(m[1],m[1]),text)


@timed_often
def history_text(text,tags,states,regions):
    text=re.sub(r'\bhome_region\s*=\s*(?:s:)?STATE_\w+','home_region = random',text)
    output=[]
    dropped_branch=False
    for key,operator,value in commands(text):
        heading=key+' '+value
        refs=set(re.findall(r'\b(?:c|region_state):([A-Z0-9]{3})\b',heading))-tags.keys()
        missing=set(re.findall(r'\bSTATE_\w+',heading))-states.keys()
        absent_regions=set(re.findall(r'\bsr:(\w+)',heading))-regions.keys()
        provinces=re.findall(r'\bp:x[0-9A-Fa-f]+',heading)
        invalid=bool(refs or missing or absent_regions or provinces)
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
            inner=history_text(body(value),tags,states,regions)
            if not inner:
                dropped_branch=key in ('if','else_if')
                continue
            output.append(f'{remap(key,tags,states,regions)} {operator} {{ {inner} }}')
        elif not invalid:
            output.append(remap(f'{key} {operator} {value}',tags,states,regions))
    return '\n'.join(output)


@timed_often
def tech_counts(data,sources,donors,tech,variation):
    members={s['owner'] for pool in sources.values() for s in pool}
    counts={tag:len(data['source_countries'][tag]['techs']) for tag in members}
    low,_,high=data['tech_range']
    mean=moments(list(counts.values()))[0]
    target=level(tech,low,mean,high)
    homes={tag:max(sources,key=lambda region:sum(s['owner']==tag for s in sources[region])) for tag in members}
    regional={region:moments([counts[t] for t in members if homes[t]==region])[0] for region in sources if region in homes.values()}
    residuals={tag:counts[tag]-regional[homes[tag]] for tag in members}
    sigma=moments(list(residuals.values()))[1]
    reference=[residuals[tag] if tag in residuals else len(data['source_countries'][tag]['techs'])-mean for tag in donors]
    if not moments(reference)[1] and sigma and len(donors)>1:
        ranked=sorted(residuals.values())
        reference=[ranked[round(i*(len(ranked)-1)/(len(donors)-1))] for i in range(len(donors))]
    sampled=moments(reference)[1]
    values=spread(reference,variation*sigma/sampled if sampled else 0,center=target,lower=min(low,target),upper=max(high,target))
    return integer_counts(values),{'mean':target,'reference_mean':mean,'reference_sd':sigma,
                                   'requested_sd':variation*sigma,'realized_mean':moments(integer_counts(values))[0],
                                   'realized_sd':moments(integer_counts(values))[1]}


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
def nations(rng,data,states,groups,capitals,strategic,sources,tech=.5,ideology_uniformity=0,copies=0,
            tech_variation=1,country_economy=1,local_economy=1,primary_culture_share=None):
    by_id={s['id']:s for s in states}
    region_of={s['id']:r['key'] for r in strategic for s in r['states']}
    identity_rng=random.Random(rng.getrandbits(64))
    control_rng=random.Random(rng.getrandbits(64))
    culture_rng=random.Random(rng.getrandbits(64))
    eligible=sorted(tag for tag,source in data['source_countries'].items() if source['type']!='decentralized')
    if len(groups)>len(eligible):
        raise ValueError(f'Need at most {len(eligible)} countries')
    donors=rng.sample(eligible,len(groups))
    tags=_tags(len(groups),data['tags'])
    count=round(len(groups)*copies)
    selected=identity_rng.sample(range(len(groups)),count)
    for index in selected:
        tags[index]=donors[index]
    tag_map=dict(zip(donors,tags))
    state_map={}
    for state in states:
        state_map.setdefault(state['source']['key'],state['key'])
    region_map={r['source_region']:r['key'] for r in strategic}
    economy_reference=development(states,groups,country_economy,local_economy,data['military_buildings'],sources)
    counts,tech_reference=tech_counts(data,sources,donors,tech,tech_variation)
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
    special=data['military_buildings']|{'building_government_administration','building_construction_sector','building_trade_center'}
    for state in states:
        state['buildings']=expected(state['source']['building_records'],state['economic_scale'],special)
    for index,(tag,donor,group,capital_id,count) in enumerate(zip(tags,donors,groups,capitals,counts)):
        source=data['source_countries'][donor]
        capital=by_id[capital_id]
        local_tags=dict(tag_map,**{donor:tag})
        local_states=dict(state_map)
        for ident in group:
            state=by_id[ident]
            local_states[state['source']['key']]=state['key']
        capacity=max(by_id[i]['buildings'].get('building_barrack',0) for i in group)
        required={'standing_army','military_drill'} if capacity>data['barracks_cap']['law_peasant_levies'] else set()
        techs=_techs(rng,source['techs'],count,data['tech_requires'],required)
        for ident in group:
            state=by_id[ident]
            state['excluded_buildings']={kind:{'levels':amount,'missing_technologies':sorted(data['building_techs'][kind]-techs)}
                                         for kind,amount in state['buildings'].items() if not data['building_techs'][kind]<=techs}
            state['buildings']={kind:amount for kind,amount in state['buildings'].items() if kind not in state['excluded_buildings']}
            state['eligible_records']=[r for r in state['source']['building_records'] if scalar(r,'building') in state['buildings']]
        country_text=starting_history(data,donor,techs)
        uniformity=control_rng.uniform(*ideology_uniformity) if isinstance(ideology_uniformity,(tuple,list)) else ideology_uniformity
        share=control_rng.uniform(*primary_culture_share) if isinstance(primary_culture_share,(tuple,list)) else primary_culture_share
        realized=population(culture_rng,data,[by_id[i] for i in group],source['cultures'],share)
        country_text+=f'\nset_variable = {{ name = interface_ideology_uniformity value = {100*uniformity:.5f} }}'
        country_text='\n'.join(f'{key} {op} {value}' for key,op,value in commands(country_text)
                               if key not in ('add_company','set_capital','set_market_capital') and not key.startswith('company:'))
        country_text=politics(country_text,data,techs,max(by_id[i]['buildings'].get('building_barrack',0) for i in group))
        country_text=history_text(country_text,local_tags,local_states,region_map)
        for key,owner in companies.items():
            if owner==tag:
                setup=source_companies[key][1]
                home=scalar(setup,'set_company_state_region').removeprefix('s:')
                country_text+=f'\nadd_company = company_type:{key}\n'+history_text(setup,local_tags,dict(local_states,**{home:company_states[key]}),region_map)
        histories['countries'].append(f'c:{tag} ?= {{ {country_text} }}')
        definition=re.sub(r'^'+donor+r'\s*=',tag+' =',source['definition'],count=1)
        definition=re.sub(r'\bcapital\s*=\s*STATE_\w+',f'capital = {capital["key"]}',definition)
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
                for key,op,value in commands(text):
                    if key=='add_liberty_desire':
                        histories['global'].append(f'c:{tag} = {{ if = {{ limit = {{ is_subject = yes }} {key} {op} {value} }} }}')
                text='\n'.join(f'{key} {op} {value}' for key,op,value in commands(text) if key!='add_liberty_desire')
            text=history_text(text,local_tags,local_states,region_map)
            if text:
                histories[folder].append(f'c:{tag} ?= {{ {text} }}')
        military_history=military(data,donor,tag,[by_id[i] for i in group],region_of)
        if military_history:
            histories['military_formations'].append(f'c:{tag} ?= {{ {military_history} }}')
        for ident in group:
            state=by_id[ident]
            original=state['source']
            state['country']=tag
            own_states=dict(local_states,**{original['key']:state['key']})
            state_effects=history_text('\n'.join(f'{k} {op} {v}' for k,op,v in commands(original['state_history']) if k!='create_state'),local_tags,own_states,region_map)
            state_effects=re.sub(r'\badd_homeland\s*=\s*(\w+)',lambda m:' '.join('add_homeland = '+culture for culture in sorted(state['culture_map'].get(m[1],{m[1]}))),state_effects)
            state_type=next((scalar(text,'state_type') for key,text in blocks(original['state_history'])
                             if key=='create_state' and scalar(text,'country')=='c:'+original['owner']),None)
            histories['states'].append(f's:{state["key"]} = {{ create_state = {{ country = c:{tag} '
                                       f'{"state_type = "+state_type if state_type else ""} owned_provinces = {{ {" ".join(state["province_codes"])} }} }} '
                                       f'{state_effects} }}')
            histories['pops'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {" ".join(state["pop_records"])} }} }}')
            buildings=project(state['eligible_records'],tag,state['key'],local_tags,own_states,state_countries,
                              state['economic_scale'],special,companies)
            state['generated_buildings']=' '.join(buildings)
            histories['buildings'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {state["generated_buildings"]} }} }}')
            if original['trade_history']:
                histories['trade'].append(f's:{state["key"]} = {{ region_state:{tag} = {{ {history_text(original['trade_history'],local_tags,own_states,region_map)} }} }}')
        countries.append({'tag':tag,'name':name,'source':donor,'copy':donor if tag==donor else None,'country_type':source['type'],
                          'states':[by_id[i]['key'] for i in group],'capital':capital['key'],'culture':source['cultures'][0],
                          'cultures':source['cultures'],'primary_culture_share':realized,'ideology_uniformity':uniformity,
                          'tech_count':len(techs),'technologies':sorted(techs),
                          'starting_laws':{data['law_groups'][law]:law for law in re.findall(r'activate_law\s*=\s*law_type:(\w+)',country_text)},
                          'provinces':[p for i in group for p in by_id[i]['province_codes']]})
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
                                projected=history_text(text,state_tags,dict(state_map,**{state['source']['key']:state['key']}),region_map)
                                if projected:
                                    lines.append(f's:{state["key"]} = {{ {projected} }}')
                else:
                    projected=history_text('\n'.join(f'{key} = {{ {text} }}' for text in records),tag_map,state_map,region_map)
                    if projected:
                        lines.append(projected)
        if folder in data['history_roots']:
            files[f'common/history/{folder}/interface.txt']=data['history_roots'][folder]+' = {\n'+'\n'.join(lines)+'\n}'
    files['common/country_definitions/interface.txt']='\n'.join(definitions)
    tech_reference.update(realized_mean=moments([c['tech_count'] for c in countries])[0],
                          realized_sd=moments([c['tech_count'] for c in countries])[1])
    return {'countries':countries,'files':files,'localization':localization,'tech_reference':tech_reference,'economy_reference':economy_reference}
