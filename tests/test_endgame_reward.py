import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from advisors.data import endgame
from advisors.data.features import LAWS
from advisors.models.histogram import data as histogram
from advisors.models.row import data as row


Y=endgame.HOURS_PER_YEAR


class EndgameRewardTests(unittest.TestCase):
    def test_each_component_matches_the_selected_equation(self):
        points={'stock':[(0,100),(3*Y,150),(4*Y,200)],
                'population':[(0,100),(3*Y,110),(4*Y,120)],
                'gdp':[(0,100),(3*Y,120),(4*Y,180)]}
        score,years,parts=endgame.target(0,4*Y,dict.fromkeys(endgame.COMPONENTS,100),points)
        self.assertEqual(years,4)
        self.assertAlmostEqual(parts['stock'],1.25)
        self.assertAlmostEqual(parts['population'],.1)
        self.assertAlmostEqual(parts['gdp'],1.2)
        self.assertAlmostEqual(score,(2*1.25+24*.1+1.2)/9)

    def test_short_horizon_keeps_pre_action_values_at_duplicate_timestamps(self):
        points={name:[(0,100),(0,200),(Y/2,200)] for name in endgame.COMPONENTS}
        score,years,parts=endgame.target(0,Y/2,dict.fromkeys(endgame.COMPONENTS,100),points)
        self.assertEqual(years,.5)
        self.assertEqual(parts,dict.fromkeys(endgame.COMPONENTS,2.))
        self.assertAlmostEqual(score,(2*math.sqrt(.5)+6+4/math.sqrt(.5))/9)

    def test_last_year_uses_latest_observation_at_its_start(self):
        points={name:[(0,100),(Y,100),(Y,200),(2*Y,200)] for name in endgame.COMPONENTS}
        _,_,parts=endgame.target(0,2*Y,dict.fromkeys(endgame.COMPONENTS,100),points)
        self.assertEqual(parts,{'stock':1.,'population':0.,'gdp':1.})

    def test_terminal_levels_and_window_start_use_recorded_values(self):
        points={name:[(0,100),(Y,150),(2*Y,200)] for name in endgame.COMPONENTS}
        baseline=dict.fromkeys(endgame.COMPONENTS,100)
        score,_,parts=endgame.target(0,2*Y,baseline,points)
        self.assertEqual(parts,{'stock':1.25,'population':.5,'gdp':1.25})
        self.assertAlmostEqual(score,(1.25*math.sqrt(2)+6+2.5/math.sqrt(2))/9)

    def test_zero_ending_stock_is_finite_and_zero_starting_stock_is_ineligible(self):
        points={name:[(0,100),(Y,0)] for name in endgame.COMPONENTS}
        baseline=dict.fromkeys(endgame.COMPONENTS,100)
        self.assertEqual(endgame.target(0,Y,baseline,points)[2],{'stock':-.5,'population':-1.,'gdp':-.5})
        baseline['stock']=0
        with self.assertRaisesRegex(ValueError,'baselines'):
            endgame.target(0,Y,baseline,points)
        with self.assertRaisesRegex(ValueError,'duration'):
            endgame.target(0,0,dict.fromkeys(endgame.COMPONENTS,100),points)


