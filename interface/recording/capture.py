import json
from pathlib import Path
import re

from ..common import timed
from ..script import alerts, blocks, body, character_interactions, decisions, diplomatic_actions, diplomatic_state_triggers, journal_buttons, production_methods, read
from ..visibility import Visibility


METHOD_GATES={'unlocking_technologies':('has_technology_researched = {}','all',None),
              'unlocking_laws':('has_law = law_type:{}','any',None),
              'unlocking_principles':('has_principle = principle:{}','any','power_bloc'),
              'unlocking_identity':('has_identity = identity:{}','any','power_bloc'),
              'unlocking_religions':('country_has_state_religion = rel:{}','any',None),
              'disallowing_laws':('has_law = law_type:{}','none',None),
              'disallowing_religions':('country_has_state_religion = rel:{}','none',None)}


BUILDING_GATES=('unlocking_production_methods','required_input_goods','unlocking_global_technologies',
                'unlocking_geographic_regions','unlocking_company_categories')


ALERT_SCOPES={'player_country':(),
              'player_state':('every_scope_state',),
              'player_military_formation':('every_military_formation',),
              'player_subject':('every_direct_subject',),
              'player_treaty':('every_scope_treaty',),
              'player_article':('every_scope_treaty','every_scope_article'),
              'player_war':('every_scope_war',),
              'player_front':('every_scope_war','every_scope_front'),
              'player_diplomatic_play':('every_diplomatic_play',),
              'player_diplomatic_pact':('every_scope_diplomatic_pact',),
              'player_market':('market',),
              'player_market_goods':('market','every_market_goods'),
              'player_company':('every_company',)}


PROVIDED_SCOPES={'actor'}


REFERENCES=(('state region',r's:(STATE_\w+)'),
            ('state region',r'owns_entire_state_region\s*=\s*(STATE_\w+)'),
            ('strategic region',r'sr:(region_\w+)'),
            ('country',r'(?<![A-Za-z_])c:([A-Z]{3})\b'))


METRICS=json.loads((Path(__file__).parent/'metrics.json').read_text(encoding='utf-8'))


VISIBILITY=Visibility()


GROUPS={'public':VISIBILITY.metrics(list(METRICS['country']),'country'),
        'player':VISIBILITY.player_metrics(list(METRICS['country']),'country'),
        'state':VISIBILITY.metrics(list(METRICS['state']),'state')}


FLOAT_STEP=0.01


FLOAT_LIMITS={'Country.GetRankProgress':2}


INTEGER_PARTS={'int32':2,'int64':3}


PART=65536


CHUNK=32


UI_CHECKS=(('panel','InformationPanelBar.IsAnyPanelOpen'),('interaction','MapListPanelManager.HasCurrentInteraction'),('map_list','MapListPanelManager.IsVisible'))


def unmet_scopes(valid):
    return (set(re.findall(r'scope:(\w+)',valid))-set(re.findall(r'save_(?:temporary_)?scope_as\s*=\s*(\w+)',valid))
            -PROVIDED_SCOPES)


def missing_references(text,world):
    if world is None:
        return []
    present={state['key'] for state in world['states']}|{country['tag'] for country in world['countries']}
    return sorted({(kind,key) for kind,pattern in REFERENCES
                   for key in re.findall(pattern,text) if key not in present})


def listed(name,target):
    return f'add_to_variable_list = {{ name = {name} target = {target} }}'


def mapped(name,key,value):
    return f'add_to_variable_map = {{ name = {name} key = {key} value = {value} }}'


def on_root(effect):
    return 'root = { '+effect+' }'


def when(test,effect):
    return 'if = { limit = { '+test+' } '+effect+' }'


def method_condition(gates):
    if any(gate in gates for gate in BUILDING_GATES):
        return None
    tests=[]
    for gate,(pattern,mode,owner) in METHOD_GATES.items():
        values=gates.get(gate)
        if not values:
            continue
        parts=[pattern.format(value) for value in values]
        joined=' '.join(parts) if mode=='all' else (
            'OR = { '+' '.join(parts)+' }' if len(parts)>1 else parts[0])
        if owner:
            joined=owner+' ?= { '+joined+' }'
        tests.append('NOT = { '+joined+' }' if mode=='none' else joined)
    return ' '.join(tests) or 'always = yes'


