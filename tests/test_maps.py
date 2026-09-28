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
from interface.world.vanilla import vanilla
from interface.world.nations import FLAGS, SPECIAL, _partner, _picked, _pops, _techs, level, nations

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


class SamplingTests(unittest.TestCase):
    def test_eligible_draws_keep_the_vanilla_rate_per_country(self):
        data = {'trade': [None] * 100}
        picks = [len(_picked(random.Random(seed), data, 10, 50, list(range(25)))) for seed in range(400)]
        self.assertAlmostEqual(sum(picks) / len(picks) / 50, 0.1, delta=0.01)
        self.assertEqual(_picked(random.Random(1), data, 10, 50, []), [])

    def test_a_partner_respects_the_direction_of_a_lopsided_ratio(self):
        size = [1, 2, 8, 9]
        self.assertEqual(_partner(random.Random(1), size, 0, [1, 2, 3], 1 / 8), 2)
        self.assertIsNone(_partner(random.Random(1), size, 3, [2], 1 / 8))
        self.assertEqual(_partner(random.Random(1), size, 2, [0, 1, 3], 1.1), 3)


class NationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GAME.is_dir():
            raise unittest.SkipTest('game install not present')
        cls.data = vanilla(GAME)
        template = cls.data['templates'][0]
        cls.regions = [{'id': i, 'key': f'STATE_INTERFACE_{i}', 'province_ids': [i], 'province_codes': [f'x{i:06X}'],
                        'coastal': i % 2 == 0, 'arable_land': template['arable_land'], 'arable_resources': template['arable_resources'],
                        'capped': template['capped'], 'source': template} for i in range(1, 9)]
        cls.groups = [[1, 2, 3], [4, 5], [6], [7, 8]]
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        strategic = [{'key': 'region_interface_1', 'states': cls.regions}]
        cls.world = nations(random.Random(5), cls.data, cls.regions, cls.groups, [1, 4, 6, 7], neighbours, strategic, .5, .5, (.5, .5), .2, (.5, .5))

    @staticmethod
    def governed(world):
        return [c for c in world['countries'] if c['country_type'] != 'decentralized']

    def test_decentralized_nations_follow_vanilla_natives_and_stay_out_of_diplomacy(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        worlds = [nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                          [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .2, (.5, .5)) for seed in range(12)]
        natives = [(w, c) for w in worlds for c in w['countries'] if c['country_type'] == 'decentralized']
        self.assertTrue(natives)
        self.assertTrue(all(self.governed(w) for w in worlds))
        histories = {n['history'] for n in self.data['natives']}
        for world, country in natives:
            files, tag = world['files'], country['tag']
            self.assertIn(re.search(rf'^c:{tag} \?= \{{ (.*) \}}$', files['common/history/countries/interface.txt'], re.M)[1], histories)
            self.assertNotIn(f'{tag}_character', files['common/character_templates/interface.txt'])
            self.assertIn(f'region_state:{tag} = {{ }}', files['common/history/buildings/interface.txt'])
            for folder in ('diplomacy', 'treaties', 'diplomatic_plays', 'power_blocs', 'lobbies'):
                self.assertNotIn(f'c:{tag} ', files[f'common/history/{folder}/interface.txt'], folder)

    def test_every_starting_company_owns_a_building_of_its_own_type(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        founded = 0
        for seed in range(60):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                            [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .2, (.5, .5))
            files = world['files']
            for tag, company, state in re.findall(r'c:(\w+) \?= \{ add_company = company_type:(\w+) .*?set_company_state_region = s:(\w+)',
                                                 files['common/history/countries/interface.txt']):
                founded += 1
                kinds = self.data['companies'][company]
                block = re.search(rf's:{state} = \{{ region_state:{tag} = \{{ (.*) \}} \}}', files['common/history/buildings/interface.txt'])[1]
                self.assertTrue(re.search(rf'building = "\w+" add_ownership = \{{ company = \{{ type = {company} ', block), (seed, tag, company))
                owned = re.findall(rf'building = "(\w+)" add_ownership = \{{ company = \{{ type = {company} country = "c:{tag}" levels = (\d+)',
                                   files['common/history/buildings/interface.txt'])
                self.assertTrue(all(kind in kinds for kind, _ in owned))
                self.assertGreaterEqual(sum(int(levels) for _, levels in owned), 5, (seed, tag, company))
        self.assertTrue(founded)

    def test_every_state_is_owned_by_its_group(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        tags = [c['tag'] for c in nations(random.Random(5), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                                          [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .5, (.5, .5))['countries']]
        for tag, members in zip(tags, self.groups):
            for sid in members:
                self.assertEqual(self.regions[sid - 1]['country'], tag)

    def test_countries_are_new_and_not_vanilla(self):
        for country in self.world['countries']:
            self.assertEqual(country['tag'] in self.data['tags'], bool(country['copy']))
            self.assertEqual(country['culture'].startswith('culture_interface_'), not country['copy'])
            self.assertIn(country['religion'], {r['key'] for r in self.data['religions']})

    def test_generated_script_is_balanced_and_covers_the_vanilla_history_folders(self):
        files = self.world['files']
        for path, text in files.items():
            self.assertEqual(text.count('{'), text.count('}'), path)
        for folder in ['countries', 'population', 'characters', 'military_formations', 'states', 'pops', 'buildings', 'diplomacy', 'trade', 'ai']:
            self.assertIn(f'common/history/{folder}/interface.txt', files)
        for country in self.world['countries']:
            tag = country['tag']
            self.assertIn(f'c:{tag} ?=', files['common/history/countries/interface.txt'])
            self.assertIn(f'region_state:{tag}', files['common/history/pops/interface.txt'])
            if country['country_type'] != 'decentralized':
                self.assertIn(f'{tag}_character_1', files['common/character_templates/interface.txt'])

    def test_trade_follows_a_vanilla_country_of_similar_size(self):
        files = self.world['files']
        for country in self.governed(self.world):
            trade = country['trade']
            self.assertIn(trade, self.data['trade'])
            tag = country['tag']
            exports = re.findall(rf'region_state:{tag} = {{ sg:\w+ = {{ add_exports = (\d+)', files['common/history/trade/interface.txt'])
            self.assertEqual(len(exports), min(len(trade['exports']), len(country['produced'])))
            centers = re.findall(rf'building_trade_center" add_ownership = {{ \w+ = {{ (?:type = "\w+" )?country = "c:{tag}" levels = (\d+)', files['common/history/buildings/interface.txt'])
            self.assertEqual(sorted(map(int, centers), reverse=True), trade['centers'][:len(country['states'])])

    def test_treaties_come_from_vanilla_article_sets(self):
        kinds = {kind for treaty in self.data['treaties'] for kind, _ in treaty['articles']}
        text = self.world['files']['common/history/treaties/interface.txt']
        self.assertTrue(set(re.findall(r'article = (\w+)', text)) <= kinds)

    def test_buildings_and_pops_follow_the_template_state(self):
        template = self.data['templates'][0]
        allowed = set().union(*self.data['allowed'].values()) | set(template['arable_resources']) | set(template['capped'])
        buildings = self.world['files']['common/history/buildings/interface.txt']
        for kind in set(re.findall(r'building = "(building_\w+)"', buildings)):
            self.assertTrue(kind in template['buildings'] or kind in SPECIAL | {'building_port'}, kind)
            self.assertIn(kind, allowed | SPECIAL)
        pops = self.world['files']['common/history/pops/interface.txt']
        for chunk in pops.split('region_state:')[1:]:
            self.assertAlmostEqual(sum(map(int, re.findall(r'size = (\d+)', chunk))), self.data['province_population_range'][1], delta=self.data['province_population_range'][1] * .5)

    def test_country_types_are_vanilla_country_types(self):
        for country in self.world['countries']:
            self.assertIn(country['country_type'], {p['type'] for p in self.data['profiles']} | {'decentralized'})

    def test_armies_match_the_vanilla_country_of_similar_size(self):
        buildings = self.world['files']['common/history/buildings/interface.txt']
        for country in self.governed(self.world):
            barracks = re.findall(rf'building_barrack" add_ownership = {{ \w+ = {{ (?:type = "\w+" )?country = "c:{country["tag"]}" levels = (\d+)', buildings)
            law = next((law for law in country['laws'] if law in self.data['barracks_cap']), self.data['politics_army'][country['politics']])
            cap = self.data['barracks_cap'][law]
            self.assertTrue(all(int(level) <= cap for level in barracks))
            buildable = self.data['building_techs']['building_barrack'] <= self.data['tier_techs'][country['technology_tier']]
            self.assertEqual(sum(map(int, barracks)), min(country['trade']['barracks'], cap * len(country['states'])) if buildable else 0)
            self.assertEqual(country['trade']['tier'], country['technology_tier'])

    def test_personal_union_subjects_have_no_ruler_or_heir_of_their_own(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        worlds = (nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                          [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .2, (.5, .5))['files'] for seed in range(60))
        files = next(f for f in worlds if 'type = personal_union' in f['common/history/diplomacy/interface.txt'])
        templates = dict(re.findall(r'^(\w+) = (\{.*\})$', files['common/character_templates/interface.txt'], re.M))
        created = re.findall(r'^c:(\w+) \?= \{ create_character = \{ template = (\w+) \} \}$', files['common/history/characters/interface.txt'], re.M)
        for subject in re.findall(r'country = c:(\w+) type = personal_union', files['common/history/diplomacy/interface.txt']):
            for tag, key in created:
                if tag == subject:
                    self.assertNotRegex(templates[key], r'\b(ruler|heir) = yes')

    def test_levels_meet_the_vanilla_mean_at_half_and_the_top_at_one(self):
        self.assertEqual([level(value, 4, 10, 30) for value in (0, .25, .5, 1, 2)], [4, 7, 10, 30, 70])

    def test_populations_scale_to_the_requested_province_level(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        sizes = []
        for seed in range(30):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                            [{'key': 'region_interface_1', 'states': self.regions}], .5, 1, (.5, .5), .2, (.5, .5))
            sizes += [sum(map(int, re.findall(r'size = (\d+)', chunk))) for chunk in world['files']['common/history/pops/interface.txt'].split('region_state:')[1:]]
        top = self.data['province_population_range'][2]
        self.assertAlmostEqual(sum(sizes) / len(sizes), top, delta=top * .1)
        self.assertGreater(len({size for size in sizes}), 10)

    def test_the_lowest_tech_level_gives_every_country_the_vanilla_minimum(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        counts = []
        for seed in range(20):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                            [{'key': 'region_interface_1', 'states': self.regions}], 0, .5, (.5, .5), 0, (.5, .5))
            governed = {c['tag'] for c in self.governed(world)}
            counts += [line.count('add_technology_researched') for line in world['files']['common/history/countries/interface.txt'].splitlines()
                       if line.startswith('c:') and line[2:5] in governed and 'add_technology_researched' in line]
        low, mean, _ = self.data['tech_range']
        self.assertEqual(min(counts), low)
        self.assertGreater(counts.count(low), len(counts) / 3)
        self.assertLess(sum(counts) / len(counts), (low + mean) / 2)

    def test_extra_technologies_have_their_prerequisites(self):
        base = self.data['tier_techs'][max(self.data['tier_techs'])]
        requires = self.data['tech_requires']
        grown = _techs(random.Random(3), base, len(base) + 20, requires)
        self.assertEqual(len(grown), len(base) + 20)
        self.assertTrue(all(requires[tech] <= grown for tech in grown - base))
        shrunk = _techs(random.Random(3), grown, len(base), requires)
        self.assertEqual(len(shrunk), len(base))
        self.assertTrue(all(requires.get(tech, set()) & grown <= shrunk for tech in shrunk))

    def test_pop_shares_follow_the_sampled_vanilla_mix(self):
        state = self.regions[0]
        own, first, second = ({'key': f'culture_interface_{i}', 'religion': 'religion_a'} for i in range(1, 4))
        religions = [{'key': 'religion_a'}, {'key': 'religion_b'}]
        mix = {'primary': 0.2, 'others': [0.5, 0.2, 0.1], 'faith': 0.1}
        total, pops, homelands = _pops(random.Random(1), state, own, [first, second], religions, mix, 1)
        sizes = {(culture, religion or None): int(size) for culture, religion, size in
                 re.findall(r'culture = (\w+) +(?:religion = (\w+) +)?size = (\d+)', pops)}
        self.assertAlmostEqual(sizes[('culture_interface_2', None)] / total, 0.4, places=3)
        self.assertAlmostEqual(sizes[('culture_interface_2', 'religion_b')] / total, 0.1, places=3)
        self.assertAlmostEqual(sizes[('culture_interface_1', None)] / total, 0.3, places=3)
        self.assertAlmostEqual(sizes[('culture_interface_3', None)] / total, 0.2, places=3)
        self.assertEqual(homelands, ['culture_interface_1', 'culture_interface_2', 'culture_interface_3'])

    def test_every_character_copies_a_vanilla_character_of_its_role(self):
        records = [r for pool in self.data['rulers'].values() for r in pool] + [r for cast in self.data['casts'].values() for r in cast] + list(self.data['rulers_of'].values())
        known = {(r['role'], r['female'], tuple(r['traits'])) for r in records}
        roles = {flag: role for role, flag in FLAGS.items()}
        for line in self.world['files']['common/character_templates/interface.txt'].splitlines():
            if '_character_' not in line:
                continue
            role = next(role for flag, role in roles.items() if flag in line)
            traits = tuple(re.search(r'traits = \{ ([^}]*)\}', line)[1].split())
            self.assertIn((role, 'female = yes' in line, traits), known, line)

    def many(self, modernity, copies, seeds=40):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        return [country for seed in range(seeds) for country in nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours,
                [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (modernity, modernity), copies, (.5, .5))['countries'] if country['country_type'] != 'decentralized']

    def test_the_copied_share_of_governments_matches_a_top_vanilla_country_whole(self):
        countries = self.many(.5, .5, 25)
        copied = [c for c in countries if c['copy']]
        self.assertAlmostEqual(len(copied) / len(countries), .5, delta=.08)
        self.assertEqual([c for c in self.many(.5, 0, 10) if c['copy']], [])
        for country in copied:
            source = self.data['governments'][country['copy']]
            self.assertEqual((country['laws'], country['ruling'], country['politics']), (list(source['laws'].values()), source['ruling'], source['politics']))
            self.assertEqual((country['tag'], country['name'], country['country_type'], country['tier']), (source['tag'], source['name'], source['type'], source['rank']))

    def test_only_journal_entries_free_of_vanilla_places_and_countries_are_kept(self):
        kept = {tag: re.findall(r'type = (\w+)', ' '.join(source['journal'])) for tag, source in self.data['governments'].items()}
        self.assertEqual(kept['JAP'], ['je_sakoku', 'je_tenpo_crisis'])
        self.assertEqual(kept['FRA'], ['je_divided_monarchists'])
        self.assertEqual(kept['GBR'], [])
        self.assertIn('if = { limit = { has_dlc_feature = ep2_content } add_journal_entry = { type = je_sakoku } add_journal_entry = { type = je_tenpo_crisis } }', self.data['governments']['JAP']['journal'])

    def test_a_copied_country_keeps_its_vanilla_flag_name_and_characters(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        world = nations(random.Random(3), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours, [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), 1, (.5, .5))
        for country in world['countries']:
            if country['country_type'] == 'decentralized':
                continue
            tag = country['tag']
            self.assertIn(tag, self.data['governments'])
            self.assertNotIn(f'common/coat_of_arms/coat_of_arms/{tag}.txt', world['files'])
            self.assertFalse([line for line in world['localization'] if line.startswith(f' {tag}:')])
            self.assertIn(f'{tag} = {{ color = {{ {self.data["governments"][tag]["color"]} }} country_type = {self.data["governments"][tag]["type"]} ', world['files']['common/country_definitions/interface.txt'])
            source = self.data['governments'][tag]
            self.assertIn(f'cultures = {{ {" ".join(source["cultures"])} }}', next(line for line in world['files']['common/country_definitions/interface.txt'].splitlines() if line.startswith(tag)))
            self.assertEqual(country['culture'], source['cultures'][0])
            history = next(line for line in world['files']['common/history/countries/interface.txt'].splitlines() if line.startswith(f'c:{tag} '))
            for line in source['journal']:
                self.assertIn(line, history)
            pops = ' '.join(re.search(rf's:{key} = \{{ region_state:{tag} = \{{ (.*) \}} \}}', world['files']['common/history/pops/interface.txt'])[1] for key in country['states'])
            self.assertIn(f'culture = {source["cultures"][0]} ', pops)
            ruler = self.data['rulers_of'][tag]
            self.assertIn(f'{tag}_character_1 = {{ first_name = {ruler["first"]} last_name = {ruler["last"]} ', world['files']['common/character_templates/interface.txt'])

    def test_no_vanilla_government_is_copied_twice_in_one_world(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        for seed in range(20):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours, [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), 1, (.5, .5))
            copies = [c['copy'] for c in world['countries'] if c['copy']]
            self.assertEqual(len(copies), len(set(copies)))
            self.assertEqual(len(copies), sum(c['country_type'] != 'decentralized' for c in world['countries']))

    def test_diversity_moves_the_share_of_people_outside_the_primary_culture(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}

        def minority(diversity):
            inside = everyone = 0
            for seed in range(15):
                world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours, [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .5, (diversity, diversity))
                pops = world['files']['common/history/pops/interface.txt']
                for country in world['countries']:
                    if country['country_type'] == 'decentralized':
                        continue
                    for key in country['states']:
                        found = re.search(rf's:{key} = \{{ region_state:{country["tag"]} = \{{ (.*) \}} \}}', pops)[1]
                        for culture, size in re.findall(r'culture = (\w+) +(?:religion = \w+ +)?size = (\d+)', found):
                            everyone += int(size)
                            inside += int(size) * (culture == country['culture'])
            return 1 - inside / everyone
        national, middle, plural = minority(0), minority(.5), minority(1)
        self.assertLess(national, middle)
        self.assertLess(middle, plural)
        self.assertGreater(plural - national, .2)

    def test_countries_of_one_world_differ_in_diversity_more_than_their_own_states_do(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        within, between = [], []
        for seed in range(25):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours, [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .5, (0, 1))
            pops = world['files']['common/history/pops/interface.txt']
            means = []
            for country in world['countries']:
                if country['country_type'] == 'decentralized':
                    continue
                shares = []
                for key in country['states']:
                    sizes = [(culture, int(size)) for culture, size in re.findall(r'culture = (\w+) +(?:religion = \w+ +)?size = (\d+)',
                             re.search(rf's:{key} = \{{ region_state:{country["tag"]} = \{{ (.*) \}} \}}', pops)[1])]
                    shares.append(sum(size for culture, size in sizes if culture == country['culture']) / sum(size for _, size in sizes))
                means.append(sum(shares) / len(shares))
                within += [share - means[-1] for share in shares]
            between += [mean - sum(means) / len(means) for mean in means]
        spread = lambda values: (sum(value ** 2 for value in values) / len(values)) ** .5
        self.assertGreater(spread(between), .2)
        self.assertLess(spread(within), spread(between))

    def test_every_country_draws_its_own_modernity_and_diversity(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        drawn = []
        for seed in range(20):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours, [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (0, 1), .5, (0, 1))
            governed = [c for c in world['countries'] if c['country_type'] != 'decentralized']
            drawn += [(c['modernity'], c['diversity']) for c in governed]
            self.assertGreater(len({c['modernity'] for c in governed}), 1)
            self.assertGreater(len({c['diversity'] for c in governed}), 1)
        for position in (0, 1):
            values = sorted(pair[position] for pair in drawn)
            self.assertTrue(0 <= values[0] < .1 and .9 < values[-1] <= 1)
            self.assertAlmostEqual(sum(values) / len(values), .5, delta=.08)

    def test_law_modernity_moves_the_mean_progressiveness_of_generated_laws(self):
        def mean(modernity):
            found = self.many(modernity, 0, 15)
            return sum(self.progress(c) for c in found) / len(found)
        low, middle, high = mean(0), mean(.5), mean(1)
        self.assertLess(low, middle)
        self.assertLess(middle, high)
        self.assertGreater(high - low, 10)

    def progress(self, country):
        held = {**self.data['politics_laws'][country['politics']], **{self.data['law_groups'][law]: law for law in country['laws']}}
        return sum(self.data['law_progress'][law] for law in held.values()) / len(held)

    def test_commanders_follow_the_vanilla_rate_per_unit_and_are_all_posted(self):
        neighbours = {i: {j for j in (i - 1, i + 1) if 1 <= j <= 8} for i in range(1, 9)}
        generals = units = 0
        for seed in range(50):
            world = nations(random.Random(seed), self.data, self.regions, self.groups, [1, 4, 6, 7], neighbours, [{'key': 'region_interface_1', 'states': self.regions}], .5, .5, (.5, .5), .2, (.5, .5))
            formations = world['files']['common/history/military_formations/interface.txt']
            templates = world['files']['common/character_templates/interface.txt']
            generals += templates.count('is_general = yes')
            units += sum(c['army'] for c in world['countries'])
            created = re.findall(r'create_character = \{ template = (\w+) save_scope_as', formations)
            self.assertEqual(sorted(created), sorted(re.findall(r'scope:(\w+) = \{ transfer_to_formation', formations)))
            for country in world['countries']:
                if not country['army']:
                    self.assertNotIn(f'scope:army_{country["tag"]}', formations)
        self.assertLess(generals / units, self.data['generals_per_unit'] * 1.1)
        self.assertGreater(generals / units, self.data['generals_per_unit'] * .5)

    def test_every_character_has_a_birth_date(self):
        lines = [line for line in self.world['files']['common/character_templates/interface.txt'].splitlines() if '_character_' in line]
        self.assertTrue(lines)
        self.assertTrue(all('birth_date = ' in line for line in lines))

    def test_every_character_name_is_localized(self):
        localized = {line.split(':')[0].strip() for line in self.world['localization']}
        for key in re.findall(r'_name = (nm_\w+)', self.world['files']['common/character_templates/interface.txt']):
            self.assertIn(key, localized)


if __name__ == '__main__':
    unittest.main()
