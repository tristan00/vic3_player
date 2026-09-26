import json
from pathlib import Path
import re

from .common import timed


def blocks(text):
    depth=0;start=None;key=None;previous=[]
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|\?=|[{}]|[^\s{}=?]+|=',text):
        t=m[0]
        if t=='{':
            if depth==0 and len(previous)==2 and previous[1][0] in {'=','?='}:
                key,start=previous[0]
            depth+=1
        elif t=='}':
            depth-=1
            if depth==0 and start is not None:
                yield key,text[start:m.end()]
                start=None
        previous=(previous+[(t,m.start())])[-2:]


def body(text):
    return text[text.index('{')+1:text.rfind('}')]


def fields(text):
    depth=0;key=None;expect=False;start=None
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|\?=|[{}]|[^\s{}=?]+|=',text):
        t=m[0]
        if t=='{':
            if depth==0 and expect:
                start=m.start()
            depth+=1
        elif t=='}':
            depth-=1
            if depth==0 and start is not None:
                yield key,text[start+1:m.start()].split()
                start=None;key=None;expect=False
        elif depth==0:
            if t in ('=','?='):
                expect=key is not None
            elif expect:
                yield key,[t]
                key=None;expect=False
            else:
                key=t


def scalar(text,key):
    found=re.search(r'\b'+re.escape(key)+r'\s*=\s*"?([^\s{}"]+)',text)
    return found[1] if found else None


def clean(path):
    return re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*',lambda m:'' if m[0][0]=='#' else m[0],path.read_text(encoding='utf-8-sig'))


def script_files(game,folder,mods=()):
    files={path.relative_to(game):path for path in (game/folder).rglob('*.txt')}
    for root in map(Path,mods):
        metadata=root/'.metadata/metadata.json'
        replaced=json.loads(metadata.read_text(encoding='utf-8-sig')).get('game_custom_data',{}).get('replace_paths',[]) if metadata.exists() else []
        files={name:path for name,path in files.items() if not any(name.as_posix()==prefix or name.as_posix().startswith(prefix.rstrip('/')+'/') for prefix in replaced)}
        files.update({path.relative_to(root):path for path in (root/folder).rglob('*.txt')})
    return [files[name] for name in sorted(files)]


@timed
def read(game,folder,mods=()):
    for path in script_files(game,folder,mods):
        yield from blocks(clean(path))


GATE_PREFIXES=('unlocking_','disallowing_','required_')


def production_methods(game,mods=()):
    for name,text in read(game,'common/production_methods',mods):
        entry=dict(fields(body(text)))
        for gate,values in entry.items():
            if gate.startswith(GATE_PREFIXES) and not all(value.replace('_','').isalnum() for value in values):
                raise RuntimeError(f'{name}.{gate} is not a flat list of keys: {values}')
        yield name,entry


METHOD_TARGETS={'building_modifiers':'building','state_modifiers':'state','country_modifiers':'country'}
METHOD_SCALINGS=('workforce_scaled','level_scaled','throughput_scaled','unscaled')
METHOD_GOODS=re.compile(r'goods_(input|output)_(\w+)_add')
METHOD_EMPLOYMENT=re.compile(r'building_employment_(\w+)_add')
METHOD_REQUIREMENTS=('unlocking_technologies','unlocking_laws','disallowing_laws','unlocking_production_methods','unlocking_principles','unlocking_identity',
                     'unlocking_company_categories','unlocking_geographic_regions','unlocking_religions','disallowing_religions','unlocking_global_technologies',
                     'required_input_goods')


def method_value(name,modifier,values):
    if len(values)!=1:
        raise RuntimeError(f'{name}.{modifier} holds {values}, not one value')
    value=values[0]
    if value in ('yes','no'):
        return 1.0 if value=='yes' else 0.0
    if not re.fullmatch(r'-?\d+(\.\d+)?',value):
        raise RuntimeError(f'{name}.{modifier} holds {value}, not a number')
    return float(value)


