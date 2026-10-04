import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from loop import supervise


class SuperviseTests(unittest.TestCase):
    def test_default_run_starts_supervision_before_creating_a_game(self):
        from loop import run
        arguments=['--runs','5','--vanilla','--minutes','2']
        with mock.patch.object(supervise,'start') as start,mock.patch.object(run,'GameInterface') as game:
            run.main(arguments)
        start.assert_called_once_with(arguments)
        game.assert_not_called()

    def test_explicit_opt_out_is_the_only_unchecked_worker_path(self):
        from loop import run
        with mock.patch.object(supervise,'start') as start,mock.patch.object(supervise,'owner') as owner, \
             mock.patch.object(run,'GameInterface',side_effect=InterruptedError) as game:
            with self.assertRaises(InterruptedError):
                run.main(['--runs','5','--no-supervisor'])
        start.assert_not_called()
        owner.assert_not_called()
        game.assert_called_once()

    def test_missing_supervisor_prevents_game_start(self):
        from loop import run
        with mock.patch.object(supervise,'owner',side_effect=ProcessLookupError),mock.patch.object(run,'GameInterface') as game:
            with self.assertRaises(ProcessLookupError):
                run.main(['--runs','5','--supervisor','123','1.0'])
        game.assert_not_called()

    def test_supervised_worker_does_not_launch_another_supervisor(self):
        from loop import run
        with mock.patch.object(supervise,'owner') as owner,mock.patch.object(supervise,'start') as start, \
             mock.patch.object(run,'GameInterface'),mock.patch.object(run,'Watchdog') as watchdog:
            run.main(['--runs','0','--supervisor','123','1.0'])
        owner.assert_called_once_with('123','1.0')
        self.assertIs(watchdog.call_args.args[1],owner.return_value)
        start.assert_not_called()

    def test_launcher_uses_the_same_default_entrypoint(self):
        from loop import launch
        with mock.patch.object(sys,'argv',['loop.launch','--runs','5']),mock.patch.object(launch,'run') as run:
            launch.main()
        run.assert_called_once_with(['--runs','5'])

    def test_supervisor_is_launched_detached_with_original_arguments(self):
        with mock.patch.object(supervise,'roles',return_value=[]),mock.patch.object(supervise,'_spawn') as spawn:
            supervise.start(['--runs','5'])
        spawn.assert_called_once_with([sys.executable,'-m','loop.supervise','--runs','5'],str(supervise.ROOT))

    def test_spawn_failure_never_falls_back_to_an_unattended_run(self):
        from loop import run
        with mock.patch.object(supervise,'roles',return_value=[]),mock.patch.object(supervise,'_spawn',side_effect=OSError), \
             mock.patch.object(run,'GameInterface') as game:
            with self.assertRaises(OSError):
                run.main(['--runs','5'])
        game.assert_not_called()

    def test_owner_rejects_pid_reuse_and_non_supervisors(self):
        process=mock.Mock()
        process.create_time.return_value=1.0
        process.name.return_value='python.exe'
        process.cmdline.return_value=['python.exe','-m','loop.supervise']
        with mock.patch.object(supervise.psutil,'Process',return_value=process):
            self.assertIs(supervise.owner('123','1.0'),process)
            with self.assertRaises(RuntimeError):
                supervise.owner('123','2.0')
            process.cmdline.return_value=['python.exe','-m','loop.run']
            with self.assertRaises(RuntimeError):
                supervise.owner('123','1.0')

    def test_round_launch_passes_supervisor_identity(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(supervise,'DEFAULT_DATA',Path(folder)), \
             mock.patch.object(supervise,'_spawn') as spawn,mock.patch.object(supervise.psutil,'Process') as process:
            process.return_value.pid=123
            process.return_value.create_time.return_value=1.0
            supervise.launch(Path(folder)/'supervisor.log',['--runs','5'])
        self.assertEqual(spawn.call_args.args[0][-3:],['--supervisor','123','1.0'])

    def test_supervisor_loss_stops_the_worker(self):
        from loop import run
        supervisor=mock.Mock()
        supervisor.is_running.return_value=False
        watchdog=run.Watchdog(mock.Mock(),supervisor)
        with mock.patch.object(run.time,'sleep'),mock.patch.object(run.os,'_exit',side_effect=SystemExit) as exit:
            with self.assertRaises(SystemExit):
                watchdog.watch()
        watchdog.game.close.assert_called_once()
        exit.assert_called_once_with(run.STALLED_EXIT)

    def test_supervisor_loss_exits_even_if_game_cleanup_fails(self):
        from loop import run
        supervisor=mock.Mock()
        supervisor.is_running.return_value=False
        watchdog=run.Watchdog(mock.Mock(),supervisor)
        watchdog.game.close.side_effect=OSError
        with mock.patch.object(run.time,'sleep'),mock.patch.object(run.os,'_exit',side_effect=SystemExit) as exit:
            with self.assertRaises(SystemExit):
                watchdog.watch()
        exit.assert_called_once_with(run.STALLED_EXIT)

    def test_supervisor_restarts_failed_rounds_and_limits_repeated_failures(self):
        with mock.patch.object(supervise,'running',return_value=[]),mock.patch.object(supervise,'launch') as launch, \
             mock.patch.object(supervise,'note'),mock.patch.object(supervise.time,'sleep'), tempfile.TemporaryDirectory() as folder,mock.patch.object(supervise,'DEFAULT_DATA',Path(folder)):
            supervise.monitor(['--runs','5'])
        self.assertEqual(launch.call_count,supervise.QUICK_EXITS)

    def test_the_next_round_follows_the_highest_numbered_log(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('collect_3.log','collect_12.log','collect_12_extra.log','dashboard.log'):
                (Path(folder)/name).write_text('')
            with mock.patch.object(supervise,'DEFAULT_DATA',Path(folder)):
                self.assertEqual(supervise.next_round(),'collect_13')


class GuardTests(unittest.TestCase):
    def test_opt_out_cannot_be_combined_with_a_supervisor(self):
        from loop import run
        with mock.patch.object(run,'GameInterface') as game,mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                run.main(['--runs','1','--no-supervisor','--supervisor','123','1.0'])
        game.assert_not_called()

    def test_only_one_supervisor_can_monitor_at_a_time(self):
        with tempfile.TemporaryDirectory() as folder,mock.patch.object(supervise,'DEFAULT_DATA',Path(folder)), \
             mock.patch.object(sys,'argv',['loop.supervise','--runs','5']):
            with open(Path(folder)/'supervisor.lock','a+b') as lock:
                supervise.msvcrt.locking(lock.fileno(),supervise.msvcrt.LK_NBLCK,1)
                with mock.patch.object(supervise,'monitor') as monitor,self.assertRaises(OSError):
                    supervise.main()
                monitor.assert_not_called()
            with mock.patch.object(supervise,'monitor') as monitor:
                supervise.main()
            monitor.assert_called_once_with(['--runs','5'])


class RoleTests(unittest.TestCase):
    def test_processes_are_matched_by_exact_arguments_never_by_text_inside_them(self):
        from loop.watch import role
        self.assertEqual(role('python.exe',['D:/vic3_agent/.venv/Scripts/python.exe','D:/vic3_agent/loop/supervise.py','--runs','5']),'supervisor')
        self.assertEqual(role('cmd.exe',['cmd.exe','/c','D:\\vic3_agent\\loop\\launch.cmd','collect_4','--runs','5']),'round')
        self.assertEqual(role('python.exe',['.venv\\Scripts\\python.exe','-m','loop.run','--runs','5']),'loop')
        self.assertEqual(role('python.exe',['python.exe','-m','loop.supervise','--runs','5']),'supervisor')
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
