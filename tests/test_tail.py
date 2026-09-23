import os
import tempfile
import unittest
from pathlib import Path

from interface.runner.tail import LogTail


class TailTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.logs=Path(self.folder.name)
        self.tail=LogTail(self.logs,self.logs/'out'/'store.log')

    def tearDown(self):
        self.folder.cleanup()

    def write(self,text,name='debug.log'):
        with open(self.logs/name,'ab') as stream:
            stream.write(text.encode())

    def test_a_rotation_seen_half_done_waits_instead_of_losing_lines(self):
        self.write('a\n')
        self.tail.step()
        self.write('b\n')
        os.replace(self.logs/'debug.log',self.logs/'moving.log')
        self.write('c\n')
        self.tail.step()
        self.assertEqual(self.tail.lost,0)
        os.replace(self.logs/'moving.log',self.logs/'debug.1.log')
        self.tail.step()
        self.assertEqual(bytes(self.tail.buffer),b'a\nb\nc\n')
        self.assertEqual(self.tail.lost,0)


if __name__=='__main__':
    unittest.main()
