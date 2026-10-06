import ast
import itertools
import re
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from advisors import catalogue as C
from interface.actions.catalogue import ACCESS_PERMISSIONS, ACCESS_STATUSES, BY_NAME as COMMANDS, TOLL_LEVELS
from interface.options.available import pact_terms
from interface.script import body, fields, read
from loop import translate
from loop.translate import DEALT, ENDED, ESTABLISHED, LOOP_COMMANDS, RULES, Choice

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN=('interface.actions','interface.options','loop','dashboard')
REPLAY_TOOLING={'advisors/models/entity_graph/replay.py':{'interface.options.stored'},'advisors/models/entity_graph/source.py':{'loop.run'},
                'advisors/models/entity_graph/world.py':{'interface.options.stored','loop.run'},'advisors/models/entity_graph/world_data.py':{'interface.options.stored'}}
LAWS={40+index:next(kind for kind,found in C.LAW_GROUP.items() if found==group) for index,group in enumerate(C.LAW_GROUPS)}
TREES={tree:next(name for name,found in C.TECHNOLOGY_TREE.items() if found==tree) for tree in C.TECHNOLOGY_TREES}
PLACED=[kind for kinds in C.SECTORS.values() for kind in kinds]+list(C.NAVAL.values())
KINDS=[kinds[0] for kinds in C.SECTORS.values()]+list(C.NAVAL.values())
GAME_ARTICLES={name:dict(fields(body(text))) for name,text in read(C.GAME,'common/treaty_articles')}
GAME_ACTIONS=dict(read(C.GAME,'common/diplomatic_actions'))
OFFERABLE=[name for name,found in GAME_ARTICLES.items() if 'required_inputs' not in found]
GOODS_OFFERABLE=[name for name,found in GAME_ARTICLES.items() if set(found.get('required_inputs',()))&{'goods'} and set(found['required_inputs'])<={'goods','quantity'}]
NEVER=re.compile(r'\b(selectable|potential)\s*=\s*\{\s*(#[^\n]*\s*)?always\s*=\s*no\s*\}')
PICKS=re.compile(r'scope:(first|second)_state')
VALUES={'state':[1],'building':list(range(1,len(KINDS)+1)),'building_type':PLACED,'goods':['grain'],'country':[3],'mode':['Staged','Potential','AsDemand'],
        'law':list(LAWS),'technology':list(TREES.values()),'institution':[30],'military_formation':[7,8],'fleet':[8],'power_bloc':[5],'strait':[70],'amendment':[80],
        'treaty_article':OFFERABLE,'treaty':[60,61,62,63,64],'diplomatic_action':sorted(DEALT),'charter':['investment_charter','trade_charter'],
        'access':list(ACCESS_STATUSES),'allowed':list(ACCESS_PERMISSIONS),'ownership':['any']}
STATE_PICKING=sorted({*C.STATE_DEALS,C.STATE_TRADE})
POOLS={('break_pact','diplomatic_action'):sorted(pact_terms()),
       **{(command,'diplomatic_action'):STATE_PICKING for command in ('diplomatic_action_first_state','diplomatic_action_second_state','diplomatic_action_states')},
       **{(f'{verb}_goods_treaty_article','treaty_article'):GOODS_OFFERABLE for verb in ('offer','demand')},
       ('set_strait_toll','level'):list(TOLL_LEVELS),('set_institution_level','level'):[1,2,3],('set_supply_priority','level'):['low','medium','high'],
       **{(f'set_{direction}_{kind}','level'):list(codes) for direction in ('import','export') for kind,codes in translate.TARIFF_CODES.items()}}
TABLES={'building.building,building_type':[(index+1,kind) for index,kind in enumerate(KINDS)],'building.building,state':[(index+1,1) for index in range(len(KINDS))],
        'institution.institution,investment':[(30,2)],'country.country,power_bloc':[(3,5)],'formations.army':[7],
        'treaty_article.treaty,treaty_article_type':[(60,'trade_privilege'),(61,'alliance'),(62,'trade_privilege'),(62,'military_access'),(63,'host_power_bloc_embassy'),
                                                    (64,'offer_embassy')],
        'political_movement.political_movement,managed_status':[(1,None)]}


class Options(dict):
    def __missing__(self,key):
        return []


class Snapshot:
    player=1

    def __init__(self,**tables):
        self.tables={**TABLES,**tables}

    def rows(self,table,columns,**equal):
        return list(self.tables.get(f'{table}.{columns}',()))

    def map(self,table,columns,**equal):
        return dict(self.tables.get(f'{table}.{columns}',()))

    def formations(self,kind=None):
        return list(self.tables.get(f'formations.{kind}',()))


def state(tax=2,enacting=(),duty=3,monopolies=(),for_sale=(),target=3,strait=1):
    return [mock.patch.object(translate,'player_value',lambda s,table,column:tax),mock.patch.object(translate,'enacting_laws',lambda s:list(enacting)),
            mock.patch.object(translate,'trade_level',lambda s,direction,goods:duty),mock.patch.object(translate,'monopolies',lambda s:set(monopolies)),
            mock.patch.object(translate,'privatization_requested',lambda s,ident:ident in for_sale),mock.patch.object(translate,'changing',lambda s:{30:target}),
            mock.patch.object(translate,'strait_sides',lambda s:[(70,'first',1)]),
            mock.patch.object(translate,'strait_value',lambda s,ident,column:strait+column.endswith('permissions'))]


