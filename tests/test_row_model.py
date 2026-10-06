import ast
import importlib
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from advisors.models.row import data, features
from advisors.models.row.model import Model, pool


class RowTests(unittest.TestCase):
    def test_retired_flag_choices_keep_their_action_and_parameters_in_training(self):
        point=SimpleNamespace(hours=0,entity=lambda table,ident:None)
        rows=features.frame([features.action_features('set_army_flag',{'military_formation':7,'flag':3},point)])
        self.assertEqual(rows.action.tolist(),['set_army_flag'])
        self.assertEqual(rows['parameter.flag.int'].tolist(),[3.])

    def test_target_is_full_future_reward_without_an_action_count_argument(self):
        years=data.HOURS_PER_YEAR
        points={name:[(0,100),(years,200)] for name in data.COMPONENTS}
        baseline={name:100 for name in data.COMPONENTS}
        target,duration,parts=data.target(0,2*years,baseline,points)
        self.assertAlmostEqual(target,2*np.sqrt(2)/9)
        self.assertEqual(duration,2)
        self.assertEqual(set(parts),set(data.COMPONENTS))

    def test_target_baseline_precedes_same_timestamp_changes(self):
        years=data.HOURS_PER_YEAR
        points={name:[(0,100),(0,200),(years,200)] for name in data.COMPONENTS}
        target,_,_=data.target(0,years,{name:100 for name in data.COMPONENTS},points)
        self.assertAlmostEqual(target,10.5/9)

    def test_split_keeps_entire_runs_and_every_row_exactly_once(self):
        runs=np.repeat(np.arange(7),[1,3,5,2,9,4,8])
        train,test=data.split(runs)
        self.assertFalse(set(runs[train])&set(runs[test]))
        np.testing.assert_array_equal(np.sort(np.r_[train,test]),np.arange(len(runs)))
        for a,b in zip((train,test),data.split(runs)):
            np.testing.assert_array_equal(a,b)

    def test_event_ordinary_and_army_actions_are_single_rows_without_weights(self):
        point=SimpleNamespace()
        actions=[('answer_event',{'event':'event.1','option':0}),('raise_consumption_taxes',{'goods':'grain'}),('form_army',{'option':30})]
        rows=features.frame([features.action_features(name,params,point) for name,params in actions])
        self.assertEqual(rows.action.tolist(),[name for name,_ in actions])
        self.assertEqual(pool(rows,np.array([2.,2.,2.])).get_weight(),[1.,1.,1.])
        self.assertEqual(rows['parameter.option.int'].iloc[2],30)
        self.assertTrue(np.isnan(rows['parameter.option.int'].iloc[1]))

    def test_individual_traits_are_not_one_category_for_a_combination(self):
        trait=features.TRAITS[0]
        point=SimpleNamespace(hours=0,entity=lambda table,ident:None,traits=lambda character:[trait])
        row=features.action_features('take_away_command',{'character':1},point)
        self.assertEqual(row[f'target_character.trait.{trait}'],1)
        self.assertEqual(sum(row[f'target_character.trait.{name}'] for name in features.TRAITS),1)

    def test_predictions_preserve_rows_and_can_run_without_a_picker(self):
        rows=features.frame([{'action':'form_army','parameter.option.int':float(i)} for i in range(12)])
        targets=np.arange(12,dtype=float)
        model=Model({'iterations':5,'depth':2,'thread_count':1}).fit(rows,targets)
        together=model.predict(rows)
        separately=np.concatenate([model.predict(rows.iloc[i:i+1]) for i in range(len(rows))])
        np.testing.assert_array_equal(together,separately)
        self.assertEqual(together.shape,(len(rows),))

    def test_models_and_shared_data_never_import_pickers_or_initializers(self):
        root=Path(__file__).resolve().parents[1]/'advisors'
        for folder in ('models','data'):
            for path in (root/folder).rglob('*.py'):
                module='.'.join(path.relative_to(root.parent).with_suffix('').parts)
                package=module.rpartition('.')[0]
                for node in ast.walk(ast.parse(path.read_text())):
                    names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [importlib.util.resolve_name('.'*node.level+(node.module or ''),package)] if isinstance(node,ast.ImportFrom) else []
                    for name in names:
                        self.assertFalse(name.startswith(('advisors.pickers','advisors.initializers')),(path,name))

    def test_picker_averages_predictions_including_repeats_events_and_armies(self):
        from advisors.pickers import piecewise
        candidates=[[('answer_event',{'event':'x','option':0}),('form_army',{'option':30})],
                    [('research_production_technology',{'technology':'a'}),('research_production_technology',{'technology':'a'}),('form_army',{'option':60})],
                    [('form_army',{'option':10})]]
        picker=piecewise.CatBoostPiecewisePicker()
        picker.model=Mock(predict=Mock(return_value=np.array([1.,2.,3.,-1.,4.])))
        with patch.object(piecewise,'live',return_value='rows') as encode:
            chosen,scores=picker.pick(candidates,'snapshot')
        self.assertEqual((chosen,scores),(2,[1.5,5/3,4.]))
        self.assertEqual(len(encode.call_args.args[1]),5)
        picker.model.predict.assert_called_once_with('rows')

    def test_categorical_encoding_preserves_model_predictions_and_missing_values(self):
        rows=[{'action':'form_army','parameter.option.int':float(i%5)} for i in range(20)]
        encoded=features.frame(rows)
        original=pd.DataFrame(rows).reindex(columns=features.NUMERIC+features.CATEGORICAL)
        original[features.NUMERIC]=original[features.NUMERIC].astype(np.float32)
        original[features.CATEGORICAL]=original[features.CATEGORICAL].fillna(features.ABSENT).astype(str)
        pd.testing.assert_frame_equal(encoded.astype({name:str for name in features.CATEGORICAL}),original)
        params={'iterations':8,'depth':2,'thread_count':1,'one_hot_max_size':2}
        targets=np.arange(20,dtype=float)%5
        old=Model(params).fit(original,targets)
        new=Model(params).fit(encoded,targets)
        np.testing.assert_array_equal(old.predict(original),new.predict(encoded))
        np.testing.assert_array_equal(old.predict(original),old.predict(encoded))

    def test_piecewise_deduplication_keeps_multiplicity_parameter_values_and_first_tie(self):
        from advisors.pickers import piecewise
        first=('answer_event',{'event':'x','option':0})
        reversed_params=('answer_event',{'option':0,'event':'x'})
        other=('answer_event',{'event':'x','option':1})
        candidates=[[first,first],[reversed_params,first],[other]]
        picker=piecewise.CatBoostPiecewisePicker()
        picker.model=Mock(predict=Mock(return_value=np.array([-1.,-3.])))
        with patch.object(piecewise,'live',return_value='rows') as encode:
            self.assertEqual(picker.pick(candidates,'snapshot'),(0,[-1.,-1.,-3.]))
        self.assertEqual(encode.call_args.args[1],[first,other])
        for empty in ([],[[]],[candidates[0],[]]):
            with self.assertRaises(ValueError):
                picker.pick(empty,'snapshot')


