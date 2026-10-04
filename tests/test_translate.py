import ast
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from advisors import catalogue as C
from interface.actions.catalogue import BY_NAME
from loop.translate import Choice, RULES, UNOFFERED, offer, translate
from tests.memory_stored import Memory

PLAYER=7
FOREIGN=8
STATE=20
BUILDING=30
SECTOR=31
CENTER=32
QUANTITIES=['pm_trade_center_trade_quantity_limited','pm_trade_center_trade_quantity_normal','pm_trade_center_trade_quantity_high']
MOVEMENT=40
LAW=500
INSTITUTION=600
FORMATION=70
STRAIT=80
COMPANY=90
PLAY=100
RENAMED={'cancel_queue_item':'cancel_construction','downsize':'downsize_building','pause_construction_output':'idle_construction_sector',
         'resume_construction_output':'reactivate_construction_sector','nationalize':'nationalize_levels','subsidies_on':'subsidize_building','subsidies_off':'end_building_subsidy',
         'declare_bankruptcy':'declare_bankruptcy','cancel_enactment':'cancel_enactment','impose_law':'impose_law','repeal_amendment':'repeal_amendment',
         'negotiate':'negotiate_with_interest_group','stop_institution_change':'halt_institution_change','issue_decree':'issue_decree','remove_decree':'remove_decree',
         'dequeue_research':'dequeue_research','recruit_from_formation':'recruit_units','activate_conscription_center':'recruit_conscripts','mobilize':'mobilize_army',
         'mobilize_selected':'mobilize_army','mobilize_all':'mobilize_all_armies','demobilize':'demobilize_army','demobilize_selected':'demobilize_army',
         'demobilize_all':'demobilize_all_armies','raise_conscripts':'raise_conscripts','raise_conscripts_selected':'raise_conscripts','disband_formation':'disband_formation',
         'disband_regulars':'disband_regulars','disband_conscripts':'disband_conscripts','upgrade_regulars':'upgrade_regulars','upgrade_conscripts':'upgrade_conscripts',
         'upgrade_all_units':'upgrade_all_units','set_default_unit_type':'set_default_unit_type','commander_order':'order_commander','station_formation':'station_army',
         'station_selected':'station_army_at_headquarters','rehome_formation':'rehome_army','deploy_to_front':'deploy_to_front','deploy_selected_to_front':'deploy_to_front',
         'defend_invasion':'defend_against_invasion','cancel_invasion':'cancel_invasion','disembark':'disembark_army','set_strategic_objective':'set_strategic_objective',
         'cancel_strategic_objective_selected':'clear_strategic_objective','create_army':'create_army','transfer_battalions':'transfer_battalions',
         'set_borrow_setting':'change_unit_borrowing','build_ship':'build_ship','build_ship_for':'build_ship_for_fleet','cancel_ship':'cancel_ship_type',
         'cancel_ship_item':'cancel_ship_order','pause_ship_construction':'pause_ship_construction','resume_ship_construction':'resume_ship_construction',
         'start_naval_mission':'start_naval_mission','start_naval_mission_selected':'start_naval_mission','end_naval_mission':'end_naval_mission',
         'end_naval_mission_selected':'end_naval_mission','recall_fleet':'recall_fleet','retrofit_fleet':'retrofit_fleet','cancel_retrofit_fleet':'cancel_fleet_retrofit',
         'retrofit_all':'retrofit_all_fleets','cancel_retrofit_all':'cancel_all_retrofits','decommission_ship':'decommission_ship',
         'set_default_construction_fleet':'set_default_construction_fleet','clear_default_construction_fleet':'clear_default_construction_fleet',
         'design_ship_template':'design_ship_template','edit_ship_template':'edit_ship_template','set_default_ship_template':'set_default_ship_template',
         'set_fleet_ship_template':'set_fleet_ship_template','delete_ship_template':'delete_ship_template','hire_commander':'hire_commander',
         'hire_commander_for':'hire_commander_for_formation','promote_commander':'promote_commander','assign_commander':'assign_commander','unassign_commander':'unassign_commander',
         'character_interaction':'character_interaction','request_join_power_bloc':'request_to_join_power_bloc','form_power_bloc':'form_power_bloc',
         'kick_from_power_bloc':'expel_from_power_bloc','leave_power_bloc':'leave_power_bloc','pick_principle':'adopt_principle','upgrade_principle':'upgrade_principle',
         'start_play_country':'start_diplomatic_play','start_play_state':'start_diplomatic_play_for_state','support_initiator':'back_initiator','support_target':'back_target',
         'lean_initiator':'lean_toward_initiator','lean_target':'lean_toward_target','stay_on_fence':'stay_on_the_fence','declare_neutrality':'declare_neutrality',
         'back_down':'back_down','make_primary_demand':'make_primary_demand','add_war_goal':'add_war_goal','propose_peace':'propose_peace','white_peace':'propose_white_peace',
         'capitulate':'capitulate','toggle_accept_peace':'toggle_peace_acceptance','withdraw_treaty':'withdraw_from_treaty','accept_treaty':'accept_treaty',
         'decline_treaty':'decline_treaty','accept_demand':'accept_demand','reject_demand':'reject_demand','accept_action_proposal':'accept_action_proposal',
         'decline_action_proposal':'decline_action_proposal','accept_sway':'accept_sway','reject_sway':'reject_sway','create_company':'establish_company',
         'remove_company':'dissolve_company','colonize':'colonize','toggle_pause_colonization':'toggle_colonization_pause','abandon_colony':'abandon_colony',
         'incorporate':'incorporate_state','unincorporate':'unincorporate_state','take_decision':'take_decision','press_journal_button':'press_journal_button',
         'choose_event_option':'answer_event','agree_treaty_article':'propose_mutual_treaty_article'}
