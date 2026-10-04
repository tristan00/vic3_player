import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
from pathlib import Path
import random
from types import SimpleNamespace
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock
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

    def test_preparation_overlaps_loading_and_reports_progress_before_the_loop(self):
        import loop.run as run
        game=MagicMock()
        advisor=MagicMock(name='advisor')
        picker=MagicMock()
        picker.name='first'
        worlds=MagicMock()
        worlds.take.return_value=None
        store=MagicMock()
        store.recent_tags.return_value=[]
        started=threading.Event()
        loading=threading.Event()
        registered=threading.Event()
        heartbeat=threading.Event()
        trained=threading.Event()
        def train(*args):
            self.assertTrue(heartbeat.wait(2))
            trained.set()
        def progress(step):
            if step=='run preparation':
                heartbeat.set()
        def prepare(*args):
            started.set()
            if not loading.wait(2):
                raise AssertionError('Loading did not overlap registration')
            registered.set()
        def ready(*args):
            self.assertTrue(started.wait(2))
            loading.set()
            self.assertTrue(heartbeat.wait(2))
        def loop(*args):
            self.assertTrue(registered.is_set())
            self.assertTrue(trained.is_set())
            return MagicMock()
        game.campaign_ready.side_effect=ready
        picker.start_run.side_effect=train
        args=SimpleNamespace(warmup=2,advisors=['random'],pickers=['first'],years=1)
        with patch.object(run,'Store',return_value=store),patch.object(run,'prepare_recording',side_effect=prepare),patch.object(run,'run_record',return_value={}),patch.object(run,'Loop',side_effect=loop),patch.object(run,'progress',side_effect=progress):
            run.session(game,MagicMock(),random.Random(5),worlds,{'random':advisor},{'first':picker},args,None,1,0)
        self.assertFalse(game.campaign.call_args.kwargs['wait'])
        self.assertIsNone(game.campaign.call_args.kwargs['world'])

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

    def test_worlds_are_reusable_and_selected_by_the_run_rng(self):
        with TemporaryDirectory() as directory,patch.object(cache,'fingerprint',return_value='current'),patch.object(cache,'checked'):
            root=Path(directory)
            paths=[]
            for i in range(1000):
                path=root/'worlds'/str(i)/'manifest.json'
                path.parent.mkdir(parents=True)
                path.write_text('{}')
                paths.append(str(path.relative_to(root)))
            cache.publish(root/'index.json',{'fingerprint':'current','worlds':paths})
            worlds=cache.Cached(root,random.Random(3))
            expected=random.Random(3)
            for _ in range(10):
                self.assertEqual(worlds.take(),expected.choice(worlds.worlds))
            self.assertEqual(len(worlds.worlds),1000)
            self.assertTrue(all(path.exists() for path in worlds.worlds))

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
