import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from advisors.catalogue import LEVER
from advisors.initializers import ADVISORS, RandomAdvisor
from loop.translate import Choice


class AdvisorTests(unittest.TestCase):
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
    def test_every_weight_is_drawn_over_the_search_range_except_those_switched_off(self):
        from advisors.initializers.random import HIGH, LOW
        advisor=RandomAdvisor(1,{'construct_infrastructure':3,'cancel_queued_construction':0})
        actions=['construct_infrastructure','cancel_queued_construction','research_production']
        weights=advisor.start_run(None,actions,None)
        self.assertEqual(weights['cancel_queued_construction'],0)
        drawn=[advisor.start_run(None,actions,None)[name] for _ in range(200) for name in ('construct_infrastructure','research_production')]
        self.assertTrue(all(10**LOW<=weight<=10**HIGH for weight in drawn))
        self.assertEqual(len(set(drawn)),len(drawn))
        self.assertLess(min(drawn),.1)
        self.assertGreater(max(drawn),10)

class RandomSmacWeightingTests(unittest.TestCase):
    def test_one_scored_run_is_enough_for_a_model_proposal_and_none_is_refused(self):
        import numpy as np
        from advisors.initializers.smac import RandomSmacWeightingAdvisor
        low,high=np.full(4,-2.),np.full(4,2.)
        x,record=RandomSmacWeightingAdvisor(0).propose(np.ones((1,4)),np.array([1.0]),low,high)
        self.assertEqual(record['method'],'expected_improvement')
        self.assertTrue(((x>=low)&(x<=high)).all())
        with self.assertRaises(ValueError):
            RandomSmacWeightingAdvisor(0).propose(np.ones((0,4)),np.array([]),low,high)

    def test_the_forest_proposes_inside_the_bounds_and_toward_better_weights(self):
        import numpy as np
        from advisors.initializers.smac import HIGH, LOW, RandomSmacWeightingAdvisor
        rng=np.random.default_rng(0)
        X=rng.uniform(LOW,HIGH,(40,6))
        X[0]=0
        y=-((X-1)**2).sum(1)
        advisor=RandomSmacWeightingAdvisor(3)
        x,record=advisor.propose(X,y,np.full(6,LOW),np.full(6,HIGH),list('abcdef'))
        self.assertEqual(record['method'],'expected_improvement')
        self.assertEqual(record['candidates'],len(record['candidate_rows']))
        self.assertEqual(record['candidate_rows'][0][4],max(row[4] for row in record['candidate_rows']))
        self.assertEqual(record['expected_improvement'],record['candidate_rows'][0][4])
        self.assertEqual([name for name,_ in record['importance']],list('abcdef'))
        self.assertTrue(((x>=LOW)&(x<=HIGH)).all())
        self.assertLess(((x-1)**2).sum(),np.median(((X-1)**2).sum(1)))

    def test_the_proposal_learns_from_action_weights_alone(self):
        from advisors.data.endgame import BUILDINGS, GDP, HISTORY, HOURS_PER_YEAR, OWNERS, PLAYERS, POPULATION, SNAPSHOTS
        from advisors.data.weights import WEIGHTS
        from advisors.initializers.smac import RandomSmacWeightingAdvisor
        class Result:
            def __init__(self,rows):
                self.rows=rows
            def fetchall(self):
                return self.rows
        class Connection:
            def execute(self,sql,params):
                return Result({HISTORY:[(1,0,2*HOURS_PER_YEAR,'years'),(2,0,2*HOURS_PER_YEAR,'debt_cap')],POPULATION:[(1,0,100),(1,1,110),(2,0,100),(2,1,90)],
                               GDP:[(1,0,50),(1,1,60),(2,0,50)],
                               WEIGHTS:[(1,'build',3.0),(2,'build',1.5)],PLAYERS:[(1,7),(2,7)],
                               SNAPSHOTS:[(1,0,0),(1,1,HOURS_PER_YEAR),(1,2,2*HOURS_PER_YEAR),(2,0,0),(2,1,2*HOURS_PER_YEAR)],OWNERS:[(1,0,10,True,7),(2,0,10,True,7)],
                               BUILDINGS:[(1,0,100,True,'building_port',10,1),(1,1,100,True,'building_port',10,2),(2,0,100,True,'building_port',10,1)]}[sql])
        class Store:
            connection=Connection()
        advisor=RandomSmacWeightingAdvisor(0)
        weights=advisor.start_run(Store(),['build'],({'gdp':0.0,'population':1.0,'sol':0.0,'stock':0.0},0.0))
        self.assertEqual([(run,round(reward,6)) for run,reward in advisor.proposal['observed']],
                         [(1,round((math.sqrt(2)+1.2/math.sqrt(2))/9,6)),(2,round((math.sqrt(2)-1.2)/9,6))])
        self.assertEqual(advisor.proposal['reward'],'composite')
        self.assertEqual(set(weights),{'build'})
        self.assertEqual([name for name,_ in advisor.proposal['importance']],['build'])

    def test_smac_learns_from_all_scored_runs(self):
        import numpy as np
        from unittest import mock
        from advisors.initializers import smac as random_smac_weighting
        rng=np.random.default_rng(0)
        X=rng.uniform(-2,2,(150,2))
        advisor=random_smac_weighting.RandomSmacWeightingAdvisor(1)
        with mock.patch.object(random_smac_weighting,'history',lambda connection,space:(X,X[:,0],list(range(1,151)))):
            advisor.start_run(type('Store',(),{'connection':None})(),['build','research'],None)
        self.assertEqual([run for run,_ in advisor.proposal['observed']],list(range(1,151)))
        self.assertEqual(advisor.proposal['observations'],150)

    def test_reward_is_independent_of_other_runs(self):
        from advisors.data.rewards import breakdown, combine
        changes={1:(2.0,{'gdp':.5,'population':.1,'sol':.2,'stock':.3})}
        objective=({'gdp':.25,'population':.25,'sol':.25,'stock':.25},0.0)
        self.assertAlmostEqual(combine(changes,objective)[1],.275)
        self.assertAlmostEqual(sum(part['contribution'] for part in breakdown(changes,objective,1)[1]),.275)
        two={**changes,2:(2.0,{'gdp':.9,'population':.1,'sol':.2,'stock':.3})}
        rewards=combine(two,objective)
        self.assertGreater(rewards[2],rewards[1])
        self.assertEqual(rewards[1],combine(changes,objective)[1])
        self.assertEqual(breakdown(two,objective,1),breakdown(changes,objective,1))

    def test_rewards_are_normalized_by_rank_so_one_outlier_cannot_stretch_the_scale(self):
        from advisors.data.weights import normalized
        found=normalized([1.0,2.0,3.0,1000.0])
        self.assertEqual(list(found.argsort()),[0,1,2,3])
        self.assertAlmostEqual(found[3],-found[0])
        self.assertAlmostEqual(float(sum(found)),0.0)

    def test_svr_proposal_takes_each_weight_to_the_best_point_of_its_own_curve(self):
        import numpy as np
        from advisors.models.svr import best
        found=best(np.array([1.0,-1.0,0.0,2.0]),np.array([0.0,0.0,-1.0,-1.0]),-2.0,2.0)
        self.assertEqual(found.tolist(),[2.0,-2.0,0.0,1.0])

    def test_svr_advisor_raises_weights_that_raise_the_reward_and_lowers_the_others(self):
        import numpy as np
        from unittest import mock
        from advisors.initializers import svr as random_svr_weighting
        rng=np.random.default_rng(0)
        X=rng.uniform(-2,2,(80,3))
        y=X[:,0]-X[:,1]+rng.normal(0,.3,80)
        advisor=random_svr_weighting.RandomSvrWeightingAdvisor(1,{'raise_queue_item':0})
        with mock.patch.object(random_svr_weighting,'history',lambda connection,space:(X,y,list(range(80)))):
            weights=advisor.start_run(type('Store',(),{'connection':None})(),['build','downsize','research','raise_queue_item'],None)
        self.assertEqual(weights['raise_queue_item'],0)
        self.assertEqual(weights['build'],100.0)
        self.assertEqual(weights['downsize'],0.01)
        self.assertEqual(advisor.proposal['method'],'bootstrap_svr')
        self.assertEqual(sum(count for *_,count in advisor.proposal['observed']),80)
        self.assertEqual([name for name,*_ in advisor.proposal['coefficients']],['build','downsize','research'])

    def test_svr_proposes_from_one_scored_run_and_refuses_none(self):
        import numpy as np
        from unittest import mock
        from advisors.initializers import svr as random_svr_weighting
        store=type('Store',(),{'connection':None})()
        with mock.patch.object(random_svr_weighting,'history',lambda connection,space:(np.ones((1,2)),np.array([1.0]),[1])):
            advisor=random_svr_weighting.RandomSvrWeightingAdvisor(0)
            weights=advisor.start_run(store,['build','research'],None)
        self.assertEqual(advisor.proposal['method'],'bootstrap_svr')
        self.assertTrue(all(np.isfinite(list(weights.values()))))
        with mock.patch.object(random_svr_weighting,'history',lambda connection,space:(np.ones((0,2)),np.array([]),[])):
            with self.assertRaises(ValueError):
                random_svr_weighting.RandomSvrWeightingAdvisor(0).start_run(store,['build','research'],None)

    def test_each_run_draws_weights_that_sum_to_one_and_a_uniform_alpha(self):
        import random
        from advisors.data.rewards import COMPONENTS, draw_objective
        weights,alpha=draw_objective(random.Random(3))
        self.assertEqual(set(weights),set(COMPONENTS))
        self.assertAlmostEqual(sum(weights.values()),1.0)
        self.assertTrue(all(value>=0 for value in weights.values()))
        alphas=[draw_objective(random.Random(seed))[1] for seed in range(400)]
        self.assertTrue(all(.5<=alpha<=1 for alpha in alphas))
        self.assertAlmostEqual(sum(alpha<.75 for alpha in alphas)/len(alphas),.5,delta=.07)

    def test_rewards_weight_log_growth_by_duration_without_population_scaling(self):
        from advisors.data.rewards import combine
        changes={1:(4.0,{'gdp':40.0,'population':4.0,'sol':1.0,'stock':2.0}),2:(0.5,{'gdp':0.0,'population':0.0,'sol':3.0,'stock':0.0})}
        absolute=combine(changes,({'gdp':1.0,'population':0.0,'sol':0.0,'stock':0.0},0.0))
        self.assertAlmostEqual(absolute[1]-absolute[2],40.0)
        yearly=combine(changes,({'gdp':1.0,'population':0.0,'sol':0.0,'stock':0.0},1.0))
        self.assertAlmostEqual(yearly[1]-yearly[2],160.0)
        longer=combine({1:(4.0,{'gdp':1.0,'population':0.0,'sol':0.0,'stock':0.0}),2:(1.0,{'gdp':1.0,'population':0.0,'sol':0.0,'stock':0.0})},({'gdp':1.0,'population':0.0,'sol':0.0,'stock':0.0},.5))
        self.assertAlmostEqual(longer[1],2*longer[2])
        mixed=combine(changes,({'gdp':0.5,'population':0.5,'sol':0.0,'stock':0.0},0.0))
        self.assertAlmostEqual(mixed[1],0.5*40+0.5*4)

    def test_built_stock_counts_levels_times_cost_in_states_the_player_holds(self):
        from advisors.data.rewards import built
        events=[(0,0,10,7),(0,0,11,9),(0,1,1,(10,200.0)),(0,1,2,(11,400.0)),
                (1,1,1,(10,400.0)),
                (2,0,11,7),
                (3,1,1,None),(3,1,3,(11,100.0)),
                (4,0,10,9)]
        self.assertEqual(built(events,7,{0:0,1:10,2:20,3:30,4:40}),[(0,200.0),(10,400.0),(20,800.0),(30,500.0),(40,500.0)])
        self.assertEqual(built(events,7,{0:0,4:40}),[(0,200.0),(40,500.0)])

    def test_growth_is_the_time_weighted_mean_log_ratio_over_the_whole_run(self):
        import math
        from advisors.data.rewards import HOURS_PER_YEAR as Y, growth, mean_log
        self.assertAlmostEqual(growth(0,2*Y,[(0,100),(Y,200)]),math.log(2)/2)
        self.assertAlmostEqual(growth(0,4*Y,[(0,100),(0,100),(3*Y,50),(4*Y,50)]),math.log(.5)/4)
        self.assertAlmostEqual(growth(0,2*Y,[(0,100),(Y,150),(Y,120)]),math.log(1.2)/2)
        self.assertAlmostEqual(growth(0,2*Y,[(0,100),(Y//2,200),(2*Y,50)]),.75*math.log(2))
        self.assertAlmostEqual(mean_log([(0,100),(Y,200),(2*Y,50)],Y,3*Y),math.log(.25)/2)
        with self.assertRaises(RuntimeError):
            growth(0,2*Y,[(5,100)])
        from advisors.data.rewards import MIN_RATIO
        self.assertAlmostEqual(growth(0,3*Y,[(0,100),(Y,0)]),2*math.log(MIN_RATIO)/3)
        self.assertAlmostEqual(growth(0,3*Y,[(0,100),(Y,0),(Y,200)]),2*math.log(2)/3)
        with self.assertRaises(ValueError):
            growth(0,3*Y,[(0,100),(Y,-1)])

    def test_actions_weighted_zero_stay_excluded(self):
        from advisors.initializers import RandomSmacWeightingAdvisor
        advisor=RandomSmacWeightingAdvisor(0,{'cancel_queued_construction':0,'construct_infrastructure':3})
        self.assertEqual(advisor.excluded,{'cancel_queued_construction'})

class WorldPoolTests(unittest.TestCase):
    def test_automatic_world_ranges_and_four_run_warmup(self):
        import random
        from types import SimpleNamespace
        from loop.run import SLIDERS,SAMPLING,world_size,lineup
        rng=random.Random(42)
        rows=[world_size(rng,[None]*len(SLIDERS)) for _ in range(200)]
        for _,countries,states,*values in rows:
            self.assertTrue(20<=states<=100)
            self.assertTrue(max(2,states//8)<=countries<=states//5)
            for name,value in zip(SLIDERS,values):
                if name in ('ideology_uniformity','primary_culture_share'):
                    self.assertEqual(value,(0,1))
                else:
                    self.assertTrue(SAMPLING[name][0]<=value<=SAMPLING[name][1])
        self.assertEqual({row[3+SLIDERS.index('source_regions')] for row in rows},{1,2,3,4})
        arguments=SimpleNamespace(warmup=4,advisors=['random_smac_weighting'],pickers=['catboost'])
        self.assertEqual([lineup(arguments,i) for i in range(4)],[(['random'],['first'])]*4)
        self.assertEqual(lineup(arguments,4),(['random_smac_weighting'],['catboost']))

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


def weighted(offered,weights=None):
    advisor=RandomAdvisor(0)
    advisor.weights={LEVER[name]:1. for name in offered}|(weights or {})
    return advisor


def laws(*idents):
    return [Choice({'law':ident},[('enact_law',{'law':ident})]) for ident in idents]


def technologies(*names):
    return [Choice({'technology':name},[('research',{'technology':name})]) for name in names]


def event(name,option):
    return Choice({'event':name,'option':option},[('choose_event_option',{'event':name,'option':option})])


class BatchSamplerTests(unittest.TestCase):
    def test_a_batch_never_touches_one_object_twice_and_stops_at_a_pause_ending_action(self):
        import random
        from loop.run import Drawer
        class Snapshot:
            seq=1
        offered={'enact_economy_law':laws(1,2),'research_production_technology':technologies('a','b')}
        batch=Drawer(weighted(offered),offered,Snapshot(),{}).draw(random.Random(1))
        picked=[(decision.action,tuple(decision.params.items())) for decision in batch]
        self.assertEqual(len(picked),len(set(picked)))
        self.assertTrue(all(decision.command[1]==decision.params for decision in batch))
        offered={'surrender_war':[Choice({'war':5},[('capitulate',{'war':5})])],'research_production_technology':technologies('a')}
        ending=Drawer(weighted(offered),offered,Snapshot(),{}).draw(random.Random(3))
        names=[decision.action for decision in ending]
        self.assertTrue('surrender_war' not in names or names[-1]=='surrender_war')

    def test_batches_contain_only_actions_and_count_answers_toward_the_sixteen_action_cap(self):
        import random
        from types import SimpleNamespace
        from loop.run import Drawer
        offered={'answer_event':[event(f'e.{i}',0) for i in range(20)],'research_production_technology':technologies('a')}
        drawer=Drawer(weighted(offered),offered,SimpleNamespace(seq=1),{})
        batches=[drawer.draw(random.Random(seed)) for seed in range(40)]
        self.assertTrue(all(len(batch)==16 for batch in batches))
        self.assertEqual({decision.action for batch in batches for decision in batch},{'answer_event'})

    def test_a_decision_is_equally_likely_however_many_commands_carry_it_and_its_commands_are_picked_evenly(self):
        import random
        from collections import Counter
        from types import SimpleNamespace
        from loop.run import Drawer
        offered={'raise_subsidies':[Choice({'building':1},[('subsidies_on',{'building':1}),('subset_subsidies_on_state',{'building_type':'building_x','state':9,'ownership':'any'}),
                                                           ('subset_subsidies_on_state',{'building_type':'building_x','state':9,'ownership':'owned_private'})]),
                                    Choice({'building':2},[('subsidies_on',{'building':2})])]}
        advisor=weighted(offered)
        drawer=Drawer(advisor,offered,SimpleNamespace(seq=1),{})
        first=[drawer.draw(random.Random(seed))[0] for seed in range(4000)]
        buildings=Counter(decision.params['building'] for decision in first)
        commands=Counter(decision.command[0] for decision in first if decision.params['building']==1)
        self.assertAlmostEqual(buildings[1]/4000,.5,delta=.03)
        self.assertAlmostEqual(commands['subsidies_on']/buildings[1],1/3,delta=.04)

    def test_a_lever_is_drawn_by_weight_then_one_of_its_acts_evenly_whatever_their_target_counts(self):
        import random
        from collections import Counter
        from types import SimpleNamespace
        from loop.run import Drawer
        offered={'bolster_movement':[Choice({'political_movement':ident},[('toggle_bolster_movement',{'political_movement':ident})]) for ident in range(1,10)],
                 'stop_suppressing_movement':[Choice({'political_movement':20},[('toggle_suppress_movement',{'political_movement':20})])],
                 'raise_tax_level':[Choice({},[('set_tax_level',{'level':'High'})])]}
        drawer=Drawer(weighted(offered,{'raise_political_movements':3.}),offered,SimpleNamespace(seq=1),{})
        first=Counter(drawer.draw(random.Random(seed))[0].action for seed in range(4000))
        movements=first['bolster_movement']+first['stop_suppressing_movement']
        self.assertAlmostEqual(movements/4000,.75,delta=.03)
        self.assertAlmostEqual(first['bolster_movement']/movements,.5,delta=.04)

    def test_weights_must_name_levers_and_cannot_switch_off_both_answers_to_a_proposal(self):
        import contextlib
        import io
        from loop.run import main
        for weights in (['accept_offers=0','decline_offers=0'],['concede_demand=0','refuse_demand=0'],['agree_to_treaty=0']):
            with self.assertRaises(SystemExit),contextlib.redirect_stderr(io.StringIO()):
                main(['--runs','1','--weight',*weights])

    def test_small_batches_are_favoured_with_a_maximum_of_sixteen(self):
        import random
        from collections import Counter
        from loop.run import ACTIONS_PER_PAUSE, ramp
        rng=random.Random(0)
        sizes=Counter(ramp(rng,ACTIONS_PER_PAUSE,False) for _ in range(20000))
        self.assertEqual((min(sizes),max(sizes)),(6,16))
        self.assertAlmostEqual(sum(value*count for value,count in sizes.items())/20000,6+10/3,delta=.1)
        self.assertGreater(sizes[6],5*sizes[16])

    def test_blocks_are_redrawn_for_a_stored_pause_from_the_recorded_weights(self):
        from unittest import mock
        from loop import run

        class Snapshot:
            seq=7
            player=1

            def buildings(self):
                return []

            def rows(self,table,columns,**equal):
                return []

        class Connection:
            def execute(self,sql,arguments):
                self.asked=arguments
                return mock.Mock(fetchall=lambda:[('research_production',5.0),('laws_economy',0.0),('construct_infrastructure',2.0),('accept_offers',50.0),('decline_offers',50.0)])
        offered={'research_production_technology':technologies('a','b'),'enact_economy_law':laws(1),
                 'construct_infrastructure':[Choice({'state':1,'building_type':'building_port'},[('build',{'state':1,'building_type':'building_port'})])],
                 'answer_event':[event('x.1',0),event('x.1',1),event('y.2',0)],
                 'agree_to_treaty':[Choice({'country':3},[('accept_treaty',{'country':3})])],
                 'refuse_treaty':[Choice({'country':3},[('decline_treaty',{'country':3}),('quick_decline_proposal',{'country':3})])]}
        connection=Connection()
        with mock.patch.object(run,'Stored',lambda found,run_id,seq:Snapshot()),mock.patch.object(run,'available',lambda snapshot:{}), \
             mock.patch.object(run,'offer',lambda snapshot,options:offered):
            snapshot,blocks=run.redraw(connection,12,7,25,3)
            again=run.redraw(connection,12,7,25,3)[1]
            other=run.redraw(connection,12,7,25,4)[1]
            chosen=run.redraw(connection,12,7,25,3,{'laws_economy':1.0,'research_production':0.0,'construct_infrastructure':0.0,'accept_offers':1.0,'decline_offers':1.0})[1]
        self.assertEqual((connection.asked,snapshot.seq,len(blocks)),((12,),7,25))
        self.assertEqual(blocks,again)
        self.assertNotEqual(blocks,other)
        seen=set()
        for block in blocks:
            self.assertLessEqual(len(block),16)
            names=[name for name,_ in block]
            seen|=set(names)
            self.assertLessEqual(set(names),{'research_production_technology','construct_infrastructure','answer_event','agree_to_treaty','refuse_treaty'})
            events=[params['event'] for name,params in block if name=='answer_event']
            self.assertEqual(sorted(events),['x.1','y.2'])
            self.assertEqual(names.count('agree_to_treaty')+names.count('refuse_treaty'),1)
            self.assertLessEqual(set(names[:3]),{'answer_event','agree_to_treaty','refuse_treaty'})
            self.assertLessEqual(set(names[3:]),{'research_production_technology','construct_infrastructure'})
        self.assertLessEqual({'answer_event','agree_to_treaty','refuse_treaty'},seen)
        self.assertEqual({option for block in blocks for name,params in block if name=='answer_event' and params['event']=='x.1' for option in [params['option']]},{0,1})
        self.assertEqual({name for block in blocks for name,_ in block if name.endswith('_treaty')},{'agree_to_treaty','refuse_treaty'})
        self.assertEqual({name for block in chosen for name,_ in block[3:]},{'enact_economy_law'})
        self.assertTrue(all(sorted(params['event'] for name,params in block if name=='answer_event')==['x.1','y.2'] for block in chosen))

    def test_every_event_and_every_proposal_is_one_question_with_its_own_answers(self):
        from loop.run import questions
        def answer(command,country):
            return Choice({'country':country},[(command,{'country':country})])
        offered={'answer_event':[event('x.1',0),event('x.1',1),event('y.2',0)],
                 'agree_to_treaty':[answer('accept_treaty',3)],'refuse_treaty':[answer('decline_treaty',3),answer('decline_treaty',4)],'refuse_demand':[answer('reject_demand',3)],
                 'research_production_technology':technologies('a')}
        asked=[[(name,tuple(choice.params.items())) for name,choice in question] for question in questions(offered)]
        self.assertEqual(asked,[[('answer_event',(('event','x.1'),('option',0))),('answer_event',(('event','x.1'),('option',1)))],
                                [('answer_event',(('event','y.2'),('option',0)))],
                                [('agree_to_treaty',(('country',3),)),('refuse_treaty',(('country',3),))],
                                [('refuse_treaty',(('country',4),))],
                                [('refuse_demand',(('country',3),))]])

    def test_an_answer_whose_event_or_proposal_is_still_waiting_is_a_failure(self):
        from loop.run import unanswered
        self.assertTrue(unanswered({'action':'choose_event_option','params':{'event':'x.1','option':0}},{'x.1'},set()))
        self.assertFalse(unanswered({'action':'choose_event_option','params':{'event':'x.1','option':0}},{'y.2'},{3}))
        self.assertTrue(unanswered({'action':'decline_treaty','params':{'country':3}},set(),{3}))
        self.assertFalse(unanswered({'action':'decline_treaty','params':{'country':3}},{'x.1'},{4}))
        self.assertFalse(unanswered({'action':'research','params':{'technology':'a'}},{'x.1'},{3}))

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
        def leaders(self,action,params):
            return []
        def country(self,ident):
            return 'rank_major'

    def test_current_laws_fill_one_slot_per_law_group(self):
        from advisors.data.features import LAW_GROUP, LAW_GROUPS, NONE, laws
        found=laws(['law_serfdom'])
        self.assertEqual(len(found),len(LAW_GROUPS))
        self.assertEqual(found[LAW_GROUPS.index(LAW_GROUP['law_serfdom'])],'law_serfdom')
        self.assertEqual(found.count(NONE),len(LAW_GROUPS)-1)

    def test_prices_fill_one_number_per_good_and_mark_untraded_goods_missing(self):
        import math
        from advisors.data.features import GOODS, prices
        found=prices({'grain':30.0})
        self.assertEqual(len(found),len(GOODS))
        self.assertEqual(found[GOODS.index('grain')],30.0)
        self.assertTrue(math.isnan(found[GOODS.index('fabric')]))

    def test_institutions_fill_one_level_per_type_with_zero_when_not_established(self):
        from advisors.data.features import INSTITUTION_TYPES, institutions
        found=institutions({'institution_schools':2})
        self.assertEqual(len(found),len(INSTITUTION_TYPES))
        self.assertEqual(found[INSTITUTION_TYPES.index('institution_schools')],2.0)
        self.assertEqual(sum(found),2.0)

    def test_tariffs_fill_one_level_per_direction_and_good_with_no_tariff_when_unset(self):
        from types import SimpleNamespace as Space
        from advisors.data.features import GOODS, TARIFFS, HistoryLookup, tariffs
        found=tariffs({('import','grain'):0,('export','grain'):6})
        self.assertEqual(len(found),len(TARIFFS))
        self.assertEqual((found[TARIFFS.index('tariff.import.grain')],found[TARIFFS.index('tariff.export.grain')]),(0.0,6.0))
        self.assertEqual(sorted(set(found)),[0.0,3.0,6.0])
        levels={('import','grain'):(1,),('export','iron'):None}
        history=Space(player={1:7},terrain={1:{}},tariff_rows=Space(by_run={1:list(levels)},at=lambda run,key,seq:levels[key]))
        found=HistoryLookup(history,1,5).tariffs
        self.assertEqual((found[TARIFFS.index('tariff.import.grain')],found[len(GOODS)+GOODS.index('iron')]),(1.0,3.0))

    def test_numbers_split_the_queue_by_owner_and_include_construction_use_and_yearly_balance_over_gdp(self):
        from types import SimpleNamespace as Space
        from advisors.data.features import NUMBERS, HistoryLookup
        at=lambda value:Space(at=lambda run,key_or_seq,seq=None:value)
        history=Space(player={1:7},terrain={1:{}},interest=10,treasury=at([100.0,50.0,-3.0]),population=at([10,20,30]),politics=at([4.0]),
                      budget=at((2.0,)),sol=at((8.0,)),construction=at((12.0,10.0,True)),gdp=at((5200.0,)),
                      queue=Space(live=lambda run,seq:[(False,300.0,0,1,'a'),(False,100.0,1,1,'b'),(True,50.0,0,1,'a')]),army={5,6},military=at((20,0.25)),
                      wars=Space(live=lambda run,seq:[(7,),(9,),(7,)]),infamy=at([12.5]))
        numbers=HistoryLookup(history,1,5).numbers
        self.assertEqual(len(numbers),len(NUMBERS))
        self.assertEqual(dict(zip(NUMBERS,numbers)),{'treasury':100.0,'debt':50.0,'interest':2.0,'balance':-3.0,'population':60,'bureaucracy_available':4.0,
                                                        'standard_of_living':8.0,'government_queue_items':2,'government_queue_left':400.0,'private_queue_items':1,
                                                        'private_queue_left':50.0,'construction_capacity':12.0,'construction_used':10.0,'construction_paused':1.0,
                                                        'balance_gdp':-0.03,'battalions':20,'mobilization_ratio':0.25,'wars':2,'army_spending':4.0,
                                                        'army_spending_gdp':0.04,'infamy':12.5})

    def test_fitting_reports_progress_every_iteration_so_the_stall_watchdog_stays_quiet(self):
        from advisors.models.boosting import Beat
        from interface.common import progress_age
        self.assertTrue(Beat().after_iteration(None))
        step,age=progress_age()
        self.assertTrue(step.startswith('catboost fit'))
        self.assertLess(age,1)

    def test_the_picker_takes_the_candidate_with_the_highest_prediction(self):
        import numpy as np
        from unittest import mock
        from advisors import pickers
        from advisors.models.histogram import data
        from advisors.data.features import GOODS, INSTITUTION_TYPES, LAW_GROUPS, TARIFFS
        from advisors.data.histograms import BUILDINGS, Histograms
        seen=[]
        class Model:
            def predict(self,data):
                return np.array([0.1,0.9,0.4])
        class Lookup(self.Lookup):
            numbers=[1.0,0.0,0.0,0.0,100.0,5.0,20.0,2,300.0,0,0.0,10.0,10.0,0.0,-0.02,12,0.0,0,30.0,0.3,4.0]
            laws=['none']*len(LAW_GROUPS)
            prices=[1.0]*len(GOODS)
            institutions=[0.0]*len(INSTITUTION_TYPES)
            tariffs=[3.0]*len(TARIFFS)
        picker=pickers.CatBoostPicker()
        picker.model=Model()
        actions=Histograms([[('action','research_production_technology',1),('research_production_technology.technology','a',1)],[('action','enact_economy_law',1)]])
        held=Histograms([[(BUILDINGS,'farm',2)]])
        candidates=[[('research_production_technology',{'technology':'a'})],[('research_production_technology',{'technology':'b'})],
                    [('enact_economy_law',{'law':3})]]
        sizes={'action':2,'research_production_technology.technology':1,BUILDINGS:1}
        picker.encoder=data.Encoder(actions,held,sizes)
        with mock.patch.object(data,'LiveLookup',lambda snapshot:Lookup()),mock.patch.object(data,'live_holdings',lambda snapshot:[(BUILDINGS,'farm',5),(BUILDINGS,'mine',1)]),mock.patch.object(data,'frame',lambda *parts:seen.append(parts)):
            chosen,predictions=picker.pick(candidates,None)
        self.assertEqual(chosen,1)
        self.assertEqual([round(value,6) for value in predictions],[0.1,0.9,0.4])
        state,laws,held,batch,actions,names=seen[0]
        self.assertEqual(names[-5:],['player.buildings=farm','batch_size','action=enact_economy_law','action=research_production_technology','research_production_technology.technology=a'])
        self.assertEqual(np.hstack([held,batch,actions]).tolist(),[[5,1,0,1,1],[5,1,0,1,0],[5,1,1,0,0]])
        self.assertEqual((state.shape,laws.shape),((3,len(names)-5),(3,len(LAW_GROUPS))))


if __name__=='__main__':
    unittest.main()
