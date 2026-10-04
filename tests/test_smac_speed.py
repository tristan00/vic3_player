import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor

from advisors.models import forest as smac
from advisors.initializers.smac import RandomSmacWeightingAdvisor


def original(forest,points,best):
    per_tree=np.stack([tree.predict(points) for tree in forest.estimators_])
    mean,spread=per_tree.mean(0),per_tree.std(0)+1e-9
    z=(mean-best)/spread
    return mean,spread,(mean-best)*norm.cdf(z)+spread*norm.pdf(z),norm.cdf(z)


class SmacPredictionTests(unittest.TestCase):
    def test_start_run_uses_and_records_more_than_one_hundred_observations(self):
        advisor=RandomSmacWeightingAdvisor(17)
        X=np.linspace(-2,2,150).reshape(-1,1)
        y=np.arange(150,dtype=float)
        runs=list(range(1,151))
        record={'method':'expected_improvement','best_reward':1.,'predicted_reward':.5}
        with patch('advisors.initializers.smac.history',return_value=(X,y,runs)), patch.object(advisor,'propose',return_value=(np.zeros(1),record)) as propose:
            advisor.start_run(Mock(),['construct_infrastructure'],None)
        np.testing.assert_array_equal(propose.call_args.args[0],X)
        self.assertEqual(len(propose.call_args.args[1]),150)
        self.assertEqual(advisor.proposal['observed'],list(zip(runs,y)))

    @classmethod
    def setUpClass(cls):
        rng=np.random.default_rng(7)
        cls.X=rng.uniform(-2,2,(30,8))
        cls.y=cls.X[:,0]-cls.X[:,1]**2
        cls.forest=RandomForestRegressor(n_estimators=10,random_state=7).fit(cls.X,cls.y)

    def test_prediction_and_uncertainty_are_identical_across_input_layouts(self):
        missing=self.X.copy()
        missing[2,3]=np.nan
        for points in (self.X,self.X.astype(np.float32),np.asfortranarray(self.X),self.X[::2],missing):
            for actual,expected in zip(smac.predict(self.forest,points,1.5),original(self.forest,points,1.5)):
                np.testing.assert_array_equal(actual,expected)

    def test_validation_still_rejects_infinity_and_wrong_dimensions(self):
        for points in (np.full((3,8),np.inf),np.zeros((3,7)),np.zeros(8)):
            with self.subTest(shape=points.shape):
                with self.assertRaises(ValueError):
                    smac.predict(self.forest,points,1.)

    def test_fixed_seed_preserves_the_entire_proposal_and_candidate_ranking(self):
        low,high=np.full(8,-2.),np.full(8,2.)
        actual=RandomSmacWeightingAdvisor(17).propose(self.X,self.y,low,high)
        with patch.object(smac,'predict',original):
            expected=RandomSmacWeightingAdvisor(17).propose(self.X,self.y,low,high)
        np.testing.assert_array_equal(actual[0],expected[0])
        self.assertEqual(actual[1],expected[1])


if __name__=='__main__':
    unittest.main()
