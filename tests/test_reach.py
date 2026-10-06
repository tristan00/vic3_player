import importlib
import unittest
from unittest.mock import patch

from interface.actions import gui
from interface.actions.catalogue import BY_NAME
from tests.memory_stored import Memory

available=importlib.import_module('interface.options.available')
RULES=available.RULES
PLAYER=(1<<24)|7
OTHER=(2<<24)|8
THIRD=(3<<24)|9
MONTH=30*24


NOW=60_000_000


def snapshot(definitions=None,**tables):
    s=Memory(PLAYER,tables,definitions)
    s.hours=NOW
    return s


def pact(ident,first,second,kind):
    return {'pact':ident,'first_country':first,'second_country':second,'pact_type':kind}


class PactTests(unittest.TestCase):
    def offered(self,rows,age):
        s=snapshot(pact_history=rows)
        with patch.object(available,'opening_seq',lambda s:99),patch.object(available,'snapshot_hours',lambda s,seq:s.hours-age*MONTH):
            return RULES['break_pact'](s)

    def test_only_a_pact_we_began_is_offered(self):
        rows=[pact(1,PLAYER,OTHER,'increase_relations'),pact(2,OTHER,PLAYER,'increase_relations'),pact(3,OTHER,THIRD,'increase_relations')]
        self.assertEqual(self.offered(rows,0),[{'country':OTHER,'diplomatic_action':'increase_relations'}])

    def test_a_locked_pact_waits_for_its_forced_months(self):
        rows=[pact(1,PLAYER,OTHER,'embargo'),pact(2,PLAYER,THIRD,'rivalry')]
        self.assertEqual(available.pact_terms()['embargo'][0],12)
        self.assertEqual(self.offered(rows,11),[])
        self.assertEqual(self.offered(rows,13),[{'country':OTHER,'diplomatic_action':'embargo'},{'country':THIRD,'diplomatic_action':'rivalry'}])

    def test_a_pact_older_than_the_run_is_offered_at_once(self):
        s=snapshot(pact_history=[pact(1,PLAYER,OTHER,'embargo')])
        with patch.object(available,'opening_seq',lambda s:0):
            self.assertEqual(RULES['break_pact'](s),[{'country':OTHER,'diplomatic_action':'embargo'}])

    def test_a_pact_the_game_never_lets_a_country_end_is_left_alone(self):
        self.assertNotIn('war_reparations',available.pact_terms())
        self.assertEqual(self.offered([pact(1,PLAYER,OTHER,'war_reparations')],99),[])

    def test_a_subject_pact_is_offered_so_independence_can_be_granted(self):
        self.assertEqual(self.offered([pact(1,PLAYER,OTHER,'puppet')],0),[{'country':OTHER,'diplomatic_action':'puppet'}])


class ForcesTests(unittest.TestCase):
    def army(self,kind):
        definitions={'common/combat_unit_types':{'marines':{'group':['combat_unit_group_marines']},'line':{'group':['combat_unit_group_infantry']}},
                     'map_data/state_regions':{'coast':{'naval_exit_id':['3000']},'inland':{}}}
        return snapshot(definitions,formation_history=[{'formation':1,'country':PLAYER,'formation_type':0},{'formation':2,'country':PLAYER,'formation_type':1}],
                        ship_history=[{'ship':1,'fleet':2}],
                        formation_status=[{'formation':1,'current_location':5,'target_location':5,'mobilized':True}],
                        formation_report=[{'formation':1,'embarked':False,'invading':False,'demobilizing':False},{'formation':2,'retrofitting':False,'invading':False}],
                        combat_unit_history=[{'combat_unit':1,'formation':1,'combat_unit_type':kind,'building':None}],
                        state_history=[{'state':10,'country':OTHER,'state_region':'coast'},{'state':11,'country':OTHER,'state_region':'inland'},
                                       {'state':12,'country':THIRD,'state_region':'coast'},{'state':13,'country':PLAYER,'state_region':'coast'}],
                        war_history=[{'war':1,'diplomatic_play':4}],war_participant=[{'war':1,'country':PLAYER,'diplomatic_play':4}],
                        diplomatic_play_history=[{'diplomatic_play':4,'initiator':PLAYER,'target':OTHER,'escalation':100,'war':1}])

    def test_only_an_army_of_marines_is_offered_a_fleet_to_board(self):
        with patch.object(available,'located_buildings',lambda s:{}):
            self.assertEqual(RULES['embark_formation'](self.army('marines')),[{'military_formation':1,'fleet':2}])
            self.assertEqual(RULES['embark_formation'](self.army('line')),[])

    def test_an_invasion_targets_a_state_of_a_country_we_are_at_war_with(self):
        s=self.army('line')
        self.assertEqual(RULES['plan_land_invasion'](s),[{'military_formation':1,'state':10},{'military_formation':1,'state':11}])
        self.assertEqual(RULES['plan_naval_invasion'](s),[{'military_formation':1,'fleet':2,'state':10}])

    def test_no_invasion_is_offered_in_peace(self):
        s=snapshot(formation_history=[{'formation':1,'country':PLAYER,'formation_type':0}],combat_unit_history=[{'combat_unit':1,'formation':1,'combat_unit_type':'line'}],
                   formation_status=[{'formation':1,'current_location':5,'target_location':5,'mobilized':True}],state_history=[{'state':10,'country':OTHER,'state_region':'coast'}])
        self.assertEqual(RULES['plan_land_invasion'](s),[])
        self.assertEqual(RULES['plan_naval_invasion'](s),[])


