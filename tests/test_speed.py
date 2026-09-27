from datetime import datetime, timezone
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from interface.actions import execute
from interface.options.stored import Shared, Stored, Vocabulary
from interface.recording.spec import TABLE
from interface.recording.tables import ordered
from interface.runner.memory import Reader
from interface.runner.tail import LogTail
from interface.timing import RECORDER
from tests import test_store
from tests.test_store import LAW, PLAYER, STEPS, built


class OrderedTests(unittest.TestCase):
    def test_rows_come_out_in_column_order_with_missing_columns_empty(self):
        table=TABLE['law_history']
        names=[table.owner,*[column.name for column in table.keys],*[column.name for column in table.columns]]
        whole={name:position for position,name in enumerate(names)}
        partial={name:position for position,name in enumerate(reversed(names[:-1]))}
        self.assertEqual(ordered(table,[whole,partial,dict(reversed(whole.items()))]),
                         [tuple(range(len(names))),tuple(partial.get(name) for name in names),tuple(range(len(names)))])

    def test_an_unknown_column_is_refused(self):
        with self.assertRaisesRegex(RuntimeError,'unknown columns'):
            ordered(TABLE['law_history'],[{'nowhere':1}])


class TokenTests(unittest.TestCase):
    def test_a_known_token_is_named_without_reading_the_game(self):
        reader=Reader.__new__(Reader)
        reader.keys={('token',7):2}
        reader.names=[('token','first'),('token','second')]
        reader.tokens=mock.Mock(return_value=[1])
        self.assertEqual(reader.token(7|1<<40),'second')
        reader.tokens.assert_not_called()
        self.assertEqual(reader.item(3,9),('flag','first'))
        reader.tokens.assert_called_once()


class MarkTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.logs=Path(self.folder.name)
        self.tail=LogTail(self.logs,self.logs/'out'/'store.log')
        self.tail.thread=False

    def tearDown(self):
        self.folder.cleanup()

    def write(self,text):
        with open(self.logs/'debug.log','ab') as stream:
            stream.write(text.encode())

    def test_text_after_a_mark_holds_only_what_the_log_gained_since(self):
        self.write('old 1\n')
        mark=self.tail.mark()
        self.assertEqual(self.tail.after(mark),'')
        self.write('new 1\n')
        self.assertEqual(self.tail.after(mark),'new 1\n')
        self.assertEqual(self.tail.text(),'old 1\nnew 1\n')
        self.assertEqual(self.tail.after(self.tail.mark()),'')


class AnswerTests(unittest.TestCase):
    def executor(self,**texts):
        game=SimpleNamespace(log_since=mock.Mock(**texts))
        found=execute.Executor.__new__(execute.Executor)
        found.game=game
        return found

    def test_the_answer_is_the_first_text_that_holds_the_token(self):
        executor=self.executor(side_effect=['','other|1|','INTERFACE|action|5|1|'])
        reader=mock.Mock()
        with mock.patch.object(execute,'POLL',0):
            self.assertEqual(executor.answer(reader,3,'INTERFACE|action|5|',execute.time.monotonic()),'INTERFACE|action|5|1|')
        self.assertEqual(executor.game.log_since.call_args_list,[mock.call(3)]*3)
        self.assertEqual(reader.check.call_count,3)

    def test_no_answer_within_the_limit_gives_nothing(self):
        executor=self.executor(return_value='')
        with mock.patch.object(execute,'POLL',0),mock.patch.object(execute,'LIMIT',.01):
            self.assertIsNone(executor.answer(mock.Mock(),3,'INTERFACE|action|5|',execute.time.monotonic()))


class SharedTests(test_store.StoreTests):
    def setUp(self):
        super().setUp()
        for step in STEPS:
            self.store.write(built(step),'post_action',datetime(2026,9,23,tzinfo=timezone.utc),1.0)
        self.shared=Shared(self.store.connection)
        self.addCleanup(self.shared.close)

    def test_tables_loaded_together_equal_tables_read_one_by_one(self):
        first=Stored(self.store.connection,self.store.run_id,1,self.shared)
        wanted=('law','state','player_treasury')
        alone={name:first.table(name) for name in wanted}
        self.assertEqual(len(self.shared.wanted),len(wanted))
        again=Stored(self.store.connection,self.store.run_id,1,self.shared)
        RECORDER.reset()
        again.load()
        self.assertEqual({name:again.table(name) for name in wanted},alone)
        spans={row[0]:row[1] for row in RECORDER.totals()}
        self.assertEqual(spans['interface.options.stored.Shared.fetch'],len(wanted))
        self.assertNotIn('interface.options.stored.Stored.read',spans)
        self.assertEqual(again.rows('law','law,law_type',country=PLAYER),[(LAW,'law_one'),(LAW+1,'law_two')])

    def test_ruleset_data_is_read_once_for_all_snapshots_of_a_run(self):
        first=Stored(self.store.connection,self.store.run_id,0,self.shared)
        kept=first.order('common/laws'),first.definitions('common/laws')
        RECORDER.reset()
        later=Stored(self.store.connection,self.store.run_id,2,self.shared)
        self.assertIs(later.order('common/laws'),kept[0])
        self.assertIs(later.definitions('common/laws'),kept[1])
        self.assertEqual([row[0] for row in RECORDER.totals() if 'lambda' in row[0] or 'read_definitions' in row[0]],[])

    def test_a_name_added_after_the_first_read_is_found(self):
        words=Vocabulary(self.store.connection,'advisor')
        later=f'later {time.time_ns()}'
        code=self.store.names('advisor',[later])[0]
        self.assertNotIn(code,dict.keys(words))
        self.assertEqual(words[code],later)
        with self.assertRaises(KeyError):
            words[-1]


for inherited in [name for name in dir(test_store.StoreTests) if name.startswith('test_')]:
    setattr(SharedTests,inherited,None)


if __name__=='__main__':
    unittest.main()