def offer(options,snapshot=None,**settings):
    patches=state(**settings)
    for patch in patches:
        patch.start()
    try:
        return translate.offer(snapshot or Snapshot(),Options(options))
    finally:
        for patch in patches:
            patch.stop()


def fuzz(command):
    names=[spec.partition(':')[0] for spec in COMMANDS[command].params]
    pools=[POOLS.get((command,name)) or (['VeryLow','Low','High','VeryHigh'] if name=='level' else VALUES.get(name,[1])) for name in names]
    return [dict(zip(names,values)) for values in itertools.product(*pools)]


def carried(offered):
    return {command for choices in offered.values() for choice in choices for command,_ in choice.commands}


def everything():
    reached={}
    for settings in ({'tax':1,'duty':1,'target':1},{'tax':3,'duty':5},{'enacting':list(LAWS)[:1],'monopolies':PLACED,'for_sale':VALUES['building']}):
        for flags in ([],[(1,)]):
            snapshot=Snapshot(**{'player_taxed_goods.goods':[('grain',)] if flags else [],'player_colonization_paused.state':flags,
                                 'charter.charter,company,company_charter_type':[(9,1,'investment_charter')] if flags else [],
                                 'formation_mobilization_option.formation,mobilization_option':[(7,1)] if flags else [],
                                 'political_movement.political_movement,managed_status':[(1,translate.PROMOTED if flags else translate.SUPPRESSED)],
                                 'war_goal.diplomatic_play,war_goal_type,target_country,holder,pressed':[(1,1,3,1,True)] if flags else []})
            for name,choices in offer({command:fuzz(command) for command in COMMANDS},snapshot,**settings).items():
                reached.setdefault(name,[]).extend(choices)
    for name,choices in offer({'decline_treaty':[{'country':3}],'quick_decline_proposal':[{'country':3}]}).items():
        reached.setdefault(name,[]).extend(choices)
    return reached


class CatalogueTests(unittest.TestCase):
    def test_there_are_ninety_five_levers_in_their_blocks(self):
        self.assertEqual(len(C.NAMES),95)
        self.assertEqual(len(set(C.NAMES)),95)
        self.assertEqual(Counter(lever.domain for lever in C.LEVERS),{C.CONSTRUCT:12,C.QUEUE:7,C.RAISE:27,C.LOWER:27,C.SINGLE:18,C.ANSWER:4})
        self.assertEqual([lever.name for lever in C.LEVERS if lever.domain==C.CONSTRUCT],list(C.SECTORS))
        self.assertEqual({lever.name.removeprefix('raise_') for lever in C.LEVERS if lever.domain==C.RAISE},
                         {lever.name.removeprefix('lower_') for lever in C.LEVERS if lever.domain==C.LOWER})

    def test_laws_have_one_lever(self):
        lawful={lever.name for lever in C.LEVERS if any(C.LAW in params or C.AMENDMENT in params for _,params in lever.acts)}
        self.assertEqual(lawful,{'laws'})
        self.assertEqual({C.LEVER[name] for name in ('enact_new_law','negotiate_over_law','abandon_law_enactment','impose_law_on_subject','repeal_law_amendment')},{'laws'})

    def test_every_act_has_one_lever_and_one_name(self):
        names=[action.name for action in C.ACTIONS]
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual({C.LEVER[name] for name in names},{*C.NAMES,'answer_event'})
        for lever in C.LEVERS:
            if len(lever.acts)==1:
                self.assertEqual(lever.acts[0][0],lever.name)
        self.assertEqual(set(C.NAMES)&set(names),{lever.name for lever in C.LEVERS if len(lever.acts)==1})

    def test_no_lever_or_act_carries_the_name_of_an_interface_command(self):
        self.assertEqual((set(C.NAMES)|set(C.PARAMS))&set(COMMANDS),set())

    def test_military_commands_have_three_independent_levers_and_flags_are_retired(self):
        self.assertNotIn('disposition_of_forces',C.NAMES)
        self.assertEqual({lever.name:len(lever.acts) for lever in C.LEVERS if lever.name.startswith('military_')},
                         {'military_leadership':5,'military_organisation':13,'military_operations':23})
        for name,lever in (('recruit_commander','military_leadership'),('promote_officer','military_leadership'),
                           ('combine_armies','military_organisation'),('move_ship','military_organisation'),
                           ('send_to_front','military_operations'),('give_order','military_operations'),('recall_fleet_for_repairs','military_operations')):
            self.assertEqual(C.LEVER[name],lever)
        self.assertNotIn('set_army_flag',C.PARAMS)
        self.assertNotIn('set_formation_flag',COMMANDS)
        self.assertEqual(offer({'set_formation_flag':[{'military_formation':7,'flag':1}]}),{})

    def test_only_construction_is_split_by_building_type(self):
        self.assertEqual(len(PLACED),len(set(PLACED)))
        split=[lever.name for lever in C.LEVERS if any(C.KIND in params for _,params in lever.acts) and lever.domain not in (C.CONSTRUCT,C.QUEUE)]
        self.assertEqual(split,['raise_subsidies_statewide','lower_subsidies_statewide','raise_state_ownership','lower_state_ownership','raise_companies_and_charters',
                                'lower_companies_and_charters','raise_commercial_treaties','change_production_method_statewide','nationalise_statewide'])

    def test_every_building_the_government_can_queue_has_a_place(self):
        queued={name for name,found in C.BUILDINGS.items() if found.get('buildable')!=['no'] and found.get('recruits_combat_units')!=['yes']}
        self.assertEqual(queued-set(PLACED),set())
        self.assertLessEqual(set(PLACED),set(C.BUILDINGS))

    def test_every_treaty_article_named_exists_in_the_installed_game(self):
        self.assertLessEqual({*C.COMMERCIAL,*C.COMMERCIAL_GOODS,*C.SECURITY,*C.BLOC_ARTICLES,C.MEMBERSHIP},set(GAME_ARTICLES))
        self.assertEqual(set(GOODS_OFFERABLE),set(C.COMMERCIAL_GOODS))

    def test_every_diplomatic_action_the_game_lets_a_country_choose_has_an_act(self):
        self.assertLessEqual({*ESTABLISHED.values(),*(name for names in ENDED.values() for name in names)},set(GAME_ACTIONS))
        choosable={name for name,text in GAME_ACTIONS.items() if not NEVER.search(text) and not PICKS.search(text)}
        self.assertEqual(choosable-DEALT,set())
        self.assertEqual({name for name,text in GAME_ACTIONS.items() if not NEVER.search(text) and PICKS.search(text)},set(STATE_PICKING))
        self.assertLessEqual({name for names in ENDED.values() for name in names},set(pact_terms()))

    def test_categories_and_trees_are_the_games_own(self):
        self.assertEqual(set(C.LAW_CATEGORY.values()),{'power_structure','economy','human_rights'})
        self.assertEqual(set(C.TECHNOLOGY_TREE.values()),set(C.TECHNOLOGY_TREES))

    def test_answers_pair_an_accepting_act_with_a_declining_act(self):
        for accept,decline in C.PROPOSALS:
            self.assertEqual(C.BY_NAME[accept].domain,C.ANSWER)
            self.assertNotEqual(C.LEVER[accept],C.LEVER[decline])
        self.assertEqual(C.ANSWERS,{'answer_event',*(name for pair in C.PROPOSALS for name in pair)})


