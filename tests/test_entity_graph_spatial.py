import copy
import io
import unittest

import numpy as np
from PIL import Image
import torch

from advisors.models.entity_graph.encoding import Encoder, Survey
from advisors.models.entity_graph.model import Configuration, Network, collate
from advisors.models.entity_graph.source import records
from advisors.models.entity_graph.spatial import displacement, map_geometry
from advisors.models.entity_graph.world_data import action_graph
from advisors.models.entity_graph.world import build_world
from tests.test_entity_graph import table
from tests.test_entity_graph_world import world_fixture


def spatial_fixture():
    data,actions=world_fixture()
    data['geography']['provinces']=[(101,1,'plains',5000,24.5,49.5),(102,2,'hills',5000,74.5,49.5)]
    for seq,snapshot in data['states'].items():
        for name,rows in {
            'formation_history':[{'formation':41,'country':1,'supply_hub':11},{'formation':42,'country':1,'supply_hub':12}],
            'formation_status':[{'formation':41,'x':10.,'y':20.},{'formation':42,'x':13.,'y':24.}],
            'front_history':[{'front':71,'x':80.,'y':90.}]
        }.items():
            snapshot[name]=[{**r,'seq':seq} for r in records({name:table(name,rows)},name)]
    return data,actions


class SpatialGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_pixel_containment_uses_y_flip_and_actual_shape(self):
        data,actions=spatial_fixture()
        data['geography']['map']['raster'][79,10]=102
        graph,audit=build_world(data,actions)
        nodes={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(graph.nodes)}
        self.assertIn((nodes[2,'formation',41],nodes[2,'province',102],'spatial.formation.in_province',1.),graph.edges)
        self.assertIn((nodes[2,'formation',41],nodes[2,'state',12],'spatial.formation.in_state',1.),graph.edges)
        self.assertEqual(audit['spatial'][-1]['located_formations'],2)
        self.assertEqual(graph.nodes[nodes[2,'province',101]]['attrs']['spatial.y'],.5)

    def test_every_ordered_formation_pair_and_all_states_and_fronts_are_present(self):
        data,actions=spatial_fixture()
        graph,audit=build_world(data,actions)
        nodes={(n['seq'],n['kind'],n['key']):n for n in graph.nodes}
        forward=nodes[2,'spatial.formation_to_formation',(41,42)]['attrs']
        reverse=nodes[2,'spatial.formation_to_formation',(42,41)]['attrs']
        self.assertEqual(forward['distance_pixels'],5.)
        self.assertAlmostEqual(forward['dx'],.03)
        self.assertAlmostEqual(forward['dy'],.04)
        self.assertAlmostEqual(forward['direction_x'],.6)
        self.assertAlmostEqual(forward['direction_y'],.8)
        self.assertEqual(reverse['dx'],-forward['dx'])
        self.assertEqual(reverse['dy'],-forward['dy'])
        self.assertEqual(audit['spatial'][-1]['pairs'],{'formation':2,'state':4,'front':2})
        self.assertEqual(audit['spatial'][-1]['located_fronts'],1)

    def test_movement_changes_geometry_only_at_its_observation_time(self):
        data,actions=spatial_fixture()
        first=build_world(data,actions)[0]
        data['states'][2]['formation_status'][1].update(x=60.,y=20.)
        second=build_world(data,actions)[0]
        before={(n['seq'],n['kind'],n['key']):n for n in first.nodes}
        after={(n['seq'],n['kind'],n['key']):n for n in second.nodes}
        key='spatial.formation_to_formation'
        self.assertEqual(before[2,key,(41,42)]['attrs']['distance_pixels'],5.)
        self.assertEqual(after[2,key,(41,42)]['attrs']['distance_pixels'],50.)
        self.assertEqual(len(first.nodes),len(second.nodes))
        nodes={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(second.nodes)}
        self.assertEqual({n['seq'] for n in second.nodes},{2})
        self.assertFalse(any(r.startswith('temporal.') for a,b,r,w in second.edges))

    def test_wrapping_changes_distance_without_changing_entity_identity(self):
        data,actions=spatial_fixture()
        geo=data['geography']['map']
        self.assertEqual(displacement((99,20),(1,20),geo)['distance_pixels'],98.)
        geo['wrap_x']=True
        self.assertEqual(displacement((99,20),(1,20),geo)['distance_pixels'],2.)
        self.assertEqual(displacement((1,20),(99,20),geo)['dx'],-.02)
        self.assertEqual(displacement((50,20),(0,20),geo)['dx'],-.5)

    def test_missing_and_outside_positions_are_audited_without_invented_edges(self):
        data,actions=spatial_fixture()
        data['states'][2]['formation_status'][0]['x']=None
        data['states'][2]['formation_status'][1]['x']=101.
        graph,audit=build_world(data,actions)
        self.assertEqual(len(audit['spatial'][-1]['missing_positions']),1)
        self.assertEqual(len(audit['spatial'][-1]['outside_map']),1)
        self.assertEqual(audit['spatial'][-1]['located_formations'],0)
        self.assertEqual(sum(n['seq']==2 and n['kind']=='formation' for n in graph.nodes),2)
        self.assertFalse(any(n['seq']==2 and n['kind'].startswith('spatial.formation_to_') for n in graph.nodes))

    def test_coincident_formations_remain_distinct_with_zero_distance(self):
        data,actions=spatial_fixture()
        data['states'][2]['formation_status'][1].update(x=10.,y=20.)
        graph,_=build_world(data,actions)
        pair=next(n for n in graph.nodes if n['seq']==2 and n['kind']=='spatial.formation_to_formation')
        self.assertEqual(pair['attrs']['distance_pixels'],0.)
        self.assertEqual(pair['attrs']['coincident'],1.)
        self.assertEqual(pair['attrs']['direction_x'],0.)

    def test_coast_water_and_crossings_have_distinct_semantics(self):
        data,actions=spatial_fixture()
        data['geography']['provinces'][1]=(102,2,'ocean',5000,74.5,49.5)
        data['geography']['map']['crossings']=[{'first':101,'second':102,'through':None,'type':'sea','positions':[49.,20.,51.,20.]}]
        graph,audit=build_world(data,actions)
        relations={r for a,b,r,w in graph.edges}
        self.assertIn('province.coast',relations)
        self.assertNotIn('province.land_border',relations)
        self.assertIn('spatial.crossing.first',relations)
        self.assertEqual(audit['spatial'][-1]['crossings'],1)

    def test_nearest_border_distance_uses_segments_and_preserves_ties(self):
        data,actions=spatial_fixture()
        graph,audit=build_world(data,actions)
        found=[n for n in graph.nodes if n['seq']==2 and n['kind']=='spatial.nearest_state_border' and n['key'][0]==41]
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['attrs']['distance_pixels'],40.)
        self.assertEqual(found[0]['attrs']['border_y'],.2)
        self.assertEqual(audit['spatial'][-1]['nearest_borders']['state_border'],2)
        self.assertEqual(audit['spatial'][-1]['nearest_borders']['country_border'],0)

    def test_recorded_province_and_coordinate_disagreement_both_remain(self):
        data,actions=spatial_fixture()
        data['states'][2]['formation_status'][0]['province']=102
        graph,audit=build_world(data,actions)
        nodes={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(graph.nodes)}
        formation=nodes[2,'formation',41]
        self.assertIn((formation,nodes[2,'province',102],'formation_status.province',1.),graph.edges)
        self.assertIn((formation,nodes[2,'province',101],'spatial.formation.in_province',1.),graph.edges)
        self.assertEqual(graph.nodes[formation]['attrs']['spatial.recorded_province_agrees'],0.)
        self.assertEqual(audit['spatial'][-1]['recorded_province_disagreements'][0]['recorded'],102)

    def test_map_decode_preserves_seam_and_crossing_endpoints(self):
        rgb=np.zeros((2,4,3),np.uint8)
        rgb[:,:,2]=np.array([[1,1,2,2],[1,1,2,2]])
        stream=io.BytesIO()
        Image.fromarray(rgb).save(stream,format='PNG')
        files={'default.map':b'wrap_x = yes','provinces.png':stream.getvalue(),
               'adjacencies.csv':b'From;To;Type;Through;start_x;start_y;stop_x;stop_y;rule;Comment\nx000001;x000002;sea;-1;1;1;2;1;;\n-1;-1;;-1;-1;-1;-1;-1;'}
        found=map_geometry(files,{1:101,2:102})
        np.testing.assert_array_equal(found['raster'],[[101,101,102,102],[101,101,102,102]])
        self.assertEqual(found['seam'],[(101,102,2)])
        self.assertEqual(found['crossings'][0]['first'],101)
        self.assertEqual(found['crossings'][0]['second'],102)
        self.assertIsNone(found['crossings'][0]['through'])

    def test_spatial_values_reach_model_inputs_and_receive_gradients(self):
        data,actions=spatial_fixture()
        first=build_world(data)[0]
        moved=copy.deepcopy(data)
        moved['states'][2]['formation_status'][1].update(x=60.,y=20.)
        second=build_world(moved)[0]
        survey=Survey()
        survey.add(first)
        survey.add(second)
        delta=action_graph(first,data,actions)
        survey.add(delta)
        encoder=Encoder([survey.mapping()])
        a,b=encoder.graph(first),encoder.graph(second)
        self.assertFalse(np.array_equal(a['values'],b['values']))
        token=encoder.tokens['number','distance_pixels']
        self.assertIn(token,a['tokens'])
        torch.manual_seed(41)
        model=Network(len(encoder.tokens),len(encoder.kinds)+1,len(encoder.relations)+1,Configuration(width=8,layers=3,dropout=0)).eval()
        proposal=encoder.graph(delta)
        result=torch.cat([model(collate([graph],'cpu'),proposal)[0] for graph in (a,b)])
        self.assertGreater(float((result[0]-result[1]).abs().max().detach()),1e-7)
        result.square().sum().backward()
        self.assertGreater(float(model.feature.weight.grad[token].abs().sum()),0.)
        self.assertTrue(torch.isfinite(result).all())

    def test_old_source_without_raster_is_rejected(self):
        data,actions=spatial_fixture()
        del data['geography']['map']
        with self.assertRaisesRegex(ValueError,'recorded map raster'):
            build_world(data,actions)


if __name__=='__main__':
    unittest.main()
