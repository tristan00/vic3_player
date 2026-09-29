import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from loop import supervise


class SuperviseTests(unittest.TestCase):
    def test_the_next_round_follows_the_highest_numbered_log(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('collect_3.log','collect_12.log','collect_12_extra.log','dashboard.log'):
                (Path(folder)/name).write_text('')
            with mock.patch.object(supervise,'DEFAULT_DATA',Path(folder)):
                self.assertEqual(supervise.next_round(),'collect_13')


class RoleTests(unittest.TestCase):
    def test_processes_are_matched_by_exact_arguments_never_by_text_inside_them(self):
        from loop.watch import role
        self.assertEqual(role('python.exe',['D:/vic3_agent/.venv/Scripts/python.exe','D:/vic3_agent/loop/supervise.py','--runs','5']),'supervisor')
        self.assertEqual(role('cmd.exe',['cmd.exe','/c','D:\\vic3_agent\\loop\\launch.cmd','collect_4','--runs','5']),'round')
        self.assertEqual(role('python.exe',['.venv\\Scripts\\python.exe','-m','loop.run','--runs','5']),'loop')
        self.assertEqual(role('Victoria3.exe',[]),'game')
        self.assertIsNone(role('python.exe',['python.exe','-c','print("-m loop.run loop/launch.cmd")']))
        self.assertIsNone(role('bash.exe',['bash.exe','-c','python -m loop.run']))


class LineupTests(unittest.TestCase):
    def test_warmup_runs_use_random_weights_and_the_first_block_then_the_full_mix(self):
        from types import SimpleNamespace
        from loop.run import lineup
        arguments=SimpleNamespace(warmup=10,advisors=['random','random_svr_weighting'],pickers=['first','catboost'])
        self.assertEqual(lineup(arguments,9),(['random'],['first']))
        self.assertEqual(lineup(arguments,10),(['random','random_svr_weighting'],['first','catboost']))


if __name__=='__main__':
    unittest.main()