def method_block(name,gates):
    condition=method_condition(gates)
    return None if condition is None else when(condition,listed('cap_method','flag:'+name))


def decision_block(name,shown,possible):
    inner=(when(possible,listed('cap_decision_possible','flag:'+name)) if possible is not None
           else listed('cap_decision_unevaluable','flag:'+name))
    return when(shown,listed('cap_decision','flag:'+name)+' '+inner)


def diplomatic_evaluable(selectable,potential):
    return not unmet_scopes(selectable+' '+potential)-{'target_country'}


def shown_diplomatic(actions):
    tests='\n'.join(when(selectable+' '+potential,listed('cap_diplomatic_'+name,'scope:target_country')
                         +(' '+when(possible,listed('cap_possible_diplomatic_'+name,'scope:target_country')+picks) if possible is not None else ''))
                    for name,selectable,potential,possible,picks in actions)
    return ('every_country = { limit = { NOT = { this = root } } save_scope_as = target_country\nroot = {\nsave_scope_as = country\n'+tests+'\n} }\n'
            'every_decentralized_country = { save_scope_as = target_country\nroot = {\nsave_scope_as = country\n'+tests+'\n} }')


STATE_PICK_SCOPES={'cap_state','country','target_country'}


def state_picks(name,side,listing,trigger):
    pick='save_scope_as = cap_state '+when(state_rooted(trigger),'scope:target_country = { '+listed(f'capd_{side}_{name}','scope:cap_state')+' }')
    states=f'every_scope_state = {{ {pick} }}'+(f' every_subject_or_below = {{ every_scope_state = {{ {pick} }} }}' if listing.endswith('_and_subjects') else '')
    return f' {"root" if side=="first" else "scope:target_country"} = {{ {states} }}'


def pick_clears(body):
    names=sorted(set(re.findall(r'name = (capd_\w+)',body)))
    clear=' '.join(f'clear_variable_list = {name}' for name in names)
    return f'every_country = {{ {clear} }}\nevery_decentralized_country = {{ {clear} }}\n' if names else ''


def shown_interactions(interactions):
    tests='\n'.join(when(potential,on_root(listed('cap_interaction_'+name,'prev'))+' '+when(possible,on_root(listed('cap_possible_interaction_'+name,'prev'))))
                    for name,potential,possible in interactions)
    return 'every_scope_character = {\n'+tests+'\n}\nevery_character_in_exile_pool = {\n'+tests+'\n}'


def shown_buttons(entries):
    return '\n'.join('je:'+entry+' ?= {\nsave_scope_as = journal_entry\nPREV = {\n'
                     +'\n'.join(when(visible,listed('cap_button_'+entry,'flag:'+button)) for button,visible in buttons)+'\n}\n}'
                     for entry,buttons in entries)


def evaluable(context,valid):
    return context in ALERT_SCOPES and not unmet_scopes(valid)


def alert_block(name,context,valid):
    effect=on_root(listed('cap_alert_'+name,'prev') if context=='player_state' else 'change_variable = { name = cap_alert_'+name+' add = 1 }')
    test=when(valid,effect)
    for iterator in reversed(ALERT_SCOPES[context]):
        test=iterator+' = {\n'+test+'\n}'
    return test


def decree_triggers(game_dir,mods):
    return [(kind,body(inner['state_trigger'])) for kind,text in read(game_dir/'game','common/decrees',mods)
            for inner in [dict(blocks(body(text)))] if 'state_trigger' in inner]


def state_rooted(trigger):
    return re.sub(r'\b(?:ROOT|root)\b','scope:cap_state',trigger)


def collect(name,*openers,limit=None):
    effect=('limit = { '+limit+' } ' if limit else '')+on_root(listed(name,'prev'))
    for opener in reversed(openers):
        effect=opener+' { '+effect+' }'
    return effect


