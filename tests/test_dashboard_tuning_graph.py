from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard.server.app import app
from advisors.models.entity_graph.schema import GRAPH_VERSION


class TuningGraphTests(unittest.TestCase):
    def test_tracker_has_an_explicit_empty_state_before_any_fits(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('dashboard.server.graph_tuning.ROOT',Path(directory)):
                response=TestClient(app).get('/api/tuning/world')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['current_graph_version'],GRAPH_VERSION)
            self.assertEqual(response.json()['runs'],[])

    def test_graph_tab_assets_are_available_without_exposing_source_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            review=root/'entity_graph_spatial_test'
            review.mkdir()
            (review/'review.json').write_text('{}')
            (review/'report.html').write_text('<h1>Full world</h1>')
            (review/'source.pkl.gz').write_bytes(b'private')
            client=TestClient(app)
            with patch('dashboard.server.tuning.ROOT',root):
                response=client.get('/tuning/world/report.html')
                self.assertEqual(response.status_code,200)
                self.assertIn('Full world',response.text)
                self.assertEqual(response.headers['cache-control'],'no-cache')
                for asset in ('source.pkl.gz','missing.html','graphs/full_world.html','%2e%2e%2fsource.pkl.gz'):
                    self.assertEqual(client.get('/tuning/world/'+asset).status_code,404)


if __name__=='__main__':
    unittest.main()
