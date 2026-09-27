import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from advisors import ADVISORS, RandomAdvisor


class AdvisorTests(unittest.TestCase):
    def test_random_advisor_picks_only_offered_combinations(self):
        options={'build':[{'state':1,'building_type':'building_x'}],'research':[],'pause':[{}]}
        advisor=RandomAdvisor(0)
        for _ in range(20):
            self.assertEqual(advisor.choose(options),('build',{'state':1,'building_type':'building_x'}))

    def test_random_advisor_returns_nothing_when_nothing_is_offered(self):
        self.assertIsNone(RandomAdvisor(0).choose({'research':[],'unpause':[{}]}))

    def test_a_zero_weight_action_is_never_picked(self):
        options={'build':[{'state':1}],'subsidies_on':[{'building':2}]}
        advisor=RandomAdvisor(0,{'subsidies_on':0})
        self.assertEqual({advisor.choose(options)[0] for _ in range(30)},{'build'})

    def test_every_option_of_an_action_is_equally_likely(self):
        options={'build':[{'state':1,'building_type':'building_x'},{'state':1,'building_type':'building_y'}]}
        advisor=RandomAdvisor(0)
        picks=[advisor.choose(options)[1]['building_type'] for _ in range(4000)]
        self.assertAlmostEqual(picks.count('building_y')/len(picks),.5,delta=.03)

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


class Treasury:
    def __init__(self,principal,credit):
        self.values=[(principal,credit)]

    def rows(self,table,columns,**equal):
        return self.values if (table,columns)==('player_treasury','principal,credit') else []


class DebtCapTests(unittest.TestCase):
    def test_debt_cap_is_reached_once_principal_meets_credit(self):
        from loop.run import at_debt_cap
        self.assertTrue(at_debt_cap(Treasury(1218470.4,1206406.3)))
        self.assertTrue(at_debt_cap(Treasury(500.0,500.0)))
        self.assertFalse(at_debt_cap(Treasury(499.0,500.0)))
        self.assertFalse(at_debt_cap(Treasury(0.0,0.0)))


class RandomAdvisorTests(unittest.TestCase):
    def test_every_action_weighs_the_same_except_those_switched_off(self):
        advisor=RandomAdvisor(1,{'build':3,'cancel_construction':0})
        weights=advisor.start_run(None,['build','cancel_construction','research'],None)
        self.assertEqual(weights,{'build':1,'cancel_construction':0,'research':1})