class RowCacheTests(unittest.TestCase):
    def setUp(self):
        self.connection=SimpleNamespace(info=SimpleNamespace(dsn='first'),execute=Mock())
        self.cache=data.TrainingCache()

    def rows(self,connection,bounds):
        metadata=[{'run':run,'action_number':1,'before_seq':0,'start_hour':0,'end_hour':last,'years':last/data.HOURS_PER_YEAR,
                   **{f'baseline.{name}':100. for name in data.COMPONENTS},
                   **{f'reward_part.{name}':float(run)**(i+1) for i,name in enumerate(data.COMPONENTS)}} for run,dates in sorted(bounds.items()) for last in [dates[1]] if run!=9]
        return SimpleNamespace(X=features.frame([{'action':f'run_{row["run"]}','parameter.option.int':row['end_hour']} for row in metadata]),
                               meta=pd.DataFrame(metadata,columns=data.METADATA),
                               omitted={run:{'no_future_duration':run} for run in bounds})

    def test_cache_loads_new_or_changed_runs_and_drops_removed_runs(self):
        with patch.object(data,'training_rows',side_effect=self.rows) as load:
            self.cache.load(self.connection,{1:(0,10)})
            self.cache.load(self.connection,{1:(0,10),2:(0,20),9:(0,30)})
            self.assertEqual(load.call_args.args[1],{2:(0,20),9:(0,30)})
            same=self.cache.load(self.connection,{1:(0,10),2:(0,20),9:(0,30)})
            self.assertEqual(load.call_count,2)
            self.assertIs(same,self.cache.data)
            changed=self.cache.load(self.connection,{1:(0,40),2:(0,20)})
            self.assertEqual(load.call_args.args[1],{1:(0,40)})
            expected=self.rows(self.connection,{1:(0,40),2:(0,20)})
            pd.testing.assert_frame_equal(changed.X,expected.X)
            pd.testing.assert_frame_equal(changed.meta,expected.meta)
            self.assertEqual(changed.omitted,expected.omitted)
            self.assertTrue(self.cache.load(self.connection,{}).meta.empty)
            self.assertEqual(load.call_count,3)

    def test_cache_resets_for_database_change_and_does_not_cache_a_failed_load(self):
        with patch.object(data,'training_rows',side_effect=self.rows) as load:
            self.cache.load(self.connection,{1:(0,10)})
            self.connection.info.dsn='second'
            self.cache.load(self.connection,{1:(0,10)})
            self.assertEqual(load.call_count,2)
            previous=self.cache.data
            load.side_effect=RuntimeError('interrupted')
            with self.assertRaises(RuntimeError):
                self.cache.load(self.connection,{1:(0,10),2:(0,20)})
            self.assertEqual(self.cache.versions,{1:(0,10)})
            self.assertIs(self.cache.data,previous)

    def test_fixed_rewards_match_between_cached_and_fresh_history(self):
        self.connection.execute.return_value.fetchall.return_value=[(run,0,run*data.HOURS_PER_YEAR,'years') for run in (1,2)]
        with patch.object(data,'training_rows',side_effect=self.rows) as load:
            first=data.load(self.connection,cache=self.cache)
            cached=data.load(self.connection,cache=self.cache)
            self.assertEqual(load.call_count,1)
            fresh=data.load(self.connection)
        np.testing.assert_array_equal(first.y,cached.y)
        pd.testing.assert_frame_equal(cached.X,fresh.X)
        pd.testing.assert_frame_equal(cached.meta,fresh.meta)
        np.testing.assert_array_equal(cached.y,fresh.y)
        for row,y in zip(cached.meta.to_dict('records'),cached.y):
            self.assertAlmostEqual(y,data.reward(row['years'],{name:row[f'reward_part.{name}'] for name in data.COMPONENTS}))
        self.assertEqual(cached.omitted,{'no_future_duration':3})