def fixed(expression,kind):
    if kind=='CFixedPoint':
        return expression
    if kind=='bool':
        return f"Select_CFixedPoint({expression},'(CFixedPoint)1','(CFixedPoint)0')"
    raise ValueError(f'No fixed-point conversion for {kind}')


def limit(expression):
    return FLOAT_LIMITS.get(expression,1)


def balanced(terms):
    while len(terms)>1:
        terms=[f'Add_CFixedPoint({terms[index]},{terms[index+1]})' if index+1<len(terms) else terms[index] for index in range(0,len(terms),2)]
    return terms[0]


def integer_parts(expression,kind):
    base=f"'({kind}){PART}'"
    parts=[]
    rest=expression
    for index in range(INTEGER_PARTS[kind]):
        parts.append(rest if index==INTEGER_PARTS[kind]-1 else f'Modulo_{kind}({rest},{base})')
        rest=f'Divide_{kind}({rest},{base})'
    return [f'MakeScopeFlag(ToString_{kind}({part}))' for part in parts]


def expanded(fields):
    result=[]
    for field,expression,kind in fields:
        if kind in INTEGER_PARTS:
            result+=[(f'{field}__p{index}',part,'scope') for index,part in enumerate(integer_parts(expression,kind))]
        elif kind=='float':
            result+=[(field,expression,'float'),(field+'__above',expression,'above'),(field+'__below',expression,'below')]
        else:
            result.append((field,expression,kind))
    return result


def scoped(expression,kind):
    if kind=='scope':
        return expression
    if kind=='text':
        return f'MakeScopeFlag({expression})'
    if kind=='object':
        return f'{expression}.MakeScope'
    if kind=='above':
        return f"MakeScopeValue(Select_CFixedPoint(GreaterThan_float({expression},'(float){limit(expression)}'),'(CFixedPoint)1','(CFixedPoint)0'))"
    if kind=='below':
        return f"MakeScopeValue(Select_CFixedPoint(LessThan_float({expression},'(float)0'),'(CFixedPoint)1','(CFixedPoint)0'))"
    if kind=='float':
        return 'MakeScopeValue('+balanced([f"Select_CFixedPoint(GreaterThanOrEqualTo_float({expression},'(float){index*FLOAT_STEP:.2f}'),'(CFixedPoint){FLOAT_STEP}','(CFixedPoint)0')"
                                           for index in range(1,round(limit(expression)/FLOAT_STEP)+1)])+')'
    return f'MakeScopeValue({fixed(expression,kind)})'


def fields_of(kind,names):
    prefix='Country.' if kind=='country' else 'State.'
    return [(name,prefix+name,METRICS[kind][name]) for name in names]


def metric_map(kind,name):
    base,_,suffix=name.partition('__')
    return f'cap_metric_{kind}_{sorted(METRICS[kind]).index(base)}'+('__'+suffix if suffix else '')


class Group:
    def __init__(self,name,source,context,key,fields,naming=None):
        self.name,self.source,self.context,self.key=name,source,context,key
        self.fields=expanded(fields)
        self.maps={field:(naming(field) if naming else f'cap_{name}_{field}') for field,_,_ in self.fields}

    def chunks(self):
        return [self.fields[start:start+CHUNK] for start in range(0,len(self.fields),CHUNK)]

    def write(self,field,position):
        if self.key:
            return mapped(self.maps[field],'scope:o',f'scope:v{position}')
        return f'set_variable = {{ name = {self.maps[field]} value = scope:v{position} }}'

    def effects(self):
        return '\n'.join(f'cap_set_{self.name}_{index} = {{ scope = country effect = {{ '
                         +' '.join(self.write(field,position) for position,(field,_,_) in enumerate(chunk))+' } }'
                         for index,chunk in enumerate(self.chunks()))

    def calls(self):
        return [f"GetScriptedGui('cap_set_{self.name}_{index}').Execute(GuiScope.SetRoot(GetPlayer.MakeScope)"
                +(f".AddScope('o',{self.key})" if self.key else '')
                +''.join(f".AddScope('v{position}',{scoped(expression,kind)})" for position,(_,expression,kind) in enumerate(chunk))+'.End)'
                for index,chunk in enumerate(self.chunks())]

    def widget(self):
        states=' '.join(f'on_finish = "[{call}]"' for call in self.calls())
        item=f'widget = {{ size = {{ 0 0 }} datacontext = "[{self.context}]" state = {{ name = capture_values duration = 0.001 {states} }} }}'
        if self.source is None:
            return item
        return f"flowcontainer = {{ datamodel = \"[AccessPlayer.MakeScope.GetList('{self.source}')]\" item = {{ {item} }} }}"


