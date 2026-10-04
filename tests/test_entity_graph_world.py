import copy
import unittest

import numpy as np

from advisors.models.entity_graph.source import records
from advisors.models.entity_graph.world import build_world, WORLD_TABLES
from tests.test_entity_graph import fixture, table


def world_fixture():
    data,task,vocabulary=fixture()
    data.update(seq=task['seq'],history=task['history'],tables=WORLD_TABLES,enums={},action_history={})
    vocabulary['state_region']={1:'first_region',2:'second_region',3:'remote_region'}
    data['vocabulary']=vocabulary
    data['states']={seq:{name:[{**r,'seq':seq} for r in records(snapshot,name)] for name in WORLD_TABLES} for seq,snapshot in data['states'].items()}
    raster=np.full((100,100),101,np.int32)
    raster[:,50:]=102
    data['geography']['map']={'raster':raster,'width':100,'height':100,'wrap_x':False,'crossings':[],
                            'seam':[],'circular_centres':{},'unmapped_pixels':0,'coordinate_frame':'game_xy_bottom_left',
                            'border_centres':np.column_stack((np.full(100,50.),np.arange(100)+.5)),
                            'border_provinces':np.tile([101,102],(100,1)), 'border_axes':np.ones(100,np.int8)}
    return data,task['actions']


