import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from advisors.models.entity_graph.encoding import Encoder, Survey, fragment
from advisors.models.entity_graph.graph import Graph
from advisors.models.entity_graph.schema import GRAPH_VERSION
from advisors.models.entity_graph.removals import encode_plan
from advisors.models.entity_graph.source import labels, load, prepare, save
from advisors.models.entity_graph.world import WorldReader, build_world
from advisors.models.entity_graph.world_data import extract_run, pack_run, read, validate_dataset
from tests.test_entity_graph_world import world_fixture


class GraphCreationTests(unittest.TestCase):
    def test_training_rejects_sampled_incomplete_and_duplicate_datasets(self):
        row={'run':1,'seq':0,'split':'train','decision':True}
        for manifest in ({'rows':[row]},
                         {'coverage':'all_recorded_decisions','total_recorded_pauses':2,'rows':[row]},
                         {'coverage':'all_recorded_decisions','total_recorded_pauses':2,'rows':[row,row]}):
            with self.assertRaises(ValueError):
                validate_dataset(manifest)
        validate_dataset({'graph_version':GRAPH_VERSION,'storage':'recurrent_frames','coverage':'all_recorded_decisions','total_recorded_pauses':1,'rows':[row],'frames':[row]})

    def test_recurrent_manifest_rejects_missing_frames_duplicates_and_split_leaks(self):
        row={'run':1,'seq':2,'split':'train','decision':True}
        manifest={'graph_version':GRAPH_VERSION,'storage':'recurrent_frames','coverage':'all_recorded_decisions',
                  'total_recorded_pauses':1,'rows':[row]}
        for frames in ([],[row,row],[row,{**row,'seq':1,'decision':False,'split':'test'}]):
            with self.assertRaises(ValueError):
                validate_dataset({**manifest,'frames':frames})

    def test_bulk_encoding_equals_scalar_encoding_and_preserves_empty_features(self):
        data,actions=world_fixture()
        graph=build_world(data,actions)[0]
        survey=Survey()
        survey.add(graph)
        encoder=Encoder([survey.mapping()])
        for normalize in (False,True):
            expected=[encoder.attributes(node,normalize) for node in graph.nodes]
            actual=encoder.graph(graph,normalize=normalize)
            np.testing.assert_array_equal(actual['tokens'],np.concatenate([ids for ids,_ in expected]))
            np.testing.assert_array_equal(actual['values'],np.concatenate([values for _,values in expected]))
        empty=Graph([{'seq':0,'kind':'missing','attrs':{}}],[],0,0,{})
        packed=encoder.graph(empty)
        self.assertEqual(packed['edge_index'].shape,(2,0))
        self.assertEqual(packed['offsets'].tolist(),[0,0])

    def test_intermediate_encoding_keeps_precision_until_normalization(self):
        from advisors.models.entity_graph.world_data import remap
        nodes=[{'seq':0,'kind':'country','attrs':{'gdp':value}} for value in (2.1e8,2.2e8,2.3e8)]
        graph=Graph(nodes,[],0,0,{})
        survey=Survey()
        survey.add(graph)
        encoder=Encoder([survey.mapping()])
        packed=encoder.graph(graph,normalize=False,dtype=np.float64)
        actual=remap(packed,encoder,encoder)
        expected=encoder.graph(graph)
        np.testing.assert_array_equal(actual['values'],expected['values'])

    def test_grouped_features_keep_mixed_types_unknowns_and_original_feature_order(self):
        data,actions=world_fixture()
        graph=build_world(data,actions)[0]
        graph.nodes[0]['attrs'].update(mixed=1.,extra='known')
        graph.nodes[1]['attrs'].update(mixed='text',extra=2.)
        graph.nodes[2]['attrs']={}
        survey=Survey()
        survey.add(graph)
        expected=Encoder([survey.mapping()])
        found,mapping=fragment(graph)
        self.assertEqual(found['encoder'].tokens,expected.tokens)
        for field,values in mapping['numeric'].items():
            np.testing.assert_allclose(values,survey.mapping()['numeric'][field],rtol=1e-12,atol=1e-12)
        graph.nodes[0]['attrs'].update(mixed=5000.,unknown_number=100.,extra='unseen')
        for normalize in (False,True):
            scalar=[expected.attributes(node,normalize) for node in graph.nodes]
            packed=expected.graph(graph,normalize)
            np.testing.assert_array_equal(packed['tokens'],np.concatenate([ids for ids,values in scalar]))
            np.testing.assert_array_equal(packed['values'],np.concatenate([values for ids,values in scalar]))

    def test_extraction_restores_collection_after_failure(self):
        import gc
        enabled=gc.isenabled()
        with patch('advisors.models.entity_graph.world_data.extract_frames',side_effect=ValueError('stop')):
            with self.assertRaisesRegex(ValueError,'stop'):
                extract_run(None)
        self.assertEqual(gc.isenabled(),enabled)

    def test_reader_reads_only_requested_observation_without_actions(self):
        reader=WorldReader.__new__(WorldReader)
        reader.run=1
        reader.player=2
        reader.dates={0:0,1:0,2:24,3:24,4:48,5:48,6:72}
        reader.actions={seq:[('form_army',{'option':1})] for seq in (0,2,4,6)}
        reader.geography=reader.vocabulary=reader.enums={}
        reader.snapshot=Mock(side_effect=lambda seq:{'seq':seq})
        first=reader.read(4)
        second=reader.read(6)
        self.assertEqual(first['history'],[4])
        self.assertEqual(second['history'],[6])
        self.assertEqual(reader.snapshot.call_count,2)
        self.assertEqual(second['action_history'],{})
        self.assertNotIn(6,first['dates'])

    def test_missing_baselines_and_future_values_mask_individual_targets(self):
        dates={0:0,1:90*24}
        series={'gdp':[(0,0)],'population':[(0,10),(1,20)],'sol':[],'stock':[(0,3),(1,4)]}
        base,y,mask,age=labels(0,dates,series)
        self.assertEqual(base.tolist(),[0,10,0,3])
        self.assertEqual(mask[0].tolist(),[False,True,False,True])
        self.assertTrue(np.isfinite(y).all())
        self.assertFalse(labels(1,dates,series)[2].any())

    def test_source_retains_every_pause_including_all_masked_decisions(self):
        actions={seq:[('form_army',{'option':30})] for seq in range(24)}
        connection=Mock()
        connection.execute.return_value.fetchall.return_value=[(1,1)]
        dates={seq:seq*24 for seq in actions}
        series={name:[] for name in ('gdp','population','sol','stock')}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source'
            with patch('advisors.models.entity_graph.source.psycopg.connect') as connect,patch('advisors.models.entity_graph.source.blocks',return_value=actions),patch('advisors.models.entity_graph.source.outcomes',return_value=(dates,series)),patch('builtins.print'):
                connect.return_value.__enter__.return_value=connection
                manifest=prepare(path)
            tasks=load(path/'run_1.pkl.gz')['tasks']
            self.assertEqual(len(manifest['tasks']),24)
            self.assertEqual([task['seq'] for task in tasks],list(actions))
            self.assertTrue(all(not task['mask'].any() for task in tasks))
            self.assertEqual(manifest['coverage'],'all_recorded_decisions')

    def test_recurrent_frames_preserve_every_observation_decision_and_action_delta(self):
        data,actions=world_fixture()
        first={**data,'seq':0,'history':[0],'action_history':{}}
        second={**data,'action_history':{0:actions}}
        middle=copy.deepcopy(first)
        middle.update(seq=1,history=[1],dates={1:0})
        middle['states']={1:copy.deepcopy(data['states'][0])}
        cases={0:first,1:middle,2:second}
        tasks=[{'run':1,'seq':seq,'hour':cases[seq]['dates'][seq],'split':'validation','actions':actions,
                'y':np.zeros((5,4)),'mask':np.zeros((5,4),bool),'baseline':np.zeros(4)} for seq in (0,2)]
        reader=Mock()
        reader.actions={seq:actions for seq in (0,2)}
        reader.dates={seq:cases[seq]['dates'][seq] for seq in cases}
        reader.vocabulary=data['vocabulary']
        reader.read.side_effect=lambda seq:cases[seq]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'source'
            output=root/'packed'
            source.mkdir()
            output.mkdir()
            save(source/'run_1.pkl.gz',{'tasks':tasks})
            with patch('advisors.models.entity_graph.world_data.psycopg.connect'),patch('advisors.models.entity_graph.world_data.ReplayReader',return_value=reader),patch('advisors.models.entity_graph.world_data.Shared'),patch('advisors.models.entity_graph.world_data.ReplaySnapshot'),patch('advisors.models.entity_graph.world_data.candidates',return_value=[actions,[('form_army',{'option':60})]]),patch('builtins.print'):
                partition=extract_run((source,output,1))
            self.assertEqual(len(partition['rows']),2)
            self.assertEqual([r['seq'] for r in partition['frames']],[0,1,2])
            self.assertEqual(len(list(output.glob('*.raw'))),3)
            graphs=[build_world(cases[seq],actions)[0] for seq in cases]
            survey=Survey()
            for graph in graphs:
                survey.add(graph)
            encoder=Encoder([survey.mapping()])
            save(output/'encoder.pkl.gz',encoder)
            pack_run((output,1))
            from advisors.models.entity_graph.world_data import join
            for task in tasks:
                graph=build_world(cases[task['seq']],actions)[0]
                metadata=read(output/f'1_{task["seq"]}.pkl',materialize=False)
                self.assertEqual(metadata['record']['seq'],task['seq'])
                actual=read(output/f'1_{task["seq"]}.pkl')
                combined=join(actual['graph'],actual['proposal'])
                expected=encoder.graph(graph)
                expected.update(encode_plan(graph,cases[task['seq']],encoder,expected))
                for key in ('tokens','values','offsets','kind','current','action','edge_index','relation','weight','player','block','nodes'):
                    np.testing.assert_allclose(combined[key],expected[key],rtol=1e-6,atol=1e-6,err_msg=key)
                    if hasattr(expected[key],'dtype'):
                        self.assertEqual(combined[key].dtype,expected[key].dtype,key)
                for delta,alternative in zip(actual['deltas'],actual['actions']):
                    rebuilt=encoder.graph(build_world(cases[task['seq']],alternative)[0])
                    combined=join(actual['graph'],delta)
                    for key in ('tokens','values','offsets','kind','current','action','edge_index','relation','weight','player','block'):
                        np.testing.assert_allclose(combined[key],rebuilt[key],rtol=1e-6,atol=1e-6,err_msg=key)
            self.assertIsNone(read(output/'1_1.pkl')['proposal'])
            np.testing.assert_array_equal(read(output/'1_0.pkl')['graph']['identity'],read(output/'1_1.pkl')['graph']['identity'])


if __name__=='__main__':
    unittest.main()