def metric_groups():
    return [Group('metric_public','cap_obj_country','Scope.GetCountry','Country.MakeScope',fields_of('country',GROUPS['public']),lambda field:metric_map('country',field)),
            Group('metric_player',None,'GetPlayer','Country.MakeScope',fields_of('country',GROUPS['player']),lambda field:metric_map('country',field)),
            Group('metric_state','cap_obj_state','Scope.GetState','State.MakeScope',fields_of('state',GROUPS['state']),lambda field:metric_map('state',field))]


GROUP_SPECS=(
    ('building','cap_obj_building','Scope.GetBuilding','Building.MakeScope',
     (('auto_expand','Building.IsAutoExpanding','bool'),('output_paused','Building.IsConstructionOutputPaused','bool'),
      ('monopoly','Building.GetBuildingType.HasCountryMonopoly','bool'),('privatizable','Building.CanBePrivatized','bool'))),
    ('formation','cap_obj_formation','Scope.GetMilitaryFormation','MilitaryFormation.MakeScope',
     (('default_fleet','MilitaryFormation.IsDefaultConstructionFleet','bool'),('demobilizing','MilitaryFormation.IsDemobilizing','bool'),
      ('invading','MilitaryFormation.HasInvasion','bool'),('embarked','MilitaryFormation.IsAttachedToFleet','bool'),
      ('docked','MilitaryFormation.IsDocked','bool'),('recalled','MilitaryFormation.IsRecalledForRepairs','bool'),
      ('hit_points_percent','MilitaryFormation.GetHitPointsPercentage','CFixedPoint'),('deployable','MilitaryFormation.CanDeployToFront','bool'),
      ('name','MilitaryFormation.GetNameNoFormatting','text'),('retrofittable','MilitaryFormation.GetShipList.GetNumShipsCanRetrofit','int32'),
      ('retrofitting','MilitaryFormation.GetShipList.IsToRetrofit','bool'))),
    ('company','cap_obj_company','Scope.GetCompany','Company.MakeScope',
     (('investment','Company.HasAnyInvestmentCharterActive','bool'),('trade','Company.HasAnyTradeCharterActive','bool'),
      ('established','Company.GetEstablishmentDate.GetString','text'))),
    ('character','cap_obj_character','Scope.GetCharacter','Character.MakeScope',
     (('popularity','Character.GetPopularity','CFixedPoint'),('has_formation','Character.HasMilitaryFormation','bool'))),
    ('interest_group','cap_obj_interest_group','Scope.GetInterestGroup','InterestGroup.MakeScope',
     (('amenability','InterestGroup.GetAmenability','CFixedPoint'),('negotiated','InterestGroup.HasNegotiated','bool'))),
    ('player_state','cap_obj_player_state','Scope.GetState','State.MakeScope',(('colonization_paused','State.IsColonizationPaused','bool'),)),
    ('law','cap_obj_law','Scope.GetLaw','Law.MakeScope',(('chance','Law.GetCheckpointSuccessChance','CFixedPoint'),)),
    ('power_bloc','cap_obj_power_bloc','Scope.GetPowerBloc','PowerBloc.MakeScope',(('mandates','PowerBloc.GetNumMandates','int32'),)),
    ('journal','cap_obj_journal','Scope.GetJournalEntry','JournalEntry.MakeScope',
     (('progress','JournalEntry.GetGoalProgressValue','CFixedPoint'),('goal','JournalEntry.CalcCurrentGoalValue','CFixedPoint'),
      ('percent','JournalEntry.GetGoalProgressPercent','CFixedPoint'))),
    ('front','cap_obj_front','Scope.GetFront','Front.MakeScope',
     (('advantage','Front.GetPlayerAdvantageRaw','int32'),('shown','Not(StringIsEmpty(Front.GetPlayerAdvantageDesc))','bool'))),
    ('invasion','cap_obj_invasion','Scope.GetInvasion','Invasion.MakeScope',
     (('front','Invasion.GetFront','object'),('invader','Invasion.GetInvaderCountry','object'),('invaded','Invasion.GetInvadedCountry','object'),
      ('state','Invasion.GetTargetState','object'),('ended','Invasion.HasEnded','bool'))),
    ('treaty','cap_obj_treaty_enforced','Scope.GetTreaty','Treaty.MakeScope',
     (('first','Treaty.GetFirstCountry','object'),('second','Treaty.GetSecondCountry','object'))),
    ('strait','cap_obj_strait','Scope.GetStrait','Strait.MakeScope',
     (('first','Strait.GetFirstState','object'),('second','Strait.GetSecondState','object'),('type','Strait.GetDefinition.GetType','text'))),
    ('time',None,'GetPlayer',None,(('paused','TimeKeeper.IsPaused','bool'),('speed','TimeKeeper.GetGameSpeed','int32'))),
)


