import copy
import unittest
from unittest.mock import Mock, patch

import numpy as np
import torch

from advisors.models.entity_graph.encoding import Encoder, Survey
from advisors.models.entity_graph.model import Configuration, Network, collate
from advisors.models.entity_graph.source import blocks
from advisors.models.entity_graph.world import build_world
from advisors.models.entity_graph.world_data import Identities, action_graph
from advisors.models.entity_graph.world_experiment import sequences, train_epoch
from tests.test_entity_graph_world import world_fixture


class ActionHistoryTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(41)
        self.data,self.actions=world_fixture()
        self.raw,self.audit=build_world(self.data)
        self.alternative=[('create_army',{'option':90})]
        deltas=[action_graph(self.raw,self.data,actions) for actions in (self.actions,self.alternative)]
        survey=Survey()
        for graph in (self.raw,*deltas):
            survey.add(graph)
        self.encoder=Encoder([survey.mapping()])
        self.graph=self.encoder.graph(self.raw)
        self.deltas=[self.encoder.graph(graph) for graph in deltas]
        self.model=Network(len(self.encoder.tokens),len(self.encoder.kinds)+1,len(self.encoder.relations)+1,
                           Configuration(width=8,layers=2,dropout=0,sequence_length=2)).eval()
        self.batch=collate([self.graph],'cpu')

    def test_recorded_blocks_use_decision_cutoff_without_outcome_filters(self):
        connection=Mock()
        connection.execute.return_value.fetchall.return_value=[
            (1,8,'build_monument','building_type',None,'building_eiffel_tower'),
            (1,8,'build_monument','state',11,None),
            (1,9,'create_army','option',30,None)]
        self.assertEqual(blocks(connection,7,1,2),{1:[['build_monument',{'building_type':'building_eiffel_tower','state':11}],['create_army',{'option':30}]]})
        sql,args=connection.execute.call_args.args
        self.assertEqual(args,[7,1,2])
        self.assertIn('la.before_seq>=%s',sql)
        self.assertIn('la.before_seq<%s',sql)
        for forbidden in ('status','after_seq','logged_at','valid','detail'):
            self.assertNotIn(forbidden,sql)

    def test_graph_contains_only_current_world_without_temporal_edges(self):
        self.assertEqual({node['seq'] for node in self.raw.nodes},{self.data['seq']})
        self.assertFalse(any(relation.startswith('temporal.') for a,b,relation,w in self.raw.edges))
        self.assertFalse(any('action' in node['kind'] for node in self.raw.nodes))
        other=copy.deepcopy(self.data)
        other['action_history']={0:self.actions,2:self.alternative,99:self.actions}
        self.assertEqual(build_world(other)[0],self.raw)

    def test_candidates_are_read_only_and_order_independent(self):
        observation=self.model.observe(self.batch,None,24)
        original=observation.memory.nodes.detach().clone()
        first=self.model.propose(observation,self.deltas[0])
        other=self.model.propose(observation,self.deltas[1])
        repeated=self.model.propose(observation,self.deltas[0])
        torch.testing.assert_close(first.prediction,repeated.prediction,rtol=0,atol=0)
        torch.testing.assert_close(observation.memory.nodes,original,rtol=0,atol=0)
        self.assertGreater(float((first.prediction-other.prediction).abs().max().detach()),1e-7)
        committed=self.model.commit(observation,first)
        self.assertGreater(float((committed.global_state-observation.memory.global_state).abs().max().detach()),1e-7)
        torch.testing.assert_close(observation.memory.nodes,original,rtol=0,atol=0)

    def test_prior_actions_and_same_time_observations_reach_later_forecasts(self):
        first=self.model.observe(self.batch,None,24)
        histories=[self.model.commit(first,self.model.propose(first,delta)) for delta in self.deltas]
        histories[0].nodes.retain_grad()
        outputs=[self.model(self.batch,self.deltas[0],memory,24)[0] for memory in histories]
        cold=self.model(self.batch,self.deltas[0],None,24)[0]
        self.assertGreater(float((outputs[0]-outputs[1]).abs().max().detach()),1e-7)
        self.assertGreater(float((outputs[0]-cold).abs().max().detach()),1e-7)
        outputs[0].square().sum().backward()
        self.assertGreater(float(histories[0].nodes.grad.abs().sum()),0)
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in self.model.parameters() if p.grad is not None))
        detached=histories[0].detach()
        torch.testing.assert_close(detached.nodes,histories[0].nodes)
        self.assertIsNone(detached.nodes.grad_fn)
        self.assertIsNone(detached.global_state.grad_fn)
        with self.assertRaisesRegex(ValueError,'game time'):
            self.model.observe(self.batch,detached,23)

    def test_entity_identity_survives_reordering_absence_and_new_entities(self):
        identities=Identities()
        original=identities.graph(self.raw)
        changed=copy.deepcopy(self.raw)
        changed.nodes=changed.nodes[::-1]
        np.testing.assert_array_equal(identities.graph(changed),original[::-1])
        old=changed.nodes.pop()
        changed.nodes.append({**old,'key':'new_entity'})
        next_ids=identities.graph(changed)
        self.assertGreater(int(next_ids[-1]),int(original.max()))
        np.testing.assert_array_equal(identities.graph(self.raw),original)

    def test_sequence_training_keeps_unlabelled_decisions_and_intervening_frames(self):
        records=[{'run':1,'seq':i,'hour':i//2,'decision':i!=1,'y':np.zeros((5,4)),
                  'mask':np.full((5,4),i>=2,dtype=bool)} for i in range(5)]
        frames=[{'record':r,'graph':self.graph,'proposal':self.deltas[0] if r['decision'] else None} for r in records]
        optimizer=torch.optim.AdamW(self.model.parameters(),lr=.001)
        progress=Mock()
        before=self.model.head[0].weight.detach().clone()
        with patch('advisors.models.entity_graph.world_experiment.stream',return_value=iter(frames)),patch.object(self.model,'observe',wraps=self.model.observe) as observe,patch.object(optimizer,'step',wraps=optimizer.step) as step:
            loss=train_epoch(self.model,optimizer,None,[records],np.zeros((5,4)),np.ones((5,4)),progress)
        self.assertTrue(np.isfinite(loss))
        self.assertEqual(observe.call_count,5)
        self.assertEqual(step.call_count,2)
        self.assertEqual(progress.advance.call_count,4)
        self.assertIsNone(observe.call_args_list[0].args[1])
        self.assertFalse(torch.equal(before,self.model.head[0].weight))
        manifest={'frames':records}
        decisions=[r for r in records if r['decision']]
        self.assertEqual(sequences(manifest,decisions),[records])
        with self.assertRaisesRegex(ValueError,'every decision'):
            sequences(manifest,decisions[1:])

    def test_memory_grows_for_new_identities_and_retains_absent_entities(self):
        first=self.model.observe(self.batch,None,24)
        changed={**self.batch,'identity':self.batch['identity'].clone()}
        count=len(first.nodes)
        changed['identity'][0]=count
        following=self.model.observe(changed,first.memory,48)
        self.assertEqual(len(following.memory.nodes),count+1)
        torch.testing.assert_close(following.memory.nodes[0],first.memory.nodes[0],rtol=0,atol=0)
        self.assertGreater(float(following.memory.nodes[count].abs().sum().detach()),0)
        restored=self.model.observe(self.batch,following.memory,72)
        self.assertEqual(len(restored.memory.nodes),count+1)
        self.assertTrue(torch.isfinite(restored.memory.nodes).all())


if __name__=='__main__':
    unittest.main()
