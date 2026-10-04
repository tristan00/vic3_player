import ast
import itertools
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from advisors import catalogue as C
from interface.actions.catalogue import BY_NAME as COMMANDS
from interface.script import read
from loop import translate
from loop.translate import LEFT_OUT, RULES, UNOFFERED, Choice

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN=('interface.actions','interface.options','loop','dashboard')
REPLAY_TOOLING={'advisors/models/entity_graph/replay.py':{'interface.options.stored'},'advisors/models/entity_graph/source.py':{'loop.run'},
                'advisors/models/entity_graph/world.py':{'interface.options.stored','loop.run'},'advisors/models/entity_graph/world_data.py':{'interface.options.stored'}}
LAWS={40+index:next(kind for kind,found in C.LAW_GROUP.items() if found==group) for index,group in enumerate(C.LAW_GROUPS)}
TREES={tree:next(name for name,found in C.TECHNOLOGY_TREE.items() if found==tree) for tree in C.TECHNOLOGY_TREES}
KINDS=[kinds[0] for kinds in C.SECTORS.values()]+[C.NAVAL_ADMINISTRATION,'building_art_academy']
VALUES={'state':[1],'building':list(range(1,len(KINDS)+1)),'building_type':KINDS,'goods':['grain'],'country':[3],'mode':['Staged','Potential','AsDemand'],
        'law':list(LAWS),'technology':list(TREES.values()),'institution':[30],'military_formation':[7,8],'power_bloc':[5],
        'treaty_article':[*C.COMMERCIAL,*C.COMMERCIAL_GOODS,*C.SECURITY,'join_power_bloc','take_on_debt'],'treaty':[60,61,62],
        'diplomatic_action':[*translate.DIPLOMACY.values(),'join_power_bloc','fund_lobbies'],'charter':['investment_charter','trade_charter']}
LEVELS_OF={'set_institution_level':[1,2,3],'set_supply_priority':['low','medium','high'],
           **{f'set_{direction}_{kind}':list(codes) for direction in ('import','export') for kind,codes in translate.TARIFF_CODES.items()}}