def method_effects(game,mods=()):
    goods,employment,modifiers,requirements,ratios=[],[],[],[],[]
    for name,entry in production_methods(game,mods):
        for field,values in entry.items():
            if field in METHOD_TARGETS:
                target=METHOD_TARGETS[field]
                for scaling,inner in fields(' '.join(values)):
                    if scaling not in METHOD_SCALINGS:
                        raise RuntimeError(f'{name}.{field} has an unknown scaling {scaling}')
                    for modifier,found in fields(' '.join(inner)):
                        value=method_value(name,modifier,found)
                        flow=METHOD_GOODS.fullmatch(modifier) if target=='building' else None
                        job=METHOD_EMPLOYMENT.fullmatch(modifier) if target=='building' else None
                        if flow:
                            goods.append((name,flow[2],flow[1],scaling,value))
                        elif job:
                            employment.append((name,job[1],scaling,value))
                        else:
                            modifiers.append((name,target,scaling,modifier,value))
            elif field in METHOD_REQUIREMENTS:
                requirements+=[(name,field,key) for key in values]
            elif field=='profession_ratio':
                ratios+=[(name,pop,method_value(name,pop,found)) for pop,found in fields(' '.join(values))]
    return {'goods':goods,'employment':employment,'modifiers':modifiers,'requirements':requirements,'ratios':ratios}


def diplomatic_actions(game,mods=()):
    for name,text in read(game,'common/diplomatic_actions',mods):
        inner=dict(blocks(body(text)))
        groups=re.search(r'\bgroups\s*=\s*\{([^}]*)\}',text)
        yield (name,body(inner['selectable']) if 'selectable' in inner else '',body(inner['potential']) if 'potential' in inner else '',
               set(groups[1].split()) if groups else set(),bool(re.search(r'scope:(first|second)_state',text)),
               body(inner['possible']) if 'possible' in inner else 'always = yes')


def diplomatic_state_triggers(game,mods=()):
    for name,text in read(game,'common/diplomatic_actions',mods):
        inner=dict(blocks(body(text)))
        for side,listing in re.findall(r'\b(first|second)_state_list\s*=\s*(\w+)',text):
            yield name,side,listing,body(inner[f'{side}_state_trigger']) if f'{side}_state_trigger' in inner else 'always = yes'


def character_interactions(game,mods=()):
    for name,text in read(game,'common/character_interactions',mods):
        inner=dict(blocks(body(text)))
        yield name,body(inner['potential']) if 'potential' in inner else '',body(inner['possible']) if 'possible' in inner else 'always = yes'


def journal_buttons(game,mods=()):
    visible={}
    for name,text in read(game,'common/scripted_buttons',mods):
        inner=dict(blocks(body(text)))
        visible[name]=body(inner['visible']) if 'visible' in inner else ''
    for name,text in read(game,'common/journal_entries',mods):
        buttons=[button for field,values in fields(body(text)) if field=='scripted_button' for button in values]
        if buttons:
            yield name,[(button,visible[button]) for button in buttons]


def decisions(game,mods=()):
    for name,text in dict(read(game,'common/decisions',mods)).items():
        inner=dict(blocks(body(text)))
        yield (name,body(inner['is_shown']) if 'is_shown' in inner else 'always = yes',
               body(inner['possible']) if 'possible' in inner else 'always = yes')


def alerts(game,mods=()):
    for name,text in read(game,'common/alert_types',mods):
        inner=dict(blocks(body(text)))
        if 'valid' in inner:
            yield name,scalar(text,'script_context'),body(inner['valid'])


def building_methods(game,mods=()):
    groups={name:dict(fields(body(text))).get('production_methods',[]) for name,text in read(game,'common/production_method_groups',mods)}
    return [(building,group,method) for building,text in read(game,'common/buildings',mods)
            for group in dict(fields(body(text))).get('production_method_groups',[]) for method in groups[group]]