class RowTuningTests(unittest.TestCase):
    def test_search_parameters_stay_inside_the_requested_space(self):
        from advisors.models.row import tune
        low,high=tune.space()
        points=[low,high,*np.random.default_rng(0).uniform(low,high,(200,len(low)))]
        for params in [*tune.initial(),*[tune.decode(point) for point in points]]:
            self.assertEqual(params['iterations'],50)
            for name in tune.NAMES:
                if name in tune.CHOICES:
                    if name in params:
                        self.assertIn(params[name],tune.RANGES[name])
                else:
                    if name not in params:
                        continue
                    least,most=tune.RANGES[name]
                    self.assertGreaterEqual(params[name],least*(1-1e-12))
                    self.assertLessEqual(params[name],most*(1+1e-12))
            restored=tune.decode(tune.encode(params))
            for name,value in params.items():
                if isinstance(value,str):
                    self.assertEqual(restored[name],value)
                else:
                    self.assertAlmostEqual(restored[name],value)

    def test_trial_retains_fifty_trees_even_when_validation_stops_improving(self):
        from advisors.models.row import tune
        rows=features.frame([{'action':'form_army','parameter.option.int':float(i)} for i in range(24)])
        targets=np.linspace(-1,1,24)
        params=tune.initial()[0]
        metric=tune.Validation(targets,-targets,pd.DataFrame({'run':np.repeat([1,2],12),'before_seq':0}))
        result=tune.trial(0,params,pool(rows,targets),pool(rows,-targets),metric,1)
        self.assertEqual(result['iterations'],50)
        self.assertEqual(result['completed'],50)
        self.assertIsNone(result['stop'])
        self.assertTrue(np.isfinite(result['rmse']))
        self.assertAlmostEqual(result['score'],.5*result['reward_loss']+.5*result['entropy_loss'])

    def test_time_budget_never_stops_a_trial_for_validation_error(self):
        from advisors.models.row import tune
        monitor=tune.Monitor(1)
        for iteration in range(1,51):
            self.assertTrue(monitor.after_iteration(SimpleNamespace(iteration=iteration,metrics={'validation':{'RMSE':[float(iteration)]}})))
        self.assertEqual(monitor.completed,50)

    def test_wall_clock_limit_kills_a_worker_before_training_can_report(self):
        from advisors.models.row import tune
        processes=[]
        original=subprocess.Popen

        def spawn(*args,**kwargs):
            process=original(*args,**kwargs)
            processes.append(process)
            return process

        with tempfile.TemporaryDirectory() as directory, patch.object(tune.subprocess,'Popen',side_effect=spawn):
            output=Path(directory)
            result=tune.run_trial(0,tune.initial()[0],output/'unopened.pkl',output,.05,1)
        self.assertEqual(result['stop'],'time_limit')
        self.assertNotIn('score',result)
        self.assertLess(result['wall_seconds'],2)
        self.assertEqual(len(processes),1)
        self.assertIsNotNone(processes[0].poll())

