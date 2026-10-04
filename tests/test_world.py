import collections
import random
import re
import unittest

import numpy as np

from interface.common import DEFAULT_GAME
from interface.script import blocks, body, definitions, scalar
from interface.world.audit import audit
from interface.world.buildings import compare, expected, project, levels
from interface.world.military import military
from interface.world.generate import _absent, _company_scopes, _rewrites
from interface.world.project import history_text, nations, politics, tech_counts
from interface.world.source import assignments, integer_counts, moments, select_regions, spread
from interface.world.vanilla import vanilla


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



class FidelityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=vanilla(DEFAULT_GAME/'game')

    def world(self,key,copies=0,tech=.5,tech_variation=1,**controls):
        rng=random.Random(12)
        sources=select_regions(rng,self.data,1,[key])
        templates=sources[key]
        states=[{'id':i+1,'key':f'STATE_INTERFACE_{i+1}','source':t,'source_region':key,'province_codes':[f'x{i+1:06X}']}
                for i,t in enumerate(templates)]
        groups=[[s['id'] for s in states if s['source']['owner']==tag] for tag in dict.fromkeys(s['source']['owner'] for s in states)]
        strategic=[{'key':'region_interface_1','source_region':key,'states':states}]
        world=nations(rng,self.data,states,groups,[g[0] for g in groups],strategic,sources,tech=tech,copies=copies,tech_variation=tech_variation,**controls)
        return states,world

    def test_laws_precede_institutions_and_support_the_retained_barracks(self):
        text='set_institution_investment_level = { institution = institution_schools level = 2 } effect_starting_politics_traditional = yes activate_law = law_type:law_warrior_caste'
        result=politics(text,self.data,set(self.data['tech_requires']),40)
        self.assertNotIn('law_warrior_caste',result)
        self.assertIn('activate_law = law_type:law_professional_army',result)
        self.assertLess(result.index('activate_law'),result.index('set_institution_investment_level'))
        self.assertIn('limit = { has_institution = institution_schools }',result)

    def test_country_profiles_are_independent_of_the_sampled_state_owners(self):
        worlds=[]
        for region in ('region_western_europe','region_north_china'):
            sources=select_regions(random.Random(1),self.data,1,[region])
            states=[{'id':i,'key':f'STATE_INTERFACE_{i}','source':source,'province_codes':[f'x{i:06X}']}
                    for i,source in enumerate(sources[region][:3],1)]
            strategic=[{'key':'region_interface_1','source_region':region,'states':states}]
            worlds.append(nations(random.Random(42),self.data,states,[[1],[2],[3]],[1,2,3],strategic,sources,copies=1))
        self.assertEqual([c['source'] for c in worlds[0]['countries']],[c['source'] for c in worlds[1]['countries']])

    def test_armies_are_initialized_once_from_barracks(self):
        states,world=self.world('region_western_europe',copies=1)
        owned={s['key']:s['country'] for s in states}
        counts=collections.Counter()
        text=world['files']['common/history/military_formations/interface.txt']
        for country,history in blocks(body(text)):
            tag=country.removeprefix('c:')
            for key,formation in blocks(body(history)):
                if key!='create_military_formation':
                    continue
                self.assertEqual(scalar(formation,'hq_region'),'sr:region_interface_1')
                for kind,unit in blocks(body(formation)):
                    if kind=='combat_unit':
                        state=scalar(unit,'state_region').removeprefix('s:')
                        self.assertEqual(owned[state],tag)
                        counts[state]+=int(scalar(unit,'count'))
        self.assertEqual(sum(counts.values()),0)
        self.assertGreater(sum(s['buildings'].get('building_barrack',0) for s in states),100)
        saves=set(re.findall(r'save_scope_as\s*=\s*(\w+)',text))
        self.assertLessEqual(set(re.findall(r'scope:(\w+)',text)),saves)

    def test_regional_defaults_preserve_populations_land_buildings_and_methods(self):
        for region in ('region_western_europe','region_northern_europe','region_north_china','region_west_africa'):
            with self.subTest(region=region):
                states,world=self.world(region)
                report=audit(states,world['files'])
                self.assertTrue(report['population_structure_preserved'])
                self.assertTrue(report['production_methods_match_projection'])
                self.assertEqual(report['company_errors'],[])
                self.assertEqual(report['ownership_errors'],[])
                self.assertEqual(report['duplicate_buildings'],[])
                for row in report['states']:
                    self.assertEqual(row['population'],row['source_population'])
                    self.assertEqual(row['levels']+row['excluded_levels'],row['source_levels'])
                    self.assertEqual(row['arable'],row['source_arable'])
                for path,text in world['files'].items():
                    self.assertEqual(text.count('{'),text.count('}'),path)

    def test_copies_retain_the_source_identities_without_changing_the_economy(self):
        states,original=self.world('region_western_europe',copies=1)
        _,renamed=self.world('region_western_europe',copies=0)
        self.assertTrue(all(c['tag']==c['source']==c['copy'] for c in original['countries']))
        self.assertTrue(all(c['copy'] is None and c['tag']!=c['source'] for c in renamed['countries']))
        self.assertEqual(audit(states,original['files'])['totals'],audit(states,renamed['files'])['totals'])
        self.assertEqual(set(re.findall(r'^(\w+)\s*=',original['files']['common/country_definitions/interface.txt'],re.M)),
                         {c['tag'] for c in original['countries']})

    def test_full_copies_work_when_one_source_country_supplies_many_countries(self):
        rng=random.Random(4)
        sources=select_regions(rng,self.data,1,['region_north_china'])
        states=[{'id':i+1,'key':f'STATE_INTERFACE_{i+1}','source':s,'province_codes':[f'x{i+1:06X}']}
                for i,s in enumerate(sources['region_north_china'])]
        groups=[[s['id']] for s in states]
        strategic=[{'key':'region_interface_1','source_region':'region_north_china','states':states}]
        world=nations(rng,self.data,states,groups,[g[0] for g in groups],strategic,sources,copies=1)
        self.assertEqual(len({c['copy'] for c in world['countries']}),len(states))
        self.assertNotIn(None,{c['copy'] for c in world['countries']})
        self.assertEqual(world['tech_reference']['mean'],len(self.data['source_countries']['CHI']['techs']))

    def test_default_tech_mean_comes_from_selected_countries_including_extra_research(self):
        states,world=self.world('region_western_europe',copies=1)
        tags={s['source']['owner'] for s in states}
        expected=sum(len(self.data['source_countries'][t]['techs']) for t in tags)/len(tags)
        self.assertAlmostEqual(world['tech_reference']['mean'],expected)
        self.assertAlmostEqual(sum(c['tech_count'] for c in world['countries'])/len(world['countries']),expected)

    def test_zero_tech_dispersion_and_endpoints_obey_the_count_budget(self):
        for value in (0,.5,1):
            _,world=self.world('region_western_europe',tech=value,tech_variation=0)
            counts=[c['tech_count'] for c in world['countries']]
            self.assertLessEqual(max(counts)-min(counts),1)
            self.assertEqual(sum(counts),round(len(counts)*world['tech_reference']['mean']))
            emitted=world['files']['common/history/countries/interface.txt']
            self.assertNotIn('effect_starting_technology_tier_',emitted)

    def test_technology_exclusions_are_explicit_and_are_the_only_removed_levels(self):
        states,world=self.world('region_western_europe',tech=0,tech_variation=0)
        technologies={c['tag']:set(c['technologies']) for c in world['countries']}
        excluded=0
        for state in states:
            for kind,item in state['excluded_buildings'].items():
                self.assertEqual(set(item['missing_technologies']),self.data['building_techs'][kind]-technologies[state['country']])
                self.assertTrue(item['missing_technologies'])
                self.assertNotIn(kind,state['buildings'])
                excluded+=item['levels']
            for kind in state['buildings']:
                self.assertLessEqual(self.data['building_techs'][kind],technologies[state['country']])
        self.assertGreater(excluded,0)
        report=audit(states,world['files'])
        self.assertEqual(report['totals']['source_levels'],report['totals']['levels']+excluded)

    def test_company_assets_keep_the_company_when_its_original_headquarters_is_absent(self):
        rng=random.Random(4)
        sources=select_regions(rng,self.data,1,['region_canada'])
        source=next(s for s in sources['region_canada'] if any('company_hbc' in r for r in s['building_records']))
        state={'id':1,'key':'STATE_INTERFACE_1','source':source,'province_codes':['x000001']}
        strategic=[{'key':'region_interface_1','source_region':'region_canada','states':[state]}]
        world=nations(rng,self.data,[state],[[1]],[1],strategic,sources)
        text=world['files']['common/history/countries/interface.txt']
        self.assertIn('add_company = company_type:company_hbc',text)
        self.assertIn('set_company_state_region = s:STATE_INTERFACE_1',text)
        self.assertRegex(state['generated_buildings'],r'type\s*=\s*company_hbc')
        self.assertEqual(audit([state],world['files'])['company_errors'],[])

    def test_source_companies_keep_their_source_headquarters(self):
        states,world=self.world('region_western_europe',copies=1)
        locations={s['source']['key']:s['key'] for s in states}
        text=world['files']['common/history/countries/interface.txt']
        self.assertIn('company:company_john_cockerill',text)
        self.assertIn('set_company_state_region = s:'+locations['STATE_WALLONIA'],text)
        self.assertIn('company:company_dmc',text)
        self.assertIn('set_company_state_region = s:'+locations['STATE_ALSACE_LORRAINE'],text)

    def test_global_initialization_has_only_projected_references(self):
        states,world=self.world('region_western_europe')
        tags={c['tag'] for c in world['countries']}
        keys={s['key'] for s in states}
        for folder in ('global','cultures','conscription'):
            text=world['files'][f'common/history/{folder}/interface.txt']
            self.assertLessEqual(set(re.findall(r'\bc:([A-Z0-9]{3})\b',text)),tags)
            self.assertLessEqual(set(re.findall(r'\bSTATE_\w+',text)),keys)
            emitted=collections.Counter(key for key,_ in blocks(body(text)))
            self.assertLessEqual(emitted['every_country'],len(self.data['history'][folder].get('every_country',[])))

    def test_absent_owned_countries_do_not_erase_company_headquarters(self):
        states,world=self.world('region_western_europe',copies=1)
        countries=dict(blocks(body(world['files']['common/history/countries/interface.txt'])))
        home_owner=next(s['country'] for s in states if s['source']['key']=='STATE_HOME_COUNTIES')
        british=dict(blocks(body(countries['c:'+home_owner])))
        home=next(s['key'] for s in states if s['source']['key']=='STATE_HOME_COUNTIES')
        for key in ('company_hbc','company_east_india_company'):
            company=british['company:'+key]
            self.assertEqual(scalar(company,'set_company_state_region'),'s:'+home)
            self.assertIn('set_company_establishment_date',company)
            self.assertNotIn('add_owned_country',company)

    def test_audit_rejects_creation_without_company_setup(self):
        states,world=self.world('region_western_europe',copies=1)
        path='common/history/countries/interface.txt'
        countries=dict(blocks(body(world['files'][path])))
        home_owner=next(s['country'] for s in states if s['source']['key']=='STATE_HOME_COUNTIES')
        company=dict(blocks(body(countries['c:'+home_owner])))['company:company_hbc']
        world['files'][path]=world['files'][path].replace(company,'')
        self.assertIn(f'company_hbc in {home_owner}: missing or foreign headquarters',audit(states,world['files'])['company_errors'])

    def test_company_definitions_only_prefer_existing_generated_states(self):
        states,_=self.world('region_western_europe')
        for state in states:
            state['template']=state['source']['key']
        strategic=[{'key':'region_interface_1','states':states}]
        files=_rewrites(DEFAULT_GAME/'game',states,strategic,self.data['regions'],{'XAA'})
        existing={s['key'] for s in states}
        checked=0
        for path,text in files.items():
            if path.startswith('common/company_types/'):
                self.assertLessEqual(set(re.findall(r'\bs:(STATE_\w+)\s*\??=\s*\{',text)),existing,path)
                for values in re.findall(r'preferred_headquarters\s*=\s*\{([^{}]*)\}',text):
                    self.assertLessEqual(set(re.findall(r'\bSTATE_\w+',values)),existing,path)
                    checked+=1
        self.assertGreater(checked,100)

    def test_recorded_company_definitions_include_attainability(self):
        rows=definitions(DEFAULT_GAME/'game')
        captured=[value for folder,name,field,value in rows
                  if folder=='common/company_types' and name=='company_krupp' and field=='attainable']
        self.assertEqual(len(captured),1)
        self.assertIn('STATE_RUHR',captured[0])
        self.assertIn(('common/company_types','company_construction_power_bloc','unlocking_principles','principle_construction_3'),rows)

    def test_repeated_templates_keep_company_building_owners_linked_to_the_company(self):
        rng=random.Random(4)
        sources=select_regions(rng,self.data,1,['region_western_europe'])
        source=next(s for s in sources['region_western_europe'] if s['key']=='STATE_ALSACE_LORRAINE')
        states=[{'id':i,'key':f'STATE_INTERFACE_{i}','source':source,'province_codes':[f'x{i:06X}']} for i in (1,2)]
        strategic=[{'key':'region_interface_1','source_region':'region_western_europe','states':states}]
        world=nations(rng,self.data,states,[[1],[2]],[1,2],strategic,sources)
        histories=dict(blocks(body(world['files']['common/history/countries/interface.txt'])))
        owners=[tag[2:] for tag,text in histories.items() if 'add_company = company_type:company_dmc' in text]
        self.assertEqual(len(owners),1)
        for state in states:
            matches=[record for key,record in blocks(state['generated_buildings']) if re.search(r'type\s*=\s*company_dmc',record)]
            self.assertTrue(matches)
            for record in matches:
                company=dict(blocks(body(dict(blocks(body(record)))['add_ownership'])))['company']
                self.assertEqual(scalar(company,'country'),'c:'+owners[0])

    def test_company_owner_follows_its_sampled_headquarters_when_borders_change(self):
        sources=select_regions(random.Random(4),self.data,1,['region_western_europe'])
        templates={s['key']:s for s in sources['region_western_europe']}
        states=[{'id':i+1,'key':f'STATE_INTERFACE_{i+1}','source':templates[key],'province_codes':[f'x{i+1:06X}']}
                for i,key in enumerate(('STATE_NORMANDY','STATE_ALSACE_LORRAINE'))]
        strategic=[{'key':'region_interface_1','source_region':'region_western_europe','states':states}]
        world=nations(random.Random(4),self.data,states,[[1],[2]],[1,2],strategic,sources)
        countries=dict(blocks(body(world['files']['common/history/countries/interface.txt'])))
        first,second=[c['tag'] for c in world['countries']]
        self.assertNotIn('add_company = company_type:company_dmc',countries['c:'+first])
        self.assertIn('add_company = company_type:company_dmc',countries['c:'+second])
        company=dict(blocks(body(countries['c:'+second])))['company:company_dmc']
        self.assertEqual(scalar(company,'set_company_state_region'),'s:STATE_INTERFACE_2')

    def test_source_records_preserve_slaves_and_local_production_methods(self):
        source=next(s for s in self.data['templates'] if any(scalar(p,'pop_type')=='slaves' for p in s['pop_records']))
        states,world=self.world(self.data['regions'][source['key']])
        self.assertRegex(world['files']['common/history/pops/interface.txt'],r'pop_type\s*=\s*slaves')
        self.assertIn('activate_production_methods',world['files']['common/history/buildings/interface.txt'])
        self.assertTrue(audit(states,world['files'])['population_structure_preserved'])

    def test_region_sampling_stays_inside_the_selected_sources(self):
        rng=random.Random(42)
        sources=select_regions(rng,self.data,2,['region_western_europe','region_north_china'])
        regions=[{'key':f'r{i}','source_region':key,'states':[{'id':i*10+j,'center':np.array([i*100+j,0])} for j in range(10)]}
                 for i,key in enumerate(sources)]
        assignments(rng,regions,sources)
        states=[s for r in regions for s in r['states']]
        self.assertEqual({s['source_region'] for s in states},set(sources))
        self.assertTrue(all(s['source'] in sources[s['source_region']] for s in states))

    def test_economic_controls_preserve_pops_and_respect_land_and_resource_limits(self):
        for country,local in ((0,0),(.5,1.5),(2,2)):
            states,world=self.world('region_western_europe',country_economy=country,local_economy=local)
            self.assertTrue(audit(states,world['files'])['population_structure_preserved'])
            for state in states:
                levels=collections.Counter()
                for _,record in blocks(state['generated_buildings']):
                    levels[scalar(record,'building')]+=sum(map(int,re.findall(r'\blevels\s*=\s*(\d+)',record)))
                for kind,cap in state['source']['capped'].items():
                    self.assertLessEqual(levels[kind],cap)
                self.assertLessEqual(sum(levels[k] for k in state['source']['arable_resources']),state['source']['arable_land'])

    def test_coastal_buildings_are_not_sampled_into_inland_states(self):
        rng=random.Random(42)
        sources=select_regions(rng,self.data,1,['region_western_europe'])
        states=[{'id':i,'center':np.array([i,0]),'coastal':bool(i%2)} for i in range(20)]
        assignments(rng,[{'source_region':'region_western_europe','states':states}],sources)
        self.assertTrue(all(s['coastal'] or not s['source']['coastal'] for s in states))

    def test_extra_map_coasts_do_not_force_sampling_only_coastal_templates(self):
        rng=random.Random(42)
        sources=select_regions(rng,self.data,1,['region_western_europe'])
        states=[{'id':i,'center':np.array([i,0]),'coastal':True} for i in range(len(sources['region_western_europe']))]
        assignments(rng,[{'source_region':'region_western_europe','states':states}],sources)
        self.assertEqual({s['source']['key'] for s in states},{s['key'] for s in sources['region_western_europe']})

    def test_ideology_uniformity_does_not_change_laws_or_technology(self):
        _,base=self.world('region_western_europe')
        for uniformity in (0,.5,1):
            _,changed=self.world('region_western_europe',ideology_uniformity=uniformity)
            self.assertEqual([c['tech_count'] for c in changed['countries']],[c['tech_count'] for c in base['countries']])
            self.assertEqual([c['starting_laws'] for c in changed['countries']],[c['starting_laws'] for c in base['countries']])
            self.assertTrue(all(c['ideology_uniformity']==uniformity for c in changed['countries']))

    def test_primary_share_controls_preserve_population_structure(self):
        for share in (0,.25,.5,1):
            states,world=self.world('region_western_europe',primary_culture_share=share)
            countries={c['tag']:c for c in world['countries']}
            populations=collections.Counter()
            primary=collections.Counter()
            for state in states:
                for record in state['pop_records']:
                    size=int(scalar(record,'size'))
                    populations[state['country']]+=size
                    if scalar(record,'culture') in countries[state['country']]['cultures']:
                        primary[state['country']]+=size
            for tag,total in populations.items():
                self.assertLessEqual(abs(primary[tag]-share*total),.5)
            report=audit(states,world['files'])
            self.assertTrue(report['population_structure_preserved'])
            self.assertTrue(report['culture_projection_matches'])
