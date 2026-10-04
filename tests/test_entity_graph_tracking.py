import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from advisors.models.entity_graph.model import Configuration
from advisors.models.entity_graph.schema import GRAPH_VERSION
from advisors.models.entity_graph.tracking import FitTracker, RunTracker
from advisors.models.entity_graph.world_experiment import fit, run
from dashboard.server import graph_tuning


class GraphTrackingTests(unittest.TestCase):
    def test_live_progress_uses_runner_files_and_finished_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            output=root/'entity_graph_test'/'world_experiments'
            with patch('advisors.models.entity_graph.tracking.REGISTRY',root/'entity_graph_tracking'),patch.object(graph_tuning,'ROOT',root):
                tracker=RunTracker(output,root/'packed',Configuration(),('full_world',))
                live=FitTracker(output/'full_world','full_world',Configuration())
                live.update(phase='training',epoch=2,done=3,total=12)
                state=graph_tuning.results()
                self.assertEqual(len(state.runs),1)
                self.assertEqual((state.runs[0].state,state.runs[0].completed,state.runs[0].requested),('running',0,1))
                self.assertEqual((state.runs[0].trials[0].epoch,state.runs[0].trials[0].done),(2,3))
                result={'graph_version':GRAPH_VERSION,'configuration':Configuration().mapping(),'epochs':[],
                        'validation':{'score':.2,'sequence_nrmse':.4},'test':{'score':.3},'best_epoch':2,'seconds':10}
                (output/'full_world'/'result.json').write_text(json.dumps(result))
                live.update(state='complete',phase='fitted')
                tracker.update(state='complete',phase='complete')
                completed=graph_tuning.results().runs[0]
                self.assertEqual(completed.completed,1)
                self.assertEqual(completed.selected,'full_world')
                self.assertEqual(completed.trials[0].validation.score,.2)
                self.assertEqual(completed.trials[0].test.score,.3)

    def test_reused_process_id_is_interrupted_and_earlier_graph_stays_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            output=root/'entity_graph_old'/'world_experiments'
            (output/'full_world').mkdir(parents=True)
            old={'configuration':{'epochs':24},'epochs':[],'validation':{'score':.1},'test':{'score':.2},'seconds':10}
            (output/'full_world'/'result.json').write_text(json.dumps(old))
            with patch('advisors.models.entity_graph.tracking.REGISTRY',root/'entity_graph_tracking'),patch.object(graph_tuning,'ROOT',root):
                tracker=RunTracker(root/'new',root/'packed',Configuration(),('full_world',))
                tracker.update(process_created=0)
                state=graph_tuning.results()
                current=next(row for row in state.runs if row.graph_version==GRAPH_VERSION)
                historical=next(row for row in state.runs if row.graph_version==1)
                self.assertEqual(current.state,'interrupted')
                self.assertEqual(current.completed,0)
                self.assertEqual(historical.state,'complete')
                self.assertEqual(historical.completed,1)

    def test_fit_reports_failure_and_propagates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            with patch('advisors.models.entity_graph.world_experiment.fit_model',side_effect=ValueError('test failure')):
                with self.assertRaisesRegex(ValueError,'test failure'):
                    fit(output,output,'full_world',Configuration(),{})
            status=json.loads((output/'status.json').read_text())
            self.assertEqual(status['state'],'failed')
            self.assertEqual(status['error'],'test failure')

    def test_runner_publishes_completion_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('advisors.models.entity_graph.tracking.REGISTRY',root/'registry'):
                with patch('advisors.models.entity_graph.world_experiment.experiment'):
                    run(root/'packed',root/'complete',24)
                self.assertEqual(json.loads((root/'complete'/'tracking.json').read_text())['state'],'complete')
                with patch('advisors.models.entity_graph.world_experiment.experiment',side_effect=ValueError('test failure')):
                    with self.assertRaisesRegex(ValueError,'test failure'):
                        run(root/'packed',root/'failed',24)
                self.assertEqual(json.loads((root/'failed'/'tracking.json').read_text())['state'],'failed')


if __name__=='__main__':
    unittest.main()
