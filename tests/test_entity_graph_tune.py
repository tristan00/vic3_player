import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import torch

from advisors.models.entity_graph.schema import GRAPH_VERSION
from advisors.models.entity_graph.world_tune import configurations, search


class GraphSearchTests(unittest.TestCase):
    def test_initial_search_is_repeatable_and_keeps_full_world(self):
        first=configurations(12,24)
        self.assertEqual(first,configurations(12,24))
        self.assertEqual(len(first),12)
        self.assertEqual(first['full_world'].width,48)
        self.assertEqual({config.operator for config in first.values()},{'relational_mean','relational_attention'})
        self.assertEqual({config.seed for config in first.values()},{41})
        self.assertEqual(len({(config.operator,config.width,config.layers) for config in first.values()}),12)

    def test_search_uses_full_graph_and_only_tests_baseline_and_selected_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            packed=root/'packed'
            packed.mkdir()
            (packed/'complete.json').write_text('{}')
            (packed/'dataset.json').write_text(json.dumps({'graph_version':GRAPH_VERSION,'storage':'recurrent_frames','source_sha256':'source','coverage':'all_recorded_decisions','total_recorded_pauses':1,'rows':[{'run':1,'seq':0,'split':'test'}],'frames':[{'run':1,'seq':0,'split':'test','decision':True}]}))
            seen=[]
            def fitted(packed,output,design,config,manifest):
                self.assertEqual(design,'full_world')
                seen.append(output.name)
                return {'graph_version':GRAPH_VERSION,'name':design,'configuration':config.mapping(),'validation':{'score':3-len(seen)}}
            def saved(path,value):
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(value))
            with patch('advisors.models.entity_graph.tracking.REGISTRY',root/'registry'),patch('advisors.models.entity_graph.world_tune.fit',side_effect=fitted),patch('advisors.models.entity_graph.world_tune.record',side_effect=saved),patch('advisors.models.entity_graph.world_tune.restore',return_value=(None,{})),patch('advisors.models.entity_graph.world_tune.evaluate',return_value={'score':99}) as evaluate:
                search(packed,root/'output',3,24,None)
            self.assertEqual(seen,['full_world','trial_001','trial_002'])
            self.assertEqual(evaluate.call_count,2)
            selected=json.loads((root/'output'/'selection.json').read_text())
            self.assertEqual(selected['selected'],'trial_002')
            state=json.loads((root/'output'/'tracking.json').read_text())
            self.assertEqual((state['state'],state['completed_fits']),('complete',3))

    def test_non_memory_errors_fail_the_search_instead_of_skipping_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'complete.json').write_text('{}')
            (root/'dataset.json').write_text(json.dumps({'graph_version':GRAPH_VERSION,'storage':'recurrent_frames','source_sha256':'source','coverage':'all_recorded_decisions','total_recorded_pauses':0,'rows':[],'frames':[]}))
            with patch('advisors.models.entity_graph.tracking.REGISTRY',root/'registry'),patch('advisors.models.entity_graph.world_tune.fit',side_effect=ValueError('data problem')):
                with self.assertRaisesRegex(ValueError,'data problem'):
                    search(root,root/'output',2,24,None)
            state=json.loads((root/'output'/'tracking.json').read_text())
            self.assertEqual(state['state'],'failed')


if __name__=='__main__':
    unittest.main()