class SwayTests(unittest.TestCase):
    def play(self,escalation,war=None):
        return snapshot(diplomatic_play_history=[{'diplomatic_play':4,'initiator':PLAYER,'target':OTHER,'escalation':escalation,'war':war}],
                        diplomatic_play_country=[{'diplomatic_play':4,'country':THIRD+1,'role':'initiator'}],
                        state_history=[{'state':1,'country':PLAYER},{'state':2,'country':OTHER},{'state':3,'country':THIRD},{'state':4,'country':THIRD+1}])

    def test_a_country_outside_our_confrontation_can_be_swayed_during_manoeuvres(self):
        self.assertEqual(RULES['offer_sway'](self.play(30)),[{'diplomatic_play':4,'country':THIRD}])
        self.assertEqual(RULES['offer_sway_ally'](self.play(30)),[])
        self.assertEqual(RULES['offer_sway_pact'](self.play(30)),[])
        self.assertEqual(available.sway_pacts(),([],{'protectorate':'subject_type_protectorate','tributary':'subject_type_tributary'}))
        with patch.object(available,'subject_fits',lambda s,kind,country,overlord:kind=='subject_type_tributary' and (country,overlord)==(PLAYER,THIRD)):
            self.assertEqual(RULES['offer_sway_subjection'](self.play(30)),[{'diplomatic_play':4,'country':THIRD,'diplomatic_action':'tributary'}])

    def test_nobody_is_swayed_in_the_opening_the_countdown_or_a_war(self):
        for escalation,war in ((available.OPENING_PHASE_END-1,None),(available.COUNTDOWN,None),(100,1)):
            self.assertEqual(RULES['offer_sway'](self.play(escalation,war)),[],escalation)

    def test_no_unification_goal_and_no_debug_only_goal_is_demanded_or_offered(self):
        types={'humiliation':{'target_type':['country'],'settings':[]},'unification_leadership':{'target_type':['country'],'settings':[]},
               'regime_change':{'target_type':['country'],'settings':['debug']}}
        s=snapshot({'common/war_goal_types':types})
        s.keys=lambda name:list(types)
        self.assertEqual(available.listed_goals(s,'country'),['humiliation'])

    def test_a_confrontation_over_a_debug_only_goal_is_not_started(self):
        s=snapshot({'common/war_goal_types':{'regime_change':{'settings':['debug']}},'common/diplomatic_plays':{'dp_regime_change':{'war_goal':['regime_change']}}})
        self.assertFalse(available.play_allowed(s,'dp_regime_change',target_country=('country',OTHER)))

    def test_the_offer_type_is_picked_by_the_games_name_for_it_and_a_missing_one_is_refused_without_waiting(self):
        kinds={'offer_sway':'OBLIGATIONS','offer_sway_ally':'SWAY_TYPE_CALL_ALLY','offer_sway_state':'SWAY_TYPE_TRANSFER_STATE','offer_sway_subject':'SWAY_TYPE_TRANSFER_SUBJECT',
               'offer_sway_pact':'SWAY_TYPE_DIPLOMATIC_PACT','offer_sway_subjection':'SWAY_TYPE_BECOME_SUBJECT'}
        sways=[action for action in BY_NAME.values() if action.name.startswith('offer_sway')]
        self.assertEqual(len(sways),12)
        for action in sways:
            window,chain,calls=action.stages[0]
            self.assertEqual(chain,(('SwayCountryPanel.AccessSwayOfferTypes',f"EqualTo_string(SwayOfferType.GetName, Localize('{kinds.get(action.name,'WARGOALS')}'))"),),action.name)
            self.assertTrue(action.deadline,action.name)
            self.assertNotIn('offer:int',action.params,action.name)