class TrainingRewardTests(unittest.TestCase):
    def setUp(self):
        self.tables={endgame.HISTORY:[(1,0,4.5*Y,'debt_cap')],
                     endgame.SNAPSHOTS:[(1,0,0),(1,1,4*Y),(1,2,4*Y),(1,3,4.5*Y)],
                     endgame.GDP:[(1,i,v) for i,v in enumerate([100,200,300,400])],
                     endgame.POPULATION:[(1,i,v) for i,v in enumerate([100,200,300,400])],
                     endgame.PLAYERS:[(1,7)],endgame.OWNERS:[(1,0,10,True,7)],
                     endgame.BUILDINGS:[(1,i,100,True,'building_x',10,v) for i,v in enumerate([100,200,300,400])],
                     row.ACTIONS:[(1,1,2,4*Y,'raise_consumption_taxes','goods',None,'grain')],
                     histogram.PAUSES:[(1,2,4*Y,1,'raise_consumption_taxes','goods',None,'grain')]}
        self.connection=SimpleNamespace(info=SimpleNamespace(dsn='reward_test'),execute=Mock(side_effect=lambda sql,params:Mock(fetchall=Mock(return_value=self.tables[sql]))))
        self.costs=patch.object(endgame,'COSTS',{'building_x':1})
        self.costs.start()
        self.addCleanup(self.costs.stop)

    def test_run_and_pause_baselines_are_separate_and_pause_precedes_all_actions(self):
        history=endgame.Trajectories(self.connection,[1])
        self.assertEqual(history.baseline(1,0),dict.fromkeys(endgame.COMPONENTS,100))
        self.assertEqual(history.baseline(1,4*Y),dict.fromkeys(endgame.COMPONENTS,200))
        self.assertEqual(history.starts[1,4*Y],1)
        expected=(math.sqrt(4.5)*3.5+6*4.5*3+7/math.sqrt(4.5))/9
        for reason in ('time','years','defeated','debt_cap'):
            with self.subTest(reason=reason):
                self.tables[endgame.HISTORY]=[(1,0,4.5*Y,reason)]
                self.assertAlmostEqual(endgame.rewards(self.connection)[1],expected)
                self.assertEqual([part['end_ratio'] for part in endgame.outcomes(self.connection)[1]['parts']],[4.,4.,4.])

    def test_both_picker_datasets_use_first_snapshot_of_nonopening_pause(self):
        lookup=SimpleNamespace(numbers=[1.]*len(histogram.NUMBERS),prices=[1.]*len(histogram.PRICES),
                               institutions=[1.]*len(histogram.INSTITUTIONS),tariffs=[1.]*len(histogram.TARIFFS),taxes=[1.]*len(histogram.TAXES),
                               laws=['law']*len(LAWS),player=7,country=lambda ident:'rank_major_power')
        point=SimpleNamespace(state=lookup)
        expected=(2*math.sqrt(.5)+6+4/math.sqrt(.5))/9
        for reason in ('time','years','defeated','debt_cap'):
            with self.subTest(reason=reason):
                self.tables[endgame.HISTORY]=[(1,0,4.5*Y,reason)]
                with patch.object(histogram,'History') as states,patch.object(histogram,'Holdings') as holdings:
                    states.return_value.at.return_value=lookup
                    holdings.return_value.at.return_value=[]
                    whole=histogram.training_data(self.connection)
                with patch.object(row,'Historical') as states,patch.object(row,'context',return_value={'treasury':1.}),patch.object(row,'action_features',return_value={'action':'raise_consumption_taxes'}):
                    states.return_value.at.return_value=point
                    actions=row.load(self.connection)
                self.assertAlmostEqual(whole.y[0],expected)
                self.assertEqual(whole.categories[0,-1],'rank_major_power')
                self.assertAlmostEqual(actions.y[0],expected)
                self.assertEqual(actions.meta.before_seq.tolist(),[2])
                self.assertEqual(actions.meta.baseline_seq.tolist(),[1])
                self.assertEqual(actions.meta.years.tolist(),[.5])
                for name in endgame.COMPONENTS:
                    self.assertEqual(actions.meta[f'baseline.{name}'].tolist(),[200])

    def test_picker_caches_reload_when_end_reason_changes_without_date_changes(self):
        first={1:(0,2*Y,'debt_cap')}
        second={1:(0,2*Y,'defeated')}
        with patch.object(histogram,'training_rows',return_value={1:[]}) as loader:
            cache=histogram.TrainingCache()
            cache.load(self.connection,first)
            cache.load(self.connection,second)
            self.assertEqual(loader.call_args.args[1],second)
            self.assertEqual(loader.call_count,2)
        with patch.object(row,'training_rows',return_value=SimpleNamespace(X=row.frame([]),meta=row.pd.DataFrame(columns=row.METADATA),omitted={1:{}})) as loader:
            cache=row.TrainingCache()
            cache.load(self.connection,first)
            cache.load(self.connection,second)
            self.assertEqual(loader.call_args.args[1],second)
            self.assertEqual(loader.call_count,2)

    def test_dashboard_run_and_pause_breakdowns_match_training_targets(self):
        from dashboard.server import runs
        from dashboard.server.app import app
        from fastapi.testclient import TestClient
        pool=Mock()
        pool.connection.return_value.__enter__=Mock(return_value=SimpleNamespace(cursor=lambda **kwargs:self.connection))
        pool.connection.return_value.__exit__=Mock(return_value=False)
        for reason in ('time','years','defeated','debt_cap'):
            with self.subTest(reason=reason):
                self.tables[endgame.HISTORY]=[(1,0,4.5*Y,reason)]
                with patch.object(runs.db,'POOL',pool),patch.object(runs.db,'row',return_value={'ended_at':'now','end_reason':reason}),patch.object(runs.db,'value',return_value=4*Y):
                    whole=runs.run_reward(1)
                    pause=TestClient(app).get('/api/policy/runs/1/reward?seq=2')
                self.assertEqual(pause.status_code,200)
                pause=pause.json()
                self.assertEqual(whole.baseline_seq,0)
                self.assertEqual([p.end_ratio for p in whole.parts],[4.,4.,4.])
                self.assertEqual([p['end_ratio'] for p in pause['parts']],[2.,2.,2.])
                self.assertEqual((pause['baseline_seq'],pause['years'],pause['window_years']),(1,.5,.5))
                self.assertAlmostEqual(pause['score'],(2*math.sqrt(.5)+6+4/math.sqrt(.5))/9)
                self.assertAlmostEqual(sum(p['contribution'] for p in pause['parts']),pause['score'])
                self.assertEqual([p['start_value'] for p in pause['parts']],[200,200,200])
                self.assertNotEqual(whole.score,pause['score'])


if __name__=='__main__':
    unittest.main()
