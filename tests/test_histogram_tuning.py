import copy
import json
from pathlib import Path
import pickle
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix

from advisors.data.histograms import Histograms
from advisors.models.histogram import data as histogram, tune
from advisors.models.histogram.validation import METRIC, Validation, candidate_pool
from loop import prepare_histogram_tuning as preparation


def dataset():
    data=SimpleNamespace(y=np.array([-3.,-1.,1.,3.,-4.,-2.,2.,4.]),runs=np.repeat(np.arange(4),2),played=4,
                         state=np.zeros((8,len(histogram.STATE)),np.float32),categories=np.full((8,len(histogram.CATEGORIES)),'law',object),
                         sizes=np.array([[index+1] for index in range(8)],np.float32),
                         actions=Histograms([[('action','form_army',index+1)] for index in range(8)]),held=Histograms([[] for _ in range(8)]),
                         pauses=np.array([(run,seq) for run in range(4) for seq in (0,2)]),metric=METRIC.copy(),
                         sampling={'candidates':4,'seed':0},folds=[])
    for train,test in ((np.arange(4),np.arange(4,8)),(np.arange(4,8),np.arange(4))):
        data.folds.append({'train':train,'test':test,'pauses':test[:2],
                           'actions':csr_matrix(np.tile(np.arange(1,5,dtype=np.float32),(2,1)).reshape(-1,1)),
                           'sizes':np.tile(np.array([[1],[2],[3],[4]],np.float32),(2,1))})
    return data


class CandidateEntropyTests(unittest.TestCase):
    def test_blend_is_ten_percent_fold_normalized_rmse_and_ninety_percent_candidate_entropy_loss(self):
        data=dataset()
        metric=Validation(data)
        predictions=data.y+1
        batches=[np.array([[0,0,0,0],[0,1,2,3]],float),np.array([[0,0,1,1],[0,1,2,3]],float)]
        score=metric.score(predictions,batches)
        expected_loss=np.mean([1/np.std(data.y[fold['train']]) for fold in data.folds])
        self.assertEqual(score['rmse'],1)
        self.assertAlmostEqual(score['reward_loss'],expected_loss)
        self.assertAlmostEqual(score['mean_pause_entropy'],.625)
        self.assertAlmostEqual(score['score'],.1*expected_loss+.9*.375)
        self.assertEqual(score['tied_pause_fraction'],.25)

    def test_outlier_magnitude_and_between_pause_offsets_do_not_improve_entropy(self):
        data=dataset()
        metric=Validation(data)
        original=[np.array([[0,0,0,1],[2,2,2,3]],float) for _ in data.folds]
        enlarged=[np.array([[100,100,100,1000000],[-2,-2,-2,1000000]],float) for _ in data.folds]
        self.assertEqual(metric.score(data.y,original),metric.score(data.y,enlarged))
        self.assertEqual(metric.configuration()['constant']['mean_pause_entropy'],0)

    def test_reward_and_entropy_use_only_each_folds_training_scale(self):
        data=dataset()
        data.y[:4]*=1000
        metric=Validation(data)
        tolerance=metric.scales[0]*1e-6
        close=np.array([[0,tolerance*.1,tolerance*.2,tolerance*.3]]*2)
        score=metric.score(data.y,[close,close])
        self.assertAlmostEqual(score['mean_pause_entropy'],.5)
        self.assertEqual(score['reward_loss'],0)

    def test_rejects_leakage_wrong_metric_and_incomplete_or_nonfinite_predictions(self):
        data=dataset()
        for change in ('runs','pauses','metric'):
            bad=copy.deepcopy(data)
            if change=='runs':
                bad.runs[4]=bad.runs[0]
            elif change=='pauses':
                bad.folds[0]['pauses'][0]=0
            else:
                bad.metric={'name':'spread'}
            with self.assertRaises(ValueError):
                Validation(bad)
        metric=Validation(data)
        for batches in ([],[np.full((2,4),np.nan)]*2,[np.zeros((1,4))]*2):
            with self.assertRaises(ValueError):
                metric.score(data.y,batches)

    def test_candidate_encoding_uses_fixed_pause_state_and_fresh_block_actions(self):
        data=dataset()
        data.state[:,0]=np.arange(8)+100
        with patch.object(histogram,'frame',side_effect=lambda state,laws,held,sizes,actions,names:np.hstack([state,held,sizes,actions])):
            rows=candidate_pool(data,data.folds[0],{'action':1})
        np.testing.assert_array_equal(rows[:,0],[104]*4+[105]*4)
        np.testing.assert_array_equal(rows[:,len(histogram.STATE):len(histogram.STATE)+1],data.folds[0]['sizes'])
        np.testing.assert_array_equal(rows[:,len(histogram.STATE)+1],np.tile(np.arange(1,5),2))


