from functools import cache
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interface.recording.capture import (BUILDING_GATES, GROUPS, METHOD_GATES,
                               decision_block, method_block)
from interface.script import decisions, production_methods
from interface.common import DEFAULT_GAME

GAME = DEFAULT_GAME / 'game'


@cache
def generated():
    from interface.recording.capture import capture_body
    return capture_body(DEFAULT_GAME, 'XAA')


@cache
def event_widget():
    from interface.runner.control import event_capture_widget
    return event_capture_widget(DEFAULT_GAME)


class StartupTests(unittest.TestCase):
    def test_world_hud_survives_control_mod_generation(self):
        from tempfile import TemporaryDirectory
        from interface.runner.control import prepare
        from interface.runner.session import GameInterface
        with TemporaryDirectory() as directory:
            game=GameInterface('probe',data_dir=directory,quarterly_pause=True)
            root=Path(directory)/'world'
            (root/'gui').mkdir(parents=True)
            (root/'map_data').mkdir()
            for name in ('province_terrains.txt','default.map'):
                (root/'map_data'/name).write_text('')
            source=(GAME/'gui/ingame_hud.gui').read_text(encoding='utf-8-sig')
            source=source.replace('name = "ingame_hud"','name = "ingame_hud" widget = { name = interface_uniform_offer size = { 0 0 } }',1)
            (root/'gui/ingame_hud.gui').write_text(source,encoding='utf-8')
            mod=prepare(game,'XAA',{'mod':str(root),'width':100,'height':100,'countries':[],'states':[],'seas':[]})
            text=(mod/'gui/ingame_hud.gui').read_text(encoding='utf-8-sig')
            self.assertIn('name = interface_uniform_offer',text)
            self.assertIn('name = interface_ctrl',text)
            self.assertIn('name = interface_quarterly_pause',text)
            pulse=(mod/'common/on_actions/interface_quarterly.txt').read_text(encoding='utf-8-sig')
            self.assertIn('on_monthly_pulse',pulse)
            self.assertIn('OR = { month = 0 month = 3 month = 6 month = 9 }',pulse)
            scripted=(mod/'common/scripted_guis/interface.txt').read_text(encoding='utf-8-sig')
            self.assertIn('if = { limit = { NOT = { has_variable = interface_quarterly_pause } }',scripted)

    def test_loading_can_be_quiet_until_the_requested_startup_timeout(self):
        import json
        from tempfile import TemporaryDirectory
        from unittest.mock import MagicMock
        import numpy as np
        from interface.runner.session import GameInterface
        with TemporaryDirectory() as directory:
            game=GameInterface('probe',data_dir=directory)
            token=Path(directory)/'control/probe/session.json'
            token.parent.mkdir(parents=True)
            token.write_text(json.dumps({'startup_token':'ready'}))
            game._running=MagicMock()
            game.log=MagicMock()
            game.tail=MagicMock(fatal=None)
            game.tail.quiet.return_value=45
            reader=MagicMock()
            reader.table.return_value=({'id':np.array([1]),'country_definition':np.array([1])},None)
            reader.player.return_value=1
            reader.names=[(0,'GBR')]
            game._started=MagicMock(return_value=(reader,'1836.1.1'))
            game._wait=MagicMock()
            game.session=MagicMock(return_value={'started':0})
            self.assertTrue(game.ready('GBR',timeout=180)['ready'])

    def test_a_console_command_is_followed_by_a_long_gap(self):
        import re
        from interface.runner.control import CONSOLE_GAP, widget
        delays = [float(d) for d in re.findall(r'duration = ([\d.]+)', widget(['a', "ExecuteConsoleCommand('x')", 'b']))]
        self.assertGreaterEqual(delays[2], CONSOLE_GAP)

    def test_startup_commands_cannot_expire_together_during_a_loading_frame(self):
        from interface.runner.control import widget
        text=widget(["ExecuteConsoleCommand('a')", "ExecuteConsoleCommand('b')", 'c'])
        self.assertEqual(text.count('trigger_on_create = yes'),1)
        names=re.findall(r'name = (interface_execute_\w+)',text)
        triggered=re.findall(r"PdxGuiTriggerAllAnimations\('([^']+)'\)",text)
        self.assertEqual(triggered,names[1:])
        self.assertTrue(set(names).isdisjoint(re.findall(r'name = (interface_execute_\w+)',widget(['d']))))


