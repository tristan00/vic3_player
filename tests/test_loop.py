import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from advisors import ADVISORS, RandomAdvisor
from loop.effects import verify
from tests.memory_stored import Memory


class Queue:
    player=7

    def __init__(self,*items):
        self.items=items

    def rows(self,table,columns,**equal):
        return list(self.items) if (table,columns,equal)==('player_construction_queue_item','construction_left,speed',{'private':False}) else []


class EffectTests(unittest.TestCase):
    def test_research_and_subject_verdicts_read_stored_rows(self):
        before=Memory(7,{'country_research_history':[{'country_research':3,'country':7,'researching':None}],
                         'formation_history':[{'formation':5,'country':7}],'formation_private':[{'formation':5,'recalled':False}]})
        after=Memory(7,{'country_research_history':[{'country_research':3,'country':7,'researching':'tech_x'}],
                        'formation_history':[{'formation':5,'country':7}],'formation_private':[{'formation':5,'recalled':True}]})
        self.assertTrue(verify('research',{'technology':'tech_x'},before,after,{},None))
        self.assertFalse(verify('research',{'technology':'tech_y'},before,after,{},None))
        self.assertTrue(verify('recall_fleet',{'military_formation':5},before,after,{},None))


class AdvisorTests(unittest.TestCase):
    def test_random_advisor_picks_only_offered_combinations(self):
        options={'build':[{'state':1,'building_type':'building_x'}],'research':[],'pause':[{}]}
        advisor=RandomAdvisor(0)
        for _ in range(20):
            self.assertEqual(advisor.choose(options,Queue()),('build',{'state':1,'building_type':'building_x'}))

    def test_random_advisor_returns_nothing_when_nothing_is_offered(self):
        self.assertIsNone(RandomAdvisor(0).choose({'research':[],'unpause':[{}]},Queue()))

    def test_a_zero_weight_action_is_never_picked(self):
        options={'build':[{'state':1}],'auto_expand_on':[{'building':2}]}
        advisor=RandomAdvisor(0,{'auto_expand_on':0})
        self.assertEqual({advisor.choose(options,Queue())[0] for _ in range(30)},{'build'})

    def test_building_waits_while_the_queue_exceeds_a_year_of_output(self):
        options={'build':[{'state':1}],'research':[{'technology':'x'}]}
        advisor=RandomAdvisor(0)
        self.assertEqual({advisor.choose(options,Queue((600.0,10.0),(200.0,0.0)))[0] for _ in range(30)},{'research'})
        self.assertIn('build',{advisor.choose(options,Queue((400.0,10.0),(100.0,0.0)))[0] for _ in range(30)})
        self.assertIn('build',{advisor.choose(options,Queue((4000.0,100.0),(1000.0,0.0)))[0] for _ in range(30)})

    def test_advisors_are_registered_by_name(self):
        self.assertIs(ADVISORS['random'],RandomAdvisor)


class CoverageTests(unittest.TestCase):
    def test_coverage_names_only_catalogue_actions(self):
        from interface.actions.catalogue import BY_NAME
        from loop.coverage import COVERED
        self.assertEqual({name for names in COVERED.values() for name in names}-set(BY_NAME),set())

    def test_every_catalogue_action_is_mapped_to_a_row(self):
        from interface.actions.catalogue import BY_NAME
        from loop.coverage import COVERED
        self.assertEqual(set(BY_NAME)-{name for names in COVERED.values() for name in names},set())

    def test_rows_are_either_covered_infeasible_or_known(self):
        from loop.coverage import COVERED, INFEASIBLE, ROWS
        self.assertEqual(len(ROWS),164)
        self.assertEqual((set(COVERED)|set(INFEASIBLE))-set(ROWS),set())
        self.assertEqual(set(COVERED)&set(INFEASIBLE),set())


class TurnTests(unittest.TestCase):
    def test_actions_on_the_same_object_conflict_and_choices_do_not(self):
        from loop.run import targets
        self.assertEqual(targets('build',{'state':3,'building_type':'building_x'}),{('state',3),('building_type','building_x')})
        self.assertEqual(targets('set_import_tariff',{'goods':'grain','level':'High'}),{('goods','grain')})

    def test_a_building_conflicts_with_actions_on_its_type(self):
        from loop.run import targets
        self.assertIn(('building_type','building_glassworks'),targets('subsidies_on',{'building':164},{('building',164):('building_type','building_glassworks')}))

    def test_a_commander_conflicts_with_actions_on_its_formation(self):
        from loop.run import targets
        links={('character',51):('military_formation',5)}
        self.assertTrue(targets('unassign_commander',{'character':51},links)&targets('hire_commander_for',{'character':121,'military_formation':5},links))

    def test_two_authority_spenders_conflict(self):
        from loop.run import targets
        self.assertTrue(targets('toggle_bolster_movement',{'political_movement':1})&targets('issue_decree',{'state':2,'decree':'d'}))

    def test_two_queue_moves_conflict(self):
        from loop.run import targets
        self.assertTrue(targets('raise_queue_item',{'state':1,'building_type':'a'})&targets('last_queue_item',{'state':2,'building_type':'b'}))

    def test_a_queue_move_is_judged_on_the_items_both_snapshots_hold(self):
        from loop import effects
        test=effects.EFFECTS['raise_queue_item'][1]
        queues={}
        original=effects.queue
        effects.queue=lambda snapshot:list(queues[snapshot])
        try:
            queues.update(a=[(1,'x'),(2,'y'),(3,'z')],b=[(2,'y'),(1,'x'),(4,'new')])
            self.assertTrue(test('a','b',{'state':2,'building_type':'y'},None))
            queues.update(a=[(1,'x'),(2,'y'),(3,'z')],b=[(2,'y'),(1,'x'),(3,'z'),(4,'new')])
            self.assertTrue(test('a','b',{'state':2,'building_type':'y'},None))
            queues.update(a=[(1,'x'),(2,'y'),(3,'z')],b=[(2,'y'),(3,'z')])
            self.assertIsNone(test('a','b',{'state':2,'building_type':'y'},None))
            queues.update(a=[(1,'x'),(2,'y'),(3,'z')],b=[(1,'x'),(2,'y')])
            self.assertFalse(test('a','b',{'state':2,'building_type':'y'},None))
        finally:
            effects.queue=original

    def test_actions_without_objects_conflict_within_their_group(self):
        from loop.run import targets
        self.assertEqual(targets('pause_construction',{}),targets('resume_all_construction',{}))
        self.assertEqual(targets('set_tax_level',{'level':'High'}),{('group','budget')})


if __name__=='__main__':
    unittest.main()
