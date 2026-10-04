import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from interface.runner import tail as tail_module
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

    def test_appends_need_one_read_and_do_not_depend_on_cached_file_size(self):
        self.write('a\n')
        self.tail.step()
        files=self.tail.files()
        self.write('b\n')
        with mock.patch.object(self.tail,'files',return_value=files),mock.patch.object(tail_module,'shared_read',wraps=tail_module.shared_read) as read:
            self.tail.step()
            self.assertEqual(read.call_count,1)
            self.write('c\n')
            self.tail.step()
            self.assertEqual(read.call_count,2)
        self.assertEqual(bytes(self.tail.buffer),b'a\nb\nc\n')
        self.assertEqual(self.tail.lost,0)


if __name__=='__main__':
    unittest.main()
