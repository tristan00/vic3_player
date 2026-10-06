from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from loop import run, supervise


class QuarterlyTests(unittest.TestCase):
    def test_calendar_uses_game_month_lengths_and_rolls_over_the_year(self):
        start=(5000+1836)*365*24
        for day,hour,expected in ((0,0,90),(0,18,90),(31,0,90),(59,0,90),(89,18,90),(90,0,181),(180,18,181),(181,0,273),(272,18,273),(273,0,365),(364,18,365),(365,0,455)):
            self.assertEqual(run.next_quarter(start+day*24+hour),start+expected*24)

    def test_quarter_advance_is_never_saved_as_a_pickable_action(self):
        loop=run.Loop.__new__(run.Loop)
        loop.turn=2
        loop.late=[]
        loop.game=Mock()
        reader=loop.game.reader.return_value
        reader.date.side_effect=[(0,'1836.1.1.0'),(2160,'1836.4.1.0')]
        loop.days=Mock(return_value=.02)
        before=SimpleNamespace(seq=1,hours=0)
        after=SimpleNamespace(seq=3,hours=2160)
        loop.snapshot=Mock(return_value=after)
        loop.open_ui=Mock(return_value=[])
        loop.entry=Mock(side_effect=AssertionError('Time advancement is not an action'))
        loop.perform=Mock()
        loop.note=Mock()
        with patch.object(run,'settle'):
            self.assertIs(loop.advance_quarter(before),after)
        loop.perform.assert_called_once_with('loop','unpause',{},before,[],raced='running')
        loop.days.assert_called_once_with(reader,2160)
        loop.entry.assert_not_called()
        loop.note.assert_not_called()

    def test_supervisor_preserves_progress_through_restarts_and_stops_at_total(self):
        with TemporaryDirectory() as folder,patch.object(supervise,'DEFAULT_DATA',Path(folder)),patch.object(supervise,'running',return_value=[]),patch.object(supervise.time,'sleep'):
            completed=[]
            paths=[]
            def launch(log,arguments):
                path=Path(arguments[arguments.index('--progress-file')+1])
                paths.append(path)
                completed.append(supervise.read_progress(path))
                supervise.save_progress(path,completed[-1]+2)
            with patch.object(supervise,'launch',side_effect=launch) as launched:
                supervise.monitor(['--runs','4','--warmup','2'])
            self.assertEqual(completed,[0,2])
            self.assertEqual(launched.call_count,2)
            self.assertEqual(paths[0],paths[1])
            self.assertEqual(supervise.read_progress(paths[-1]),4)
            args=SimpleNamespace(warmup=2,advisors=['random','random_smac_weighting','random_svr_weighting'],pickers=['first','catboost','catboost_piecewise'])
            self.assertEqual(run.lineup(args,completed[0]),(['random'],['first']))
            self.assertEqual(run.lineup(args,completed[1]),(args.advisors,args.pickers))

    def test_removed_duration_is_absent_from_model_schemas(self):
        from advisors.models.row import features
        from advisors.models.entity_graph import schema
        self.assertNotIn('run_days',features.PARAMETERS)
        self.assertNotIn('run_days',schema.PARAMETERS)
        self.assertNotIn('parameter.days.int',features.NUMERIC)

    def test_resuming_a_supervisor_keeps_its_completed_warmup_count(self):
        with TemporaryDirectory() as folder,patch.object(supervise,'DEFAULT_DATA',Path(folder)),patch.object(supervise,'running',return_value=[]),patch.object(supervise.time,'sleep'):
            path=Path(folder)/'progress.json'
            supervise.save_progress(path,40)
            def launch(log,arguments):
                self.assertEqual(arguments.count('--progress-file'),1)
                self.assertEqual(supervise.read_progress(path),40)
                supervise.save_progress(path,240)
            with patch.object(supervise,'launch',side_effect=launch) as launched:
                supervise.monitor(['--runs','240','--warmup','40','--progress-file',str(path)])
            launched.assert_called_once()
            self.assertEqual(supervise.read_progress(path),240)

    def test_histogram_training_keeps_an_action_block_without_a_duration_row(self):
        from advisors.models.histogram import data
        connection=Mock()
        connection.execute.return_value.fetchall.return_value=[(1,0,0,1,'raise_consumption_taxes','goods',None,'grain')]
        lookup=SimpleNamespace(numbers=[1.]*len(data.NUMBERS),prices=[],institutions=[],tariffs=[],taxes=[],laws=[],player=7,country=lambda ident:'rank_major_power')
        with patch.object(data,'Trajectories') as outcomes,patch.object(data,'History') as history,patch.object(data,'Holdings') as holdings:
            outcomes.return_value.reason.return_value=None
            outcomes.return_value.target.return_value=(1.,1.,dict.fromkeys(data.COMPONENTS,1.))
            history.return_value.at.return_value=lookup
            holdings.return_value.at.return_value=[]
            rows=data.training_rows(connection,{1:(0,8760,'years')})
        self.assertEqual(len(rows[1]),1)
        self.assertEqual(rows[1][0][4],[1])
        self.assertIn(('action','raise_consumption_taxes',1),rows[1][0][2])


if __name__=='__main__':
    unittest.main()
