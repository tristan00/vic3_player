import subprocess
import sys
import unittest
from pathlib import Path

import psutil

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface.runner.guard import watch


class GuardTests(unittest.TestCase):
    def spawn(self):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
        self.addCleanup(child.kill)
        return psutil.Process(child.pid)

    def test_sustained_high_gpu_kills_the_game(self):
        process=self.spawn()
        self.assertTrue(watch(process,lambda:90,limit=50,seconds=.2,interval=.02,log=lambda line:None))
        process.wait(5)
        self.assertFalse(process.is_running())

    def test_short_spikes_do_not_kill_the_game(self):
        process=self.spawn()
        samples=iter([90,90,10]*5)
        def sample():
            use=next(samples,None)
            if use is None:
                process.kill()
                return 0
            return use
        self.assertFalse(watch(process,sample,limit=50,seconds=.1,interval=.02,log=lambda line:None))


if __name__=='__main__':
    unittest.main()