def groups():
    return metric_groups()+[Group(*spec) for spec in GROUP_SPECS]


def object_lists():
    return '\n'.join([
        collect('cap_obj_building','every_scope_state =','every_scope_building ='),
        collect('cap_obj_formation','every_military_formation ='),
        collect('cap_obj_company','every_company ='),
        collect('cap_obj_character','every_scope_character ='),
        collect('cap_obj_interest_group','every_interest_group ='),
        collect('cap_obj_player_state','every_scope_state ='),
        collect('cap_obj_law','every_law ='),
        collect('cap_obj_power_bloc','power_bloc ?='),
        collect('cap_obj_front','every_scope_war =','every_scope_front ='),
        collect('cap_obj_invasion','every_scope_war =','every_scope_front =','invasion ?='),
        collect('cap_obj_strait','every_scope_strait ='),
        collect('cap_obj_treaty_enforced','every_scope_treaty =',limit='is_enforced = yes enforced_on_country ?= { this = scope:actor }'),
        collect('cap_obj_state','every_state ='),
    ])


def country_typing(game_dir,tag,mods,world):
    typing=[when(f'is_country_type = {kind}',on_root(mapped('cap_country_type','scope:cap_country',f'flag:{kind}')))
            for kind in dict(read(game_dir/'game','common/country_types',mods))]
    typing+=[when(f'country_rank = rank_value:{rank}',on_root(mapped('cap_country_rank','scope:cap_country',f'flag:{rank}')))
             for rank in dict(read(game_dir/'game','common/country_ranks',mods))]
    typing+=[when('is_power_bloc_leader = yes',on_root(listed('cap_bloc_leader','scope:cap_country'))),
             when(f'is_adjacent_to_country = c:{tag}',on_root(listed('cap_adjacent','scope:cap_country'))),
             when(f'has_diplomats_expelled = c:{tag}',on_root(listed('cap_expelled_by','scope:cap_country'))),
             when(f'c:{tag} = {{ has_diplomats_expelled = prev }}',on_root(listed('cap_expelled_of','scope:cap_country'))),
             when(f'owes_obligation_to = c:{tag}',on_root(listed('cap_owes_player','scope:cap_country'))),
             when(f'c:{tag} = {{ owes_obligation_to = prev }}',on_root(listed('cap_player_owes','scope:cap_country'))),
             on_root(listed('cap_obj_country','scope:cap_country'))]
    owning='owning_company ?= { '+on_root(mapped('cap_owning_company','scope:cap_country','prev'))+' }'
    body='\n'.join(typing)
    return (f'every_country = {{ save_scope_as = cap_country\n{body}\n{owning}\n}}\n'
            f'every_decentralized_country = {{ save_scope_as = cap_country\n{body}\n}}')


def map_data(game_dir,world):
    return Path(world['mod'])/'map_data' if world else Path(game_dir)/'game'/'map_data'