class GateTests(unittest.TestCase):
    GATED=tuple(name for name in BY_NAME if name.endswith(('_treaty_article','_treaty_articles')))

    def test_the_gated_commands_are_the_treaty_proposals(self):
        self.assertEqual({action.name for action in BY_NAME.values() if action.admit},set(self.GATED))

    def test_one_decision_lets_the_first_stage_run_or_refuses_and_never_both(self):
        for name in self.GATED:
            action=BY_NAME[name]
            code=list(BY_NAME).index(name)+1
            values=gui.bindings(action)
            text=gui.absent_widget(code,action,None,values)
            decided=f"GetVariableSystem.Set('interface_admit', Select_CString({gui.fill(action.admit,values)}, '1', '0'))"
            self.assertEqual(text.count(decided),4,name)
            self.assertEqual(text.count("EqualTo_string(GetVariableSystem.Get('interface_admit'), '0')"),4,name)
            window,chain,calls=action.stages[0]
            stage=gui.stage_widget(code,action,None,values,0,chain,calls)
            self.assertEqual(stage.count("EqualTo_string(GetVariableSystem.Get('interface_admit'), '1')"),4,name)
            self.assertEqual(text.count("Not(GetVariableSystem.Exists('interface_admit'))"),4,name)

    def test_the_decision_is_made_where_the_command_first_opens_and_is_forgotten_afterwards(self):
        placed={window for window,text in gui.action_widgets(True) if 'name = admit_' in text}
        self.assertEqual(placed,{BY_NAME[name].stages[0][0] for name in self.GATED})
        self.assertTrue(all("GetVariableSystem.Clear('interface_admit')" in text for text in gui.start_widgets()))
        for name in self.GATED:
            action=BY_NAME[name]
            for state in gui.states(list(BY_NAME).index(name)+1,action,action.datamodels,None,gui.bindings(action)):
                self.assertIn("GetVariableSystem.Clear('interface_admit')",state,name)

    def test_a_goods_proposal_sets_the_good_itself_and_waits_for_no_list_item(self):
        for name in ('offer_goods_treaty_article','demand_goods_treaty_article'):
            action=BY_NAME[name]
            self.assertEqual([chain for _,chain,_ in action.stages[1:]],[(),()])
            self.assertEqual(action.stages[1][2]({}),['ArticleDraft.SetGood({goods}.Self)'])
            self.assertEqual(action.stages[2][2]({}),['TreatyDraft.AddArticleDraft(ArticleDraft.Self)'])