PLACE={'state':STATE,'building_type':'building_mill'}
CASES=[
    ('build',{'state':STATE,'building_type':'building_big_ben'},'build_monument',{'state':STATE,'building_type':'building_big_ben'}),
    ('cancel_construction',{'building':BUILDING},'cancel_construction',PLACE),
    ('raise_queue_item',PLACE,'prioritize_construction',{**PLACE,'step':'one'}),
    ('first_queue_item',PLACE,'prioritize_construction',{**PLACE,'step':'front'}),
    ('lower_queue_item',PLACE,'deprioritize_construction',{**PLACE,'step':'one'}),
    ('last_queue_item',PLACE,'deprioritize_construction',{**PLACE,'step':'back'}),
    ('pause_construction',{},'pause_construction',{'scope':'government'}),
    ('pause_all_construction',{},'pause_construction',{'scope':'all'}),
    ('resume_construction',{},'resume_construction',{'scope':'government'}),
    ('resume_all_construction',{},'resume_construction',{'scope':'all'}),
    ('bulk_nationalize_state',{**PLACE,'ownership':'owned_private'},'nationalize_holdings',{'building':BUILDING,'ownership':'owned_private'}),
    ('toggle_privatization',{'building':BUILDING},'privatize_building',{'building':BUILDING}),
    ('toggle_privatization',{'building':SECTOR},'stop_privatizing_building',{'building':SECTOR}),
    ('toggle_monopoly',{'building_type':'building_mill'},'grant_monopoly',{'building_type':'building_mill'}),
    ('toggle_monopoly',{'building_type':'building_port'},'revoke_monopoly',{'building_type':'building_port'}),
    ('subset_subsidies_on_state',{**PLACE,'ownership':'any'},'subsidize_building',{'building':BUILDING}),
    ('subset_subsidies_off_state',{**PLACE,'ownership':'owned_private'},'end_building_subsidy',{'building':BUILDING}),
    ('switch_production_method',{'building':BUILDING,'production_method':'pm_c'},'advance_production_method',{'building':BUILDING,'production_method':'pm_c'}),
    ('switch_production_method',{'building':BUILDING,'production_method':'pm_a'},'revert_production_method',{'building':BUILDING,'production_method':'pm_a'}),
    ('bulk_switch_production_method_state',{**PLACE,'production_method':'pm_c','ownership':'any'},'advance_production_method',{'building':BUILDING,'production_method':'pm_c'}),
    ('switch_production_method',{'building':CENTER,'production_method':'pm_trade_center_trade_quantity_high'},'raise_trade_quantity',
     {'building':CENTER,'production_method':'pm_trade_center_trade_quantity_high'}),
    ('switch_production_method',{'building':CENTER,'production_method':'pm_trade_center_trade_quantity_limited'},'lower_trade_quantity',
     {'building':CENTER,'production_method':'pm_trade_center_trade_quantity_limited'}),
    ('bulk_switch_production_method_state',{**PLACE,'production_method':'pm_a','ownership':'any'},'revert_production_method',{'building':BUILDING,'production_method':'pm_a'}),
    ('set_tax_level',{'level':'VeryHigh'},'raise_taxes',{'level':'very_high'}),
    ('set_tax_level',{'level':'Low'},'lower_taxes',{'level':'low'}),
    ('set_government_wages',{'level':'High'},'raise_government_wages',{'level':'high'}),
    ('set_government_wages',{'level':'VeryLow'},'lower_government_wages',{'level':'very_low'}),
    ('set_military_wages',{'level':'High'},'raise_military_wages',{'level':'high'}),
    ('set_military_wages',{'level':'Low'},'lower_military_wages',{'level':'low'}),
    ('set_supply_ship_construction',{'level':'High'},'raise_supply_ship_construction',{'level':'high'}),
    ('set_supply_ship_construction',{'level':'Low'},'lower_supply_ship_construction',{'level':'low'}),
    ('toggle_consumption_tax',{'goods':'grain'},'tax_consumption',{'goods':'grain'}),
    ('toggle_consumption_tax',{'goods':'wine'},'untax_consumption',{'goods':'wine'}),
    ('set_import_tariff',{'goods':'grain','level':'High'},'raise_import_duty',{'goods':'grain','duty':'tariff_high'}),
    ('set_import_tariff',{'goods':'iron','level':'None'},'lower_import_duty',{'goods':'iron','duty':'none'}),
    ('set_import_subvention',{'goods':'grain','level':'Max'},'lower_import_duty',{'goods':'grain','duty':'subvention_max'}),
    ('set_import_subvention',{'goods':'coal','level':'Low'},'raise_import_duty',{'goods':'coal','duty':'subvention_low'}),
    ('set_export_tariff',{'goods':'grain','level':'Low'},'raise_export_duty',{'goods':'grain','duty':'tariff_low'}),
    ('set_export_tariff',{'goods':'iron','level':'Low'},'lower_export_duty',{'goods':'iron','duty':'tariff_low'}),
    ('set_export_subvention',{'goods':'grain','level':'High'},'lower_export_duty',{'goods':'grain','duty':'subvention_high'}),
    ('set_export_subvention',{'goods':'coal','level':'High'},'raise_export_duty',{'goods':'coal','duty':'subvention_high'}),
    ('set_strait_toll',{'strait':STRAIT,'level':'HighTolls'},'raise_strait_toll',{'strait':STRAIT,'level':'high'}),
    ('set_strait_toll',{'strait':STRAIT,'level':'NoTolls'},'lower_strait_toll',{'strait':STRAIT,'level':'none'}),
    ('set_strait_access',{'strait':STRAIT,'state':STATE,'access':'Closed'},'tighten_strait_access',{'strait':STRAIT,'state':STATE,'access':'closed'}),
    ('set_strait_access',{'strait':STRAIT,'state':STATE,'access':'Open'},'loosen_strait_access',{'strait':STRAIT,'state':STATE,'access':'open'}),
    ('set_strait_allowed',{'strait':STRAIT,'state':STATE,'allowed':'OnlyController'},'tighten_strait_passage',{'strait':STRAIT,'state':STATE,'allowed':'only_controller'}),
    ('set_strait_allowed',{'strait':STRAIT,'state':STATE,'allowed':'NoEnemies'},'loosen_strait_passage',{'strait':STRAIT,'state':STATE,'allowed':'no_enemies'}),
    ('toggle_bolster_movement',{'political_movement':MOVEMENT},'bolster_movement',{'political_movement':MOVEMENT}),
    ('toggle_bolster_movement',{'political_movement':MOVEMENT+1},'stop_bolstering_movement',{'political_movement':MOVEMENT+1}),
    ('toggle_suppress_movement',{'political_movement':MOVEMENT},'suppress_movement',{'political_movement':MOVEMENT}),
    ('toggle_suppress_movement',{'political_movement':MOVEMENT+2},'stop_suppressing_movement',{'political_movement':MOVEMENT+2}),
    ('reform_government',{'interest_group':5,'mode':'Potential'},'invite_to_government',{'interest_group':5}),
    ('reform_government',{'interest_group':5,'mode':'Staged'},'dismiss_from_government',{'interest_group':5}),
    ('reform_government_party',{'member':5,'mode':'Potential'},'invite_party_to_government',{'member':5}),
    ('reform_government_party',{'member':5,'mode':'Staged'},'dismiss_party_from_government',{'member':5}),
    ('research',{'technology':'railways'},'research_production',{'technology':'railways'}),
    ('research',{'technology':'line_infantry'},'research_military',{'technology':'line_infantry'}),
    ('research',{'technology':'democracy'},'research_society',{'technology':'democracy'}),
    ('queue_research',{'technology':'railways'},'queue_production_research',{'technology':'railways'}),
    ('queue_research',{'technology':'line_infantry'},'queue_military_research',{'technology':'line_infantry'}),
    ('queue_research',{'technology':'democracy'},'queue_society_research',{'technology':'democracy'}),
    ('recruit',{'building':BUILDING,'military_formation':FORMATION,'combat_unit_type':'infantry'},'recruit_units',
     {'military_formation':FORMATION,'combat_unit_type':'infantry','state':STATE}),
    ('toggle_mobilization_option',{'military_formation':FORMATION,'mobilization_option':'rations'},'enable_mobilization_option',
     {'military_formation':FORMATION,'mobilization_option':'rations'}),
    ('toggle_mobilization_option',{'military_formation':FORMATION,'mobilization_option':'tobacco'},'disable_mobilization_option',
     {'military_formation':FORMATION,'mobilization_option':'tobacco'}),
    ('set_supply_priority',{'military_formation':FORMATION,'level':'high'},'raise_supply_priority',{'military_formation':FORMATION,'level':'high'}),
    ('set_supply_priority',{'military_formation':FORMATION,'level':'low'},'lower_supply_priority',{'military_formation':FORMATION,'level':'low'}),
    ('raise_ship_item',{'index':2},'prioritize_ship',{'index':2,'step':'one'}),
    ('first_ship_item',{'index':2},'prioritize_ship',{'index':2,'step':'front'}),
    ('lower_ship_item',{'index':2},'deprioritize_ship',{'index':2,'step':'one'}),
    ('last_ship_item',{'index':2},'deprioritize_ship',{'index':2,'step':'back'}),
    ('diplomatic_action',{'country':FOREIGN,'diplomatic_action':'embargo'},'embargo',{'country':FOREIGN}),
    ('diplomatic_action',{'country':FOREIGN,'diplomatic_action':'rivalry'},'diplomatic_action',{'country':FOREIGN,'diplomatic_action':'rivalry','obligation':'none'}),
    ('diplomatic_action_obligation',{'country':FOREIGN,'diplomatic_action':'rivalry','obligation':'CallInObligation'},'diplomatic_action',
     {'country':FOREIGN,'diplomatic_action':'rivalry','obligation':'call_in'}),
    ('diplomatic_action_obligation',{'country':FOREIGN,'diplomatic_action':'embargo','obligation':'OweObligation'},'diplomatic_action',
     {'country':FOREIGN,'diplomatic_action':'embargo','obligation':'owe'}),
    ('start_play_confirmed',{'country':FOREIGN,'diplomatic_play_type':'dp_x','mode':'AsDemand'},'make_diplomatic_demand',{'country':FOREIGN,'diplomatic_play_type':'dp_x'}),
    ('start_play_confirmed',{'country':FOREIGN,'diplomatic_play_type':'dp_x','mode':'ForcePlay'},'start_diplomatic_play',{'country':FOREIGN,'diplomatic_play_type':'dp_x'}),
    ('toggle_press_war_goal',{'diplomatic_play':PLAY,'war_goal_type':'conquer','country':FOREIGN},'press_war_goal',
     {'diplomatic_play':PLAY,'war_goal_type':'conquer','country':FOREIGN}),
    ('toggle_press_war_goal',{'diplomatic_play':PLAY,'war_goal_type':'humiliate','country':FOREIGN},'release_war_goal',
     {'diplomatic_play':PLAY,'war_goal_type':'humiliate','country':FOREIGN}),
    ('toggle_charter',{'company':COMPANY,'charter':'trade_charter'},'grant_charter',{'company':COMPANY,'charter':'trade_charter'}),
    ('toggle_charter',{'company':COMPANY,'charter':'investment_charter'},'revoke_charter',{'company':COMPANY,'charter':'investment_charter'}),
    ('toggle_ignore_decision',{'decision':'found_x'},'ignore_decision',{'decision':'found_x'}),
    ('toggle_ignore_decision',{'decision':'found_y'},'stop_ignoring_decision',{'decision':'found_y'}),
    ('quick_decline_proposal',{'country':FOREIGN},'decline_treaty',{'country':FOREIGN}),
    *(('build',{'state':STATE,'building_type':kind},action,{'state':STATE}) for kind,action in C.EXPAND.items()),
    *((f'{verb}{"_goods" if kind in C.GOODS_ARTICLES else ""}_treaty_article',{'country':FOREIGN,'treaty_article':kind,**({'goods':'grain'} if kind in C.GOODS_ARTICLES else {})},
       f'{verb}_{name}',{'country':FOREIGN,**({'goods':'grain'} if kind in C.GOODS_ARTICLES else {})}) for kind,name in C.TRADE_ARTICLES.items() for verb in ('offer','demand')),
    ('offer_treaty_article',{'country':FOREIGN,'treaty_article':'alliance'},'offer_treaty_article',{'country':FOREIGN,'treaty_article':'alliance'}),
    ('demand_treaty_article',{'country':FOREIGN,'treaty_article':'military_access'},'demand_treaty_article',{'country':FOREIGN,'treaty_article':'military_access'}),
    *(('enact_law',{'law':LAW+index},C.ENACT[group],{'law':LAW+index}) for index,group in enumerate(C.LAW_GROUPS)),
    *(('set_institution_level',{'institution':INSTITUTION+index,'level':4},C.INVEST[kind],{'institution':INSTITUTION+index,'level':4}) for index,kind in enumerate(C.INSTITUTIONS)),
    *(('set_institution_level',{'institution':INSTITUTION+index,'level':1},C.DIVEST[kind],{'institution':INSTITUTION+index,'level':1}) for index,kind in enumerate(C.INSTITUTIONS)),
]