def province_block(maps):
    colors=list(dict.fromkeys('x'+color[1:].upper() for name in ('province_terrains.txt','default.map')
                              for color in re.findall(r'x[0-9A-Fa-f]{6}',(maps/name).read_text(encoding='utf-8-sig'))))
    return '\n'.join('p:'+color+' = { save_scope_as = cap_province '+on_root(listed('cap_province','scope:cap_province'))
                     +' '+on_root(mapped('cap_province_color','scope:cap_province','flag:'+color))
                     +' state ?= { '+on_root(mapped('cap_province_state','scope:cap_province','prev'))+' }'
                     +' controller ?= { '+on_root(mapped('cap_province_controller','scope:cap_province','prev'))+' } }' for color in colors)


def province_colors(maps):
    return re.findall(r'p:(x[0-9A-Fa-f]{6}) ',province_block(maps))


@timed
def capture_body(game_dir,tag,world=None):
    mods=[world['mod']] if world else []
    shown='\n'.join(decision_block(name,shown,None if missing_references(possible,world) else possible)
                    for name,shown,possible in decisions(game_dir/'game',mods) if not missing_references(shown,world))
    methods='\n'.join(filter(None,(method_block(name,gates) for name,gates in production_methods(game_dir/'game',mods))))
    picks={}
    for name,side,listing,trigger in diplomatic_state_triggers(game_dir/'game',mods):
        if not unmet_scopes(trigger)-STATE_PICK_SCOPES and not missing_references(trigger,world):
            picks[name]=picks.get(name,'')+state_picks(name,side,listing,trigger)
    diplomatic=shown_diplomatic([(name,selectable,potential,possible if diplomatic_evaluable(possible,'') and not missing_references(possible,world) else None,picks.get(name,''))
                                 for name,selectable,potential,_,_,possible in diplomatic_actions(game_dir/'game',mods)
                                 if diplomatic_evaluable(selectable,potential) and not missing_references(selectable+' '+potential,world)])
    interactions=shown_interactions([(name,potential,possible) for name,potential,possible in character_interactions(game_dir/'game',mods)
                                     if not unmet_scopes(potential+' '+possible) and not missing_references(potential+' '+possible,world)])
    buttons=shown_buttons([(entry,[(button,visible) for button,visible in entry_buttons if not unmet_scopes(visible)-{'journal_entry'} and not missing_references(visible,world)])
                           for entry,entry_buttons in journal_buttons(game_dir/'game',mods)])
    checks='\n'.join(alert_block(name,context,valid) for name,context,valid in alerts(game_dir/'game',mods)
                     if evaluable(context,valid) and not missing_references(valid,world))
    goals=[key for key,content in dict(read(game_dir/'game','common/journal_entries',mods)).items()
           if re.search(r'\b(current_value|goal_add_value)\b',content)]
    journal='\n'.join(when(f'has_journal_entry = {key}',f'je:{key} ?= {{ '+on_root(listed('cap_obj_journal','prev'))+' }') for key in goals)
    objectives='\n'.join(when(f'has_objective = {key}',listed('cap_objective','flag:'+key)) for key in dict(read(game_dir/'game','common/objectives',mods)))
    subgoals='\n'.join(when(f'has_completed_subgoal = {key}',listed('cap_subgoal','flag:'+key)) for key in dict(read(game_dir/'game','common/objective_subgoals',mods)))
    issued='every_scope_state = {\n'+'\n'.join(when(f'has_decree = {kind}',on_root(listed('cap_decree_'+kind,'prev')))
                                               for kind in dict(read(game_dir/'game','common/decrees',mods)))+'\n}'
    valid='every_scope_state = { save_scope_as = cap_state\n'+'\n'.join(
        when(state_rooted(trigger),on_root(listed('cap_valid_decree_'+kind,'scope:cap_state'))) for kind,trigger in decree_triggers(game_dir,mods)
        if not unmet_scopes(trigger)-{'cap_state'} and not missing_references(trigger,world))+'\n}'
    upkeep={goods for folder in ('common/combat_unit_types','common/mobilization_options')
            for _,content in read(game_dir/'game',folder,mods) for goods in re.findall(r'goods_input_(\w+)_add',content)}
    supply='every_scope_state = { save_scope_as = cap_state\n'+'\n'.join(f'sg:{goods} ?= {{ '+when('has_potential_supply = yes',on_root(listed('cap_supply_'+goods,'scope:cap_state')))+' }'
                                                                        for goods in sorted(upkeep))+'\n}'
    monopolies='\n'.join(when(f'country_has_building_type_monopoly = bt:{kind}',listed('cap_monopoly','flag:'+kind))
                         for kind in dict(read(game_dir/'game','common/buildings',mods)))
    consumed='market ?= {\n'+'\n'.join(f'mg:{goods} ?= {{ '+when('is_consumed_by_government_buildings = yes',on_root(listed('cap_consumed_government','flag:'+goods)))
                                         +' '+when('is_consumed_by_military_buildings = yes',on_root(listed('cap_consumed_military','flag:'+goods)))+' }'
                                         for goods in dict(read(game_dir/'game','common/goods',mods)))+'\n}'
    straits=when('can_toll_straits = yes',listed('cap_strait_power','flag:toll'))+'\n'+when('can_close_straits = yes',listed('cap_strait_power','flag:close'))
    ports='every_state = { limit = { is_potential_treaty_port = PREV } '+on_root(listed('cap_treaty_port','prev'))+' }'
    body=(f'save_scope_as = actor\nset_variable = {{ name = cap_seq value = var:interface_capture_seq }}\n'
          f'{country_typing(game_dir,tag,mods,world)}\n{object_lists()}\n{journal}\n{objectives}\n{subgoals}\n{checks}\n{shown}\n{methods}\n'
          f'{issued}\n{valid}\n{supply}\n{monopolies}\n{consumed}\n{straits}\n{ports}\n{diplomatic}\n{interactions}\n{buttons}\n{province_block(map_data(game_dir,world))}\n')
    return clears(body)+pick_clears(body)+body


