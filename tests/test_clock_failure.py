import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from loop import diagnostics
from loop.run import ClockStalled, Loop


class ClockFailureTests(unittest.TestCase):
    def test_preserves_native_rotations_and_reader_tail_before_the_next_launch_erases_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            profile=root/'profiles'/'actions'
            logs=profile/'logs'
            logs.mkdir(parents=True)
            (logs/'debug.log').write_bytes(b'old'+b'a'*80)
            (logs/'debug.1.log').write_bytes(b'rotated acknowledgement')
            (logs/'error.log').write_bytes(b'game error')
            (logs/'game.log').write_bytes(b'game event')
            (logs/'unrelated.log').write_bytes(b'not needed')
            (profile/'debug_store.log').write_bytes(b'polled acknowledgement')
            game=SimpleNamespace(data_dir=root,profile=profile,session_file=profile/'interface_session.json')
            with patch.object(diagnostics,'TAIL_BYTES',64):
                output=diagnostics.clock_failure(game,173,ClockStalled('date stopped'))
            (logs/'debug.log').write_bytes(b'new launch')
            with ZipFile(output) as archive:
                self.assertEqual(archive.read('logs/debug.log'),b'a'*64)
                self.assertEqual(archive.read('logs/debug.1.log'),b'rotated acknowledgement')
                self.assertEqual(archive.read('debug_store.log'),b'polled acknowledgement')
                self.assertNotIn('logs/unrelated.log',archive.namelist())
                report=json.loads(archive.read('incident.json'))
            self.assertEqual(report['run'],173)
            self.assertEqual(report['error'],'date stopped')
            missing=next(row for row in report['files'] if row['name']=='interface_session.json')
            self.assertIn('error',missing)
            newest=next(row for row in report['files'] if row['name']=='logs/debug.log')
            self.assertEqual((newest['size'],newest['offset'],newest['saved']),(83,19,64))

    def test_capture_failure_preserves_the_original_error_and_normal_supervisor_recovery(self):
        loop=Loop.__new__(Loop)
        failure=ClockStalled('date stopped')
        loop.play=Mock(side_effect=failure)
        loop.game=object()
        loop.store=SimpleNamespace(run_id=173)
        loop.process=SimpleNamespace(gone=lambda:False,exits_within=lambda milliseconds:False)
        loop.end=Mock()
        with patch('loop.run.clock_failure',side_effect=OSError('disk full')) as capture:
            with self.assertLogs('loop',level='ERROR'):
                with self.assertRaises(ClockStalled) as found:
                    loop.run(1,60)
        self.assertIs(found.exception,failure)
        capture.assert_called_once_with(loop.game,173,failure)
        loop.end.assert_called_once_with('loop_crashed','ClockStalled: date stopped')


if __name__=='__main__':
    unittest.main()
