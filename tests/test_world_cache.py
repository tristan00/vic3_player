import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from unittest.mock import Mock

import numpy as np

from interface.world import cache
from interface.world.vanilla import textures
from interface.world.buildings import loaded
from interface.world.source import spread


class CacheTests(unittest.TestCase):
    def test_loading_poll_does_not_parse_definitions_before_databases_exist(self):
        from interface.runner.memory import Reader
        with patch('interface.runner.memory.Process'),patch.object(Reader,'word',side_effect=OSError('not loaded')),patch('interface.runner.memory.read') as parse:
            with self.assertRaises(OSError):
                Reader(1)
            parse.assert_not_called()

    def test_resume_recovers_completed_worlds_without_regenerating_them(self):
        with TemporaryDirectory() as directory,patch.object(cache,'MINIMUM',2),patch.object(cache,'fingerprint',return_value='current'),patch.object(cache,'prepare_sources'),patch.object(cache,'checked',side_effect=lambda path:int(path.parent.name.split('_')[1])):
            root=Path(directory)
            sizes=cache.jobs(42,2)
            first=cache.manifest_path(root,sizes[0])
            first.parent.mkdir(parents=True)
            first.write_text('{}')
            created=[]
            def generate(root,game,size):
                created.append(size[0])
                path=cache.manifest_path(root,size)
                path.parent.mkdir(parents=True)
                path.write_text('{}')
                return str(path),1
            def pool(workers,**kwargs):
                return ThreadPoolExecutor(workers)
            with patch.object(cache,'ProcessPoolExecutor',side_effect=pool),patch.object(cache,'build_one',side_effect=generate),redirect_stdout(io.StringIO()):
                cache.build(root,root,2,1,42)
                cache.build(root,root,2,1,42)
            self.assertEqual(created,[sizes[1][0]])
            self.assertEqual(json.loads((root/'status.json').read_text())['phase'],'complete')
            self.assertEqual(len(json.loads((root/'index.json').read_text())['worlds']),2)

    def test_spread_roundoff_cannot_push_a_zero_target_below_zero(self):
        rng=random.Random(0)
        for _ in range(1000):
            values=[rng.random() for _ in range(3)]
            center=rng.random()/10000
            changed=spread(values,rng.random()*2,center=center)
            self.assertGreaterEqual(min(changed),0)
            self.assertAlmostEqual(sum(changed)/3,center,places=14)
            for target in changed:
                self.assertEqual(spread([1,1],0,center=target),[target,target])

    def test_dead_buildings_are_not_opening_buildings(self):
        reader=Mock()
        reader.names=[(0,'XAA'),(0,'STATE_A'),(0,'building_iron_mine')]
        tables={'country':{'id':[1],'country_definition':[1]},'state':{'id':[2],'country':[1],'state_region':[2]},
                'building':{'state':[2,-1],'building':[3,3],'levels':[7,4],'dead':[False,True]}}
        reader.table.side_effect=lambda name:(tables[name],None)
        manifest={'states':[{'country':'XAA','key':'STATE_A','buildings':{'building_iron_mine':7}}]}
        self.assertEqual(loaded(reader,manifest)['differences'],[])
        tables['building']['dead'][1]=False
        with self.assertRaises(KeyError):
            loaded(reader,manifest)

    def test_schedule_is_unique_and_resume_keeps_the_prefix(self):
        sizes=cache.jobs(42,1000)
        self.assertEqual(len({s[0] for s in sizes}),1000)
        self.assertEqual(sizes,cache.jobs(42,1010)[:1000])

    def test_incomplete_cache_cannot_be_selected(self):
        with TemporaryDirectory() as directory,patch.object(cache,'fingerprint',return_value='current'):
            root=Path(directory)
            cache.publish(root/'index.json',{'fingerprint':'current','worlds':['worlds/a/manifest.json']*1000})
            with self.assertRaisesRegex(ValueError,'at least 1000'):
                cache.Cached(root,random.Random(1))

    def test_wrong_sources_cannot_be_selected(self):
        with TemporaryDirectory() as directory,patch.object(cache,'fingerprint',return_value='current'):
            root=Path(directory)
            cache.publish(root/'index.json',{'fingerprint':'old','worlds':[]})
            with self.assertRaisesRegex(ValueError,'different sources'):
                cache.Cached(root,random.Random(1))

    def test_shared_rasters_produce_the_same_texture_samples(self):
        source={'provinces':np.array([[1,1,2],[1,2,2]]),'height':np.arange(6).reshape(2,3)}
        bounds={'x000001':(slice(0,2),slice(0,2))}
        for array in source.values():
            array.flags.writeable=False
        u=np.array([0,.3,.8]);v=np.array([0,.8,.3])
        with patch('interface.world.vanilla.rasters',return_value=source),patch('interface.world.vanilla.boxes',return_value=bounds):
            expected=textures(None,['x000001'],u,v)
        actual=textures(None,['x000001'],u,v,(source,bounds))
        for key in source:
            np.testing.assert_array_equal(actual[key],expected[key])


if __name__=='__main__':
    unittest.main()