def clears(body):
    lists=sorted(set(re.findall(r'add_to_variable_list = \{ name = (cap_\w+)',body)))
    maps=sorted(set(re.findall(r'add_to_variable_map = \{ name = (cap_\w+)',body))|{name for group in groups() if group.key for name in group.maps.values()}
                |set(MESSAGE_MAPS)|set(PROPOSAL_MAPS)|set(FORMABLE_MAPS)|set(BORROW_MAPS)|set(RELEASE_MAPS))
    counters=sorted(set(re.findall(r'change_variable = \{ name = (cap_alert_\w+)',body)))
    return ('\n'.join(f'clear_variable_list = {name}' for name in lists+['cap_open'])+'\n'
            +'\n'.join(f'clear_variable_map = {name}' for name in maps)+'\n'
            +'\n'.join(f'set_variable = {{ name = {name} value = 0 }}' for name in counters+['cap_message_count','cap_proposal_count'])+'\n')


MESSAGE_MAPS=('cap_message_date','cap_message_type','cap_message_name','cap_message_text')


PROPOSAL_MAPS=('cap_proposal_actor','cap_proposal_kind')


FORMABLE_MAPS=('cap_formable_name','cap_formable_ignored','cap_formable_formable')


BORROW_MAPS=('cap_borrow_name','cap_borrow_selected')


RELEASE_MAPS=('cap_release_name','cap_release_possible')


RELEASE_WIDGET=('flowcontainer = { datamodel = "[AccessPlayer.AccessReleasableCountries]" item = { widget = { size = { 0 0 } state = { name = capture_values duration = 0.001 '
                'on_finish = "[GetScriptedGui(\'cap_release\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope)'
                '.AddScope(\'index\',MakeScopeFlag(ToString_int32(PdxGuiWidget.GetIndexInDataModel))).AddScope(\'name\',MakeScopeFlag(CountryCreation.GetDefinition.GetName))'
                '.AddScope(\'possible\',MakeScopeValue(Select_CFixedPoint(CountryCreation.CanReleaseCountry(GetPlayer),\'(CFixedPoint)1\',\'(CFixedPoint)0\'))).End)]" } } } }\n')