class RatificationTests(unittest.TestCase):
    def test_treaty_proposals_respect_the_general_signing_rule(self):
        definitions={'common/treaty_articles':{'article':{'kind':['directed']}},
                     'common/scripted_rules':{'can_sign_treaty_with':{'body':['NOT = { is_diplomatic_play_enemy_of = scope:other_country }']}}}
        s=snapshot(definitions,player_diplomatic_option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}],
                   diplomatic_play_history=[{'diplomatic_play':1,'initiator':PLAYER,'target':OTHER}])
        with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())),patch.object(available,'ratification',lambda:{'article':''}):
            self.assertEqual(RULES['offer_treaty_article'](s),[])
            self.assertEqual(RULES['demand_treaty_article'](s),[])

    def test_naval_threats_require_the_ship_count_in_the_game_rule(self):
        definitions={'common/treaty_articles':{'article':{'kind':['directed']}},
                     'common/scripted_rules':{'can_threaten_naval_hostilities':{'body':['navy_size >= 10']}}}
        with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())),patch.object(available,'ratification',lambda:{'article':''}),patch.object(Memory,'dlc',('ep2',)):
            for ships in (0,9,10):
                s=snapshot(definitions,player_diplomatic_option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}],
                           country_military_report=[{'country':PLAYER,'num_ships':ships}])
                self.assertEqual(bool(RULES['threaten_treaty_article'](s)),ships>=10)

    def test_amendments_do_not_add_mutually_exclusive_articles(self):
        s=snapshot(treaty_article_history=[{'treaty':1,'treaty_article_type':'guarantee_independence'}])
        with patch.object(available,'standing_treaties',return_value={1:OTHER}),patch.object(available,'treaty_articles',return_value=[{'country':OTHER,'treaty_article':'alliance'}]):
            self.assertEqual(available.amendments(s,'mutual',True),[])

    def test_building_rules_receive_the_investing_country(self):
        definitions={'common/buildings':{'trade':{'can_build_government':['scope:investor_country = { always = no }']}}}
        s=snapshot(definitions,state_history=[{'state':1,'country':PLAYER,'state_region':'x'}])
        with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())):
            self.assertEqual(available.buildable(s),[])

    def test_an_article_the_game_would_not_ratify_is_not_offered(self):
        articles={'refused':{'kind':['directed']},'ratified':{'kind':['directed']},'unknown':{'kind':['directed']}}
        terms={'refused':'always = no','ratified':'always = yes','unknown':'a_trigger_the_evaluator_does_not_know = yes'}
        s=snapshot({'common/treaty_articles':articles},player_diplomatic_option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}])
        with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())),patch.object(available,'ratification',lambda:terms):
            self.assertEqual(RULES['offer_treaty_article'](s),[{'country':OTHER,'treaty_article':'ratified'},{'country':OTHER,'treaty_article':'unknown'}])
            self.assertEqual(RULES['demand_treaty_article'](s),RULES['offer_treaty_article'](s))

    def test_a_naval_threat_is_offered_with_the_expansion_that_provides_it(self):
        s=snapshot({'common/treaty_articles':{'ratified':{'kind':['directed']}}},player_diplomatic_option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}])
        with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())),patch.object(available,'ratification',lambda:{'ratified':''}):
            for installed,offered in (((),[]),(('ep2',),[{'country':OTHER,'treaty_article':'ratified'}])):
                with patch.object(type(s),'dlc',installed):
                    self.assertEqual(RULES['threaten_treaty_article'](s),offered,installed)

    def test_a_strait_article_needs_the_giver_to_border_a_strait(self):
        articles={'no_tolls':{'kind':['directed'],'visible':['has_any_strait_province = scope:source_country'],
                              'possible':['has_any_strait_province = scope:source_country has_any_strait_control = scope:source_country']}}
        option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}]
        states=[{'state':1,'country':PLAYER},{'state':2,'country':OTHER},{'state':3,'country':THIRD}]
        strait=[{'strait':5,'strait_definition':'a'}]
        cases=(({},[],[]),
               ({'strait_history':strait,'strait_endpoint':[{'strait':5,'first_state':1,'second_state':3}]},[{'country':OTHER,'treaty_article':'no_tolls'}],[]),
               ({'strait_history':strait,'strait_endpoint':[{'strait':5,'first_state':2,'second_state':3}]},[],[{'country':OTHER,'treaty_article':'no_tolls'}]),
               ({'strait_history':strait},[],[{'country':OTHER,'treaty_article':'no_tolls'}]),
               ({'strait_history':strait,'occupation_history':[{'state':2,'controller':PLAYER}]},[{'country':OTHER,'treaty_article':'no_tolls'}],[{'country':OTHER,'treaty_article':'no_tolls'}]))
        for tables,offered,demanded in cases:
            s=snapshot({'common/treaty_articles':articles},player_diplomatic_option=option,state_history=states,**tables)
            with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())),patch.object(available,'ratification',lambda:{'no_tolls':''}):
                self.assertEqual(RULES['offer_treaty_article'](s),offered,tables)
                self.assertEqual(RULES['demand_treaty_article'](s),demanded,tables)

    def test_every_article_of_the_installed_game_has_ratification_terms(self):
        from interface.script import read
        from interface.common import DEFAULT_GAME
        self.assertEqual(set(available.ratification()),{name for name,_ in read(DEFAULT_GAME/'game','common/treaty_articles')})


