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
    def test_every_weight_is_drawn_over_the_search_range_except_those_switched_off(self):
        from advisors.random_picker import HIGH, LOW
        advisor=RandomAdvisor(1,{'build':3,'cancel_construction':0})
        actions=['build','cancel_construction','research']
        weights=advisor.start_run(None,actions,None)
        self.assertEqual(weights['cancel_construction'],0)
        drawn=[advisor.start_run(None,actions,None)[name] for _ in range(200) for name in ('build','research')]
        self.assertTrue(all(10**LOW<=weight<=10**HIGH for weight in drawn))
        self.assertEqual(len(set(drawn)),len(drawn))
        self.assertLess(min(drawn),.1)
        self.assertGreater(max(drawn),10)

class RandomSmacWeightingTests(unittest.TestCase):
    def test_too_few_scored_runs_give_random_weights(self):
        import numpy as np
        from advisors.random_smac_weighting import INITIAL, RandomSmacWeightingAdvisor
        low,high=np.full(4,-2.),np.full(4,2.)
        for observations in (0,INITIAL-1):
            x,record=RandomSmacWeightingAdvisor(0).propose(np.ones((observations,4)),np.arange(float(observations)),low,high)
            self.assertEqual(record['method'],'random')
            self.assertIsNone(record['predicted_reward'])
            self.assertTrue(((x>=low)&(x<=high)).all())
            self.assertGreater(len(set(x.tolist())),1)

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
        names=[name for _,name,_ in ending[:-1]]
        self.assertTrue('capitulate' not in names or names[-1]=='capitulate')

    def test_every_batch_ends_with_running_a_drawn_number_of_days(self):
        import random
        from loop.run import RUN_DAYS, Drawer
        class Snapshot:
            seq=1
        drawer=Drawer(RandomAdvisor(0),{'research':[{'technology':'a'},{'technology':'b'}]},Snapshot(),{},set())
        rng=random.Random(2)
        batches=[drawer.draw(rng) for _ in range(40)]
        self.assertEqual({batch[-1][1] for batch in batches},{'run_days'})
        self.assertTrue(all('run_days' not in [name for _,name,_ in batch[:-1]] for batch in batches))
        days=[batch[-1][2]['days'] for batch in batches]
        self.assertTrue(all(RUN_DAYS[0]<=value<=RUN_DAYS[1] for value in days))
        self.assertGreater(len(set(days)),10)

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
                return mock.Mock(fetchall=lambda:[('research',5.0),('enact_law',0.0),('build',2.0),('choose_event_option',50.0),('accept_treaty',50.0),('decline_treaty',50.0)])
        offered={'research':[{'technology':'a'},{'technology':'b'}],'enact_law':[{'law':1}],'build':[{'state':1,'building_type':'farm'}],
                 'choose_event_option':[{'event':'x.1','option':0},{'event':'x.1','option':1},{'event':'y.2','option':0}],
                 'accept_treaty':[{'country':3}],'decline_treaty':[{'country':3}],'pause':[{}]}
        connection=Connection()
        with mock.patch.object(run,'Stored',lambda found,run_id,seq:Snapshot()),mock.patch.object(run,'available',lambda snapshot:offered):
            snapshot,blocks=run.redraw(connection,12,7,25,3)
            again=run.redraw(connection,12,7,25,3)[1]
            other=run.redraw(connection,12,7,25,4)[1]
            chosen=run.redraw(connection,12,7,25,3,{'enact_law':1.0,'research':0.0,'build':0.0})[1]
        self.assertEqual((connection.asked,snapshot.seq,len(blocks)),((12,),7,25))
        self.assertEqual(blocks,again)
        self.assertNotEqual(blocks,other)
        seen=set()
        for block in blocks:
            self.assertEqual(block[-1][0],'run_days')
            self.assertTrue(run.RUN_DAYS[0]<=block[-1][1]['days']<=run.RUN_DAYS[1])
            names=[name for name,_ in block[:-1]]
            seen|=set(names)
            self.assertLessEqual(set(names),{'research','build','choose_event_option','accept_treaty','decline_treaty'})
            events=[params['event'] for name,params in block if name=='choose_event_option']
            self.assertEqual(sorted(events),['x.1','y.2'])
            self.assertEqual(names.count('accept_treaty')+names.count('decline_treaty'),1)
            self.assertLessEqual(set(names[:3]),{'choose_event_option','accept_treaty','decline_treaty'})
            self.assertLessEqual(set(names[3:]),{'research','build'})
        self.assertLessEqual({'choose_event_option','accept_treaty','decline_treaty'},seen)
        self.assertEqual({option for block in blocks for name,params in block if name=='choose_event_option' and params['event']=='x.1' for option in [params['option']]},{0,1})
        self.assertEqual({name for block in blocks for name,_ in block if name.endswith('_treaty')},{'accept_treaty','decline_treaty'})
        self.assertEqual({name for block in chosen for name,_ in block[3:-1]},{'enact_law'})
        self.assertTrue(all(sorted(params['event'] for name,params in block if name=='choose_event_option')==['x.1','y.2'] for block in chosen))

    def test_every_event_and_every_proposal_is_one_question_with_its_own_answers(self):
        from loop.run import questions
        options={'choose_event_option':[{'event':'x.1','option':0},{'event':'x.1','option':1},{'event':'y.2','option':0}],
                 'accept_treaty':[{'country':3}],'decline_treaty':[{'country':3},{'country':4}],'reject_demand':[{'country':3}],'quick_decline_proposal':[{'country':4}],
                 'research':[{'technology':'a'}]}
        asked=[[(name,tuple(combo.items())) for name,combo,_ in question] for question in questions(options,{})]
        self.assertEqual(asked,[[('choose_event_option',(('event','x.1'),('option',0))),('choose_event_option',(('event','x.1'),('option',1)))],
                                [('choose_event_option',(('event','y.2'),('option',0)))],
                                [('accept_treaty',(('country',3),)),('decline_treaty',(('country',3),))],
                                [('decline_treaty',(('country',4),)),('quick_decline_proposal',(('country',4),))],
                                [('reject_demand',(('country',3),))]])

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
        def country(self,ident):
            return 'rank_major'

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
        from advisors.features import GOODS, INSTITUTION_TYPES, LAW_GROUPS
        from advisors.histograms import BUILDINGS, Histograms
        seen=[]
        class Model:
            def predict(self,data):
                return np.array([0.1,0.9,0.4])
        class Lookup(self.Lookup):
            numbers=[1.0,0.0,0.0,0.0,100.0,5.0,20.0,2,300.0,10.0]
            laws=['none']*len(LAW_GROUPS)
            prices=[1.0]*len(GOODS)
            institutions=[0.0]*len(INSTITUTION_TYPES)
        picker=pickers.CatBoostPicker()
        picker.model=Model()
        picker.actions=Histograms([[('action','research',1),('research.technology','a',1)],[('action','enact_law',1)]])
        picker.held=Histograms([[(BUILDINGS,'farm',2)]])
        candidates=[[(None,'research',{'technology':'a'}),(None,'run_days',{'days':30})],[(None,'research',{'technology':'b'}),(None,'run_days',{'days':45})],
                    [(None,'enact_law',{'law':3}),(None,'run_days',{'days':60})]]
        sizes={'action':2,'research.technology':1,BUILDINGS:1}
        with mock.patch.object(pickers,'LiveLookup',lambda snapshot:Lookup()),mock.patch.object(pickers,'live_holdings',lambda snapshot:[(BUILDINGS,'farm',5),(BUILDINGS,'mine',1)]),                mock.patch.object(pickers,'SIZES',sizes),mock.patch.object(pickers,'frame',lambda *parts:seen.append(parts)):
            chosen,predictions=picker.pick(candidates,None)
        self.assertEqual(chosen,1)
        self.assertEqual([round(value,6) for value in predictions],[0.1,0.9,0.4])
        state,laws,held,batch,actions,names=seen[0]
        self.assertEqual(names[-6:],['player.buildings=farm','batch_size','run_days','action=enact_law','action=research','research.technology=a'])
        self.assertEqual(np.hstack([held,batch,actions]).tolist(),[[5,1,30,0,1,1],[5,1,45,0,1,0],[5,1,60,1,0,0]])
        self.assertEqual((state.shape,laws.shape),((3,len(names)-6),(3,len(LAW_GROUPS))))


if __name__=='__main__':
    unittest.main()
