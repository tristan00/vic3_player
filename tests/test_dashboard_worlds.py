import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dashboard.server import worlds
from interface.recording.geography import mini_world


class WorldDashboardTests(unittest.TestCase):
    def test_inventory_keeps_unrun_and_incomplete_worlds_and_deduplicates_registered_artifacts(self):
        with TemporaryDirectory() as root:
            root=Path(root)
            manifest=json.dumps({'seed':4,'countries':[],'states':[],'mod':str(root/'complete/mod')}).encode()
            (root/'complete').mkdir()
            (root/'complete/manifest.json').write_bytes(manifest)
            (root/'pending.building').mkdir()
            (root/'broken').mkdir()
            (root/'broken/manifest.json').write_text('{')
            with patch.object(worlds,'ROOTS',(root,)),patch.object(worlds.db,'rows',return_value=[{'world_id':2,'data':manifest}]):
                entries=worlds.catalog()
            self.assertEqual(len(entries),3)
            self.assertEqual(entries['2']['directory'],root/'complete')
            self.assertEqual(worlds.summary(entries['2'],[])['status'],'Generated')
            self.assertEqual(sum(worlds.summary(e,[])['status']=='Incomplete' for e in entries.values()),2)

    def test_generated_contents_parse_nested_pops_and_building_ownership(self):
        pops=worlds.population('region_state:AAA = { create_pop = { culture = french religion = catholic size = 500 } }')
        self.assertEqual(pops,[{'culture':'french','religion':'catholic','pop_type':None,'size':'500'}])
        buildings=worlds.buildings('region_state:AAA = { create_building = { building = building_mine activate_production_methods = { "pm_one" } add_ownership = { country = { levels = 2 } country = { levels = 3 } } } }')
        self.assertEqual(buildings,[{'type':'building_mine','levels':5,'methods':['pm_one']}])

    def test_archiving_history_does_not_change_world_identity(self):
        with TemporaryDirectory() as root:
            root=Path(root)
            (root/'mod/map_data').mkdir(parents=True)
            (root/'mod/map_data/default.map').write_text('map')
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps({'mod':str(root/'mod'),'states':[]}))
            original=mini_world(manifest)[0]
            (root/'mod/common/history/pops').mkdir(parents=True)
            (root/'mod/common/history/pops/interface.txt').write_text('POPS = {}')
            (root/'mod/common/history/military_formations').mkdir(parents=True)
            (root/'mod/common/history/military_formations/interface.txt').write_text('MILITARY_FORMATIONS = {}')
            (root/'opening_buildings.json').write_text('{"differences": []}')
            (root/'audit.json').write_text('{}')
            digest,_,_,assets=mini_world(manifest)
            self.assertEqual(digest,original)
            self.assertEqual(assets['history/pops.txt'],b'POPS = {}')
            self.assertEqual(assets['audit.json'],b'{}')
            self.assertEqual(assets['history/military_formations.txt'],b'MILITARY_FORMATIONS = {}')
            self.assertEqual(assets['opening_buildings.json'],b'{"differences": []}')

    def test_run_from_another_world_is_rejected(self):
        with patch.object(worlds,'catalog',return_value={'2':{'world_id':2}}),patch.object(worlds,'run_rows',return_value=[{'run_id':8}]):
            with self.assertRaisesRegex(ValueError,'does not belong'):
                worlds.detail('2',9)

    def test_valid_json_with_invalid_manifest_shape_is_rejected(self):
        for value in ('[]','{}','{"countries":[],"states":[{}]}'):
            with self.assertRaises(ValueError):
                worlds.manifest(value)

    def test_archived_history_survives_local_directory_cleanup(self):
        entry={'key':'2','world_id':2,'manifest':{'countries':[],'states':[{'key':'STATE_A','name':'A','country':'AAA','provinces':[],'coastal':False}]},'directory':None,'issue':None}
        assets=[{'name':'history/pops.txt','data':b'POPS = { s:STATE_A = { region_state:AAA = { create_pop = { culture = french size = 500 } } } }'},
                {'name':'history/buildings.txt','data':b'BUILDINGS = { s:STATE_A = { region_state:AAA = { create_building = { building = building_monument level = 1 } } } }'}]
        with patch.object(worlds,'catalog',return_value={'2':entry}),patch.object(worlds,'run_rows',return_value=[]),patch.object(worlds.db,'rows',return_value=assets):
            state=worlds.detail('2')['states'][0]
        self.assertEqual((state['population'],state['levels']),(500,1))


if __name__=='__main__':
    unittest.main()