class HistogramPreparationTests(unittest.TestCase):
    def test_redraw_is_seeded_at_each_held_out_pause_and_does_not_reuse_recorded_blocks(self):
        connection=object()
        def redraw(found,run,seq,count,seed):
            self.assertIs(found,connection)
            rng=np.random.default_rng(seed)
            return SimpleNamespace(run=run,seq=seq),[[('form_army',{'option':int(rng.integers(1,100))})] for _ in range(count)]
        with patch.object(preparation,'redraw',side_effect=redraw) as draw, patch.object(preparation,'LiveLookup',side_effect=lambda snapshot:snapshot), \
             patch.object(preparation,'entries',side_effect=lambda actions,lookup:[('action','form_army',actions[0][1]['option'])]):
            data=preparation.prepare(connection,dataset(),2,2,4,19)
            calls=draw.call_args_list.copy()
            same=preparation.prepare(connection,dataset(),2,2,4,19)
            other=preparation.prepare(connection,dataset(),2,2,4,20)
        self.assertEqual(len(calls),4)
        for fold,again,changed in zip(data.folds,same.folds,other.folds):
            self.assertTrue(set(fold['pauses'])<=set(fold['test']))
            np.testing.assert_array_equal(fold['actions'].toarray(),again['actions'].toarray())
            np.testing.assert_array_equal(fold['sizes'],[[1]]*8)
            self.assertFalse(np.array_equal(fold['actions'].toarray(),changed['actions'].toarray()))
        expected=[tuple(map(int,data.pauses[row])) for fold in data.folds for row in fold['pauses']]
        self.assertEqual([call.args[1:3] for call in calls],expected)


class HistogramSearchTests(unittest.TestCase):
    def test_both_tuners_share_every_catboost_range_except_tree_count(self):
        from advisors.models.row import tune as row
        self.assertEqual({name:value for name,value in tune.RANGES.items() if name!='iterations'},
                         {name:value for name,value in row.RANGES.items() if name!='iterations'})
        self.assertEqual(tune.RANGES['iterations'],(100,1000))
        self.assertEqual(row.RANGES['iterations'],50)
        self.assertEqual(tune.TRIALS,400)
        bins={'action':32,'other':16}
        low,high,names=tune.space(bins)
        self.assertEqual(names[:len(tune.NAMES)],tune.NAMES)
        self.assertEqual(names[len(tune.NAMES):],['action.included','action.size','other.included','other.size'])
        for point in [low,high,tune.initial(bins),*np.random.default_rng(3).uniform(low,high,(100,len(low)))]:
            params,sizes=tune.decode(point,bins)
            self.assertGreaterEqual(params['iterations'],100)
            self.assertLessEqual(params['iterations'],min(1000,tune.BUDGET//2**params['depth']))
            expected=row.decode(point[1:len(tune.NAMES)])
            self.assertEqual({name:value for name,value in params.items() if name!='iterations'},
                             {name:value for name,value in expected.items() if name!='iterations'})
            self.assertTrue(all(1<=size<=bins[name] for name,size in sizes.items()))

    def test_timed_out_trial_has_no_score_and_passes_the_hard_deadline_to_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            with patch.object(tune.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',30)) as run:
                found=tune.run_trial(0,{'iterations':100},{'action':1},output/'data.pkl',output,30,2)
            self.assertEqual(run.call_args.kwargs['timeout'],30)
            self.assertEqual(found['stop'],'time_limit')
            self.assertNotIn('score',found)

    def test_search_minimizes_the_blend_penalizes_timeouts_and_refuses_old_observations(self):
        data=dataset()
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            source=output/'data.pkl'
            source.write_bytes(pickle.dumps(data))
            points=tune.initial(tune.available(data))
            results=[{'stop':None,'score':.6,'wall_seconds':1},{'stop':'time_limit','wall_seconds':20},
                     {'stop':None,'score':.4,'wall_seconds':1}]
            with patch.object(tune,'run_trial',side_effect=results), patch.object(tune,'propose',return_value=(points,{'method':'expected_improvement'})) as propose:
                selected=tune.search(data,source,output,3)
            self.assertEqual(selected['score'],.4)
            self.assertAlmostEqual(propose.call_args.args[1][0],-.6)
            self.assertAlmostEqual(propose.call_args.args[1][1],-10*Validation(data).configuration()['constant']['score'])
            self.assertTrue(np.isfinite(propose.call_args.args[1]).all())
            self.assertEqual(json.loads((output/'status.json').read_text())['completed_fits'],2)
            with self.assertRaises(FileExistsError):
                tune.search(data,source,output,3)

if __name__=='__main__':
    unittest.main()
