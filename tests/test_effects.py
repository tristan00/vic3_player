import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from interface.actions.catalogue import ACTIONS
from interface.options import effects
from loop import run
from tests.memory_stored import Memory

PLAYER=(1<<24)|7
OTHER=(2<<24)|8


def snapshot(**tables):
    s=Memory(PLAYER,tables,None)
    s.hours=60_000_000
    return s


def pact(ident,first,second,kind='increase_relations'):
    return {'pact':ident,'first_country':first,'second_country':second,'pact_type':kind}


class CoverageTests(unittest.TestCase):
    def test_every_command_has_a_check_or_a_stated_reason_it_cannot_be_seen(self):
        self.assertEqual(set(effects.EFFECTS)|set(effects.UNSEEN),{action.name for action in ACTIONS})
        self.assertEqual(set(effects.EFFECTS)&set(effects.UNSEEN),set())
        self.assertLessEqual(set(effects.LATER),set(effects.EFFECTS))
        self.assertTrue(all(effects.UNSEEN.values()))

    def test_every_check_takes_exactly_its_commands_parameters(self):
        for action in ACTIONS:
            for checks in (effects.EFFECTS,effects.LATER):
                if action.name in checks:
                    with self.subTest(action.name):
                        inspect.signature(checks[action.name]).bind(None,None,**{spec.partition(':')[0]:None for spec in action.params})


class TransitionTests(unittest.TestCase):
    def test_a_command_passes_only_when_the_game_went_from_not_so_to_so(self):
        checks={'flagged':lambda b,a:a.flag}
        on,off=SimpleNamespace(flag=True),SimpleNamespace(flag=False)
        self.assertTrue(effects.held(checks,'flagged',off,on,{}))
        self.assertFalse(effects.held(checks,'flagged',on,on,{}))
        self.assertFalse(effects.held(checks,'flagged',off,off,{}))
        self.assertFalse(effects.held(checks,'unknown',off,on,{}))

    def test_a_queued_building_passes_and_one_that_was_already_queued_does_not(self):
        item={'private':False,'position':0,'state':3,'building_type':'building_port'}
        empty,queued=snapshot(),snapshot(player_construction_queue_item=[item])
        params={'state':3,'building_type':'building_port'}
        self.assertTrue(effects.took_effect('build',empty,queued,params))
        self.assertFalse(effects.took_effect('build',queued,queued,params))
        self.assertFalse(effects.took_effect('build',empty,empty,params))

    def test_improving_relations_passes_only_when_a_pact_of_ours_is_new(self):
        option=[{'target_country':OTHER,'action_type':'increase_relations','possible':True}]
        theirs=snapshot(pact_history=[pact(1,OTHER,PLAYER)],player_diplomatic_option=option)
        both=snapshot(pact_history=[pact(1,OTHER,PLAYER),pact(2,PLAYER,OTHER)],player_diplomatic_option=option)
        params={'country':OTHER,'diplomatic_action':'increase_relations'}
        self.assertTrue(effects.took_effect('diplomatic_action',theirs,both,params))
        self.assertFalse(effects.took_effect('diplomatic_action',both,both,params))
        self.assertFalse(effects.took_effect('diplomatic_action',theirs,theirs,params))

    def test_a_pact_is_broken_when_the_very_pact_is_gone_even_if_the_other_country_starts_one(self):
        ours=snapshot(pact_history=[pact(1,PLAYER,OTHER)])
        theirs=snapshot(pact_history=[pact(2,OTHER,PLAYER)])
        params={'country':OTHER,'diplomatic_action':'increase_relations'}
        self.assertFalse(effects.took_effect('break_pact',ours,ours,params))
        self.assertTrue(effects.took_effect_later('break_pact',ours,theirs,params))
        self.assertFalse(effects.took_effect_later('break_pact',theirs,theirs,params))

    def test_an_article_both_sides_give_is_found_without_a_direction(self):
        treaty=[{'treaty':5,'first_country':PLAYER,'second_country':OTHER}]
        article=[{'treaty_article':9,'treaty':5,'treaty_article_type':'defensive_pact','source_country':None,'target_country':None}]
        before,after=snapshot(),snapshot(treaty_history=treaty,treaty_article_history=article)
        params={'country':OTHER,'treaty_article':'defensive_pact'}
        self.assertTrue(effects.took_effect('agree_treaty_article',before,after,params))
        self.assertFalse(effects.took_effect('offer_treaty_article',before,after,params))
        self.assertFalse(effects.took_effect('agree_treaty_article',after,after,params))

    def test_moving_to_end_ignores_construction_added_later_in_the_batch(self):
        def queued(kinds):
            return snapshot(player_construction_queue_item=[{'private':False,'position':i,'state':3,'building_type':kind} for i,kind in enumerate(kinds)])
        params={'state':3,'building_type':'a'}
        before=queued(['a','b'])
        self.assertTrue(effects.took_effect('last_queue_item',before,queued(['b','a','c']),params))
        self.assertFalse(effects.took_effect('last_queue_item',before,queued(['a','b','c']),params))
        self.assertFalse(effects.took_effect('last_queue_item',queued(['b','a']),queued(['b','a','c']),params))
        self.assertFalse(effects.took_effect('last_queue_item',before,queued(['b','c']),params))

    def test_breaking_our_one_sided_pact_does_not_require_theirs_to_end(self):
        before=snapshot(pact_history=[pact(1,PLAYER,OTHER),pact(2,OTHER,PLAYER)])
        after=snapshot(pact_history=[pact(2,OTHER,PLAYER)])
        params={'country':OTHER,'diplomatic_action':'increase_relations'}
        self.assertTrue(effects.took_effect_later('break_pact',before,after,params))
        self.assertFalse(effects.took_effect_later('break_pact',before,before,params))

    def test_a_request_can_create_a_differently_named_reverse_pact(self):
        before=snapshot()
        before.given_definitions={'common/diplomatic_actions':{'da_request_support_regime':{'reverse_pact':['da_support_regime']}}}
        after=snapshot(pact_history=[pact(1,OTHER,PLAYER,'da_support_regime')])
        params={'country':OTHER,'diplomatic_action':'da_request_support_regime'}
        self.assertTrue(effects.took_effect_later('diplomatic_action',before,after,params))
        self.assertFalse(effects.took_effect_later('diplomatic_action',before,before,params))

    def test_abandoning_a_petition_is_verified_when_its_button_disappears(self):
        entry={'journal_entry':1,'journal_entry_type':'je_government_petition','active':True}
        button={'journal_entry_type':'je_government_petition','scripted_button':'je_government_petition_go_away_button'}
        before=snapshot(journal_entry_history=[entry],player_journal_button=[button])
        before.given_definitions={'common/journal_entries':{'je_government_petition':{'scripted_button':['je_government_petition_go_away_button']}}}
        after=snapshot(journal_entry_history=[entry])
        params={'journal_entry':1,'button':0}
        self.assertTrue(effects.took_effect('press_journal_button',before,after,params))
        self.assertFalse(effects.took_effect('press_journal_button',before,before,params))

    def test_caudillo_decree_requires_its_recorded_modifier(self):
        entry={'journal_entry':1,'journal_entry_type':'je_caudillo','active':True}
        button={'journal_entry_type':'je_caudillo','scripted_button':'caudillo_decree_button'}
        before=snapshot(journal_entry_history=[entry],player_journal_button=[button])
        before.given_definitions={'common/journal_entries':{'je_caudillo':{'scripted_button':['caudillo_decree_button']}}}
        after=snapshot(country_timed_modifier=[{'country':PLAYER,'modifier':'caudillo_rule_by_decree_modifier'}])
        params={'journal_entry':1,'button':0}
        self.assertTrue(effects.took_effect('press_journal_button',before,after,params))
        self.assertFalse(effects.took_effect('press_journal_button',before,before,params))