DEFINITION_FIELDS={
    'common/buildings':('building_group','buildable','expandable','downsizeable','unlocking_technologies','unique','should_auto_expand','required_construction',
                         'recruits_combat_units'),
    'common/building_groups':('parent_group','is_government_funded','should_auto_expand','default_building'),
    'common/technology/technologies':('unlocking_technologies','can_research'),
    'common/laws':('group','unlocking_technologies','unlocking_laws','disallowing_laws'),
    'common/state_traits':('required_techs_for_colonization',),
    'common/decrees':('unlocking_technologies','unlocking_laws','cost'),
    'common/goods':('cost','consumption_tax_cost','local','tradeable'),
    'common/combat_unit_types':('group','unlocking_technologies','upgrades'),
    'common/commander_orders':('military_type',),
    'common/journal_entries':('scripted_button',),
    'common/diplomatic_plays':('war_goal','requires_interest_marker','allow_negotiated_peace'),
    'common/war_goal_types':('target_type','kind','settings'),
    'common/strait_definitions':('type','total_block_requires_full_control','military_block_requires_full_control','tolls_require_full_control'),
    'common/subject_types':('valid_overlord_country_types','valid_subject_country_types','valid_overlord_ranks','valid_subject_ranks','overlord_must_be_higher_rank',
                            'can_start_own_diplomatic_plays','can_have_subjects','higher_autonomy_subject_type_alternatives','lower_autonomy_subject_type_alternatives'),
    'common/ship_types':('unlocking_technologies','ship_group'),
    'common/ship_modifications':('type','unlocking_technologies'),
    'common/ship_modification_slots':('utility',),
    'common/strategic_regions':('states',),
    'common/geographic_regions':('strategic_regions','state_regions'),
    'common/country_ranks':('rank_value','diplo_pact_cost'),
    'common/commander_ranks':('rank_value',),
    'map_data/state_regions':('arable_resources','naval_exit_id'),
    'common/mobilization_options':('unlocking_technologies','unlocking_principles'),
    'common/amendments':('parent',),
    'common/diplomatic_actions':('unlocking_technologies','groups','can_use_obligations','first_state_list','second_state_list','reverse_pact'),
    'common/interest_tier_types':('rank','min_involvement'),
    'common/power_bloc_principle_groups':('primary_for_identity','levels','unlocking_identity','blocking_identity'),
    'common/cultures':('heritage','language','traditions'),
}


BLOCK_FIELDS={
    'common/commander_orders':('possible',),
    'common/naval_mission_types':('potential',),
    'common/laws':('modifier','can_enact','is_visible','can_impose'),
    'common/technology/technologies':('modifier',),
    'common/company_types':('potential','possible','building_types'),
    'common/ship_types':('modifications','modifier'),
    'common/ship_modifications':('modifier',),
    'common/decisions':('possible',),
    'common/buildings':('potential','possible','can_build','can_build_government'),
    'common/power_bloc_identities':('can_leave','visible','possible'),
    'common/diplomatic_actions':('possible',),
    'common/diplomatic_plays':('possible','potential','selectable_in_lens'),
    'common/character_interactions':('possible',),
    'common/mobilization_options':('possible','can_be_turned_off'),
    'common/combat_unit_types':('upkeep_modifier',),
    'common/decrees':('state_trigger','country_trigger'),
    'common/war_goal_types':('possible','valid'),
    'common/amendments':('can_repeal','modifier'),
    'common/scripted_buttons':('possible',),
    'common/law_groups':('change_allowed_trigger',),
    'common/power_bloc_principles':('power_bloc_modifier','visible','possible'),
    'common/journal_entries':('modifiers_while_active',),
}