class RandomSmacWeightingTests(unittest.TestCase):
    def test_every_weight_at_one_is_played_before_anything_else(self):
        import numpy as np
        from advisors import RandomSmacWeightingAdvisor
        low,high=np.full(4,-2.),np.full(4,2.)
        x,record=RandomSmacWeightingAdvisor(0).propose(np.ones((12,4)),np.arange(12.),low,high)
        self.assertEqual(record['method'],'default')
        self.assertTrue((x==0).all())
        self.assertIsNotNone(record['predicted_reward'])
        x,record=RandomSmacWeightingAdvisor(0).propose(np.zeros((1,4)),np.zeros(1),low,high)
        self.assertEqual(record['method'],'random')
        self.assertIsNone(record['predicted_reward'])

    def test_the_forest_proposes_inside_the_bounds_and_toward_better_weights(self):
        import numpy as np
        from advisors.random_smac_weighting import HIGH, LOW, RandomSmacWeightingAdvisor
        rng=np.random.default_rng(0)
        X=rng.uniform(LOW,HIGH,(40,6))
        X[0]=0
        y=-((X-1)**2).sum(1)
        advisor=RandomSmacWeightingAdvisor(3)
        advisor.random.random=lambda:1.0
        x,record=advisor.propose(X,y,np.full(6,LOW),np.full(6,HIGH),list('abcdef'))
        self.assertEqual(record['method'],'expected_improvement')
        self.assertEqual(record['candidates'],len(record['candidate_rows']))
        self.assertEqual(record['candidate_rows'][0][4],max(row[4] for row in record['candidate_rows']))
        self.assertEqual(record['expected_improvement'],record['candidate_rows'][0][4])
        self.assertEqual([name for name,_ in record['importance']],list('abcdef'))
        self.assertTrue(((x>=LOW)&(x<=HIGH)).all())
        self.assertLess(((x-1)**2).sum(),np.median(((X-1)**2).sum(1)))

    def test_the_proposal_learns_from_action_weights_alone(self):
        from advisors.random_smac_weighting import GDP, HISTORY, HOURS_PER_YEAR, POPULATION, SOL, WEIGHTS, RandomSmacWeightingAdvisor
        class Result:
            def __init__(self,rows):
                self.rows=rows
            def fetchall(self):
                return self.rows
        class Connection:
            def execute(self,sql,params):
                return Result({HISTORY:[(1,0,2*HOURS_PER_YEAR),(2,0,2*HOURS_PER_YEAR)],POPULATION:[(1,0,100),(1,HOURS_PER_YEAR,110),(2,0,100),(2,2*HOURS_PER_YEAR,90)],
                               GDP:[(1,0,50),(1,HOURS_PER_YEAR,60),(2,0,50)],SOL:[(1,0,5),(2,0,5),(2,HOURS_PER_YEAR,6)],
                               WEIGHTS:[(1,'build',3.0),(2,'build',1.5)]}[sql])
        class Store:
            connection=Connection()
        advisor=RandomSmacWeightingAdvisor(0)
        weights=advisor.start_run(Store(),['build'],({'gdp':0.0,'population':1.0,'sol':0.0},0.0))
        self.assertEqual([(run,round(reward,6)) for run,reward in advisor.proposal['observed']],[(1,2.0),(2,0.0)])
        self.assertEqual(advisor.proposal['reward'],'composite')
        self.assertEqual(set(weights),{'build'})
        self.assertEqual([name for name,_ in advisor.proposal['importance']],[])

    def test_each_run_draws_weights_that_sum_to_one_and_an_alpha_in_the_unit_range(self):
        import random
        from advisors.random_smac_weighting import COMPONENTS, draw_objective
        weights,alpha=draw_objective(random.Random(3))
        self.assertEqual(set(weights),set(COMPONENTS))
        self.assertAlmostEqual(sum(weights.values()),1.0)
        self.assertTrue(all(value>=0 for value in weights.values()) and 0<=alpha<=1)

    def test_rewards_discount_by_years_to_alpha_and_normalize_each_component(self):
        from advisors.random_smac_weighting import combine
        changes={1:(4.0,{'gdp':40.0,'population':4.0,'sol':1.0}),2:(0.5,{'gdp':0.0,'population':0.0,'sol':3.0})}
        absolute=combine(changes,({'gdp':1.0,'population':0.0,'sol':0.0},0.0))
        self.assertAlmostEqual(absolute[1]-absolute[2],2.0)
        yearly=combine(changes,({'gdp':1.0,'population':0.0,'sol':0.0},1.0))
        self.assertAlmostEqual(yearly[1]-yearly[2],2.0)
        mixed=combine(changes,({'gdp':0.5,'population':0.5,'sol':0.0},0.0))
        self.assertAlmostEqual(mixed[1],0.5*40/20+0.5*4/2)

    def test_change_is_the_trailing_year_peak_over_the_start(self):
        from advisors.random_smac_weighting import HOURS_PER_YEAR as Y, change
        self.assertAlmostEqual(change(0,3*Y,[(0,100),(Y,150),(int(1.5*Y),130)]),.3)
        self.assertAlmostEqual(change(0,3*Y,[(0,100),(Y,150)]),.5)
        self.assertAlmostEqual(change(0,Y//2,[(0,100),(Y//4,80)]),0.0)
        self.assertAlmostEqual(change(0,Y//2,[(0,100),(Y//4,120)]),.2)
        with self.assertRaises(RuntimeError):
            change(0,2*Y,[(5,100)])

    def test_actions_weighted_zero_stay_excluded(self):
        from advisors import RandomSmacWeightingAdvisor
        advisor=RandomSmacWeightingAdvisor(0,{'cancel_construction':0,'build':3})
        self.assertEqual(advisor.excluded,{'cancel_construction'})

class WorldPoolTests(unittest.TestCase):
    def test_a_world_built_apart_returns_the_spans_of_its_own_process(self):
        from unittest import mock
        from interface.common import timed
        from interface.timing import RECORDER
        from loop import run

        @timed
        def generate(*size):
            return size
        RECORDER.reset()
        with mock.patch.object(run,'generate',generate):
            world,spans=run.build_apart(1,2,3,.5,1.5)
        self.assertEqual(world,(1,2,3,.5,1.5))
        self.assertEqual({name:stats.calls for name,stats in spans.items()},
                         {'tests.test_loop.WorldPoolTests.test_a_world_built_apart_returns_the_spans_of_its_own_process.<locals>.generate':1,'loop.run.build':1})
        self.assertEqual(RECORDER.drain(),[])


class BatchSamplerTests(unittest.TestCase):
    def test_a_batch_never_touches_one_object_twice_and_stops_at_a_pause_ending_action(self):
        import random
        from loop.run import Drawer
        class Snapshot:
            seq=1
        advisor=RandomAdvisor(0)
        options={'enact_law':[{'law':1},{'law':2}],'research':[{'technology':'a'},{'technology':'b'}]}
        batch=Drawer(advisor,options,Snapshot(),{},set()).draw(random.Random(1))
        picked=[(name,tuple(params.items())) for _,name,params in batch]
        self.assertEqual(len(picked),len(set(picked)))
        self.assertTrue(all(a is advisor for a,_,_ in batch))
        ending=Drawer(advisor,{'capitulate':[{}],'research':[{'technology':'a'}]},Snapshot(),{},set()).draw(random.Random(3))
        names=[name for _,name,_ in ending]
        self.assertTrue('capitulate' not in names or names[-1]=='capitulate')

    def test_pick_first_takes_the_first_batch(self):
        from advisors.pickers import PickFirst
        self.assertEqual(PickFirst().pick([['a'],['b']],None),(0,None))

class FeatureTests(unittest.TestCase):
    class Lookup:
        player=7
        terrain={'STATE_A':'plains'}
        def state(self,state):
            return {1:('STATE_A',7),2:('STATE_A',9)}.get(state,(None,None))
        def building(self,ident):
            return {5:'building_livestock_ranch'}.get(ident)
        def typed(self,kind,ident):
            return {'law':'law_serfdom','military_formation':1}.get(kind)
        def character(self,ident):
            return 'ideology_reformer'
        def country(self,ident):
            return 'rank_major'

    def test_an_action_becomes_its_type_and_its_two_most_telling_parameters(self):
        from advisors.features import slot
        lookup=self.Lookup()
        self.assertEqual(slot('switch_production_method',{'building':5,'production_method':'pm_open_air_cattle'},lookup),
                         ['switch_production_method','pm_open_air_cattle','building_livestock_ranch'])
        self.assertEqual(slot('build',{'state':2,'building_type':'building_rye_farm'},lookup),['build','building_rye_farm','foreign/plains'])
        self.assertEqual(slot('enact_law',{'law':3},lookup),['enact_law','law_serfdom','none'])
        self.assertEqual(slot('research',{'technology':'railways'},lookup),['research','railways','none'])
        self.assertEqual(slot('white_peace',{'war':4},lookup),['white_peace','war','none'])

    def test_current_laws_fill_one_slot_per_law_group(self):
        from advisors.features import LAW_GROUP, LAW_GROUPS, NONE, laws
        found=laws(['law_serfdom'])
        self.assertEqual(len(found),len(LAW_GROUPS))
        self.assertEqual(found[LAW_GROUPS.index(LAW_GROUP['law_serfdom'])],'law_serfdom')
        self.assertEqual(found.count(NONE),len(LAW_GROUPS)-1)

    def test_prices_fill_one_number_per_good_and_mark_untraded_goods_missing(self):
        import math
        from advisors.features import GOODS, prices
        found=prices({'grain':30.0})
        self.assertEqual(len(found),len(GOODS))
        self.assertEqual(found[GOODS.index('grain')],30.0)
        self.assertTrue(math.isnan(found[GOODS.index('fabric')]))

    def test_institutions_fill_one_level_per_type_with_zero_when_not_established(self):
        from advisors.features import INSTITUTION_TYPES, institutions
        found=institutions({'institution_schools':2})
        self.assertEqual(len(found),len(INSTITUTION_TYPES))
        self.assertEqual(found[INSTITUTION_TYPES.index('institution_schools')],2.0)
        self.assertEqual(sum(found),2.0)

    def test_a_batch_fills_sixteen_slots_of_three(self):
        from advisors.features import CATEGORIES, categories
        filled=categories([('research',{'technology':'railways'}),('enact_law',{'law':3})],self.Lookup())
        self.assertEqual(len(filled),len(CATEGORIES))
        self.assertEqual(filled[:6],['research','railways','none','enact_law','law_serfdom','none'])
        self.assertEqual(set(filled[6:]),{'none'})
        self.assertEqual(len(categories([('research',{'technology':'a'})]*20,self.Lookup())),len(CATEGORIES))

    def test_numbers_include_the_construction_queue_and_capacity(self):
        from types import SimpleNamespace as Space
        from advisors.features import NUMBERS, HistoryLookup
        at=lambda value:Space(at=lambda run,key_or_seq,seq=None:value)
        history=Space(player={1:7},terrain={1:{}},interest=10,treasury=at([100.0,50.0,-3.0]),population=at([10,20,30]),politics=at([4.0]),
                      budget=at((2.0,)),sol=at((8.0,)),capacity=at((12.0,)),queue=Space(live=lambda run,seq:[(300.0,),(100.0,)]))
        numbers=HistoryLookup(history,1,5).numbers
        self.assertEqual(len(numbers),len(NUMBERS))
        self.assertEqual(dict(zip(NUMBERS,numbers)),{'treasury':100.0,'debt':50.0,'interest':2.0,'balance':-3.0,'population':60,'bureaucracy_available':4.0,
                                                        'standard_of_living':8.0,'construction_queue_items':2,'construction_queue_left':400.0,'construction_capacity':12.0})

    def test_fitting_reports_progress_every_iteration_so_the_stall_watchdog_stays_quiet(self):
        from advisors.pickers import Beat
        from interface.common import progress_age
        self.assertTrue(Beat().after_iteration(None))
        step,age=progress_age()
        self.assertTrue(step.startswith('catboost fit'))
        self.assertLess(age,1)

    def test_the_picker_takes_the_candidate_with_the_highest_prediction(self):
        import numpy as np
        from unittest import mock
        from advisors import pickers
        class Model:
            def predict(self,data):
                return np.array([0.1,0.9,0.4])
        from advisors.features import GOODS, INSTITUTION_TYPES, LAW_GROUPS
        class Lookup(self.Lookup):
            numbers=[1.0,0.0,0.0,0.0,100.0,5.0,20.0,2,300.0,10.0]
            laws=['none']*len(LAW_GROUPS)
            prices=[1.0]*len(GOODS)
            institutions=[0.0]*len(INSTITUTION_TYPES)
        picker=pickers.CatBoostPicker()
        picker.model=Model()
        candidates=[[(None,'research',{'technology':'a'})],[(None,'research',{'technology':'b'})],[(None,'enact_law',{'law':3})]]
        with mock.patch.object(pickers,'LiveLookup',lambda snapshot:Lookup()):
            chosen,predictions=picker.pick(candidates,None)
        self.assertEqual(chosen,1)
        self.assertEqual([round(value,6) for value in predictions],[0.1,0.9,0.4])


if __name__=='__main__':
    unittest.main()
