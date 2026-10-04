import math
import unittest
from unittest.mock import Mock, patch

from advisors.data import rewards


class ZeroOutcomeTests(unittest.TestCase):
    def test_opening_pause_collapse_keeps_the_original_baseline(self):
        connection=Mock()
        connection.execute.return_value.fetchall.return_value=[(25,0,100)]
        def series(connection,component,runs):
            return {25:[(0,100),(0,0 if component=='stock' else 100),(50,0 if component=='stock' else 100)]}
        with patch.object(rewards,'series',side_effect=series):
            changes=rewards.outcomes(connection)
        self.assertAlmostEqual(changes[25][1]['stock'],math.log(rewards.MIN_RATIO))
        self.assertTrue(all(math.isfinite(value) for value in changes[25][1].values()))

    def test_opening_pause_changes_affect_the_entire_following_interval(self):
        self.assertAlmostEqual(rewards.growth(0,100,[(0,100),(0,200),(50,100)]),math.log(2)/2)
        self.assertEqual(rewards.mean_log([(0,100),(0,200)],0,100),0)

    def test_collapsed_stock_stays_in_rewards_and_all_breakdown_values_are_finite(self):
        connection=Mock()
        connection.execute.return_value.fetchall.return_value=[(1,0,100),(2,0,100),(3,0,0)]
        def series(connection,component,runs):
            return {1:[(0,100),(50,0 if component=='stock' else 100)],2:[(0,100),(50,150)],3:[(0,100)]}
        with patch.object(rewards,'series',side_effect=series):
            changes=rewards.outcomes(connection)
        self.assertEqual(set(changes),{1,2})
        self.assertAlmostEqual(changes[1][1]['stock'],math.log(rewards.MIN_RATIO)/2)
        objective=({component:.25 for component in rewards.COMPONENTS},.5)
        scores=rewards.combine(changes,objective)
        self.assertTrue(all(math.isfinite(value) for value in scores.values()))
        self.assertLess(scores[1],scores[2])
        for run in changes:
            _,parts=rewards.breakdown(changes,objective,run)
            self.assertTrue(all(math.isfinite(value) for part in parts for value in part.values() if isinstance(value,(int,float))))


if __name__=='__main__':
    unittest.main()
