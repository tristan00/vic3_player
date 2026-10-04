import random
import re
import struct
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interface.common import DEFAULT_GAME
from interface.world.generate import CROSS, LAKE, LAND, OCEAN, _absent, _cells, _detach, _domains, _graph, _grow, _morton, _path, _size, _splnet, _straits

GAME = DEFAULT_GAME / 'game'


def neighbours_of(cells):
    found = {p: set() for p in range(1, int(cells.max()) + 1)}
    for a, b in _graph(cells):
        found[a].add(b)
        found[b].add(a)
    return found


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.domain = _domains(np.random.default_rng(3), 512, 256, .45, 6)
        cls.cells, cls.kinds = _cells(cls.domain.copy(), 40, 4, np.random.default_rng(3))

    def test_every_province_is_one_contiguous_piece(self):
        for index, box in enumerate(ndimage.find_objects(self.cells), 1):
            self.assertEqual(ndimage.label(self.cells[box] == index, CROSS)[1], 1, index)

    def test_the_sea_has_several_provinces_and_the_border_is_water(self):
        self.assertGreaterEqual(int((self.kinds == OCEAN).sum()), 2)
        border = np.concatenate([self.cells[0], self.cells[-1], self.cells[:, 0], self.cells[:, -1]])
        self.assertTrue((self.kinds[border] == OCEAN).all())

    def test_no_four_way_junctions(self):
        c = self.cells
        a, b, d, e = c[:-1, :-1], c[:-1, 1:], c[1:, :-1], c[1:, 1:]
        self.assertFalse(((a != b) & (a != d) & (a != e) & (b != d) & (b != e) & (d != e)).any())

    def test_lakes_never_touch_the_ocean(self):
        for a, b in _graph(self.cells):
            self.assertNotEqual({self.kinds[a], self.kinds[b]}, {LAKE, OCEAN})

    def test_growth_assigns_every_node_to_one_of_the_requested_groups(self):
        land = [p for p in range(1, len(self.kinds)) if self.kinds[p] == LAND]
        graph = {p: {q for q in n if self.kinds[q] == LAND} for p, n in neighbours_of(self.cells).items() if self.kinds[p] == LAND}
        centers = {p: np.argwhere(self.cells == p).mean(0) for p in land}
        owner, seeds = _grow(land, graph, centers, 5, [8] * 5, random.Random(1))
        self.assertEqual(set(owner), set(land))
        self.assertEqual(set(owner.values()), set(range(5)))

    def test_island_source_regions_seed_every_state_on_a_coast(self):
        nodes=list(range(12))
        neighbours={i:{j for j in (i-1,i+1) if j in nodes} for i in nodes}
        centers={i:np.array([i,0]) for i in nodes}
        candidates={0,5,11}
        owner,seeds=_grow(nodes,neighbours,centers,3,[4]*3,random.Random(1),candidates=candidates)
        self.assertEqual(set(seeds),candidates)
        self.assertEqual(set(owner),set(nodes))


class StraitTests(unittest.TestCase):
    def test_a_narrow_channel_between_landmasses_is_a_strait(self):
        cells = np.full((64, 128), 3, dtype=np.int32)
        cells[10:54, 10:60] = 1
        cells[10:54, 66:118] = 2
        cells[:, 64:] = np.where(cells[:, 64:] == 3, 4, cells[:, 64:])
        kinds = np.array([0, LAND, LAND, OCEAN, OCEAN], dtype=np.int8)
        straits = _straits(cells, kinds, neighbours_of(cells), 128, 5)
        self.assertEqual(len(straits), 1)
        self.assertEqual({straits[0]['from'], straits[0]['to']}, {1, 2})
        self.assertEqual(sorted(straits[0]['seas']), [3, 4])

    def test_distant_landmasses_have_no_strait(self):
        cells = np.full((64, 256), 3, dtype=np.int32)
        cells[10:54, 10:40] = 1
        cells[10:54, 200:240] = 2
        kinds = np.array([0, LAND, LAND, OCEAN], dtype=np.int8)
        self.assertEqual(_straits(cells, kinds, neighbours_of(cells), 256, 5), [])


class NetworkTests(unittest.TestCase):
    def test_spline_network_header_counts_and_pair_index(self):
        anchors = {100: (1.5, 2.5), 101: (9.5, 2.5), 0x10000000: (5.5, 2.5)}
        data = _splnet(anchors, [(1, [100, 0x10000000, 101])])
        self.assertEqual(struct.unpack_from('<HHHi', data, 0), (0xee, 1, 0x0c, 4))
        self.assertEqual(struct.unpack_from('<HHHHiHiHi', data, 10)[4::2], (3, 1, 1))
        key = struct.pack('<Q', 101 << 35 | 100 << 6 | 1)
        self.assertIn(key, data)

    def test_paths_stay_on_allowed_cells_and_end_exactly(self):
        cost = np.full((40, 80), np.inf)
        cost[5:35, 5:15] = 1
        cost[5:10, 5:75] = 1
        cost[5:35, 65:75] = 1
        route = _path(cost, (8, 30), (70, 30), ((0, 40), (0, 80)), 2, 6)
        self.assertEqual((route[0], route[-1]), ((8, 30), (70, 30)))
        for x, y in route[1:-1]:
            self.assertTrue(np.isfinite(cost[y - 1:y + 2, x - 1:x + 2]).any(), (x, y))
        self.assertTrue(any(y < 12 for _, y in route))

    def test_detached_states_leave_donors_connected_and_sit_away_from_their_new_owner(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 9} for i in range(1, 10)}
        ownership = {i: (i - 1) // 3 for i in range(1, 10)}
        before = dict(ownership)
        _detach(random.Random(2), ownership, [2, 5, 8], neighbours, set(range(1, 10)), 1)
        moved = [s for s in ownership if ownership[s] != before[s]]
        self.assertTrue(moved)
        for state in moved:
            self.assertNotIn(ownership[state], {ownership[n] for n in neighbours[state]})


class SizeTests(unittest.TestCase):
    def test_every_spline_cell_has_a_morton_index_inside_the_engine_grid(self):
        for provinces in range(10, 1200, 7):
            width, height, _ = _size(random.Random(provinces), provinces)
            cells = -(-max(width, height) // 128)
            worst = max(_morton(x, y) for x in range(-(-width // 128)) for y in range(-(-height // 128)))
            self.assertLess(worst, cells * cells, (width, height))


class AbsentTagTests(unittest.TestCase):
    def test_comparisons_with_absent_countries_become_false_and_scopes_stay(self):
        text = 'NOT = { c:FRA ?= this } c:XAA ?= this c:FRA ?= { x = 1 } c:RUS = root c:MEX ?=scope:target exists = c:FRA exists = c:XAA'
        self.assertEqual(_absent(text, {'XAA'}),
                         'NOT = { always = no } c:XAA ?= this c:FRA ?= { x = 1 } always = no always = no always = no exists = c:XAA')