class Snapshot(Memory):
    @property
    def methods(self):
        return [('building_mill','pmg_base','pm_a'),('building_mill','pmg_base','pm_b'),('building_mill','pmg_base','pm_c'),('building_mill','pmg_other','pm_z'),
                *(('building_trade_center','pmg_trade_quantity_trade_center',method) for method in QUANTITIES)]


def snapshot():
    return Snapshot(PLAYER,{
        'state_history':[{'state':STATE,'country':PLAYER,'state_region':'STATE_A'}],
        'building_history':[{'building':BUILDING,'building_type':'building_mill','state':STATE,'levels':2,'privatization_requested':0},
                            {'building':SECTOR,'building_type':'building_construction_sector','state':STATE,'levels':1,'privatization_requested':1},
                            {'building':CENTER,'building_type':'building_trade_center','state':STATE,'levels':1,'privatization_requested':0}],
        'building_production_method_active':[{'building':BUILDING,'production_method':'pm_b'},{'building':BUILDING,'production_method':'pm_z'},
                                             {'building':CENTER,'production_method':QUANTITIES[1]}],
        'player_policy':[{'tax_level':2,'government_wage_level':2,'military_wage_level':2,'supply_ship_construction_level':2}],
        'player_taxed_goods':[{'goods':'wine'}],'player_monopoly':[{'building_type':'building_port'}],
        'player_tariff':[{'direction':'import','goods':'iron','level':5},{'direction':'import','goods':'coal','level':0},
                         {'direction':'export','goods':'iron','level':6},{'direction':'export','goods':'coal','level':0}],
        'strait_history':[{'strait':STRAIT,'first_toll_rate':1,'first_access_status':1,'first_access_permissions':2}],
        'strait_endpoint':[{'strait':STRAIT,'first_state':STATE,'second_state':99}],
        'law_history':[{'law':LAW+index,'country':PLAYER,'law_type':next(law for law,found in C.LAW_GROUP.items() if found==group)} for index,group in enumerate(C.LAW_GROUPS)],
        'political_movement_history':[{'political_movement':MOVEMENT,'country':PLAYER,'managed_status':None},{'political_movement':MOVEMENT+1,'country':PLAYER,'managed_status':2},
                                      {'political_movement':MOVEMENT+2,'country':PLAYER,'managed_status':1}],
        'institution_history':[{'institution':INSTITUTION+index,'country':PLAYER,'institution_type':kind,'investment':2} for index,kind in enumerate(C.INSTITUTIONS)],
        'formation_history':[{'formation':FORMATION,'country':PLAYER,'supply_priority':1}],
        'formation_mobilization_option':[{'formation':FORMATION,'mobilization_option':'tobacco'}],
        'diplomatic_play_history':[{'diplomatic_play':PLAY}],
        'war_goal_history':[{'war_goal':1,'diplomatic_play':PLAY,'war_goal_type':'conquer','target_country':FOREIGN,'holder':PLAYER,'pressed':0},
                            {'war_goal':2,'diplomatic_play':PLAY,'war_goal_type':'humiliate','target_country':FOREIGN,'holder':PLAYER,'pressed':1}],
        'charter_history':[{'charter':1,'company':COMPANY,'company_charter_type':'investment_charter'}],
        'player_proposal':[{'country':FOREIGN,'kind':'treaty'}],'player_ignored_decision':[{'decision':'found_y'}]},
        {'common/production_method_groups':{'pmg_base':{'production_methods':['pm_a','pm_b','pm_c']},'pmg_other':{'production_methods':['pm_z']},
                                            'pmg_trade_quantity_trade_center':{'production_methods':QUANTITIES}}})