BORROW_WIDGET=("flowcontainer = { datamodel = \"[AccessPlayer.MakeScope.GetList('cap_obj_formation')]\" item = { widget = { size = { 0 0 } datacontext = \"[Scope.GetMilitaryFormation]\" "
               'flowcontainer = { datamodel = "[MilitaryFormation.GetBorrowSettings]" item = { widget = { size = { 0 0 } state = { name = capture_values duration = 0.001 '
               'on_finish = "[GetScriptedGui(\'cap_borrow\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope)'
               '.AddScope(\'key\',MakeScopeFlag(Concatenate(Concatenate(MilitaryFormation.GetIDString, \'|\'), ToString_int32(PdxGuiWidget.GetIndexInDataModel))))'
               '.AddScope(\'name\',MakeScopeFlag(MilitaryFormationBorrowSetting.GetName))'
               '.AddScope(\'selected\',MakeScopeValue(Select_CFixedPoint(MilitaryFormationBorrowSetting.IsSelected,\'(CFixedPoint)1\',\'(CFixedPoint)0\'))).End)]" } } } } } } }\n')


FORMABLE_WIDGET=('flowcontainer = { datamodel = "[AccessPlayer.AccessFormableCountries]" item = { widget = { size = { 0 0 } state = { name = capture_values duration = 0.001 '
                 'on_finish = "[GetScriptedGui(\'cap_formable\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope)'
                 '.AddScope(\'index\',MakeScopeFlag(ToString_int32(PdxGuiWidget.GetIndexInDataModel))).AddScope(\'name\',MakeScopeFlag(CountryFormation.GetName))'
                 '.AddScope(\'ignored\',MakeScopeValue(Select_CFixedPoint(GetPlayer.IsIgnoringCountryFormation(CountryFormation.Self),\'(CFixedPoint)1\',\'(CFixedPoint)0\')))'
                 '.AddScope(\'formable\',MakeScopeValue(Select_CFixedPoint(IsValid(CountryFormation.FormCountry(GetPlayer)),\'(CFixedPoint)1\',\'(CFixedPoint)0\'))).End)]" } } } }\n')


def counted(counter,maps):
    return (f'change_variable = {{ name = {counter} add = 1 }} '
            +' '.join(mapped(name,f'var:{counter}',f'scope:{name.rsplit("_",1)[1]}') for name in maps))


CAPTURE_GUIS=('cap_message = { scope = country effect = { '+counted('cap_message_count',MESSAGE_MAPS)+' } }\n'
              'cap_proposal = { scope = country effect = { '+counted('cap_proposal_count',PROPOSAL_MAPS)+' } }\n'
              'cap_ui = { scope = country effect = { '+' '.join(f'set_variable = {{ name = cap_ui_{name} value = scope:{name} }}' for name,_ in UI_CHECKS)+' } }\n'
              'cap_open = { scope = country effect = { '+listed('cap_open','scope:name')+' } }\n'
              'cap_borrow = { scope = country effect = { '+' '.join(mapped(name,'scope:key',f'scope:{name.rsplit("_",1)[1]}') for name in BORROW_MAPS)+' } }\n'
              'cap_release = { scope = country effect = { '+' '.join(mapped(name,'scope:index',f'scope:{name.rsplit("_",1)[1]}') for name in RELEASE_MAPS)+' } }\n'
              'cap_formable = { scope = country effect = { '+' '.join(mapped(name,'scope:index',f'scope:{name.rsplit("_",1)[1]}') for name in FORMABLE_MAPS)+' } }\n')


def capture_guis():
    return CAPTURE_GUIS+'\n'.join(group.effects() for group in groups())+'\n'


def capture_widgets():
    return '\n'.join(group.widget() for group in groups())+'\n'+FORMABLE_WIDGET+BORROW_WIDGET+RELEASE_WIDGET


def plain(text):
    return ' '.join(re.sub(r'[\x00-\x1f]',' ',re.sub(r'\x15!|\x15(?:tooltip:\S+|\w+;?) |\b(?:[a-z][a-z0-9_]*|[A-Z]{3}\d+)! ?','',text)).split())