class FullWorldTests(unittest.TestCase):
    def test_training_snapshot_cannot_silently_stand_in_for_full_world(self):
        data,task,vocabulary=fixture()
        with self.assertRaisesRegex(ValueError,'complete recording schema'):
            build_world(data,task['actions'])

    def test_full_world_keeps_remote_entities_populations_provinces_and_ownership(self):
        data,actions=world_fixture()
        additions={
            'country_history':[{'country':2,'market':10}],
            'state_history':[{'state':91,'country':2}],
            'building_history':[{'building':92,'state':91,'levels':3}],
            'pop_history':[{'pop':93,'location':91,'workplace':92,'culture':8,'pop_type':3,'religion':4}],
            'pop_status':[{'pop':93,'workforce':7,'dependents':2}],
            'province_history':[{'province':103,'state':91,'controller':2}],
            'market_history':[{'market':10,'owner':2}],
            'formation_history':[{'formation':94,'country':2,'supply_hub':91}],
            'building_ownership_history':[{'building_ownership':95,'building':92,'owner_kind':'country','owner_country':1,'levels':2}],
            'country_research_history':[{'country_research':96,'country':2}]
        }
        for name,rows in additions.items():
            data['states'][2][name].extend({**r,'seq':2} for r in records({name:table(name,rows)},name))
        data['geography']['provinces'].append((103,3,'hills',10,40,50))
        graph,summary=build_world(data,actions)
        found={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(graph.nodes)}
        for kind,key in (('country',2),('state',91),('building',92),('pop',93),('province',103),('formation',94),('building_ownership',95),('country_research',96)):
            self.assertIn((2,kind,key),found)
        self.assertNotIn('population_cohort',summary['node_types'])
        self.assertIn((found[(2,'building_ownership',95)],found[(2,'country',1)],'building_ownership_history.owner_country',1.),graph.edges)
        for relation in ('province.land_border','state.land_border','building.output','pop_history.workplace','pop_history.culture','action.parameter.building'):
            self.assertIn(relation,summary['relations'])
        self.assertTrue(all(c['source_rows']==c['represented_rows'] for c in summary['coverage']))
        self.assertEqual(summary['missing_entity_records'],[])

    def test_unrecorded_targets_remain_explicit_without_invented_attributes(self):
        data,actions=world_fixture()
        data['states'][2]['formation_history'][0]['supply_hub']=999
        graph,summary=build_world(data,actions)
        missing=[n for n in graph.nodes if n['kind']=='unobserved.state']
        self.assertEqual(len(missing),1)
        self.assertEqual(missing[0]['key'],999)
        self.assertEqual(set(missing[0]['attrs']),{'age_days'})
        self.assertEqual(summary['missing_entity_records'][0]['field'],'supply_hub')

    def test_future_world_facts_do_not_leak_into_snapshot(self):
        data,actions=world_fixture()
        first,summary=build_world(data,actions)
        data['states'][99]=copy.deepcopy(data['states'][2])
        data['dates'][99]=99999
        data['states'][99]['building_history'][0]['levels']=99999
        second,_=build_world(data,actions)
        self.assertEqual(first.nodes,second.nodes)
        self.assertEqual(first.edges,second.edges)

    def test_reference_id_fields_are_links_and_provenance_stays_outside_features(self):
        data,actions=world_fixture()
        graph,summary=build_world(data,actions)
        node=next(n for n in graph.nodes if n['kind']=='pop' and n['key']==31 and n['seq']==2)
        self.assertNotIn('pop_history.workplace',node['attrs'])
        self.assertEqual(node['sources']['pop_history']['observed_seq'],2)
        self.assertIn('definition.religion',summary['node_types'])

    def test_entity_date_field_is_distinct_from_time_series_metadata(self):
        data,actions=world_fixture()
        for name,rows in {
            'diplomatic_catalyst_history':[{'diplomatic_catalyst':70}],
            'diplomatic_catalyst_private':[{'diplomatic_catalyst':70,'country':1,'target_country':1,'date':10}]
        }.items():
            data['states'][2][name]=[{**r,'seq':2} for r in records({name:table(name,rows)},name)]
        graph,summary=build_world(data,actions)
        node=next(n for n in graph.nodes if n['kind']=='diplomatic_catalyst')
        self.assertAlmostEqual(node['attrs']['diplomatic_catalyst_private.date'],14/24)
        self.assertEqual(node['sources']['diplomatic_catalyst_private'],{'observed_seq':2})

    def test_unassigned_province_retains_its_recorded_geography(self):
        data,actions=world_fixture()
        data['states'][2]['province_history'].extend({**r,'seq':2} for r in records({'province_history':table('province_history',[{'province':999}])},'province_history'))
        data['geography']['provinces'].append((999,None,'ocean',100,50,60))
        graph,summary=build_world(data,actions)
        node=next(n for n in graph.nodes if n['kind']=='province' and n['key']==999)
        self.assertEqual(node['attrs']['area_pixels'],100)
        self.assertEqual(node['attrs']['terrain'],'ocean')
        self.assertEqual(node['attrs']['x'],50)

    def test_empty_script_scope_does_not_create_an_unknown_reference(self):
        data,actions=world_fixture()
        data['enums']['scope_type']={0:'none'}
        data['vocabulary']['scope_name']={1:'target'}
        for name,rows in {
            'journal_entry_history':[{'journal_entry':70,'country':1}],
            'journal_entry_target':[{'journal_entry':70,'name_key':1,'scope_type':0,'scope_target':0}]
        }.items():
            data['states'][2][name]=[{**r,'seq':2} for r in records({name:table(name,rows)},name)]
        graph,summary=build_world(data,actions)
        self.assertEqual(summary['opaque_scope_targets'],[])

    def test_formation_parameters_link_entities_and_decree_parameters_keep_named_types(self):
        data,actions=world_fixture()
        actions=[('set_army_supply_priority',{'military_formation':41,'level':'low'}),('raise_state_decrees',{'state':11,'decree':'road_maintenance'}),('form_army',{'option':30})]
        graph,summary=build_world(data,actions)
        supply=next(n for n in graph.nodes if n['kind']=='action' and n['key']==0)
        decree=next(n for n in graph.nodes if n['kind']=='action' and n['key']==1)
        self.assertNotIn('parameter.military_formation',supply['attrs'])
        self.assertEqual(supply['parameters'],{'military_formation':41,'level':'low'})
        self.assertIn('action.parameter.military_formation',summary['relations'])
        self.assertEqual(decree['attrs']['parameter.decree'],'road_maintenance')


if __name__=='__main__':
    unittest.main()
