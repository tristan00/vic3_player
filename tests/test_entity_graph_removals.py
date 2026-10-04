import unittest

import numpy as np

from advisors.models.entity_graph.encoding import Encoder, Survey
from advisors.models.entity_graph.graph import Graph
from advisors.models.entity_graph.removals import ATTEMPTS, derive, encode_plan, subset
from advisors.models.entity_graph.source import records
from advisors.models.entity_graph.world import build_world
from advisors.models.entity_graph.world_data import action_graph, join, remap
from tests.test_entity_graph import table
from tests.test_entity_graph_world import world_fixture


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.data,self.actions=world_fixture()
        self.data['vocabulary']['culture_type']={7:'test_culture'}
        rows={
            'country_history':[{'country':2,'market':9}],
            'state_history':[{'state':91,'country':2}],
            'pop_history':[{'pop':93,'location':91,'workplace':21,'culture':8,'religion':4,'pop_type':3}],
            'pop_status':[{'pop':93,'workforce':7,'dependents':2,'wealth':12,'food_security':.8,'num_literate':4,'political_strength':9}],
            'country_ai_history':[{'country_ai':71,'country':1},{'country_ai':72,'country':2}],
            'country_ai_goal':[{'country_ai':71,'target_country':2,'neighbour':True},{'country_ai':72,'target_country':1,'neighbour':True}],
            'country_profession_population':[{'country':1,'pop_type':3,'population':30},{'country':2,'pop_type':3,'population':9}],
            'country_economy_report':[{'country':2,'gdp':123}],
            'country_standard_of_living_report':[{'country':2,'average_standard_of_living_by_population':12,'average_standard_of_living_middle':15}],
            'state_pop_need':[{'state':11,'culture_type':7,'need':1,'goods':5,'weight':2}],
            'interest_group_history':[{'interest_group':81,'country':1}],
            'political_movement_history':[{'political_movement':82,'country':1}],
            'interest_group_pop':[{'interest_group':81,'pop':31}],
            'pop_movement_support':[{'pop':31,'political_movement':82,'supporters':3}]
        }
        for name,values in rows.items():
            self.data['states'][2][name].extend({**r,'seq':2} for r in records({name:table(name,values)},name))
        self.graph,_=build_world(self.data,self.actions)
        survey=Survey()
        survey.add(self.graph)
        self.encoder=Encoder([survey.mapping()])

    def test_every_attempt_is_deletion_only_and_retains_entities(self):
        original={(n['seq'],n['kind'],n['key']):n for n in self.graph.nodes}
        for name in ATTEMPTS:
            found=derive(self.graph,self.data,name)
            for node in found.nodes:
                source=original[node['seq'],node['kind'],node['key']]
                self.assertLessEqual(node['attrs'].items(),source['attrs'].items())
            identities=[(n['seq'],n['kind'],n['key']) for n in self.graph.nodes]
            source_edges={(identities[a],identities[b],r,w) for a,b,r,w in self.graph.edges}
            keys=[(n['seq'],n['kind'],n['key']) for n in found.nodes]
            self.assertTrue(all((keys[a],keys[b],r,w) in source_edges for a,b,r,w in found.edges))
            for kind in ('pop','country','state','province','building','formation'):
                self.assertEqual(sum(n['kind']==kind for n in found.nodes),sum(n['kind']==kind for n in self.graph.nodes))

    def test_foreign_removal_preserves_aggregate_economy_and_domestic_detail(self):
        graph=derive(self.graph,self.data,'without_foreign_detail')
        self.assertEqual([n['key'] for n in graph.nodes if n['kind']=='country_ai_goal'],[(71,2)])
        country=next(n for n in graph.nodes if n['seq']==2 and n['kind']=='country' and n['key']==2)
        self.assertEqual(country['attrs']['country_economy_report.gdp'],123)
        self.assertEqual(country['attrs']['country_standard_of_living_report.average_standard_of_living_by_population'],12)
        self.assertNotIn('country_standard_of_living_report.average_standard_of_living_middle',country['attrs'])
        pop=next(n for n in graph.nodes if n['kind']=='pop' and n['key']==93)
        self.assertNotIn('pop_status.num_literate',pop['attrs'])
        self.assertEqual(pop['attrs']['pop_status.food_security'],.8)

    def test_population_removals_delete_only_the_named_facts(self):
        political=derive(self.graph,self.data,'without_pop_politics')
        needs=derive(self.graph,self.data,'without_pop_needs')
        self.assertFalse(any(n['kind'] in ('pop_movement_support','interest_group_pop') for n in political.nodes))
        self.assertTrue(any(n['kind']=='state_pop_need' for n in political.nodes))
        self.assertFalse(any(n['kind']=='state_pop_need' for n in needs.nodes))
        self.assertTrue(any(n['kind']=='pop_movement_support' for n in needs.nodes))

    def test_encoded_removals_match_actual_graph_removals(self):
        packed=self.encoder.graph(self.graph)
        packed.update(encode_plan(self.graph,self.data,self.encoder,packed))
        for name in ATTEMPTS:
            actual=subset(packed,name)
            expected=self.encoder.graph(derive(self.graph,self.data,name))
            for key in ('tokens','values','offsets','kind','edge_index','relation','weight'):
                np.testing.assert_allclose(actual[key],expected[key],err_msg=name+' '+key)

    def test_candidate_delta_matches_full_rebuild(self):
        actions=[('create_army',{'option':60})]
        delta=action_graph(self.graph,self.data,actions)
        survey=Survey()
        survey.add(self.graph)
        survey.add(delta)
        encoder=Encoder([survey.mapping()])
        base=encoder.graph(self.graph)
        base.update(encode_plan(self.graph,self.data,encoder,base))
        packed=encoder.graph(delta)
        packed.update(remove_nodes=np.zeros(packed['nodes'],np.uint8),remove_tokens=np.zeros(len(packed['tokens']),np.uint8))
        combined=join(base,packed)
        expected=encoder.graph(build_world(self.data,actions)[0])
        for key in ('tokens','values','offsets','kind','edge_index','relation','weight','player','block'):
            np.testing.assert_allclose(combined[key],expected[key],err_msg=key)

    def test_local_raw_encoding_remaps_to_training_encoder(self):
        numeric=[{'kind':'x','key':i,'seq':1,'hour':1,'attrs':{'number':float(i*i),'text':str(i)}} for i in range(3)]
        other=Graph(numeric,[],0,0,{})
        survey=Survey()
        survey.add(other)
        local=Encoder([survey.mapping()])
        training=Survey()
        training.add(self.graph)
        training.add(other)
        encoder=Encoder([training.mapping()])
        actual=remap(local.graph(other,normalize=False),local,encoder)
        expected=encoder.graph(other)
        np.testing.assert_allclose(actual['values'],expected['values'],atol=1e-6)
        np.testing.assert_array_equal(actual['tokens'],expected['tokens'])

    def test_unseen_numeric_fields_do_not_change_feature_normalization(self):
        graph=Graph([{'kind':'pop','seq':1,'hour':1,'key':1,'attrs':{'unseen':1.,'age_days':0.}}],[],0,0,{})
        survey=Survey()
        survey.add(graph)
        local=Encoder([survey.mapping()])
        actual=remap(local.graph(graph,normalize=False),local,self.encoder)
        expected=self.encoder.graph(graph)
        np.testing.assert_array_equal(actual['tokens'],expected['tokens'])
        np.testing.assert_array_equal(actual['offsets'],expected['offsets'])
        np.testing.assert_allclose(actual['values'],expected['values'],atol=1e-6)


if __name__=='__main__':
    unittest.main()