class PrincipleTests(unittest.TestCase):
    def bloc(self,mandates):
        definitions={'common/power_bloc_principle_groups':{'trade':{'levels':['trade_1','trade_2']},'army':{'levels':['army_1']},'navy':{'levels':['navy_1']}}}
        return snapshot(definitions,country_history=[{'country':PLAYER,'power_bloc':6,'bloc_leader':True}],power_bloc_history=[{'power_bloc':6,'power_bloc_identity':'league'}],
                        power_bloc_adopted_principle=[{'power_bloc':6,'power_bloc_principle':'trade_1'}],player_policy=[{'has_bloc_mandates':mandates}])

    def test_a_held_principle_can_be_replaced_by_one_from_a_group_not_held(self):
        with patch.object(available,'principle_allowed',lambda s,kind:True):
            self.assertEqual(RULES['replace_principle'](self.bloc(True)),[{'slot':0,'power_bloc_principle':'army_1'},{'slot':0,'power_bloc_principle':'navy_1'}])
            self.assertEqual(RULES['replace_principle'](self.bloc(False)),[])


if __name__=='__main__':
    unittest.main()


class JoinedPactTests(unittest.TestCase):
    def offered(self,rows):
        s=snapshot(pact_history=rows)
        with patch.object(available,'opening_seq',lambda s:99),patch.object(available,'snapshot_hours',lambda s,seq:s.hours-99*MONTH):
            return RULES['break_pact'](s)

    def test_a_two_sided_pact_the_other_country_began_can_be_ended_by_us(self):
        self.assertEqual(self.offered([pact(1,OTHER,PLAYER,'da_knowledge_sharing')]),[{'country':OTHER,'diplomatic_action':'da_knowledge_sharing'}])

    def test_a_one_sided_pact_and_our_own_subjection_stay_with_the_country_that_began_them(self):
        self.assertIsNone(available.pact_terms()['rivalry'][2])
        self.assertEqual(self.offered([pact(1,OTHER,PLAYER,'rivalry'),pact(2,OTHER,PLAYER,'puppet')]),[])


class StatePickTests(unittest.TestCase):
    def picks(self,*rows):
        return snapshot(player_diplomatic_option_state=[{'target_country':country,'action_type':action,'side':side,'state':state} for country,action,side,state in rows])

    def test_a_state_is_offered_on_the_side_the_game_listed_it(self):
        s=self.picks((OTHER,'take_state','target',5),(OTHER,'grant_state','source',6))
        with patch.object(available,'diplomatic_allowed',lambda s,country,action:True):
            self.assertEqual(RULES['diplomatic_action_second_state'](s),[{'country':OTHER,'diplomatic_action':'take_state','state':5,'obligation':'None'}])
            self.assertEqual(RULES['diplomatic_action_first_state'](s),[{'country':OTHER,'diplomatic_action':'grant_state','state':6,'obligation':'None'}])
            self.assertEqual(RULES['diplomatic_action_states'](s),[])

    def test_an_action_with_states_on_both_sides_is_a_trade(self):
        s=self.picks((OTHER,'trade_states','source',6),(OTHER,'trade_states','target',5))
        with patch.object(available,'diplomatic_allowed',lambda s,country,action:True):
            self.assertEqual(RULES['diplomatic_action_states'](s),[{'country':OTHER,'diplomatic_action':'trade_states','given':6,'taken':5,'obligation':'None'}])
            self.assertEqual(RULES['diplomatic_action_first_state'](s)+RULES['diplomatic_action_second_state'](s),[])

    def test_a_refused_action_offers_no_state(self):
        s=self.picks((OTHER,'take_state','target',5))
        with patch.object(available,'diplomatic_allowed',lambda s,country,action:False):
            self.assertEqual(RULES['diplomatic_action_second_state'](s),[])


