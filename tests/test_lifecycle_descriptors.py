import unittest

import numpy as np

from artifacts.lifecycle_clustering_20261003.extract import describe,mean,sampled


class LifecycleDescriptorsTests(unittest.TestCase):
    def test_same_timestamp_adjustment_retains_opening_and_has_no_time_weight(self):
        t=np.array([0.,0.,1.,2.])
        x=np.array([100.,50.,50.,50.])
        found=describe(t,x,100.)
        self.assertEqual(found['opening_jump'],-.5)
        self.assertEqual(found['mean'],-.5)
        self.assertEqual(found['drawdown'],.5)
        self.assertEqual(found['loss_timing'],0)
        self.assertEqual(found['loss_aftermath'],.5)

    def test_observation_density_does_not_change_time_weighted_descriptors(self):
        a=describe(np.array([0.,0.,1.,2.]),np.array([100.,100.,50.,50.]),100.)
        b=describe(np.array([0.,0.,.1,.2,.3,1.,1.2,2.]),np.array([100.,100.,100.,100.,100.,50.,50.,50.]),100.)
        for key in a:
            self.assertAlmostEqual(a[key],b[key],msg=key)

    def test_recovery_is_distinct_from_a_similar_final_value_without_a_crash(self):
        t=np.array([0.,0.,1.,2.,3.])
        recovered=describe(t,np.array([100.,100.,150.,50.,120.]),100.)
        smooth=describe(t,np.array([100.,100.,105.,110.,120.]),100.)
        self.assertAlmostEqual(recovered['end'],smooth['end'])
        self.assertAlmostEqual(recovered['recovery'],.7)
        self.assertGreater(recovered['drawdown'],.6)
        self.assertEqual(smooth['drawdown'],0)
        self.assertGreater(recovered['quarter_churn'],smooth['quarter_churn'])

    def test_sampling_uses_the_last_measurement_at_a_timestamp_and_does_not_backfill(self):
        values=sampled([(1,10),(1,20),(2,30)],[0,1,1.5,2])
        self.assertTrue(np.isnan(values[0]))
        np.testing.assert_array_equal(values[1:],[20,20,30])

    def test_zero_baselines_are_missing_and_flat_runs_have_no_invented_recovery(self):
        t=np.array([0.,0.,1.])
        self.assertEqual(describe(t,np.zeros(3),0),{})
        found=describe(t,np.ones(3),1.)
        self.assertTrue(all(value==0 for value in found.values()))
        self.assertEqual(mean(t,np.ones(3)),1)


if __name__=='__main__':
    unittest.main()