TABLES={'building.building,building_type':[(index+1,kind) for index,kind in enumerate(KINDS)],'building.building,state':[(index+1,1) for index in range(len(KINDS))],
        'law.law,law_type':list(LAWS.items()),'institution.institution,investment':[(30,2)],'country.country,power_bloc':[(3,5)],'formations.army':[7],
        'treaty_article.treaty,treaty_article_type':[(60,'trade_privilege'),(61,'alliance'),(62,'trade_privilege'),(62,'military_access')],
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


def state(tax=2,enacting=(),duty=3,monopolies=(),for_sale=()):
    return [mock.patch.object(translate,'player_value',lambda s,table,column:tax),mock.patch.object(translate,'enacting_laws',lambda s:list(enacting)),
            mock.patch.object(translate,'trade_level',lambda s,direction,goods:duty),mock.patch.object(translate,'monopolies',lambda s:set(monopolies)),
            mock.patch.object(translate,'privatization_requested',lambda s,ident:ident in for_sale)]


def offer(options,snapshot=None,**settings):
    with contextlib_stack(state(**settings)):
        return translate.offer(snapshot or Snapshot(),Options(options))


class contextlib_stack:
    def __init__(self,patches):
        self.patches=patches

    def __enter__(self):
        for patch in self.patches:
            patch.start()

    def __exit__(self,*error):
        for patch in self.patches:
            patch.stop()


def fuzz(command):
    names=[spec.partition(':')[0] for spec in COMMANDS[command].params]
    pools=[LEVELS_OF.get(command,['VeryLow','Low','High','VeryHigh']) if name=='level' else VALUES.get(name,[1]) for name in names]
    return [dict(zip(names,values)) for values in itertools.product(*pools)]


def carried(offered):
    return {command for choices in offered.values() for choice in choices for command,_ in choice.commands}


class CatalogueTests(unittest.TestCase):
    def test_there_are_seventy_nine_levers_in_the_agreed_blocks(self):
        self.assertEqual(len(C.NAMES),79)
        self.assertEqual(len(set(C.NAMES)),79)
        self.assertEqual(Counter(lever.domain for lever in C.LEVERS),{C.CONSTRUCT:11,C.QUEUE:4,C.RAISE:24,C.LOWER:24,C.SINGLE:12,C.ANSWER:4})
        self.assertEqual([lever.name for lever in C.LEVERS if lever.domain==C.CONSTRUCT],list(C.SECTORS))
        self.assertEqual({lever.name.removeprefix('raise_') for lever in C.LEVERS if lever.domain==C.RAISE},
                         {lever.name.removeprefix('lower_') for lever in C.LEVERS if lever.domain==C.LOWER})

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

    def test_only_construction_is_split_by_building_type(self):
        kinds=[kind for found in C.SECTORS.values() for kind in found]
        self.assertEqual(len(kinds),len(set(kinds)))
        split=[lever.name for lever in C.LEVERS if any(C.KIND in params for _,params in lever.acts) and lever.domain not in (C.CONSTRUCT,C.QUEUE)]
        self.assertEqual(split,['raise_state_ownership','lower_state_ownership'])

    def test_everything_the_catalogue_and_the_rules_name_exists_in_the_installed_game(self):
        game={folder:{name for name,_ in read(C.GAME,f'common/{folder}')} for folder in ('buildings','treaty_articles','diplomatic_actions')}
        self.assertLessEqual({*[kind for kinds in C.SECTORS.values() for kind in kinds],C.NAVAL_ADMINISTRATION},game['buildings'])
        self.assertLessEqual({*C.COMMERCIAL,*C.COMMERCIAL_GOODS,*C.SECURITY,'join_power_bloc'},game['treaty_articles'])
        self.assertLessEqual({*translate.DIPLOMACY.values(),'join_power_bloc'},game['diplomatic_actions'])
        self.assertEqual(set(C.LAW_CATEGORY.values()),set(C.LAW_CATEGORIES))
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


class TranslationTests(unittest.TestCase):
    def test_every_rule_belongs_to_an_act_and_the_rest_are_listed_as_unoffered(self):
        self.assertLessEqual(set(RULES),set(C.PARAMS))
        self.assertEqual(UNOFFERED,{'lower_embargoes','stop_damaging_relations','end_rivalry','stop_improving_relations','refund_bloc_principle','end_service_exemption',
                                    'take_back_subject_market','grant_independence','sway_country','plan_invasion','embark_troops'})

    def test_every_interface_command_is_carried_or_left_out_on_purpose(self):
        self.assertLessEqual(LEFT_OUT,set(COMMANDS))
        reached=set()
        for settings in ({'tax':1,'duty':1},{'tax':3,'duty':5},{'enacting':list(LAWS),'monopolies':KINDS,'for_sale':VALUES['building']}):
            for flags in ([],[(1,)]):
                snapshot=Snapshot(**{'player_taxed_goods.goods':[('grain',)] if flags else [],'player_colonization_paused.state':flags,
                                     'charter.charter,company,company_charter_type':[(9,1,'investment_charter')] if flags else [],
                                     'formation_mobilization_option.formation,mobilization_option':[(7,1)] if flags else [],
                                     'political_movement.political_movement,managed_status':[(1,translate.PROMOTED if flags else translate.SUPPRESSED)],
                                     'war_goal.diplomatic_play,war_goal_type,target_country,holder,pressed':[(1,1,3,1,True)] if flags else []})
                reached|=carried(offer({command:fuzz(command) for command in COMMANDS},snapshot,**settings))
        reached|=carried(offer({'decline_treaty':[{'country':3}],'quick_decline_proposal':[{'country':3}]}))
        self.assertEqual(reached&LEFT_OUT,set())
        self.assertEqual(set(COMMANDS)-reached-LEFT_OUT,set())

    def test_construction_is_split_by_what_is_built(self):
        options=[{'state':1,'building_type':kind} for kind in KINDS]
        found=offer({'build':options})
        for name,kinds in C.SECTORS.items():
            self.assertEqual([choice.params for choice in found[name]],[{'state':1,'building_type':kinds[0]}])
        self.assertEqual(found['construct_naval_administration'],[Choice({'state':1},[('build',{'state':1,'building_type':C.NAVAL_ADMINISTRATION})])])
        self.assertEqual(sum(len(choices) for choices in found.values()),len(KINDS)-1)

    def test_cancelling_merges_the_queue_route_and_the_building_route(self):
        found=offer({'cancel_queue_item':[{'state':1,'building_type':KINDS[0]}],'cancel_construction':[{'building':1},{'building':2}]})['cancel_queued_construction']
        self.assertEqual(found[0],Choice({'state':1,'building_type':KINDS[0]},[('cancel_queue_item',{'state':1,'building_type':KINDS[0]}),('cancel_construction',{'building':1})]))
        self.assertEqual(found[1],Choice({'state':1,'building_type':KINDS[1]},[('cancel_construction',{'building':2})]))

    def test_queue_priority_has_a_raising_and_a_lowering_lever(self):
        item={'state':1,'building_type':KINDS[0]}
        found=offer({'raise_queue_item':[item],'first_queue_item':[item],'lower_queue_item':[item],'last_queue_item':[item]})
        self.assertEqual(found['raise_construction_priority'],[Choice(item,[('raise_queue_item',item),('first_queue_item',item)])])
        self.assertEqual(found['lower_construction_priority'],[Choice(item,[('lower_queue_item',item),('last_queue_item',item)])])

    def test_a_level_moves_one_step_at_a_time(self):
        levels=[{'level':level} for level in ('VeryLow','Low','High','VeryHigh')]
        found=offer({'set_tax_level':levels},tax=2)
        self.assertEqual(found['raise_tax_level'],[Choice({},[('set_tax_level',{'level':'High'})])])
        self.assertEqual(found['lower_tax_level'],[Choice({},[('set_tax_level',{'level':'Low'})])])
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

    def test_an_institution_moves_one_level(self):
        found=offer({'set_institution_level':[{'institution':30,'level':level} for level in (1,3,4)]})
        self.assertEqual(found['raise_institutions'],[Choice({'institution':30},[('set_institution_level',{'institution':30,'level':3})])])
        self.assertEqual(found['lower_institutions'],[Choice({'institution':30},[('set_institution_level',{'institution':30,'level':1})])])

    def test_government_takes_a_group_or_its_party_in_or_out(self):
        found=offer({'reform_government':[{'interest_group':4,'mode':'Potential'},{'interest_group':5,'mode':'Staged'}],
                     'reform_government_party':[{'member':6,'mode':'Potential'}]})
        self.assertEqual([choice.params for choice in found['raise_government']],[{'interest_group':4},{'interest_group':6}])
        self.assertEqual(found['lower_government'],[Choice({'interest_group':5},[('reform_government',{'interest_group':5,'mode':'Staged'})])])

    def test_a_treaty_is_filed_by_its_article_and_says_who_gives(self):
        found=offer({'offer_treaty_article':[{'country':3,'treaty_article':'trade_privilege'},{'country':3,'treaty_article':'military_access'},{'country':3,'treaty_article':'take_on_debt'}],
                     'demand_treaty_article':[{'country':3,'treaty_article':'foreign_investment_rights'}],'agree_treaty_article':[{'country':3,'treaty_article':'alliance'}],
                     'demand_goods_treaty_article':[{'country':3,'treaty_article':'goods_transfer','goods':'grain'}]})
        self.assertEqual([choice.params for choice in found['propose_commercial_article']],
                         [{'country':3,'treaty_article':'trade_privilege','giver':'us'},{'country':3,'treaty_article':'foreign_investment_rights','giver':'them'}])
        self.assertEqual([choice.params for choice in found['raise_security_treaties']],
                         [{'country':3,'treaty_article':'military_access','giver':'us'},{'country':3,'treaty_article':'alliance','giver':'both'}])
        self.assertEqual([choice.params for choice in found['propose_goods_article']],[{'country':3,'treaty_article':'goods_transfer','goods':'grain','giver':'them'}])
        self.assertEqual(sum(len(choices) for choices in found.values()),5)

    def test_withdrawing_files_a_mixed_treaty_under_security(self):
        found=offer({'withdraw_treaty':[{'treaty':60},{'treaty':61},{'treaty':62}]})
        self.assertEqual([choice.params for choice in found['lower_commercial_treaties']],[{'treaty':60}])
        self.assertEqual([choice.params for choice in found['lower_security_treaties']],[{'treaty':61},{'treaty':62}])

    def test_a_diplomatic_action_goes_to_the_lever_it_moves(self):
        found=offer({'diplomatic_action':[{'country':3,'diplomatic_action':action} for action in VALUES['diplomatic_action']]})
        self.assertEqual({name:found[name][0].commands[0][1]['diplomatic_action'] for name in translate.DIPLOMACY},translate.DIPLOMACY)
        self.assertEqual(found['ask_to_join_power_bloc'],[Choice({'power_bloc':5},[('diplomatic_action',{'country':3,'diplomatic_action':'join_power_bloc'})])])
        self.assertEqual(len(found),len(translate.DIPLOMACY)+1)

    def test_every_demand_is_one_of_two_acts(self):
        option={'country':3,'diplomatic_play_type':'dp_open_market'}
        found=offer({'start_play_country':[option],'start_play_confirmed':[{**option,'mode':'AsDemand'},{**option,'mode':'ForcePlay'}],
                     'start_play_state':[{'state':1,'diplomatic_play_type':'dp_conquer_state'}],'add_war_goal':[{'diplomatic_play':2,'war_goal_type':'conquer_state','index':0}]})
        self.assertEqual(found['demand_of_country'],[Choice(option,[('start_play_country',option),('start_play_confirmed',{**option,'mode':'AsDemand'}),
                                                                   ('start_play_confirmed',{**option,'mode':'ForcePlay'})])])
        self.assertEqual(found['demand_for_state'][0].params,{'state':1,'diplomatic_play_type':'dp_conquer_state'})
        self.assertEqual(found['add_demand'][0].params,{'diplomatic_play':2,'war_goal_type':'conquer_state'})
        self.assertEqual({C.LEVER[name] for name in found},{'raise_confrontations'})

    def test_laws_are_filed_by_category_and_negotiation_follows_the_law_under_way(self):
        under_way=next(law for law,kind in LAWS.items() if C.LAW_CATEGORY[C.LAW_GROUP[kind]]=='economy')
        found=offer({'enact_law':[{'law':law} for law in LAWS],'negotiate':[{'interest_group':4}]},enacting=[under_way])
        for category in C.LAW_CATEGORIES:
            self.assertEqual({C.LAW_CATEGORY[C.LAW_GROUP[LAWS[choice.params['law']]]] for choice in found[f'enact_{category}_law']},{category})
        self.assertEqual(sum(len(found[f'enact_{category}_law']) for category in C.LAW_CATEGORIES),len(LAWS))
        self.assertEqual(found['negotiate_economy_law'],[Choice({'interest_group':4},[('negotiate',{'interest_group':4})])])
        self.assertNotIn('negotiate_power_structure_law',found)
        self.assertNotIn('negotiate_human_rights_law',found)

    def test_research_is_filed_by_tree(self):
        found=offer({'research':[{'technology':name} for name in TREES.values()],'queue_research':[{'technology':TREES['military']}]})
        for tree,name in TREES.items():
            self.assertEqual(found[f'research_{tree}_technology'],[Choice({'technology':name},[('research',{'technology':name})])])
        self.assertEqual(sorted(name for name in found if name.startswith('queue_')),['queue_military_technology'])

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

    def test_a_choice_that_departs_from_the_catalogue_is_refused(self):
        with mock.patch.dict(RULES,{'raise_subsidies':lambda c:[Choice({'building':1,'extra':2},[('subsidies_on',{'building':1})])]}):
            with self.assertRaises(RuntimeError):
                offer({})

    def test_every_offered_choice_carries_exactly_the_declared_parameters(self):
        found=offer({command:fuzz(command) for command in COMMANDS},Snapshot(**{'formation_mobilization_option.formation,mobilization_option':[]}),enacting=list(LAWS))
        for name,choices in found.items():
            for choice in choices:
                self.assertEqual(set(choice.params),{param for param,_ in C.PARAMS[name]},name)
                self.assertTrue(choice.commands,name)


if __name__=='__main__':
    unittest.main()
