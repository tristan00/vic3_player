import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interface.common import slot
from interface.runner import GameInterface
from interface.runner import tail as tail_module


def block(stamp, date, extra='', nonce=7):
    return (f'[{stamp}][x.cpp:1]: events/interface_capture.txt:3: INTERFACE|tick|begin|{date}|{nonce}\n'
            f'{extra}'
            f'[{stamp}][x.cpp:1]: events/interface_capture.txt:9: INTERFACE|tick|end|{date}\n')


class LogFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / 'logs').mkdir()
        self.game = GameInterface.__new__(GameInterface)
        self.game.profile = self.root
        self.game.since = ''
        self.game._running = lambda: None

    def tearDown(self):
        if 'tail' in self.game.__dict__:
            self.game.tail.close()

    def write(self, name, text):
        (self.root / 'logs' / name).write_bytes(text.encode('utf-8'))
        time.sleep(0.01)

    def rotate(self):
        logs = self.root / 'logs'
        for index in range(4, 0, -1):
            if (logs / f'debug.{index}.log').exists():
                (logs / f'debug.{index}.log').replace(logs / f'debug.{index + 1}.log')
        (logs / 'debug.1.log').write_bytes((logs / 'debug.log').read_bytes())
        with open(logs / 'debug.log', 'r+b') as handle:
            handle.truncate(0)
        time.sleep(0.01)

    def append(self, name, text):
        with open(self.root / 'logs' / name, 'ab') as handle:
            handle.write(text.encode('utf-8'))
        time.sleep(0.01)


class TailTests(LogFixture):
    def test_the_tail_follows_a_rotation_without_duplicating(self):
        self.write('debug.log', block('01:00:00', 'first', nonce=1))
        self.game.log()
        self.game.tail.close()
        self.append('debug.log', block('01:00:01', 'second', nonce=2))
        self.rotate()
        self.append('debug.log', block('01:00:02', 'third', nonce=3))
        text = self.game.log()
        self.assertEqual([text.count(name) for name in ('first', 'second', 'third')], [2, 2, 2])
        self.assertLess(text.index('second'), text.index('third'))
        self.assertEqual((self.root / 'debug_store.log').read_text(encoding='utf-8'), text)
        self.assertEqual(self.game.tail.lost, 0)

    def test_a_rotation_whose_copy_is_gone_is_counted_lost(self):
        self.write('debug.log', block('01:00:00', 'first', nonce=1))
        self.game.log()
        self.game.tail.close()
        (self.root / 'logs' / 'debug.log').write_bytes(b'')
        self.append('debug.log', block('01:00:02', 'third', nonce=3))
        self.game.tail.step()
        self.assertEqual(self.game.tail.lost, 0)
        with mock.patch.object(tail_module, 'SETTLE', 0):
            self.game.tail.step()
        self.assertEqual(self.game.tail.lost, 1)

    def test_a_refused_console_command_after_launch_fails_the_wait(self):
        self.game.since = '01:00:00'
        self.write('debug.log', "[00:59:59][console.cpp:1]: You can't add new commands while the console is still running commands.\n")
        self.game.log()
        self.assertIsNone(self.game.tail.fatal)
        self.append('debug.log', "[01:00:02][console.cpp:1]: You can't add new commands while the console is still running commands.\n")
        with self.assertRaises(RuntimeError) as caught:
            self.game.check(30)
        self.assertIn('refused a command', str(caught.exception))

    def test_a_silent_log_fails_the_wait(self):
        self.write('debug.log', block('01:00:00', 'first', nonce=1))
        self.game.log()
        self.game._running = lambda: None
        self.game.tail.grown -= 31
        with self.assertRaises(RuntimeError) as caught:
            self.game.check(30)
        self.assertIn('has not grown', str(caught.exception))


class SlotTests(unittest.TestCase):
    def test_runtime_identity_is_masked_to_the_slot(self):
        self.assertEqual(slot(0x4000007), 7)

    def test_sentinel_stays_negative(self):
        self.assertEqual(slot(-1), -1)


if __name__ == '__main__':
    unittest.main()
