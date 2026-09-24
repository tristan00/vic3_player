from datetime import datetime, timezone
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface.common import GameCrashed
from interface.runner.memory import Process


def sleeper():
    return subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)


class ProcessTests(unittest.TestCase):
    def test_a_killed_process_is_flagged_within_a_second_with_its_exit_time(self):
        child=sleeper()
        try:
            process=Process(child.pid)
            self.assertFalse(process.exited())
            process.check()
            before=datetime.now(timezone.utc)
            child.kill()
            child.wait()
            started=time.monotonic()
            with self.assertRaises(GameCrashed):
                process.check()
            self.assertLess(time.monotonic()-started,1)
            self.assertTrue(process.exited())
            self.assertTrue(process.exits_within(0))
            self.assertLess(abs((process.exit_time()-before).total_seconds()),1)
        finally:
            child.kill()

    def test_the_watcher_alerts_within_a_second_and_stays_quiet_once_stopped(self):
        child=sleeper()
        alerted=threading.Event()
        try:
            process=Process(child.pid)
            stopped=process.watch(alerted.set)
            child.kill()
            child.wait()
            self.assertTrue(alerted.wait(1))
            stopped.set()
        finally:
            child.kill()
        child=sleeper()
        alerted=threading.Event()
        try:
            stopped=Process(child.pid).watch(alerted.set)
            stopped.set()
            time.sleep(.1)
            child.kill()
            child.wait()
            self.assertFalse(alerted.wait(.3))
        finally:
            child.kill()


if __name__=='__main__':
    unittest.main()
