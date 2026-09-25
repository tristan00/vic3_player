import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from advisors import ADVISORS, RandomAdvisor


class Queue:
    player=7

    def __init__(self,*items):
        self.items=items

    def rows(self,table,columns,**equal):
        return list(self.items) if (table,columns,equal)==('player_construction_queue_item','construction_left,speed',{'private':False}) else []


class AdvisorTests(unittest.TestCase):
    def test_random_advisor_picks_only_offered_combinations(self):
        options={'build':[{'state':1,'building_type':'building_x'}],'research':[],'pause':[{}]}
        advisor=RandomAdvisor(0)
        for _ in range(20):
            self.assertEqual(advisor.choose(options,Queue()),('build',{'state':1,'building_type':'building_x'}))

    def test_random_advisor_returns_nothing_when_nothing_is_offered(self):
        self.assertIsNone(RandomAdvisor(0).choose({'research':[],'unpause':[{}]},Queue()))

    def test_a_zero_weight_action_is_never_picked(self):
        options={'build':[{'state':1}],'subsidies_on':[{'building':2}]}
        advisor=RandomAdvisor(0,{'subsidies_on':0})
        self.assertEqual({advisor.choose(options,Queue())[0] for _ in range(30)},{'build'})

    def test_building_waits_while_the_queue_exceeds_a_year_of_output(self):
        options={'build':[{'state':1}],'research':[{'technology':'x'}]}
        advisor=RandomAdvisor(0)
        self.assertEqual({advisor.choose(options,Queue((600.0,10.0),(200.0,0.0)))[0] for _ in range(30)},{'research'})
        self.assertIn('build',{advisor.choose(options,Queue((400.0,10.0),(100.0,0.0)))[0] for _ in range(30)})
        self.assertIn('build',{advisor.choose(options,Queue((4000.0,100.0),(1000.0,0.0)))[0] for _ in range(30)})

    def test_advisors_are_registered_by_name(self):
        self.assertIs(ADVISORS['random'],RandomAdvisor)


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

    def test_actions_without_objects_conflict_within_their_group(self):
        from loop.run import targets
        self.assertTrue(targets('pause_construction',{})&targets('resume_all_construction',{}))
        self.assertTrue(targets('pause_all_construction',{})&targets('pause_ship_construction',{}))
        self.assertEqual(targets('set_tax_level',{'level':'High'}),{('group','budget'),('shared','bureaucracy')})
        self.assertTrue(targets('set_tax_level',{'level':'High'})&targets('set_government_wages',{'level':'Low'}))
        self.assertTrue(targets('set_tax_level',{'level':'High'})&targets('set_institution_level',{'institution':3,'level':2}))


if __name__=='__main__':
    unittest.main()