class DeadlineTests(unittest.TestCase):
    def test_every_command_with_a_deadline_is_refused_when_its_request_runs_out(self):
        timed=[action for action in BY_NAME.values() if action.deadline]
        text='\n'.join(gui.deadline_widgets())
        self.assertTrue(timed)
        for action in timed:
            code=list(BY_NAME).index(action.name)+1
            turns=4*len(gui.variants(action))
            self.assertEqual(text.count(f'state = {{ name = deadline_{code}_'),turns,action.name)
            self.assertEqual(text.count(f'state = {{ name = late_{code}_'),turns,action.name)

    def test_a_deadline_only_refuses_the_request_that_started_it(self):
        timer,late=gui.deadline_widgets()[:2]
        own=timer.split("GetVariableSystem.Set('")[1].split("'")[0]
        self.assertTrue(own.startswith('interface_deadline_'))
        self.assertIn(f"on_start = \"[GetVariableSystem.Set('{own}', {gui.FIRED})]\"",timer)
        self.assertIn(f"on_finish = \"[GetVariableSystem.Set('interface_tick', GetVariableSystem.Get('{own}'))]\"",timer)
        self.assertIn(gui.TICKED,late)
        self.assertNotIn('SetIf',timer+late)

    def test_a_stage_only_counts_for_the_request_that_reached_it(self):
        for number in range(gui.MAX_STAGES):
            self.assertIn(f"GetVariableSystem.Set('{gui.stage_flag(number)}', GetVariableSystem.Get('{gui.armed_flag(number)}'))",gui.STAGE_TIMERS)
        for text in gui.start_widgets():
            self.assertIn(f"GetVariableSystem.Set('interface_map_go', {gui.FIRED})",text)
        generated='\n'.join([text for _,text in gui.action_widgets(True)]+gui.deadline_widgets()+[gui.ship_navigation()])
        self.assertIn(f"GetVariableSystem.Set('{gui.armed_flag(0)}', {gui.FIRED})",generated)
        for flag in ('interface_stage','interface_armed','interface_map_go'):
            self.assertNotIn(f"GetVariableSystem.Exists('{flag}",generated)

    def test_a_command_opens_once_and_never_again_after_it_has_fired(self):
        for text in gui.start_widgets():
            self.assertEqual(text.count('name = start_'),4)
            self.assertEqual(text.count(gui.UNFIRED),4)

    def test_a_later_refusal_stops_once_the_next_stage_has_begun(self):
        action=BY_NAME['exchange_treaty_articles']
        index,values=next(iter(gui.variants(action)))
        text=gui.absent_widget(list(BY_NAME).index(action.name)+1,action,index,values)
        state=next(line for line in text.split('\n') if 'name = absent_' in line)
        self.assertIn(gui.reached(gui.stage_flag(0)),state)
        for flag in (gui.armed_flag,gui.stage_flag):
            self.assertIn(f'Not({gui.reached(flag(1))})',state)

    def test_a_later_refusal_is_written_for_the_request(self):
        for code,action in enumerate(BY_NAME.values(),1):
            if action.absent:
                for index,values in gui.variants(action):
                    self.assertNotRegex(gui.absent_widget(code,action,index,values),r'\{\w+\}',action.name)

    def test_a_staged_command_gets_time_for_each_stage(self):
        staged=next(action for action in BY_NAME.values() if action.deadline and len(action.stages)>1)
        code=list(BY_NAME).index(staged.name)+1
        text=next(widget for widget in gui.deadline_widgets() if f'name = deadline_{code}_' in widget)
        self.assertIn(f'duration = {round(staged.deadline+len(staged.stages)*(gui.STAGE+.05),2)} ',text)


class DraftTests(unittest.TestCase):
    def test_every_new_proposal_starts_from_an_empty_draft_and_leaves_one(self):
        from interface.actions.catalogue import OPEN_DRAFT, RESET
        opened=[action for action in BY_NAME.values() if action.start==OPEN_DRAFT]
        self.assertGreater(len(opened),20)
        for action in opened:
            self.assertEqual(action.prepare,(RESET,),action.name)
            self.assertLess(action.cleanup.index(RESET),action.cleanup.index('InformationPanelBar.ClosePanel'),action.name)

    def test_the_draft_is_emptied_before_the_gate_decides(self):
        action=BY_NAME['offer_treaty_article']
        text=gui.absent_widget(list(BY_NAME).index(action.name)+1,action,None,gui.bindings(action))
        self.assertLess(text.index('TreatyDraftPanel.GetDraft.ResetAll'),text.index("GetVariableSystem.Set('interface_admit'"))

    def test_a_refused_proposal_carries_the_games_reason(self):
        action=BY_NAME['offer_treaty_article']
        text=gui.absent_widget(list(BY_NAME).index(action.name)+1,action,None,gui.bindings(action))
        told=text.split("GetVariableSystem.Set('interface_action_desc', ")[1].split(']"')[0]
        self.assertTrue(told.startswith('Select_CString('),told)
        for reason in ('.IsAvailable(','TreatyDraftPanel.GetDraft.GetCanIncludeArticleTypeDesc(','.GetIsAvailableDesc('):
            self.assertIn(reason,told)

    def test_a_proposal_is_admitted_on_the_two_conditions_of_the_games_own_button(self):
        from interface.actions.catalogue import INPUTS, OPEN_DRAFT, REDRAFT, available, includable
        typed={f'{verb}_{kind}_treaty_article' for verb in ('offer','demand') for kind in INPUTS}
        for action in BY_NAME.values():
            if action.start==OPEN_DRAFT:
                holder='Right' if action.name.startswith(('demand','threaten','work_out')) else 'Left'
                self.assertIn(available(holder),action.admit,action.name)
                self.assertEqual(includable(holder) in action.admit,action.name not in typed,action.name)
            if action.start in (OPEN_DRAFT,REDRAFT):
                self.assertTrue(action.deadline,action.name)


