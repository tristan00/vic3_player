import logging
import pickle
import random
import threading
import time
import unittest

from interface.timing import COLUMNS, RECORDER, TRACE, Recorder, Stats, current, span, timer

timed=timer('timing_test')


def recorded(name):
    return next(dict(zip(COLUMNS,row)) for row in RECORDER.totals() if row[0]==name)


@timed
def inner():
    time.sleep(.005)


@timed
def outer():
    inner()
    inner()


@timed
def failing():
    raise KeyError('gone')


@timed
def threaded():
    worker=threading.Thread(target=inner)
    worker.start()
    worker.join()


class TimingTests(unittest.TestCase):
    def test_quantiles_stay_within_one_bucket_of_the_exact_value_and_in_order(self):
        rng=random.Random(7)
        values=sorted(int(rng.lognormvariate(14,2))+1 for _ in range(5000))
        stats=Stats()
        for value in values:
            stats.add(value,value,False)
        found=[stats.quantile(share) for share in (.5,.95,.99)]
        for share,got in zip((.5,.95,.99),found):
            exact=values[int(share*len(values))-1]
            self.assertLessEqual(exact,got)
            self.assertLess(got,exact*1.1)
        self.assertEqual((stats.low,stats.high),(values[0],values[-1]))
        self.assertEqual(found,sorted(found))
        self.assertLessEqual(found[-1],stats.high)

    def test_a_single_call_reports_its_own_duration_at_every_quantile(self):
        stats=Stats()
        stats.add(1234567,1234567,False)
        self.assertEqual({stats.quantile(share) for share in (.5,.95,.99)},{1234567})

    def test_self_time_excludes_the_spans_opened_inside(self):
        RECORDER.reset()
        outer()
        parent,child=recorded('tests.test_timing.outer'),recorded('tests.test_timing.inner')
        self.assertEqual((parent['calls'],child['calls']),(1,2))
        self.assertGreaterEqual(child['total_ms'],8)
        self.assertGreaterEqual(parent['total_ms'],child['total_ms'])
        self.assertAlmostEqual(parent['self_ms'],parent['total_ms']-child['total_ms'],places=6)
        self.assertLess(parent['self_ms'],child['total_ms'])
        self.assertAlmostEqual(child['self_ms'],child['total_ms'],places=6)

    def test_a_span_in_another_thread_leaves_the_waiting_span_its_whole_time(self):
        RECORDER.reset()
        threaded()
        waiting=recorded('tests.test_timing.threaded')
        self.assertGreaterEqual(waiting['self_ms'],4)
        self.assertAlmostEqual(waiting['self_ms'],waiting['total_ms'],places=6)
        self.assertEqual(recorded('tests.test_timing.inner')['calls'],1)

    def test_a_raising_call_is_counted_as_an_error_logged_and_raised(self):
        RECORDER.reset()
        with self.assertLogs('timing_test',level='INFO') as logged,self.assertRaises(KeyError):
            failing()
        self.assertEqual((recorded('tests.test_timing.failing')['calls'],recorded('tests.test_timing.failing')['errors']),(1,1))
        self.assertRegex(logged.output[0],r'tests\.test_timing\.failing FAILED KeyError \d+\.\dms$')

    def test_a_returning_call_logs_its_full_name_and_milliseconds(self):
        with self.assertLogs('timing_test',level='INFO') as logged:
            inner()
        self.assertRegex(logged.output[0],r'tests\.test_timing\.inner \d+\.\dms$')

    def test_generators_and_coroutines_are_refused(self):
        def generator():
            yield 1

        async def coroutine():
            return 1
        for function in (generator,coroutine):
            with self.assertRaises(TypeError):
                timed(function)

    def test_the_stamp_is_called_on_entry_and_exit_even_when_the_call_raises(self):
        stamps=[]

        def broken():
            stamps.append('inside')
            raise ValueError
        with self.assertRaises(ValueError):
            timer('timing_test',stamps.append)(broken)()
        self.assertEqual([stamp.rpartition('.')[2] for stamp in stamps],['broken','inside','broken done'])

    def test_a_trace_collects_every_span_closed_in_its_context(self):
        trace=[]
        token=TRACE.set(trace)
        try:
            outer()
        finally:
            TRACE.reset(token)
        outer()
        self.assertEqual([name for name,_ in trace],['tests.test_timing.inner','tests.test_timing.inner','tests.test_timing.outer'])

    def test_a_block_is_timed_under_its_given_name_and_reports_its_seconds(self):
        RECORDER.reset()
        with span('block',log='timing_test') as timing:
            time.sleep(.005)
        self.assertGreaterEqual(timing.seconds,.004)
        self.assertAlmostEqual(recorded('block')['total_ms'],timing.seconds*1000,places=6)

    def test_draining_empties_the_interval_and_keeps_the_whole(self):
        recorder=Recorder()
        recorder.add('a',2_000_000,1_000_000,False)
        recorder.add('a',4_000_000,4_000_000,True)
        recorder.add('b',1_000_000,1_000_000,False)
        self.assertEqual(recorder.drain(),[('a',2,1,6.0,5.0,4.0),('b',1,0,1.0,1.0,1.0)])
        recorder.add('b',3_000_000,3_000_000,False)
        self.assertEqual(recorder.drain(),[('b',1,0,3.0,3.0,3.0)])
        self.assertEqual(recorder.drain(),[])
        self.assertEqual([row[:7] for row in recorder.totals()],[('a',2,1,6.0,5.0,2.0,4.0),('b',2,0,4.0,4.0,1.0,3.0)])

    def test_spans_taken_in_another_process_merge_into_the_whole_and_the_interval(self):
        apart=Recorder()
        apart.add('shared',2_000_000,2_000_000,False)
        apart.add('shared',8_000_000,6_000_000,True)
        apart.add('theirs',1_000_000,1_000_000,False)
        taken=pickle.loads(pickle.dumps(apart.take()))
        self.assertEqual(apart.take(),{})
        recorder=Recorder()
        recorder.add('shared',4_000_000,4_000_000,False)
        recorder.merge(taken)
        self.assertEqual([row[:7] for row in recorder.totals()],[('shared',3,1,14.0,12.0,2.0,8.0),('theirs',1,0,1.0,1.0,1.0,1.0)])
        median,*upper=recorder.totals()[0][7:]
        self.assertTrue(4<=median<4.4)
        self.assertEqual(upper,[8.0,8.0])
        self.assertEqual(recorder.drain(),[('shared',3,1,14.0,12.0,8.0),('theirs',1,0,1.0,1.0,1.0)])

    def test_the_open_span_reports_the_time_elapsed_so_far(self):
        readings=[]

        @timed
        def measured():
            readings.append(current().ms)
            time.sleep(.005)
            readings.append(current().ms)
            return current()
        done=measured()
        self.assertIsNone(current())
        self.assertLess(readings[0],readings[1])
        self.assertGreaterEqual(readings[1],4)
        self.assertGreaterEqual(done.ms,readings[1])
        self.assertEqual(done.ms,done.ms)

    def test_a_frequent_call_is_recorded_and_logged_only_at_debug(self):
        RECORDER.reset()
        often=timer('timing_test',level=logging.DEBUG)(lambda:None)
        with self.assertNoLogs('timing_test',level='INFO'):
            often()
        with self.assertLogs('timing_test',level='DEBUG'):
            often()
        self.assertEqual(recorded('tests.test_timing.TimingTests.test_a_frequent_call_is_recorded_and_logged_only_at_debug.<locals>.<lambda>')['calls'],2)

    def test_concurrent_calls_are_all_counted(self):
        recorder=Recorder()

        def work():
            for _ in range(2000):
                recorder.add('shared',1000,1000,False)
        workers=[threading.Thread(target=work) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(recorder.totals()[0][1:4],(16000,0,16.0))


if __name__=='__main__':
    unittest.main()
