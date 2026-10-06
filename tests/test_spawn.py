import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

ROOT=Path(__file__).resolve().parents[1]
PROBE='''import ctypes
from ctypes import wintypes
import json
import multiprocessing
from pathlib import Path
import sys
import time

def record(path):
    kernel=ctypes.WinDLL('kernel32')
    user=ctypes.WinDLL('user32')
    kernel.GetConsoleWindow.restype=wintypes.HWND
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    window=kernel.GetConsoleWindow()
    Path(path).write_text(json.dumps({'window':window,'visible':bool(user.IsWindowVisible(window))}))

if __name__=='__main__':
    folder=Path(sys.argv[1])
    record(folder/'parent.json')
    child=multiprocessing.Process(target=record,args=(folder/'child.json',))
    child.start()
    child.join(5)
    if child.exitcode!=0:
        raise RuntimeError('Child process failed')
    print('background logging works',flush=True)
    until=time.monotonic()+10
    while not (folder/'release').exists() and time.monotonic()<until:
        time.sleep(.02)
'''


class SpawnTests(unittest.TestCase):
    def test_detached_console_and_child_stay_hidden_and_keep_logging_after_launcher_exits(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/"broker's working directory"
            folder.mkdir()
            script=folder/'probe.py'
            script.write_text(PROBE)
            log=folder/'output.log'
            wrapper=folder/'launch.cmd'
            wrapper.write_text(f'@echo off\n"{sys.executable}" "{script}" "{folder}" > "{log}" 2>&1\n')
            command=['cmd.exe','/d','/c',str(wrapper)]
            launcher=f'from interface.runner.session import _spawn; print(_spawn({command!r},{str(folder)!r}).pid)'
            result=subprocess.run([sys.executable,'-c',launcher],cwd=ROOT,capture_output=True,text=True,timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode,0,result.stderr)
            process=psutil.Process(int(result.stdout))
            try:
                until=time.monotonic()+5
                while not (folder/'child.json').exists() and time.monotonic()<until:
                    time.sleep(.02)
                for name in ('parent','child'):
                    self.assertFalse(json.loads((folder/f'{name}.json').read_text())['visible'],name)
                self.assertTrue(process.is_running())
                (folder/'release').touch()
                self.assertEqual(process.wait(5),0)
                self.assertIn('background logging works',log.read_text())
            finally:
                if process.is_running():
                    for child in process.children(recursive=True):
                        child.kill()
                    process.kill()
                    process.wait(5)


if __name__=='__main__':
    unittest.main()
