import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface.common import STALL_LIMIT, progress, progress_age, timed
from loop.run import Watchdog
from loop.watch import events


class Game:
    closed=False

    def close(self):
        self.closed=True


class Store:
    run_id=4
    flagged=None

    def flag_stalled(self,step,age):
        self.flagged=(step,age)


class WatchdogTests(unittest.TestCase):
    def test_timed_functions_stamp_progress_on_entry_and_exit(self):
        @timed
        def slow():
            self.assertEqual(progress_age()[0],'slow')
        progress('before')
        slow()
        step,age=progress_age()
        self.assertEqual(step,'slow done')
        self.assertLess(age,1)
        self.assertGreater(STALL_LIMIT,10)

    def test_tripping_flags_the_run_and_closes_the_game(self):
        game,store=Game(),Store()
        watchdog=Watchdog(game)
        watchdog.store=store
        with self.assertLogs('loop',level='CRITICAL') as logged:
            watchdog.trip('validate x',31.5)
        self.assertIn('LOOP STALLED: validate x made no progress for 31.5 s',logged.output[0])
        self.assertEqual(store.flagged,('validate x',31.5))
        self.assertTrue(game.closed)

    def test_tripping_before_the_run_row_exists_only_closes_the_game(self):
        game=Game()
        with self.assertLogs('loop',level='CRITICAL'):
            Watchdog(game).trip('ready',40.0)
        self.assertTrue(game.closed)

    def test_watch_events_keep_failure_lines_and_the_exception_after_a_traceback(self):
        lines=['2026 action 1 build {}\n','Traceback (most recent call last):\n','  File "x", line 1\n','    raise RuntimeError\n',
               'RuntimeError: boom\n','2026 write 0.1s\n','{"end": "time"}\n','ROUND EXITED code=1 at now\n']
        self.assertEqual(events(lines),['Traceback (most recent call last):','RuntimeError: boom','{"end": "time"}','ROUND EXITED code=1 at now'])


if __name__=='__main__':
    unittest.main()
