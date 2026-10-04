import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import torch

from advisors.models.entity_graph.encoding import Encoder, Survey
from advisors.models.entity_graph.experiment import restore
from advisors.models.entity_graph.inference import Forecaster
from advisors.models.entity_graph.model import Configuration, Network
from advisors.models.entity_graph.schema import GRAPH_VERSION
from advisors.models.entity_graph.world import build_world
from advisors.models.entity_graph.world_data import Identities, action_graph, write
from advisors.models.entity_graph.world_experiment import forecasts
from tests.test_entity_graph_world import world_fixture


class RecurrentInferenceTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(13)
        data,self.actions=world_fixture()
        self.cases={seq:{**data,'seq':seq,'history':[seq],'dates':{seq:hour},
                         'states':{seq:copy.deepcopy(data['states'][0 if seq<2 else 2])}}
                    for seq,hour in ((0,0),(1,0),(2,24))}
        self.graphs=[build_world(data)[0] for data in self.cases.values()]
        self.deltas=[action_graph(graph,self.cases[seq],self.actions) for seq,graph in enumerate(self.graphs)]
        survey=Survey()
        for graph in self.graphs+self.deltas:
            survey.add(graph)
        self.encoder=Encoder([survey.mapping()])
        self.model=Network(len(self.encoder.tokens),len(self.encoder.kinds)+1,len(self.encoder.relations)+1,
                           Configuration(width=8,layers=2,dropout=0)).eval()
        self.checkpoint={'graph_version':GRAPH_VERSION,'mean':np.zeros((5,4)).tolist(),'scale':np.ones((5,4)).tolist()}
        with patch('advisors.models.entity_graph.inference.restore',return_value=(self.model,self.checkpoint)),patch('advisors.models.entity_graph.inference.load',return_value=self.encoder):
            self.forecaster=Forecaster('unused','unused','cpu')
        self.reader=Mock()
        self.reader.dates={0:0,1:0,2:24}
        self.reader.actions={0:self.actions,2:[('create_army',{'option':900})]}
        self.reader.read.side_effect=lambda seq:self.cases[seq]

    def test_replayed_live_predictions_match_chronological_offline_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            identities=Identities()
            rows=[]
            for seq,(graph,delta) in enumerate(zip(self.graphs,self.deltas)):
                record={'run':1,'seq':seq,'hour':self.reader.dates[seq],'decision':seq!=1}
                rows.append(record)
                packed=self.encoder.graph(graph)
                packed['identity']=identities.graph(graph)
                write(root/f'1_{seq}.pkl',{'graph_version':GRAPH_VERSION,'record':record,'graph':packed,
                      'proposal':self.encoder.graph(delta) if record['decision'] else None,'deltas':[]})
            (root/'dataset.json').write_text(json.dumps({'frames':rows}))
            expected=forecasts(self.model,root,[r for r in rows if r['decision']],'full_world',np.zeros((5,4)),np.ones((5,4)))[0][-1]
            with patch('advisors.models.entity_graph.inference.WorldReader',return_value=self.reader),patch('advisors.models.entity_graph.inference.baseline',return_value=np.ones(4)),patch.object(self.forecaster,'commit',wraps=self.forecaster.commit) as commit:
                found=self.forecaster.from_snapshot(SimpleNamespace(connection=None,run_id=1,seq=2),[self.actions])
            self.assertEqual([call.args[0] for call in self.reader.read.call_args_list],[0,1,2])
            self.assertEqual(commit.call_count,1)
            self.assertEqual(commit.call_args.args[0],self.actions)
            np.testing.assert_allclose(found['log_ratios'][0],expected,rtol=1e-6,atol=1e-6)
            self.assertTrue(self.forecaster.pending)

    def test_incremental_replay_commits_preceding_action_once(self):
        with patch('advisors.models.entity_graph.inference.WorldReader',return_value=self.reader),patch('advisors.models.entity_graph.inference.baseline',return_value=np.ones(4)),patch.object(self.forecaster,'commit',wraps=self.forecaster.commit) as commit:
            self.forecaster.from_snapshot(SimpleNamespace(connection=None,run_id=1,seq=0),[self.actions])
            found=self.forecaster.from_snapshot(SimpleNamespace(connection=None,run_id=1,seq=2),[self.actions])
            repeated=self.forecaster.from_snapshot(SimpleNamespace(connection=None,run_id=1,seq=2),[self.actions])
        self.assertEqual(commit.call_count,1)
        np.testing.assert_array_equal(found['log_ratios'],repeated['log_ratios'])
        self.forecaster.commit(self.actions)
        with self.assertRaisesRegex(ValueError,'already committed'):
            self.forecaster.commit(self.actions)
        self.forecaster.reset()
        self.assertIsNone(self.forecaster.memory)
        self.assertEqual(self.forecaster.identities.indices,{})

    def test_live_state_requires_commit_and_reset_before_rewind_or_run_change(self):
        with patch('advisors.models.entity_graph.inference.baseline',return_value=np.ones(4)):
            self.forecaster.forecast(self.cases[0],[self.actions])
        with self.assertRaisesRegex(ValueError,'Commit'):
            self.forecaster.observe(self.cases[1])
        self.forecaster.commit(self.actions)
        self.forecaster.observe(self.cases[1])
        with self.assertRaisesRegex(ValueError,'snapshot order'):
            self.forecaster.observe(self.cases[0])
        with self.assertRaisesRegex(ValueError,'changing runs'):
            self.forecaster.observe({**self.cases[2],'run':2})

    def test_obsolete_checkpoints_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old.pt'
            torch.save({'graph_version':GRAPH_VERSION-1},path)
            with self.assertRaisesRegex(ValueError,'obsolete'):
                restore(path,'cpu')


if __name__=='__main__':
    unittest.main()