def sample(name):
    values={}
    for part in BY_NAME[name].params:
        param,_,kind=part.partition(':')
        values[param]=1 if kind=='int' else BY_NAME[name].choices[0] if kind=='choice' else 'x'
    return values


class TranslationTests(unittest.TestCase):
    def test_every_interface_action_has_one_checked_translation_and_every_advisor_action_is_reached(self):
        cased={name for name,*_ in CASES}
        self.assertEqual(set(RENAMED)|cased|set(UNOFFERED),set(BY_NAME))
        self.assertFalse(set(RENAMED)&cased or (set(RENAMED)|cased)&set(UNOFFERED))
        self.assertEqual(set(RULES),set(RENAMED)|cased)
        reached={action for *_,action,_ in CASES}|set(RENAMED.values())
        self.assertEqual(reached,set(C.NAMES))

    def test_renamed_actions_keep_their_parameters(self):
        s=snapshot()
        for name,action in RENAMED.items():
            with self.subTest(name=name):
                params=sample(name)
                self.assertEqual(translate(s,name,params),(action,params))

    def test_directions_toggles_and_subjects_follow_the_snapshot(self):
        s=snapshot()
        for name,params,action,chosen in CASES:
            with self.subTest(name=name,params=params):
                self.assertEqual(translate(s,name,params),(action,chosen))

    def test_a_quick_decline_is_not_offered_when_the_country_has_several_kinds_of_proposal(self):
        s=snapshot()
        s.given['player_proposal'].append({'country':FOREIGN,'kind':'demand'})
        self.assertIsNone(translate(s,'quick_decline_proposal',{'country':FOREIGN}))

    def test_commands_that_carry_the_same_decision_are_grouped_and_unoffered_actions_are_left_out(self):
        s=snapshot()
        found=offer(s,{'subsidies_on':[{'building':BUILDING}],'subset_subsidies_on_state':[{**PLACE,'ownership':'any'},{**PLACE,'ownership':'owned_private'}],
                       'pause':[{}],'set_formation_flag':[{'military_formation':FORMATION,'flag':1}],'set_tax_level':[{'level':'High'},{'level':'Low'}]})
        self.assertEqual(found,{'subsidize_building':[Choice({'building':BUILDING},[('subset_subsidies_on_state',{**PLACE,'ownership':'any'}),
                                                                                  ('subset_subsidies_on_state',{**PLACE,'ownership':'owned_private'}),
                                                                                  ('subsidies_on',{'building':BUILDING})])],
                                'raise_taxes':[Choice({'level':'high'},[('set_tax_level',{'level':'High'})])],
                                'lower_taxes':[Choice({'level':'low'},[('set_tax_level',{'level':'Low'})])]})

    def test_a_translation_that_differs_from_the_catalogue_parameters_is_refused(self):
        from unittest import mock
        with mock.patch.dict(RULES,{'downsize':lambda s,p:('downsize_building',{})}),self.assertRaises(ValueError):
            translate(snapshot(),'downsize',{'building':BUILDING})


class SeparationTests(unittest.TestCase):
    def test_nothing_under_advisors_imports_the_interface_actions_or_options_or_names_an_interface_only_action(self):
        foreign=set(BY_NAME)-set(C.NAMES)
        allowed={'interface.options.stored'}
        found=[]
        for path in sorted((ROOT/'advisors').rglob('*.py')):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                modules=[node.module] if isinstance(node,ast.ImportFrom) and node.module else [alias.name for alias in node.names] if isinstance(node,ast.Import) else []
                found+=[(path.relative_to(ROOT).as_posix(),module) for module in modules
                        if (module.startswith('interface.actions') or module.startswith('interface.options')) and module not in allowed]
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value in foreign:
                    found.append((path.relative_to(ROOT).as_posix(),node.value))
        self.assertEqual(found,[])

    def test_every_weight_an_initializer_draws_is_keyed_by_an_advisor_action(self):
        from advisors.initializers import RandomAdvisor
        self.assertEqual(set(RandomAdvisor(1).start_run(None,C.NAMES,None)),set(C.NAMES))


if __name__=='__main__':
    unittest.main()