def definitions(game,mods=()):
    return ([(folder,name,field,value.strip('"')) for folder,wanted in DEFINITION_FIELDS.items() for name,text in read(game,folder,mods)
             for field,values in fields(body(text)) if field in wanted for value in values]
            +[(folder,name,field,' '.join(values)) for folder,wanted in BLOCK_FIELDS.items() for name,text in read(game,folder,mods)
              for field,values in fields(body(text)) if field in wanted]
            +[('common/static_modifiers',name,field,values[0]) for name,text in read(game,'common/static_modifiers',mods)
              for field,values in fields(body(text)) if len(values)==1]
            +[('common/defines',f'{namespace}|{field}','value',values[0]) for namespace,text in read(game,'common/defines',mods)
              for field,values in fields(body(text)) if len(values)==1]
            +[('common/ideologies',name,'stance',f'{law} {stance}') for name,text in read(game,'common/ideologies',mods)
              for field,values in fields(body(text)) if field.startswith('lawgroup_')
              for law,stance in zip(values[0::3],values[2::3])]
            +[('common/diplomatic_actions',name,'picks_states','yes') for name,text in read(game,'common/diplomatic_actions',mods)
              if re.search(r'scope:(first|second)_state',text)]
            +[('common/script_values',name,'value',value) for path in script_files(game,'common/script_values',mods)
              for name,value in re.findall(r'^(\w+)\s*=\s*(-?[\d.]+)(?=\s|$)',clean(path),re.M)]
            +[(folder,name,'body',' '.join(body(text).split())) for folder in ('common/scripted_triggers','common/scripted_rules') for name,text in read(game,folder,mods)]
            +[('common/diplomatic_actions',name,'pact_cost',cost) for name,text in read(game,'common/diplomatic_actions',mods)
              for cost in re.findall(r'\bpact\s*=\s*\{\s*cost\s*=\s*([\d.]+)',text)[:1]]
            +[('common/diplomatic_actions',name,'pact_hostile',value) for name,text in read(game,'common/diplomatic_actions',mods)
              for field,values in fields(body(text)) if field=='pact'
              for inner,found in fields(' '.join(values)) if inner=='is_hostile' for value in found]
            +[('common/diplomatic_actions',name,'maintain',' '.join(trigger)) for name,text in read(game,'common/diplomatic_actions',mods)
              for field,values in fields(body(text)) if field=='pact'
              for inner,requirement in fields(' '.join(values)) if inner=='requirement_to_maintain'
              for kind,trigger in fields(' '.join(requirement)) if kind=='trigger']
            +[('common/pop_needs',name,'goods',goods) for name,text in read(game,'common/pop_needs',mods)
              for goods in re.findall(r'\bgoods\s*=\s*(\w+)',text)]
            +[('common/diplomatic_actions',name,field,value) for name,text in read(game,'common/diplomatic_actions',mods)
              for found in re.findall(r'(?<!is_)subject_type\s*=\s*(subject_type_\w+)',text)[:1]
              for field,value in (('subject_pact','yes'),('subject_type',found))]
            +[('common/diplomatic_plays',name,'never_selectable','yes') for name,text in read(game,'common/diplomatic_plays',mods)
              if re.search(r'selectable_in_lens\s*=\s*\{\s*always\s*=\s*no\s*\}',text)])


def event_namespaces(game,mods=()):
    return list(dict.fromkeys(key.rsplit('.',1)[0] for path in script_files(game,'events',mods)
                              for key,_ in blocks(clean(path)) if re.fullmatch(r'[\w-]+\.\d+',key)))


def keys(game,folder,mods=()):
    return list(dict.fromkeys(key for key,_ in read(game,folder,mods)))


@timed
def event_options(game,mods=()):
    events={}
    for path in script_files(game,'events',mods):
        for key,value in blocks(clean(path)):
            if re.fullmatch(r'[\w-]+\.\d+',key):
                events[key]=[]
                options=[option for kind,option in blocks(body(value)) if kind=='option']
                for index,option in enumerate(options):
                    inner=dict(blocks(body(option)))
                    events[key].append((key,index,scalar(option,'name'),int('trigger' in inner),int(bool(re.search(r'\bdefault_option\s*=\s*yes',option)))))
    return [row for rows in events.values() for row in rows]


def entries(game,folder):
    for root,outer in read(game,folder):
        for key,value in blocks(body(outer)):
            yield root,key.strip('"').split(':')[-1],value


@timed
def iterators(docs):
    entries={}
    text=Path(docs).joinpath('effects.log').read_text(encoding='utf-8',errors='replace')
    for chunk in re.split(r'^## ',text,flags=re.M)[1:]:
        lines=chunk.splitlines()
        listed=lambda label:[value.strip() for line in lines if line.startswith('**'+label)
                             for value in line.split(':',1)[1].split(',') if value.strip()]
        entries[lines[0].strip()]=(listed('Supported Scopes'),listed('Supported Targets'))
    return entries
