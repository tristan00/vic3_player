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
        found=RULES['offer_sway'](self.play(30))
        self.assertEqual({option['country'] for option in found},{THIRD})
        self.assertEqual([option['offer'] for option in found],list(range(available.SWAY_OFFER_TYPES)))
        self.assertEqual({option['diplomatic_play'] for option in found},{4})

    def test_nobody_is_swayed_in_the_opening_the_countdown_or_a_war(self):
        for escalation,war in ((available.OPENING_PHASE_END-1,None),(available.COUNTDOWN,None),(100,1)):
            self.assertEqual(RULES['offer_sway'](self.play(escalation,war)),[],escalation)

    def test_an_offer_the_panel_does_not_show_is_refused_without_waiting(self):
        action=BY_NAME['offer_sway']
        text=gui.absent_widget(list(BY_NAME).index('offer_sway')+1,action,None,gui.bindings(action))
        self.assertEqual([text.count(f'state = {{ name = {kind}_') for kind in ('admit','refuse','absent')],[4,4,4])
        self.assertEqual(text.count("GetVariableSystem.Set('interface_action_valid', '0')"),8)
        self.assertIn('GetDataModelSize(SwayCountryPanel.AccessSwayOfferTypes)',text)
        self.assertIn('IsDataModelEmpty(SwayCountryPanel.AccessShownSwayOffers)',text)
        self.assertLess(text.index("Set('interface_action_valid', '0')"),text.index("Set('interface_clean', 'all')"))


class GateTests(unittest.TestCase):
    GATED=('offer_treaty_article','demand_treaty_article','agree_treaty_article','offer_goods_treaty_article','demand_goods_treaty_article','offer_sway')

    def test_the_gated_commands_are_the_treaty_proposals_and_the_sway(self):
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
    def test_an_article_the_game_would_not_ratify_is_not_offered(self):
        articles={'refused':{'kind':['directed']},'ratified':{'kind':['directed']},'unknown':{'kind':['directed']}}
        terms={'refused':'always = no','ratified':'always = yes','unknown':'a_trigger_the_evaluator_does_not_know = yes'}
        s=snapshot({'common/treaty_articles':articles},player_diplomatic_option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}])
        with patch.object(available,'technologies',lambda s:(set(),set(),set(),set())),patch.object(available,'ratification',lambda:terms):
            self.assertEqual(RULES['offer_treaty_article'](s),[{'country':OTHER,'treaty_article':'ratified'},{'country':OTHER,'treaty_article':'unknown'}])
            self.assertEqual(RULES['demand_treaty_article'](s),RULES['offer_treaty_article'](s))

    def test_a_strait_article_needs_the_giver_to_border_a_strait(self):
        articles={'no_tolls':{'kind':['directed'],'visible':['has_any_strait_province = scope:source_country'],
                              'possible':['has_any_strait_province = scope:source_country has_any_strait_control = scope:source_country']}}
        option=[{'target_country':OTHER,'action_type':'rivalry','possible':True}]
        states=[{'state':1,'country':PLAYER},{'state':2,'country':OTHER},{'state':3,'country':THIRD}]
        strait=[{'strait':5,'strait_definition':'a'}]
        cases=(({},[],[]),
               ({'strait_history':strait,'strait_endpoint':[{'strait':5,'first_state':1,'second_state':3}]},[{'country':OTHER,'treaty_article':'no_tolls'}],[]),
               ({'strait_history':strait,'strait_endpoint':[{'strait':5,'first_state':2,'second_state':3}]},[],[{'country':OTHER,'treaty_article':'no_tolls'}]),
               ({'strait_history':strait},[{'country':OTHER,'treaty_article':'no_tolls'}],[{'country':OTHER,'treaty_article':'no_tolls'}]))
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