class SeparationTests(unittest.TestCase):
    def imports(self,path):
        found=set()
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node,ast.ImportFrom) and not node.level:
                found.add(node.module)
        return found

    def test_advisor_code_never_imports_the_interface_taxonomy_or_the_loop(self):
        for path in sorted((ROOT/'advisors').rglob('*.py')):
            name=path.relative_to(ROOT).as_posix()
            reached={module for module in self.imports(path) if any(module==root or module.startswith(root+'.') for root in FORBIDDEN)}
            self.assertEqual(reached,REPLAY_TOOLING.get(name,set()),name)

    def test_initializers_and_pickers_never_name_an_interface_command(self):
        commands={name for name in COMMANDS if '_' in name}
        for folder in ('initializers','pickers','data'):
            for path in sorted((ROOT/'advisors'/folder).rglob('*.py')):
                named={node.value for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
                self.assertEqual(named&commands,set(),path.name)


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reached=everything()

    def test_every_act_has_a_rule_and_every_rule_an_act(self):
        self.assertEqual(set(RULES),set(C.PARAMS))

    def test_every_act_can_fire(self):
        self.assertEqual(set(C.PARAMS)-set(self.reached),set())

    def test_every_interface_command_is_carried_except_the_loops_own_time_control(self):
        self.assertEqual(LOOP_COMMANDS,{'pause','unpause','set_speed'})
        self.assertEqual(carried(self.reached)&LOOP_COMMANDS,set())
        self.assertEqual(set(COMMANDS)-carried(self.reached)-LOOP_COMMANDS,set())

    def options(self,command,param):
        return {option[param] for choices in self.reached.values() for choice in choices for name,option in choice.commands if name==command}

    def test_every_building_type_treaty_article_and_diplomatic_action_on_offer_is_carried(self):
        self.assertEqual(self.options('build','building_type'),set(PLACED))
        for command in ('offer_treaty_article','demand_treaty_article'):
            self.assertEqual(self.options(command,'treaty_article'),set(OFFERABLE),command)
        for command in ('offer_goods_treaty_article','demand_goods_treaty_article'):
            self.assertEqual(self.options(command,'treaty_article'),set(GOODS_OFFERABLE),command)
        for command in ('diplomatic_action','diplomatic_action_obligation'):
            self.assertEqual(self.options(command,'diplomatic_action'),set(DEALT),command)
        self.assertEqual(self.options('break_pact','diplomatic_action'),set(pact_terms()))
        self.assertEqual(self.options('withdraw_treaty','treaty'),set(VALUES['treaty']))

    def test_a_diplomatic_action_no_act_carries_stops_the_offer(self):
        with self.assertRaises(RuntimeError):
            offer({'diplomatic_action':[{'country':3,'diplomatic_action':'puppet'}]})

    def test_every_offered_choice_carries_exactly_the_declared_parameters(self):
        for name,choices in self.reached.items():
            for choice in choices:
                self.assertEqual(set(choice.params),{param for param,_ in C.PARAMS[name]},name)
                self.assertTrue(choice.commands,name)

    def test_a_choice_that_departs_from_the_catalogue_is_refused(self):
        with mock.patch.dict(RULES,{'raise_subsidies':lambda c:[Choice({'building':1,'extra':2},[('subsidies_on',{'building':1})])]}):
            with self.assertRaises(RuntimeError):
                offer({})


class TranslationTests(unittest.TestCase):
    def test_construction_is_split_by_what_is_built(self):
        options=[{'state':1,'building_type':kind} for kind in [*KINDS,'building_barrack']]
        found=offer({'build':options})
        for name,kinds in C.SECTORS.items():
            self.assertEqual([choice.params for choice in found[name]],[{'state':1,'building_type':kinds[0]}])
        for name,kind in C.NAVAL.items():
            self.assertEqual(found[name],[Choice({'state':1},[('build',{'state':1,'building_type':kind})])])
        self.assertEqual(sum(len(choices) for choices in found.values()),len(KINDS))
        self.assertEqual({C.LEVER[name] for name in C.NAVAL},{'raise_navy'})

    def test_cancelling_merges_the_queue_route_and_the_building_route(self):
        found=offer({'cancel_queue_item':[{'state':1,'building_type':KINDS[0]}],'cancel_construction':[{'building':1},{'building':2}]})['cancel_queued_construction']
        self.assertEqual(found[0],Choice({'state':1,'building_type':KINDS[0]},[('cancel_queue_item',{'state':1,'building_type':KINDS[0]}),('cancel_construction',{'building':1})]))
        self.assertEqual(found[1],Choice({'state':1,'building_type':KINDS[1]},[('cancel_construction',{'building':2})]))

    def test_queue_priority_has_a_raising_and_a_lowering_lever_for_buildings_and_ships(self):
        item={'state':1,'building_type':KINDS[0]}
        ship={'index':2}
        found=offer({'raise_queue_item':[item],'first_queue_item':[item],'lower_queue_item':[item],'last_queue_item':[item],
                     'raise_ship_item':[ship],'first_ship_item':[ship],'lower_ship_item':[ship],'last_ship_item':[ship],'cancel_ship_item':[ship]})
        self.assertEqual(found['raise_building_priority'],[Choice(item,[('raise_queue_item',item),('first_queue_item',item)])])
        self.assertEqual(found['lower_building_priority'],[Choice(item,[('lower_queue_item',item),('last_queue_item',item)])])
        self.assertEqual(found['raise_ship_priority'],[Choice(ship,[('raise_ship_item',ship),('first_ship_item',ship)])])
        self.assertEqual(found['lower_ship_priority'],[Choice(ship,[('lower_ship_item',ship),('last_ship_item',ship)])])
        self.assertEqual({C.LEVER[name] for name in found},{'raise_construction_priority','lower_construction_priority','lower_navy'})

    def test_halting_and_restarting_have_a_lever_each(self):
        found=offer({'pause_construction':[{}],'pause_all_construction':[{}],'pause_construction_output':[{'building':1}],'pause_ship_construction':[{}],
                     'resume_construction':[{}],'resume_all_construction':[{}],'resume_construction_output':[{'building':1}],'resume_ship_construction':[{}]})
        self.assertEqual(found['halt_construction_queue'],[Choice({},[('pause_construction',{}),('pause_all_construction',{})])])
        self.assertEqual(found['restart_construction_queue'],[Choice({},[('resume_construction',{}),('resume_all_construction',{})])])
        self.assertEqual(Counter(C.LEVER[name] for name in found),{'halt_construction':3,'restart_construction':3})

    def test_the_whole_state_forms_have_levers_of_their_own(self):
        group={'building_type':KINDS[0],'state':1,'ownership':'any'}
        method={**group,'production_method':'pm_x'}
        found=offer({'subset_subsidies_on_state':[group],'subset_subsidies_off_state':[group],'bulk_nationalize_state':[group],'bulk_switch_production_method_state':[method],
                     'subsidies_on':[{'building':1}],'switch_production_method':[{'building':1,'production_method':'pm_x'}]})
        self.assertEqual(found['raise_subsidies_statewide'],[Choice(group,[('subset_subsidies_on_state',group)])])
        self.assertEqual(found['switch_methods_statewide'],[Choice(method,[('bulk_switch_production_method_state',method)])])
        self.assertEqual(sorted(C.LEVER[name] for name in found),['change_production_method','change_production_method_statewide','lower_subsidies_statewide','nationalise_statewide',
                                                                  'raise_subsidies','raise_subsidies_statewide'])

    def test_a_level_moves_one_step_at_a_time(self):
        levels=[{'level':level} for level in ('VeryLow','Low','High','VeryHigh')]
        found=offer({'set_tax_level':levels,'set_supply_ship_construction':levels},tax=2)
        self.assertEqual(found['raise_tax_level'],[Choice({},[('set_tax_level',{'level':'High'})])])
        self.assertEqual(found['lower_tax_level'],[Choice({},[('set_tax_level',{'level':'Low'})])])
        self.assertEqual(found['raise_supply_ship_share'],[Choice({},[('set_supply_ship_construction',{'level':'High'})])])
        self.assertEqual(C.LEVER['lower_supply_ship_share'],'lower_navy')
        self.assertNotIn('raise_government_wages',offer({'set_government_wages':levels[:3]},tax=4))

    def test_a_tariff_steps_toward_tariff_or_toward_subvention(self):
        options={f'set_import_{kind}':[{'goods':'grain','level':level} for level in codes] for kind,codes in translate.TARIFF_CODES.items()}
        found=offer(options,duty=3)
        self.assertEqual(found['raise_import_tariff'],[Choice({'goods':'grain'},[('set_import_tariff',{'goods':'grain','level':'Low'})])])
        self.assertEqual(found['lower_import_tariff'],[Choice({'goods':'grain'},[('set_import_subvention',{'goods':'grain','level':'Low'})])])
        found=offer(options,duty=2)
        self.assertEqual(found['raise_import_tariff'],[Choice({'goods':'grain'},[('set_import_tariff',{'goods':'grain','level':'None'})])])
        self.assertEqual(found['lower_import_tariff'],[Choice({'goods':'grain'},[('set_import_subvention',{'goods':'grain','level':'High'})])])
        self.assertNotIn('raise_import_tariff',offer(options,duty=6))
        self.assertNotIn('raise_export_tariff',found)

    def test_a_strait_is_restricted_or_opened_one_step_at_a_time(self):
        options={'set_strait_toll':[{'strait':70,'level':level} for level in TOLL_LEVELS],'set_strait_access':[{'strait':70,'state':1,'access':access} for access in ACCESS_STATUSES],
                 'set_strait_allowed':[{'strait':70,'state':1,'allowed':allowed} for allowed in ACCESS_PERMISSIONS]}
        found=offer(options,strait=1)
        self.assertEqual(found['raise_strait_toll'],[Choice({'strait':70},[('set_strait_toll',{'strait':70,'level':'MediumTolls'})])])
        self.assertEqual(found['lower_strait_toll'],[Choice({'strait':70},[('set_strait_toll',{'strait':70,'level':'NoTolls'})])])
        self.assertEqual(found['tighten_strait_access'][0].commands,[('set_strait_access',{'strait':70,'state':1,'access':'Closed'})])
        self.assertEqual(found['loosen_strait_access'][0].commands,[('set_strait_access',{'strait':70,'state':1,'access':'Open'})])
        self.assertEqual(found['narrow_strait_passage'][0].commands,[('set_strait_allowed',{'strait':70,'state':1,'allowed':'OnlyController'})])
        self.assertEqual(found['widen_strait_passage'][0].commands,[('set_strait_allowed',{'strait':70,'state':1,'allowed':'NoEnemies'})])
        self.assertEqual({C.LEVER[name] for name in found},{'raise_strait_restrictions','lower_strait_restrictions'})
        self.assertNotIn('lower_strait_toll',offer(options,strait=0))

    def test_a_toggle_is_read_from_the_snapshot(self):
        taxed=Snapshot(**{'player_taxed_goods.goods':[('grain',)]})
        self.assertEqual(list(offer({'toggle_consumption_tax':[{'goods':'grain'}]})),['raise_consumption_taxes'])
        self.assertEqual(list(offer({'toggle_consumption_tax':[{'goods':'grain'}]},taxed)),['lower_consumption_taxes'])
        self.assertEqual(list(offer({'toggle_monopoly':[{'building_type':'building_port'}]})),['reserve_building_type_for_state'])
        self.assertEqual(list(offer({'toggle_monopoly':[{'building_type':'building_port'}]},monopolies=['building_port'])),['end_state_monopoly'])
        self.assertEqual(list(offer({'toggle_privatization':[{'building':1}]})),['offer_building_for_sale'])
        self.assertEqual(list(offer({'toggle_privatization':[{'building':1}]},for_sale=[1])),['withdraw_building_from_sale'])
        held=Snapshot(**{'charter.charter,company,company_charter_type':[(9,1,'trade_charter')],'player_colonization_paused.state':[(1,)],
                         'formation_mobilization_option.formation,mobilization_option':[(7,'rail')]})
        options={'toggle_charter':[{'company':1,'charter':'trade_charter'},{'company':1,'charter':'investment_charter'}],'toggle_pause_colonization':[{'state':1},{'state':2}],
                 'toggle_mobilization_option':[{'military_formation':7,'mobilization_option':'rail'},{'military_formation':7,'mobilization_option':'chocolate'}]}
        found=offer(options,held)
        self.assertEqual([choice.params for choice in found['revoke_charter']],[{'company':1,'charter':'trade_charter'}])
        self.assertEqual([choice.params for choice in found['grant_charter']],[{'company':1,'charter':'investment_charter'}])
        self.assertEqual([choice.params for choice in found['resume_colony']],[{'state':1}])
        self.assertEqual([choice.params for choice in found['pause_colony']],[{'state':2}])
        self.assertEqual([choice.params['mobilization_option'] for choice in found['switch_off_mobilisation_option']],['rail'])
        self.assertEqual([choice.params['mobilization_option'] for choice in found['switch_on_mobilisation_option']],['chocolate'])

    def test_a_movement_is_bolstered_or_suppressed_by_its_present_status(self):
        options={'toggle_bolster_movement':[{'political_movement':1}],'toggle_suppress_movement':[{'political_movement':1}]}
        self.assertEqual(sorted(offer(options)),['bolster_movement','suppress_movement'])
        promoted=Snapshot(**{'political_movement.political_movement,managed_status':[(1,translate.PROMOTED)]})
        self.assertEqual(sorted(offer(options,promoted)),['stop_bolstering_movement','suppress_movement'])
        suppressed=Snapshot(**{'political_movement.political_movement,managed_status':[(1,translate.SUPPRESSED)]})
        self.assertEqual(sorted(offer(options,suppressed)),['bolster_movement','stop_suppressing_movement'])

    def test_an_institution_moves_one_level_and_a_change_under_way_is_cancelled_against_its_direction(self):
        found=offer({'set_institution_level':[{'institution':30,'level':level} for level in (1,3,4)],'stop_institution_change':[{'institution':30}]},target=3)
        self.assertEqual(found['raise_institution_level'],[Choice({'institution':30},[('set_institution_level',{'institution':30,'level':3})])])
        self.assertEqual(found['lower_institution_level'],[Choice({'institution':30},[('set_institution_level',{'institution':30,'level':1})])])
        self.assertEqual(found['cancel_institution_increase'],[Choice({'institution':30},[('stop_institution_change',{'institution':30})])])
        self.assertEqual(C.LEVER['cancel_institution_increase'],'lower_institutions')
        found=offer({'stop_institution_change':[{'institution':30}]},target=1)
        self.assertEqual(list(found),['cancel_institution_decrease'])
        self.assertEqual(C.LEVER['cancel_institution_decrease'],'raise_institutions')

    def test_government_takes_a_group_or_its_party_in_or_out(self):
        found=offer({'reform_government':[{'interest_group':4,'mode':'Potential'},{'interest_group':5,'mode':'Staged'}],
                     'reform_government_party':[{'member':6,'mode':'Potential'}]})
        self.assertEqual([choice.params for choice in found['raise_government']],[{'interest_group':4},{'interest_group':6}])
        self.assertEqual(found['lower_government'],[Choice({'interest_group':5},[('reform_government',{'interest_group':5,'mode':'Staged'})])])

    def test_a_treaty_is_filed_by_its_article_and_says_who_gives(self):
        found=offer({'offer_treaty_article':[{'country':3,'treaty_article':'trade_privilege'},{'country':3,'treaty_article':'military_access'},{'country':3,'treaty_article':'take_on_debt'},
                                             {'country':3,'treaty_article':'host_power_bloc_embassy'},{'country':3,'treaty_article':'offer_embassy'}],
                     'demand_treaty_article':[{'country':3,'treaty_article':'foreign_investment_rights'}],'agree_treaty_article':[{'country':3,'treaty_article':'alliance'}],
                     'demand_goods_treaty_article':[{'country':3,'treaty_article':'goods_transfer','goods':'grain'}]})
        self.assertEqual([choice.params for choice in found['propose_commercial_article']],
                         [{'country':3,'treaty_article':'trade_privilege','giver':'us'},{'country':3,'treaty_article':'take_on_debt','giver':'us'},
                          {'country':3,'treaty_article':'foreign_investment_rights','giver':'them'}])
        self.assertEqual([choice.params for choice in found['propose_security_article']],
                         [{'country':3,'treaty_article':'military_access','giver':'us'},{'country':3,'treaty_article':'alliance','giver':'both'}])
        self.assertEqual([choice.params for choice in found['propose_goods_article']],[{'country':3,'treaty_article':'goods_transfer','goods':'grain','giver':'them'}])
        self.assertEqual([choice.params['treaty_article'] for choice in found['propose_bloc_article']],['host_power_bloc_embassy'])
        self.assertEqual([choice.params['treaty_article'] for choice in found['propose_diplomatic_article']],['offer_embassy'])
        self.assertEqual(sum(len(choices) for choices in found.values()),8)
        self.assertEqual((C.LEVER['propose_bloc_article'],C.LEVER['propose_diplomatic_article']),('raise_power_bloc','raise_relations'))

    def test_withdrawing_files_every_treaty_once_and_a_mixed_one_under_security(self):
        found=offer({'withdraw_treaty':[{'treaty':treaty} for treaty in VALUES['treaty']]})
        self.assertEqual([choice.params for choice in found['withdraw_commercial_treaty']],[{'treaty':60}])
        self.assertEqual([choice.params for choice in found['withdraw_security_treaty']],[{'treaty':61},{'treaty':62}])
        self.assertEqual([choice.params for choice in found['withdraw_bloc_treaty']],[{'treaty':63}])
        self.assertEqual([choice.params for choice in found['withdraw_diplomatic_treaty']],[{'treaty':64}])

    def test_a_diplomatic_action_goes_to_the_lever_it_moves_with_or_without_an_obligation(self):
        plain=[{'country':3,'diplomatic_action':action} for action in sorted(DEALT)]
        owed=[{**option,'obligation':'CallInObligation'} for option in plain if option['diplomatic_action']=='embargo']
        found=offer({'diplomatic_action':plain,'diplomatic_action_obligation':owed})
        self.assertEqual({name:found[name][0].commands[0][1]['diplomatic_action'] for name in ESTABLISHED},ESTABLISHED)
        self.assertEqual(found['raise_embargoes'],[Choice({'country':3},[('diplomatic_action',plain[sorted(DEALT).index('embargo')]),('diplomatic_action_obligation',owed[0])])])
        self.assertEqual(found['ask_to_join_power_bloc'],[Choice({'power_bloc':5},[('diplomatic_action',{'country':3,'diplomatic_action':'join_power_bloc'})])])
        self.assertEqual(len(found),len(ESTABLISHED)+1)
        for lever,acts in C.ESTABLISHED.items():
            self.assertEqual({C.LEVER[name] for name in acts},{lever})

    def test_ending_a_pact_goes_to_the_lever_it_moves(self):
        found=offer({'break_pact':[{'country':3,'diplomatic_action':action} for action in sorted(pact_terms())]})
        for name,actions in ENDED.items():
            self.assertEqual({choice.commands[0][1]['diplomatic_action'] for choice in found[name]},set(actions)&set(pact_terms()),name)
            self.assertEqual(found[name][0].params,{'country':3})
        self.assertEqual({C.LEVER[name] for name in ('lower_embargoes','end_rivalry','stop_damaging_relations','stop_improving_relations','end_service_exemption',
                                                     'take_back_subject_market','grant_independence')},
                         {'lower_embargoes','raise_relations','lower_relations','raise_hold_over_subjects','lower_hold_over_subjects'})
        named={action for actions in ENDED.values() for action in actions}
        self.assertEqual({choice.params['diplomatic_action'] for choice in found[C.OTHER_PACT]},set(pact_terms())-named)
        self.assertEqual(sum(len(choices) for choices in found.values()),len(pact_terms()))

    def test_every_demand_is_one_of_two_acts_and_sides_are_taken_or_left(self):
        option={'country':3,'diplomatic_play_type':'dp_open_market'}
        play={'diplomatic_play':2}
        sway={'diplomatic_play':2,'country':3}
        pact={**sway,'diplomatic_action':'protectorate'}
        found=offer({'start_play_country':[option],'start_play_confirmed':[{**option,'mode':'AsDemand'},{**option,'mode':'ForcePlay'}],
                     'start_play_state':[{'state':1,'diplomatic_play_type':'dp_conquer_state'}],
                     'add_war_goal_state':[{'diplomatic_play':2,'war_goal_type':'conquer_state','holder':1,'state':1}],
                     'offer_sway':[sway],'offer_sway_ally':[sway],'offer_sway_subjection':[pact],'support_initiator':[play],'support_target':[play],'lean_initiator':[play],'lean_target':[play]})
        self.assertEqual(found['demand_of_country'],[Choice(option,[('start_play_country',option),('start_play_confirmed',{**option,'mode':'AsDemand'}),
                                                                   ('start_play_confirmed',{**option,'mode':'ForcePlay'})])])
        self.assertEqual(found['demand_for_state'][0].params,{'state':1,'diplomatic_play_type':'dp_conquer_state'})
        self.assertEqual(found['add_demand_for_state'][0].params,{'diplomatic_play':2,'war_goal_type':'conquer_state','holder':1,'state':1})
        self.assertEqual(found['sway_country'],[Choice(sway,[('offer_sway',sway)])])
        self.assertEqual(found['sway_ally'],[Choice(sway,[('offer_sway_ally',sway)])])
        self.assertEqual(found['sway_with_pact'],[Choice(pact,[('offer_sway_subjection',pact)])])
        self.assertEqual(len(found),10)
        self.assertEqual({C.LEVER[name] for name in found},{'raise_confrontations'})
        found=offer({'stay_on_fence':[play],'declare_neutrality':[play],'back_down':[play]})
        self.assertEqual(sorted(found),['stay_neutral','stay_on_the_fence','withdraw_from_confrontation'])
        self.assertEqual({C.LEVER[name] for name in found},{'lower_confrontations'})

    def test_everything_done_to_a_law_is_one_lever(self):
        under_way=next(iter(LAWS))
        found=offer({'enact_law':[{'law':law} for law in LAWS],'negotiate':[{'interest_group':4}],'cancel_enactment':[{}],'impose_law':[{'law':under_way}],
                     'repeal_amendment':[{'amendment':80}]},enacting=[under_way])
        self.assertEqual(len(found['enact_new_law']),len(LAWS))
        self.assertEqual(found['negotiate_over_law'],[Choice({'interest_group':4},[('negotiate',{'interest_group':4})])])
        self.assertEqual(found['abandon_law_enactment'],[Choice({'law':under_way},[('cancel_enactment',{})])])
        self.assertEqual(found['impose_law_on_subject'],[Choice({'law':under_way},[('impose_law',{'law':under_way})])])
        self.assertEqual(found['repeal_law_amendment'],[Choice({'amendment':80},[('repeal_amendment',{'amendment':80})])])
        self.assertEqual({C.LEVER[name] for name in found},{'laws'})

    def test_research_is_filed_by_tree_and_leaving_the_queue_has_its_own_lever(self):
        found=offer({'research':[{'technology':name} for name in TREES.values()],'queue_research':[{'technology':TREES['military']}],
                     'dequeue_research':[{'technology':TREES['society']}]})
        for tree,name in TREES.items():
            self.assertEqual(found[f'research_{tree}_technology'],[Choice({'technology':name},[('research',{'technology':name})])])
        self.assertEqual(sorted(name for name in found if name.startswith('queue_')),['queue_military_technology'])
        self.assertEqual(found['cancel_queued_research'],[Choice({'technology':TREES['society']},[('dequeue_research',{'technology':TREES['society']})])])
        self.assertEqual(C.BY_NAME['cancel_queued_research'].domain,C.QUEUE)

    def test_incorporation_starts_under_one_lever_and_stops_under_the_other(self):
        found=offer({'incorporate':[{'state':1}],'unincorporate':[{'state':2}]})
        self.assertEqual(found,{'raise_incorporation':[Choice({'state':1},[('incorporate',{'state':1})])],'lower_incorporation':[Choice({'state':2},[('unincorporate',{'state':2})])]})

    def test_recruiting_merges_its_two_routes(self):
        found=offer({'recruit_from_formation':[{'military_formation':7,'combat_unit_type':'line','state':1}],'recruit':[{'building':1,'military_formation':7,'combat_unit_type':'line'}]})
        self.assertEqual(found['raise_regular_army'],[Choice({'military_formation':7,'combat_unit_type':'line','state':1},
                                                             [('recruit_from_formation',{'military_formation':7,'combat_unit_type':'line','state':1}),
                                                              ('recruit',{'building':1,'military_formation':7,'combat_unit_type':'line'})])])

    def test_disbanding_tells_an_army_from_a_fleet(self):
        found=offer({'disband_formation':[{'military_formation':7},{'military_formation':8}]})
        self.assertEqual([choice.params for choice in found['disband_army']],[{'military_formation':7}])
        self.assertEqual([choice.params for choice in found['disband_fleet']],[{'military_formation':8}])
        self.assertEqual(C.LEVER['disband_army'],'lower_regular_army')
        self.assertEqual(C.LEVER['disband_fleet'],'lower_navy')

    def test_invasions_embarking_and_characters_are_carried(self):
        land={'military_formation':7,'state':1}
        sea={'military_formation':7,'fleet':8,'state':1}
        boarding={'military_formation':7,'fleet':8}
        person={'character':11,'interaction':'grant_leadership'}
        found=offer({'plan_land_invasion':[land],'plan_naval_invasion':[sea],'embark_formation':[boarding],'character_interaction':[person],'promote_commander':[{'character':11}],
                     'replace_principle':[{'slot':0,'power_bloc_principle':'principle_x_1'}]})
        self.assertEqual(found['plan_invasion'],[Choice(land,[('plan_land_invasion',land)])])
        self.assertEqual(found['plan_seaborne_invasion'],[Choice(sea,[('plan_naval_invasion',sea)])])
        self.assertEqual(found['embark_troops'],[Choice(boarding,[('embark_formation',boarding)])])
        self.assertEqual(found['interact_with_character'],[Choice(person,[('character_interaction',person)])])
        self.assertEqual(found['replace_bloc_principle'][0].params,{'slot':0,'power_bloc_principle':'principle_x_1'})
        self.assertEqual({name:C.LEVER[name] for name in found},{'plan_invasion':'military_operations','plan_seaborne_invasion':'military_operations',
                                                                 'embark_troops':'military_operations','promote_officer':'military_leadership',
                                                                 'interact_with_character':'interact_with_character','replace_bloc_principle':'raise_power_bloc'})

    def test_peace_goals_are_pressed_or_dropped_by_their_present_state(self):
        goal={'diplomatic_play':1,'war_goal_type':'conquer_state','country':3}
        self.assertEqual(list(offer({'toggle_press_war_goal':[goal]})),['press_war_goal'])
        pressed=Snapshot(**{'war_goal.diplomatic_play,war_goal_type,target_country,holder,pressed':[(1,'conquer_state',3,1,True)]})
        self.assertEqual(list(offer({'toggle_press_war_goal':[goal]},pressed)),['drop_war_goal'])

    def test_a_quick_decline_joins_the_only_refusal_waiting(self):
        country={'country':3}
        found=offer({'decline_treaty':[country],'quick_decline_proposal':[country]})
        self.assertEqual(found['refuse_treaty'],[Choice(country,[('decline_treaty',country),('quick_decline_proposal',country)])])
        found=offer({'decline_treaty':[country],'reject_demand':[country],'quick_decline_proposal':[country]})
        self.assertEqual(found['refuse_treaty'],[Choice(country,[('decline_treaty',country)])])
        self.assertEqual(found['refuse_demand'],[Choice(country,[('reject_demand',country)])])


if __name__=='__main__':
    unittest.main()