class RecordingTests(unittest.TestCase):
    def loop(self):
        loop=run.Loop.__new__(run.Loop)
        loop.counts={}
        loop.late=[]
        loop.store=Mock()
        return loop

    def test_only_an_accepted_command_without_its_effect_is_recorded_unverified(self):
        loop=self.loop()
        entry={'seq':3,'action':'build','params':{'state':1,'building_type':'x'},'status':'done'}
        with patch.object(run,'took_effect',return_value=True):
            loop.note(entry,'before',SimpleNamespace(seq=9))
        with patch.object(run,'took_effect',return_value=False):
            loop.note({**entry,'seq':4},'before',SimpleNamespace(seq=9))
        loop.note({**entry,'seq':5,'status':'invalid'})
        loop.note({**entry,'seq':6,'status':'no_object'})
        self.assertEqual([(call.args[0]['seq'],call.args[0]['unverified'],call.args[1]) for call in loop.store.log_action.call_args_list],[(3,False,9),(4,True,9),(5,False,None),(6,False,None)])
        self.assertEqual(loop.late,[])

    def test_a_refused_command_is_recorded_at_once_and_is_not_unverified(self):
        loop=self.loop()
        loop.executor=Mock()
        loop.executor.run.return_value={'valid':False,'desc':'no','ms':5}
        loop.misses=loop.seq=0
        loop.turn=1
        pending=[]
        loop.perform('random','build',{'state':1,'building_type':'x'},SimpleNamespace(seq=2),pending)
        self.assertEqual(pending,[])
        entry,after=loop.store.log_action.call_args.args
        self.assertEqual((entry['status'],entry['detail'],entry['unverified'],after),('invalid','no',False,None))

    def test_an_effect_that_needs_time_is_confirmed_at_the_end_of_the_quarter(self):
        loop=self.loop()
        entry={'seq':7,'action':'break_pact','params':{'country':OTHER,'diplomatic_action':'rivalry'},'status':'done'}
        with patch.object(run,'took_effect',return_value=False):
            loop.note(entry,'before',SimpleNamespace(seq=9))
        self.assertEqual(loop.late,[(entry,'before')])
        with patch.object(run,'took_effect_later',return_value=True) as later:
            loop.settle_late('quarter end')
        later.assert_called_once_with('break_pact','before','quarter end',entry['params'])
        loop.store.verify_action.assert_called_once_with(7)
        self.assertEqual(loop.late,[])

    def test_a_check_that_raises_leaves_the_command_unverified_and_the_run_alive(self):
        loop=self.loop()
        entry={'seq':3,'action':'build','params':{},'status':'done'}
        with patch.object(run,'took_effect',side_effect=KeyError('missing')),self.assertLogs(run.LOG,'ERROR'):
            loop.note(entry,'before',SimpleNamespace(seq=9))
        self.assertTrue(loop.store.log_action.call_args.args[0]['unverified'])
