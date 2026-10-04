from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

import numpy as np
import torch

from advisors.models.entity_graph.encoding import Encoder, Survey
from advisors.models.entity_graph.world_data import action_graph
from advisors.models.entity_graph.world import build_world
from advisors.models.entity_graph.metrics import accuracy, differentiation, scale_targets, utility
from advisors.models.entity_graph.model import Configuration, Network, collate
from tests.test_entity_graph_world import world_fixture


class EntityGraphModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def encoded(self):
        data,actions=world_fixture()
        graph=build_world(data)[0]
        delta=action_graph(graph,data,actions)
        survey=Survey()
        survey.add(graph)
        survey.add(delta)
        encoder=Encoder([survey.mapping()])
        return encoder,encoder.graph(graph),encoder.graph(delta)

    def test_graph_network_has_finite_gradients_and_twenty_outputs(self):
        encoder,graph,delta=self.encoded()
        config=Configuration(width=8,layers=2,dropout=0)
        for operator in ('relational_mean','relational_attention','untyped_mean'):
            model=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,replace(config,operator=operator))
            value,memory=model(collate([graph],'cpu'),delta)
            self.assertEqual(tuple(value.shape),(1,5,4))
            value.square().sum().backward()
            self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))

    def test_node_permutation_preserves_forecast(self):
        encoder,graph,delta=self.encoded()
        config=Configuration(width=8,layers=2,dropout=0)
        model=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,config).eval()
        permutation=np.random.default_rng(3).permutation(graph['nodes'])
        reverse=np.argsort(permutation)
        other=dict(graph)
        slices=[slice(graph['offsets'][i],graph['offsets'][i+1]) for i in permutation]
        other['tokens']=np.concatenate([graph['tokens'][s] for s in slices])
        other['values']=np.concatenate([graph['values'][s] for s in slices])
        other['offsets']=np.r_[0,np.cumsum([s.stop-s.start for s in slices])]
        for field in ('kind','current','action','identity'):
            other[field]=graph[field][permutation]
        other['edge_index']=reverse[graph['edge_index']]
        other['player']=int(reverse[graph['player']])
        other['block']=int(reverse[graph['block']])
        changed=dict(delta)
        indices=np.r_[reverse,np.arange(graph['nodes'],graph['nodes']+delta['nodes'])]
        changed['edge_index']=indices[delta['edge_index']]
        first=model(collate([graph],'cpu'),delta)[0].detach().numpy()
        second=model(collate([other],'cpu'),changed)[0].detach().numpy()
        np.testing.assert_allclose(first,second,atol=1e-6,rtol=1e-6)
        memory=model(collate([graph],'cpu'),delta)[1]
        first=model(collate([graph],'cpu'),delta,memory,1)[0].detach().numpy()
        second=model(collate([other],'cpu'),changed,memory,1)[0].detach().numpy()
        np.testing.assert_allclose(first,second,atol=1e-6,rtol=1e-6)

    def test_validation_only_category_does_not_expand_encoder(self):
        encoder,graph,delta=self.encoded()
        count=len(encoder.tokens)
        ids,values=encoder.attributes({'attrs':{'action':'never_seen_in_training'}})
        self.assertEqual(len(encoder.tokens),count)
        self.assertEqual(ids.tolist(),[encoder.tokens[('unknown','action')]])

    def test_masks_exclude_unobserved_future_and_entropy_separates_ties(self):
        y=np.ones((3,5,4))
        y[1]*=2
        y[2]*=3
        mask=np.ones_like(y,dtype=bool)
        mask[:,4]=False
        scale=np.ones((5,4))
        pred=y.copy()
        pred[:,4]=1e6
        score=accuracy(pred,y,mask,scale,1.)
        self.assertEqual(score['sequence_nrmse'],0)
        self.assertIsNone(score['reward_rmse'])
        same=np.zeros((30,5,4))
        distinct=np.arange(30)[:,None,None]*np.ones((30,5,4))
        self.assertEqual(differentiation([same],1.)['mean_pause_entropy'],0)
        self.assertAlmostEqual(differentiation([distinct],1.)['mean_pause_entropy'],1)

    def test_checkpoint_round_trip_keeps_predictions(self):
        encoder,graph,delta=self.encoded()
        config=Configuration(width=8,layers=2,dropout=0)
        model=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,config).eval()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.pt'
            torch.save(model.state_dict(),path)
            restored=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,config).eval()
            restored.load_state_dict(torch.load(path,weights_only=True))
            first=model(collate([graph],'cpu'),delta)[0].detach().numpy()
            second=restored(collate([graph],'cpu'),delta)[0].detach().numpy()
            np.testing.assert_array_equal(first,second)


if __name__=='__main__':
    unittest.main()
