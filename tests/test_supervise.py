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


if __name__=='__main__':
    unittest.main()
