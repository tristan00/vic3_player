from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import MagicMock, patch

from dashboard.server import runs


class RewardCacheTests(unittest.TestCase):
    def test_rewards_reuse_unchanged_runs_and_refresh_changed_added_and_removed_runs(self):
        pool=MagicMock()
        cursor=pool.connection.return_value.__enter__.return_value.cursor.return_value
        history=cursor.execute.return_value.fetchall
        history.return_value=[(1,0,100,'time'),(2,0,100,'time')]
        with patch.object(runs.db,'POOL',pool),patch.object(runs,'outcomes',side_effect=[{1:'first'}, {1:'changed',3:'added'}, {}]) as calculate:
            first=runs.reward_scores()
            self.assertEqual(first,{1:'first'})
            self.assertEqual(runs.reward_scores(),first)
            calculate.assert_called_once_with(cursor,[1,2])
            history.return_value=[(1,0,100,'defeated'),(2,0,100,'time'),(3,0,200,'time')]
            self.assertEqual(runs.reward_scores(),{1:'changed',3:'added'})
            self.assertEqual(calculate.call_args.args[1],[1,3])
            self.assertEqual(first,{1:'first'})
            history.return_value=[(2,0,100,'time'),(3,0,300,'time')]
            self.assertEqual(runs.reward_scores(),{})
            self.assertEqual(calculate.call_args.args[1],[3])
            self.assertEqual(runs.reward_scores(),{})
            self.assertEqual(calculate.call_count,3)

    def test_simultaneous_pages_share_one_calculation_and_a_new_database_recalculates(self):
        for _ in range(2):
            pool=MagicMock()
            cursor=pool.connection.return_value.__enter__.return_value.cursor.return_value
            cursor.execute.return_value.fetchall.return_value=[(1,0,100,'time')]
            with patch.object(runs.db,'POOL',pool),patch.object(runs,'outcomes',return_value={1:'score'}) as calculate:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    results=list(executor.map(lambda _:runs.reward_scores(),range(4)))
                self.assertEqual(results,[{1:'score'}]*4)
                calculate.assert_called_once_with(cursor,[1])

    def test_failed_refresh_keeps_prior_version_so_it_can_be_retried(self):
        pool=MagicMock()
        cursor=pool.connection.return_value.__enter__.return_value.cursor.return_value
        cursor.execute.return_value.fetchall.return_value=[(1,0,100,'time')]
        with patch.object(runs.db,'POOL',pool),patch.object(runs,'outcomes',side_effect=[RuntimeError('interrupted'),{1:'score'}]) as calculate:
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                runs.reward_scores()
            self.assertEqual(runs.reward_scores(),{1:'score'})
            self.assertEqual(calculate.call_count,2)


if __name__=='__main__':
    unittest.main()
