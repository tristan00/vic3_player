from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from advisors.models.histogram import data as pickers
from advisors.data.histograms import Histograms


class TrainingCacheTests(unittest.TestCase):
    def setUp(self):
        self.connection=SimpleNamespace(info=SimpleNamespace(dsn='first'),execute=Mock())
        self.cache=pickers.TrainingCache()

    def test_new_runs_are_loaded_once_and_changed_or_removed_runs_are_not_reused(self):
        with patch.object(pickers,'training_rows',side_effect=lambda connection,runs:{run:[dates] for run,dates in runs.items()}) as load:
            self.assertEqual(self.cache.load(self.connection,{1:(0,10)}),{1:[(0,10)]})
            self.cache.load(self.connection,{1:(0,10),2:(0,20)})
            self.assertEqual(load.call_args.args[1],{2:(0,20)})
            self.cache.load(self.connection,{1:(0,10),2:(0,20)})
            self.assertEqual(load.call_count,2)
            self.assertEqual(self.cache.load(self.connection,{2:(0,30)}),{2:[(0,30)]})
            self.assertEqual(load.call_args.args[1],{2:(0,30)})
            self.assertEqual(self.cache.versions,{2:(0,30)})

    def test_a_different_database_cannot_reuse_run_ids(self):
        with patch.object(pickers,'training_rows',return_value={1:[]}) as load:
            self.cache.load(self.connection,{1:(0,10)})
            self.connection.info.dsn='second'
            self.cache.load(self.connection,{1:(0,10)})
            self.assertEqual(load.call_count,2)

    def test_failed_loading_does_not_mark_new_rows_ready(self):
        with patch.object(pickers,'training_rows',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.cache.load(self.connection,{1:(0,10)})
        self.assertEqual(self.cache.rows,{})
        self.assertEqual(self.cache.versions,{})

    def test_fixed_rewards_and_histograms_keep_all_training_rows(self):
        rows={run:[([float(run)]*len(pickers.STATE),['law']*len(pickers.LAWS),[('action','construct_infrastructure',run)],[],[run],float(run),
                    {name:float(run)**(index+1) for index,name in enumerate(pickers.COMPONENTS)},run*2)] for run in (1,2,3)}
        self.connection.execute.return_value.fetchall.return_value=[(run,0,run*100,'years') for run in rows]
        with patch.object(pickers,'training_rows',return_value=rows) as load:
            first=pickers.training_data(self.connection,self.cache)
            cached=pickers.training_data(self.connection,self.cache)
            self.assertEqual(load.call_count,1)
            fresh=pickers.training_data(self.connection)
        np.testing.assert_array_equal(first.y,cached.y)
        for name in ('state','laws','sizes','runs','y','pauses'):
            np.testing.assert_array_equal(getattr(cached,name),getattr(fresh,name))
        for name in ('actions','held'):
            left,right=getattr(cached,name),getattr(fresh,name)
            self.assertEqual(left.column,right.column)
            np.testing.assert_array_equal(left.counts,right.counts)
        self.assertEqual(cached.played,3)
        np.testing.assert_array_equal(cached.pauses,[[1,2],[2,4],[3,6]])

    def test_catboost_labels_do_not_change_when_unrelated_runs_are_added(self):
        from advisors.data.endgame import reward
        raw={name:.1 for name in pickers.COMPONENTS}
        row=([1.]*len(pickers.STATE),['law']*len(pickers.LAWS),[],[],[1],4.,raw,0)
        extreme=([2.]*len(pickers.STATE),['law']*len(pickers.LAWS),[],[],[1],1.,{name:1000. for name in raw},0)
        self.connection.execute.return_value.fetchall.return_value=[(1,0,100,'years')]
        with patch.object(pickers,'training_rows',return_value={1:[row]}):
            original=pickers.training_data(self.connection)
        self.connection.execute.return_value.fetchall.return_value=[(1,0,100,'years'),(2,0,100,'years')]
        with patch.object(pickers,'training_rows',return_value={1:[row],2:[extreme]}):
            extended=pickers.training_data(self.connection)
        self.assertEqual(original.y[0],reward(4.,raw))
        self.assertEqual(original.y[0],extended.y[0])
        self.assertAlmostEqual(original.y[0],.3)


class SelectedHistogramTests(unittest.TestCase):
    def test_direct_encoding_matches_full_encoding_with_unseen_and_repeated_bins(self):
        histogram=Histograms([[('a','x',1),('a','y',2),('b','x',4)],[('a','x',3),('c','z',5)]])
        offered=[[('a','x',1),('a','x',2),('a','y',7),('c','z',4),('unknown','new',8)],[]]
        for sizes in ({'a':1,'c':2},{'a':9,'b':9},{}):
            np.testing.assert_array_equal(histogram.count(offered,histogram.selected(sizes)),histogram.count(offered)[:,histogram.columns(sizes)])


if __name__=='__main__':
    unittest.main()