class RowValidationTests(unittest.TestCase):
    def metric(self,targets,pauses):
        from advisors.models.row.validation import Validation
        return Validation([-1.,1.],targets,pd.DataFrame(pauses,columns=['run','before_seq']))

    def test_exact_blend_rewards_differentiation_and_penalizes_reward_error(self):
        metric=self.metric([0.,0.],[(1,0),(1,0)])
        tied=metric.score([0.,0.])
        distinct=metric.score([-.2,.2])
        self.assertEqual(tied['entropy_loss'],1.)
        self.assertEqual(distinct['entropy_loss'],0.)
        self.assertAlmostEqual(distinct['score'],.5*.2)
        self.assertGreater(metric.score([-100.,100.])['score'],distinct['score'])

    def test_only_within_pause_differentiation_counts_and_singletons_are_excluded(self):
        metric=self.metric([0.]*5,[(1,0),(2,0),(1,0),(2,0),(3,1)])
        result=metric.score([-10.,10.,-10.,10.,1000.])
        self.assertEqual(result['entropy_loss'],1.)
        self.assertEqual(result['mean_pause_entropy'],0.)
        self.assertEqual(result['entropy_pauses'],2)
        self.assertEqual(result['singleton_pauses'],1)

    def test_pauses_have_equal_weight_independent_of_action_count(self):
        metric=self.metric([0.]*6,[(1,0)]*2+[(1,1)]*4)
        result=metric.score([-1.,1.,0.,0.,0.,0.])
        self.assertEqual(result['entropy_loss'],.5)
        self.assertEqual(result['mean_pause_entropy'],.5)
        shifted=metric.score([9.,11.,-7.,-7.,-7.,-7.])
        self.assertEqual(shifted['entropy_loss'],result['entropy_loss'])

    def test_common_reward_scale_changes_leave_the_metric_unchanged(self):
        from advisors.models.row.validation import Validation
        metadata=pd.DataFrame({'run':[1,1,2,2],'before_seq':[0,0,0,0]})
        first=Validation([-2.,2.],[1.,1.,2.,2.],metadata).score([.5,1.5,1.,3.])
        second=Validation([-20.,20.],[10.,10.,20.,20.],metadata).score([5.,15.,10.,30.])
        for key in ('score','reward_loss','entropy_loss'):
            self.assertAlmostEqual(first[key],second[key])

    def test_outlier_magnitude_does_not_improve_differentiation(self):
        metric=self.metric([0.]*10,[(1,0)]*10)
        outlier=metric.score([0.]*9+[1.])
        huge=metric.score([0.]*9+[1000000.])
        balanced=metric.score([0.]*5+[1.]*5)
        distinct=metric.score(np.arange(10)/10)
        expected=-(.9*np.log(.9)+.1*np.log(.1))/np.log(10)
        self.assertAlmostEqual(outlier['mean_pause_entropy'],expected)
        self.assertEqual(huge['entropy_loss'],outlier['entropy_loss'])
        self.assertLess(balanced['entropy_loss'],outlier['entropy_loss'])
        self.assertAlmostEqual(distinct['entropy_loss'],0.)
        self.assertEqual(outlier['median_pause_entropy'],outlier['mean_pause_entropy'])

    def test_numerical_ties_use_bounded_groups_without_chaining(self):
        metric=self.metric([0.]*3,[(1,0)]*3)
        self.assertEqual(metric.score([0.,.1e-6,.9e-6])['mean_pause_entropy'],0.)
        clustered=metric.score([0.,.75e-6,1.5e-6])
        expected=-((2/3)*np.log(2/3)+(1/3)*np.log(1/3))/np.log(3)
        self.assertAlmostEqual(clustered['mean_pause_entropy'],expected)
        permuted=metric.score([1.5e-6,0.,.75e-6])
        self.assertEqual(clustered['entropy_loss'],permuted['entropy_loss'])

    def test_missing_groups_invalid_predictions_and_constant_training_fail(self):
        from advisors.models.row.validation import Validation
        with self.assertRaises(ValueError):
            self.metric([0.,0.],[(1,0),(2,0)])
        metric=self.metric([0.,0.],[(1,0),(1,0)])
        for predictions in ([0.],[np.nan,0.],[np.inf,0.]):
            with self.assertRaises(ValueError):
                metric.score(predictions)
        with self.assertRaises(ValueError):
            Validation([1.,1.],[0.,0.],pd.DataFrame({'run':[1,1],'before_seq':[0,0]}))

    def test_selection_uses_blend_and_never_selects_incomplete_or_legacy_trials(self):
        from advisors.models.row.validation import winner
        base={'params':{'iterations':50},'iterations':50,'stop':None}
        low_rmse={**base,'trial':0,'rmse':1.,'score':.9}
        balanced={**base,'trial':1,'rmse':1.1,'score':.8}
        unfinished={**base,'trial':2,'rmse':.1,'score':.1,'iterations':49}
        stopped={**base,'trial':3,'rmse':.1,'score':.1,'stop':'time_limit'}
        legacy={**base,'trial':4,'rmse':.01}
        self.assertIs(winner([low_rmse,balanced,unfinished,stopped,legacy]),balanced)
        with self.assertRaises(ValueError):
            winner([unfinished,stopped,legacy])


if __name__=='__main__':
    unittest.main()