class DecisionBlockTests(unittest.TestCase):
    def test_possible_is_recorded_inside_shown(self):
        block = decision_block('demo', 'a = yes', 'b = yes')
        self.assertLess(block.index('name = cap_decision target = flag:demo'), block.index('b = yes'))
        self.assertIn('name = cap_decision_possible target = flag:demo', block)
        self.assertEqual(block.count('{'), block.count('}'))

    def test_an_unevaluable_possible_is_marked_rather_than_guessed(self):
        block = decision_block('demo', 'a = yes', None)
        self.assertIn('name = cap_decision_unevaluable target = flag:demo', block)
        self.assertNotIn('cap_decision_possible', block)

    def test_shipped_decisions_all_generate_balanced_script(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        found = list(decisions(GAME))
        self.assertGreater(len(found), 40)
        for name, shown, possible in found:
            block = decision_block(name, shown, possible)
            self.assertEqual(block.count('{'), block.count('}'), name)


class ProductionMethodBlockTests(unittest.TestCase):
    def test_unconditional_method_is_always_reported(self):
        self.assertEqual(method_block('pm_x', {}), 'if = { limit = { always = yes } add_to_variable_list = { name = cap_method target = flag:pm_x } }')

    def test_technology_gate_is_required_not_optional(self):
        block = method_block('pm_x', {'unlocking_technologies': ['steel']})
        self.assertIn('has_technology_researched = steel', block)
        self.assertNotIn('OR = {', block)

    def test_multiple_unlocking_laws_are_alternatives(self):
        block = method_block('pm_x', {'unlocking_laws': ['law_a', 'law_b']})
        self.assertIn('OR = { has_law = law_type:law_a has_law = law_type:law_b }', block)

    def test_disallowing_laws_are_negated(self):
        block = method_block('pm_x', {'disallowing_laws': ['law_c']})
        self.assertIn('NOT = { has_law = law_type:law_c }', block)

    def test_principle_and_identity_gates_are_modelled(self):
        self.assertIn('has_principle = principle:p1',
                      method_block('pm_x', {'unlocking_principles': ['p1']}))
        self.assertIn('has_identity = identity:i1',
                      method_block('pm_x', {'unlocking_identity': ['i1']}))

    def test_building_scoped_gates_exclude_the_method(self):
        for gate in BUILDING_GATES:
            self.assertIsNone(method_block('pm_x', {gate: ['whatever']}), gate)

    def test_a_building_scoped_gate_wins_over_a_modelled_one(self):
        self.assertIsNone(method_block('pm_x', {'unlocking_technologies': ['steel'],
                                                'required_input_goods': ['electricity']}))

    def test_every_documented_gate_is_either_modelled_or_excluded(self):
        documented = {'unlocking_laws', 'unlocking_technologies', 'unlocking_production_methods',
                      'unlocking_global_technologies', 'unlocking_principles', 'unlocking_identity',
                      'required_input_goods', 'disallowing_laws', 'unlocking_religions',
                      'disallowing_religions', 'unlocking_geographic_regions',
                      'unlocking_company_categories'}
        self.assertEqual(documented - set(METHOD_GATES) - set(BUILDING_GATES), set())

    def test_shipped_methods_all_generate_balanced_script(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        found = list(production_methods(GAME))
        self.assertGreater(len(found), 300)
        for name, gates in found:
            block = method_block(name, gates)
            if block is not None:
                self.assertEqual(block.count('{'), block.count('}'), name)

    def test_no_shipped_method_has_an_unknown_gate(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        known = set(METHOD_GATES) | set(BUILDING_GATES)
        gating = {k for _n, g in production_methods(GAME) for k in g if k.startswith(('unlocking_', 'disallowing_', 'required_'))}
        self.assertEqual(gating - known, set())


class GeneratedCaptureTests(unittest.TestCase):
    def setUp(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        self.body = generated()

    def test_generated_script_has_balanced_braces_and_quotes(self):
        self.assertEqual(self.body.count('{'), self.body.count('}'))
        self.assertEqual(self.body.count('"') % 2, 0)

    def test_generated_script_never_reads_a_scope_it_does_not_push(self):
        saved = set(re.findall(r'save_(?:temporary_)?scope_as\s*=\s*(\w+)', self.body))
        self.assertEqual(set(re.findall(r'scope:(\w+)', self.body)) - saved, set())

    def test_generated_script_excludes_undeterminable_methods(self):
        for name, gates in production_methods(GAME):
            if method_block(name, gates) is None:
                self.assertNotIn('target = flag:' + name + ' ', self.body, name)

class MetricGroupTests(unittest.TestCase):
    def test_groups_are_disjoint_and_non_empty(self):
        self.assertTrue(GROUPS['public'])
        self.assertTrue(GROUPS['player'])
        self.assertTrue(GROUPS['state'])
        self.assertEqual(set(GROUPS['public']) & set(GROUPS['player']), set())

    def test_no_hidden_metric_is_requested(self):
        from interface.visibility import Visibility
        verdicts = Visibility().verdicts
        scopes = {'public': 'country', 'player': 'country', 'state': 'state'}
        for group in ('public', 'state'):
            for name in GROUPS[group]:
                self.assertIn(verdicts[scopes[group] + '|' + name], ('ANY', 'DERIVED'), name)
        for name in GROUPS['player']:
            self.assertEqual(verdicts['country|' + name], 'OWN', name)

    def test_every_listed_metric_is_either_requested_or_hidden(self):
        import json
        from pathlib import Path
        from interface.visibility import Visibility
        verdicts = Visibility().verdicts
        listed = json.loads((Path(__file__).resolve().parents[1] / 'interface' / 'recording' / 'metrics.json')
                            .read_text(encoding='utf-8'))
        requested = {('country', n) for n in GROUPS['public'] + GROUPS['player']}
        requested |= {('state', n) for n in GROUPS['state']}
        for scope in ('country', 'state'):
            for name in listed[scope]:
                if (scope, name) in requested:
                    continue
                self.assertIn(verdicts[scope + '|' + name], ('NONE', 'DEBUG', 'UNRESOLVED'),
                              f'{scope}|{name} is listed but never requested')


class CaptureBodyShapeTests(unittest.TestCase):
    def body(self):
        return generated()

    def test_the_capture_carries_the_request_nonce(self):
        self.assertIn('set_variable = { name = cap_seq value = var:interface_capture_seq }', self.body())

    def test_the_capture_never_writes_to_the_log(self):
        self.assertNotIn('debug_log', self.body())

    def test_capture_runs_as_a_console_event_so_player_relative_getters_resolve(self):
        from interface.runner.control import CAPTURE_WIDGET
        widget = CAPTURE_WIDGET('XAA')
        self.assertIn("ExecuteConsoleCommand('event interface_capture.1 XAA')", widget)
        self.assertNotIn("GetScriptedGui('interface_capture')", widget)


class MetricSignatureTests(unittest.TestCase):
    NUMERIC = {'int32', 'int64', 'int16', 'int8', 'uint32', 'uint64',
               'float', 'double', 'CFixedPoint', 'bool'}

    def setUp(self):
        import json
        import re
        from interface.common import DEFAULT_DATA
        dump = DEFAULT_DATA / 'profiles' / 'mini' / 'logs' / 'data_types'
        if not dump.is_dir():
            self.skipTest('game datatype dump not present')
        text = chr(10).join(f.read_text(encoding='utf-8', errors='replace')
                            for f in dump.glob('data_types_*.txt'))
        self.signatures = {}
        for found in re.finditer(r'^([A-Za-z_][\w.]*)(?:\( Arg0 \))?' + chr(10) + r'Definition type: Function'
                                 + chr(10) + r'Return type: (\S+)', text, re.M):
            self.signatures.setdefault(found[1], found[2])
        root = Path(__file__).resolve().parents[1]
        self.listed = json.loads((root / 'interface' / 'recording' / 'metrics.json').read_text(encoding='utf-8'))

    def test_every_requested_metric_exists_on_the_type_it_is_read_from(self):
        for scope, prefix in (('country', 'Country.'), ('state', 'State.')):
            for name in self.listed[scope]:
                self.assertIn(prefix + name.split('(')[0], self.signatures)

    def test_every_requested_metric_returns_a_number(self):
        for scope, prefix in (('country', 'Country.'), ('state', 'State.')):
            for name, kind in self.listed[scope].items():
                self.assertIn(self.signatures[prefix + name.split('(')[0]], self.NUMERIC, prefix + name)
                self.assertEqual(self.signatures[prefix + name.split('(')[0]], kind, prefix + name)

    def test_the_dump_is_the_one_this_game_build_produced(self):
        self.assertGreater(len(self.signatures), 10000)
        self.assertEqual(self.signatures['Front.GetPlayerAdvantageRaw'], 'int32')


class AbsentReferenceTests(unittest.TestCase):
    WORLD = {'states': [{'key': 'STATE_INTERFACE_1'}, {'key': 'STATE_INTERFACE_2'}],
             'countries': [{'tag': 'XAA'}, {'tag': 'XAB'}],
             'mod': str(DEFAULT_GAME / 'game')}

    def missing(self, text):
        from interface.recording.capture import missing_references
        return missing_references(text, self.WORLD)

    def test_every_way_a_trigger_names_absent_geography_is_caught(self):
        self.assertEqual(self.missing('owns = s:STATE_SINAI'), [('state region', 'STATE_SINAI')])
        self.assertEqual(self.missing('owns_entire_state_region = STATE_HOLLAND'),
                         [('state region', 'STATE_HOLLAND')])
        self.assertEqual(self.missing('has_interest_marker_in_region = sr:region_russia'),
                         [('strategic region', 'region_russia')])
        self.assertEqual(self.missing('c:AUS ?= this'), [('country', 'AUS')])

    def test_a_longer_prefix_ending_in_c_is_not_read_as_a_country(self):
        self.assertEqual(self.missing('abc:AUS'), [])
        self.assertEqual(self.missing('has_sc:AUS'), [])

    def test_references_the_world_does_contain_are_not_flagged(self):
        self.assertEqual(self.missing('owns = s:STATE_INTERFACE_1'), [])
        self.assertEqual(self.missing('owns_entire_state_region = STATE_INTERFACE_2'), [])
        self.assertEqual(self.missing('c:XAA ?= this'), [])

    def test_a_decision_whose_is_shown_is_unevaluable_is_dropped_entirely(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        from interface.recording.capture import capture_body, missing_references
        world = self.WORLD
        body = capture_body(DEFAULT_GAME, 'XAA', world)
        for name, shown, _ in decisions(GAME, [world['mod']]):
            marker = 'name = cap_decision target = flag:' + name + ' '
            if missing_references(shown, world):
                self.assertNotIn(marker, body, name)
            else:
                self.assertIn(marker, body, name)

    def test_a_vanilla_sized_world_filters_nothing(self):
        from interface.recording.capture import missing_references
        self.assertEqual(missing_references('owns = s:STATE_SINAI c:AUS ?= this', None), [])

    def test_the_generated_script_omits_decisions_gated_on_absent_regions(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        from interface.recording.capture import capture_body
        body = capture_body(DEFAULT_GAME, 'XAA', self.WORLD)
        self.assertNotIn('STATE_SINAI', body)
        self.assertNotIn('STATE_PANAMA', body)
        self.assertLess(body.count('name = cap_decision target = '), len(list(decisions(GAME))))


class EventCaptureWidgetTests(unittest.TestCase):
    def widget(self):
        return event_widget()

    def test_every_datamodel_uses_an_accessor_the_shipped_gui_also_uses(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        shipped = (GAME / 'gui' / 'outliner_ongoing_types.gui').read_text(encoding='utf-8-sig', errors='replace')
        for binding in re.findall(r'datamodel = "\[([^\]]+)\]"', self.widget()):
            root = binding.split('.')[0]
            self.assertIn(root + '.', shipped + 'Outliner.')

    def test_pending_event_categories_are_read_through_accessplayer(self):
        if not GAME.is_dir():
            self.skipTest('game install not present')
        body = self.widget()
        self.assertIn('AccessPlayer.GetEventsByCategory', body)
        self.assertNotIn('GetPlayer.GetEventsByCategory', body)


if __name__ == '__main__':
    unittest.main()
