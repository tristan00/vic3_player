import unittest

from interface.world.buildings import compare, expected, project, levels
from interface.world.military import military
from interface.world.generate import _absent, _company_scopes
from interface.world.project import history_text
from interface.world.source import integer_counts, moments, spread


class DistributionTests(unittest.TestCase):
    def test_absent_company_origin_cannot_reference_a_removed_country(self):
        text='OR = { c:PRU ?= this was_formed_from = PRU }'
        self.assertEqual(_absent(text,{'GBR'}),'OR = { always = no always = no }')
        self.assertEqual(_absent(text,{'PRU'}),text)

    def test_company_scopes_follow_repeated_templates_and_reject_absent_states(self):
        text='possible = { s:STATE_BAVARIA ?= { any_scope_state = { is_incorporated = yes } } }'
        result=_company_scopes(text,{'STATE_BAVARIA':{'STATE_INTERFACE_1','STATE_INTERFACE_2'}})
        self.assertNotIn('s:STATE_BAVARIA',result)
        self.assertIn('s:STATE_INTERFACE_1 = {',result)
        self.assertIn('s:STATE_INTERFACE_2 = {',result)
        self.assertEqual(result.count('is_incorporated = yes'),2)
        self.assertEqual(_company_scopes(text,{}),'possible = { always = no }')

    def test_spread_preserves_mean_and_changes_sd(self):
        values=[10,20,30,40]
        changed=spread(values,.5)
        self.assertEqual(moments(changed),(25, moments(values)[1]/2))
        self.assertEqual(spread(values,0),[25]*4)

    def test_bounds_shrink_dispersion_without_biasing_the_mean(self):
        for mean in (0,1,9,10):
            values=spread([0,5,10],2,center=mean,upper=10)
            self.assertAlmostEqual(moments(values)[0],mean)
            self.assertTrue(all(0<=v<=10 for v in values))

    def test_rounding_preserves_the_nearest_total(self):
        self.assertEqual(sum(integer_counts([28.3,30.3,32.3,30.3])),121)

    def test_cut_references_do_not_remove_a_guard_or_leave_an_orphan_else(self):
        self.assertEqual(history_text('limit = { this = c:FRA } add_treasury = 100',{}, {}, {}),'')
        result=history_text('if = { limit = { this = c:FRA } x = 1 } else = { x = 2 } y = 3',{}, {}, {})
        self.assertEqual(result,'y = 3')

    def test_company_references_are_remapped_only_once(self):
        result=history_text('company:example = { add_owned_country = c:FRA }',{'FRA':'GBR','GBR':'XAA'},{},{})
        self.assertIn('add_owned_country = c:GBR',result)
        self.assertNotIn('c:XAA',result)

    def test_fleet_headquarters_and_ship_locations_use_owned_coastal_territory(self):
        data={'history':{'military_formations':{'c:TUN':['create_military_formation = { type = fleet hq_region = sr:region_north_africa ship = { type = ship_type:ship_type_frigate state_region = s:STATE_TUNISIA count = 1 } }']}}}
        state={'id':1,'key':'STATE_INTERFACE_1','source':{'coastal':True},'buildings':{}}
        result=military(data,'TUN','XAA',[state],{1:'region_interface_1'})
        self.assertIn('hq_region = sr:region_interface_1',result)
        self.assertIn('state_region = s:STATE_INTERFACE_1',result)
        self.assertNotIn('STATE_TUNISIA',result)
        state['coastal']=False
        self.assertEqual(military(data,'TUN','XAA',[state],{1:'region_interface_1'}),'')

    def test_building_merge_keeps_every_level_and_resolves_the_owner_location(self):
        records=[f'create_building = {{ building = building_iron_mine add_ownership = {{ building = {{ type = building_financial_district country = c:RUS region = STATE_INGRIA levels = {n} }} }} }}' for n in (8,5)]
        result=project(records,'XAA','STATE_INTERFACE_1',{'RUS':'XAB'},{},{'STATE_INTERFACE_1':'XAA'},1,set(),{})
        self.assertEqual(len(result),1)
        self.assertEqual(levels(result[0]),13)
        self.assertIn('country = "c:XAA" region = "STATE_INTERFACE_1"',result[0])
        self.assertEqual(expected(records,1,set()),{'building_iron_mine':13})

    def test_loaded_comparison_rejects_missing_levels_even_when_global_total_matches(self):
        manifest={'states':[{'country':'AAA','key':'STATE_A','buildings':{'building_iron_mine':13}},
                            {'country':'BBB','key':'STATE_B','buildings':{'building_iron_mine':7}}]}
        actual=[('AAA','STATE_A','building_iron_mine',12),('BBB','STATE_B','building_iron_mine',8)]
        report=compare(manifest,actual)
        self.assertEqual(report['expected_levels'],report['actual_levels'])
        self.assertEqual(len(report['differences']),2)

    def test_treaties_and_global_scopes_project_only_existing_participants(self):
        text='if = { limit = { has_dlc_feature = mp1_treaties } create_treaty = { first_country = c:FRA second_country = c:GBR } create_treaty = { first_country = c:RUS second_country = c:GBR } }'
        result=history_text(text,{'FRA':'XAA','GBR':'XAB'},{},{})
        self.assertEqual(result.count('create_treaty'),1)
        self.assertIn('first_country = c:XAA second_country = c:XAB',result)
        self.assertEqual(history_text('s:STATE_A = { x = 1 }',{}, {}, {}),'')
        self.assertEqual(history_text('hq_region = sr:region_absent',{}, {}, {}),'')
        self.assertEqual(history_text('teleport_to_front = p:xAABBCC.front',{}, {}, {}),'')