class ArticleInputTests(unittest.TestCase):
    def test_a_treaty_port_is_asked_only_of_a_state_that_can_be_ours(self):
        s=snapshot(state_history=[{'state':2,'country':OTHER,'treaty_port_potential':True},{'state':5,'country':OTHER,'treaty_port_potential':False}])
        self.assertEqual(available.article_states(s,'treaty_port',OTHER,PLAYER),[2])
        self.assertEqual(available.article_states(s,'treaty_port',OTHER,THIRD),[2,5])
        self.assertEqual(available.article_states(s,'state_transfer',OTHER,PLAYER),[2,5])

    def test_a_non_colonisation_agreement_names_a_region_with_unclaimed_land(self):
        s=snapshot(state_history=[{'state':2,'country':OTHER},{'state':5,'country':THIRD}],country_history=[{'country':THIRD,'country_type':'decentralized'}])
        with patch.object(available,'state_regions',lambda s:{2:'a',5:'b'}):
            self.assertEqual(available.article_regions(s,'non_colonization_agreement'),['b'])
            self.assertEqual(available.article_regions(s,'law_commitment'),['a','b'])

    def test_nationalisation_is_demanded_only_of_a_country_that_owns_buildings_here(self):
        types={'force_nationalization':{'target_type':['country'],'settings':['validate_force_nationalization']}}
        s=snapshot({'common/war_goal_types':types})
        s.keys=lambda name:list(types)
        for owns,expected in ((False,[]),(True,[{'diplomatic_play':4,'war_goal_type':'force_nationalization','holder':PLAYER,'country':OTHER}])):
            with patch.object(available,'open_plays',lambda s:[4]),patch.object(available,'goal_targets',lambda s,play,kind:{OTHER}),patch.object(available,'owns_here',lambda s,country:owns):
                self.assertEqual(available.goal_drafts(s,'country'),expected)


class ConflictTests(unittest.TestCase):
    def test_changing_a_treaty_and_proposing_to_its_other_country_cannot_share_a_pause(self):
        from loop import run
        s=snapshot(treaty_history=[{'treaty':7,'first_country':OTHER,'second_country':PLAYER},{'treaty':8,'first_country':OTHER,'second_country':THIRD}])
        links=run.linked(s)
        self.assertEqual(links[('treaty',7)],('country',OTHER))
        self.assertNotIn(('treaty',8),links)
        amended=run.targets('amend_demand_treaty_article',{'treaty':7,'treaty_article':'abandon_piracy'},links)
        proposed=run.targets('demand_timed_treaty_article',{'country':OTHER,'treaty_article':'non_piracy_agreement','days':'5475'})
        self.assertIn(('country',OTHER),amended&proposed)

    def test_a_pause_holds_one_sway(self):
        from loop import run
        sways={name for name in BY_NAME if name.startswith('offer_sway')}
        self.assertEqual(set(run.SLOTS['sway']),sways)


class StandardMethodTests(unittest.TestCase):
    class Country:
        methods=[('farm','base','old'),('farm','base','new')]

        def __init__(self,rows):
            self.rows=rows

        def buildings(self):
            return [(ident,'farm',levels) for ident,levels,_ in self.rows]

        def grouped(self,table,columns):
            return {ident:[method] for ident,_,method in self.rows}

        def memo(self,name,compute):
            return compute()

    def test_the_standard_is_the_method_most_levels_use(self):
        self.assertEqual(available.resettable(self.Country([(1,5,'new'),(2,1,'old'),(3,1,'old')])),[2,3])

    def test_a_tie_sets_no_standard(self):
        self.assertEqual(available.resettable(self.Country([(1,2,'new'),(2,2,'old')])),[])

    def test_an_empty_building_neither_counts_nor_resets(self):
        self.assertEqual(available.resettable(self.Country([(1,3,'new'),(2,0,'old')])),[])
