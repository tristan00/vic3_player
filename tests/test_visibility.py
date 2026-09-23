import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interface.visibility import Visibility

PLAYER = 7


def manifest(tables):
    handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump({'tables': tables, 'metrics': {'country|GetShown': 'ANY', 'country|GetMine': 'OWN',
                                             'country|GetHidden': 'NONE', 'country|GetSplit': 'OWN',
                                             'state|GetSplit': 'ANY'}}, handle)
    handle.close()
    return Visibility(handle.name)


def column(*values):
    return np.array(values, dtype=np.int64)


class VisibilityTests(unittest.TestCase):
    def test_dropped_table_is_absent(self):
        vis = manifest({'secret': {'disposition': 'drop'}})
        self.assertEqual(vis.apply({'secret': {'id': column(1)}}, PLAYER), {})

    def test_hidden_columns_are_removed_but_rows_are_kept(self):
        vis = manifest({'town': {'disposition': 'public', 'drop': ['seed']}})
        out = vis.apply({'town': {'id': column(1, 2), 'seed': column(9, 9), 'size': column(4, 5)}}, PLAYER)
        self.assertEqual(sorted(out['town']), ['id', 'size'])
        self.assertEqual(out['town']['size'].tolist(), [4, 5])

    def test_player_table_keeps_only_rows_owned_by_the_player(self):
        vis = manifest({'journal': {'disposition': 'player', 'drop': [], 'owner': ['column', 'country']}})
        rows = {'id': column(1, 2, 3), 'country': column(PLAYER, 4, PLAYER), 'goal': column(10, 20, 30)}
        out = vis.apply({'journal': rows}, PLAYER)
        self.assertEqual(out['journal']['goal'].tolist(), [10, 30])

    def test_global_rows_the_player_is_involved_in_are_kept_with_their_children(self):
        vis = manifest({'journal': {'disposition': 'player', 'drop': [], 'owner': ['involved', 'country', 'journal_involved']},
                        'journal_involved': {'disposition': 'player', 'drop': [], 'owner': ['via', 'journal']}})
        rows = {'journal': {'id': column(1, 2, 3), 'country': column(-1, -1, PLAYER)},
                'journal_involved': {'id': column(1, 1, 2), 'value': column(PLAYER, 4, 4)}}
        out = vis.apply(rows, PLAYER)
        self.assertEqual(out['journal']['id'].tolist(), [1, 3])
        self.assertEqual(out['journal_involved']['value'].tolist(), [PLAYER, 4])

    def test_self_owned_table_matches_on_its_own_id(self):
        vis = manifest({'technology': {'disposition': 'player', 'drop': [], 'owner': ['self']}})
        out = vis.apply({'technology': {'id': column(4, PLAYER), 'n': column(1, 2)}}, PLAYER)
        self.assertEqual(out['technology']['n'].tolist(), [2])

    def test_split_table_moves_private_columns_to_a_player_only_sibling(self):
        vis = manifest({'state': {'disposition': 'split', 'drop': ['seed'], 'private': ['wage'],
                                  'owner': ['column', 'country']}})
        rows = {'id': column(1, 2), 'country': column(PLAYER, 4), 'seed': column(9, 9),
                'pop': column(100, 200), 'wage': column(5, 6)}
        out = vis.apply({'state': rows}, PLAYER)
        self.assertEqual(sorted(out['state']), ['country', 'id', 'pop'])
        self.assertEqual(out['state']['pop'].tolist(), [100, 200])
        self.assertEqual(sorted(out['state_private']), ['id', 'wage'])
        self.assertEqual(out['state_private']['wage'].tolist(), [5])

    def test_child_table_inherits_ownership_through_its_parent(self):
        vis = manifest({'election': {'disposition': 'player', 'drop': [], 'owner': ['column', 'country']},
                        'election_vote': {'disposition': 'player', 'drop': [], 'owner': ['via', 'election']}})
        snapshot = {'election': {'id': column(1, 2), 'country': column(PLAYER, 4)},
                    'election_vote': {'id': column(1, 1, 2), 'votes': column(10, 11, 12)}}
        out = vis.apply(snapshot, PLAYER)
        self.assertEqual(out['election_vote']['votes'].tolist(), [10, 11])

    def test_either_ownership_keeps_rows_on_both_sides(self):
        vis = manifest({'relation': {'disposition': 'split', 'drop': [], 'private': ['score'],
                                     'owner': ['either', 'first_country', 'second_country']}})
        rows = {'id': column(1, 2, 3), 'first_country': column(PLAYER, 4, 5),
                'second_country': column(4, PLAYER, 6), 'score': column(10, 20, 30)}
        out = vis.apply({'relation': rows}, PLAYER)
        self.assertEqual(out['relation_private']['score'].tolist(), [10, 20])

    def test_runtime_identity_high_bits_do_not_defeat_owner_matching(self):
        vis = manifest({'journal': {'disposition': 'player', 'drop': [], 'owner': ['column', 'country']}})
        rows = {'id': column(1, 2), 'country': column(PLAYER | 0x4000000, 4), 'goal': column(10, 20)}
        out = vis.apply({'journal': rows}, PLAYER)
        self.assertEqual(out['journal']['goal'].tolist(), [10])

    def test_missing_via_parent_is_reported_not_a_raw_key_error(self):
        vis = manifest({'election': {'disposition': 'player', 'drop': [], 'owner': ['column', 'country']},
                        'election_vote': {'disposition': 'player', 'drop': [], 'owner': ['via', 'election']}})
        with self.assertRaises(RuntimeError) as caught:
            vis.apply({'election_vote': {'id': column(1), 'votes': column(10)}}, PLAYER)
        self.assertIn('election', str(caught.exception))

    def test_cyclic_owner_chain_is_rejected_not_infinite(self):
        vis = manifest({'a': {'disposition': 'player', 'drop': [], 'owner': ['via', 'b']},
                        'b': {'disposition': 'player', 'drop': [], 'owner': ['via', 'a']}})
        with self.assertRaises(RuntimeError) as caught:
            vis.apply({'a': {'id': column(1)}, 'b': {'id': column(1)}}, PLAYER)
        self.assertIn('cyclic', str(caught.exception))

    def test_table_with_no_verdict_is_rejected_rather_than_leaked(self):
        vis = manifest({'town': {'disposition': 'public', 'drop': []}})
        with self.assertRaises(RuntimeError) as caught:
            vis.apply({'town': {'id': column(1)}, 'brand_new': {'id': column(1)}}, PLAYER)
        self.assertIn('brand_new', str(caught.exception))

    def test_metric_groups_split_by_verdict(self):
        vis = manifest({})
        names = ['GetShown', 'GetMine', 'GetHidden']
        self.assertEqual(vis.metrics(names, 'country'), ['GetShown'])
        self.assertEqual(vis.player_metrics(names, 'country'), ['GetMine'])

    def test_a_metric_is_judged_per_scope_not_by_name(self):
        vis = manifest({})
        self.assertEqual(vis.metrics(['GetSplit'], 'state'), ['GetSplit'])
        self.assertEqual(vis.metrics(['GetSplit'], 'country'), [])
        self.assertEqual(vis.player_metrics(['GetSplit'], 'country'), ['GetSplit'])

    def test_metric_with_no_verdict_in_that_scope_is_rejected(self):
        vis = manifest({})
        with self.assertRaises(RuntimeError) as caught:
            vis.metrics(['GetShown'], 'state')
        self.assertIn('state|GetShown', str(caught.exception))

    def test_shipped_manifest_keeps_loyalists_public_per_state_but_private_per_country(self):
        vis = Visibility()
        for name in ('GetNumLoyalists', 'GetNumRadicals'):
            self.assertEqual(vis.metrics([name], 'state'), [name], name)
            self.assertEqual(vis.metrics([name], 'country'), [], name)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.vis = Visibility()

    def test_shipped_manifest_hides_the_engine_rng(self):
        self.assertEqual(self.vis.tables['global_rng']['disposition'], 'drop')

    def test_shipped_manifest_hides_unfired_events_and_ai_internals(self):
        for table in ('delayed_event', 'ai_building_construction', 'navy_ai_sea', 'character_dna'):
            self.assertEqual(self.vis.tables[table]['disposition'], 'drop', table)

    def test_shipped_manifest_restricts_technology_and_journal_to_the_player(self):
        for table in ('technology', 'technology_research_queue', 'journal_entry'):
            self.assertEqual(self.vis.tables[table]['disposition'], 'player', table)

    def test_shipped_manifest_keeps_publicly_visible_world_state(self):
        for table in ('building', 'pop', 'law', 'interest_group', 'market_goods'):
            self.assertIn(self.vis.tables[table]['disposition'], ('public', 'split'), table)

    def test_every_table_with_an_owner_can_resolve_it(self):
        for table, spec in self.vis.tables.items():
            if spec['disposition'] in ('player', 'split'):
                self.assertIn(spec['owner'][0], ('self', 'column', 'via', 'through', 'either', 'all', 'involved'), table)

    def test_a_row_owned_through_a_column_takes_its_parent_row_owner(self):
        import numpy as np
        from interface.visibility import Visibility
        vis = Visibility.__new__(Visibility)
        vis.tables = {'company': {'disposition': 'public', 'owner': ['column', 'country']},
                      'charter': {'disposition': 'split', 'private': ['unlock'], 'drop': [], 'owner': ['through', 'company', 'company']}}
        snapshot = {'company': {'id': np.array([5, 6]), 'country': np.array([1, 2])},
                    'charter': {'id': np.array([0, 1]), 'company': np.array([6, 5]), 'unlock': np.array([10, 20])}}
        kept = vis.apply(snapshot, 2)
        self.assertEqual(kept['charter_private']['unlock'].tolist(), [10])

    def test_every_via_owner_points_at_a_declared_table(self):
        for table, spec in self.vis.tables.items():
            if spec.get('owner', [''])[0] in ('via', 'through'):
                self.assertIn(spec['owner'][1], self.vis.tables, table)

    def test_every_via_chain_terminates_in_a_resolvable_owner(self):
        for table, spec in self.vis.tables.items():
            if spec['disposition'] not in ('player', 'split'):
                continue
            seen, owner = set(), spec['owner']
            while owner[0] == 'via' and owner[1] not in seen:
                seen.add(owner[1])
                owner = self.vis.tables[owner[1]].get('owner', ['none'])
            self.assertNotEqual(owner[0], 'none', table)
            self.assertNotEqual(owner[0], 'via', table)

