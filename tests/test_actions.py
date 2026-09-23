import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from interface.actions import gui
from interface.actions.catalogue import ACTIONS, BY_NAME, KEYS, TYPES
from interface.common import DEFAULT_DATA, DEFAULT_GAME
from interface.options.available import RULES


class CatalogueTests(unittest.TestCase):
    def test_every_action_has_an_options_rule_and_no_rule_is_orphaned(self):
        self.assertEqual(set(RULES),set(BY_NAME))

    def test_every_action_belongs_to_exactly_one_group(self):
        from interface.actions.catalogue import GROUPS
        listed=[name for names in GROUPS.values() for name in names]
        self.assertEqual(sorted(listed),sorted(BY_NAME))

    def test_action_names_are_unique(self):
        self.assertEqual(len(BY_NAME),len(ACTIONS))

    def test_every_parameter_has_a_known_kind(self):
        for action in ACTIONS:
            for param in action.params:
                self.assertIn(gui.split(param)[1],{*TYPES,*KEYS,'int','choice','event'},(action.name,param))

    def test_choice_actions_declare_their_choices(self):
        for action in ACTIONS:
            self.assertEqual(any(gui.split(p)[1]=='choice' for p in action.params),bool(action.choices),action.name)

    def test_every_placeholder_is_bound(self):
        for action in ACTIONS:
            for _,values in gui.variants(action):
                text=gui.fill(action.command+action.valid+action.context+''.join(d+c for chain in (action.alternatives or (action.datamodels,)) for d,c in chain),values)
                self.assertNotRegex(text,r'\{\w+\}',action.name)


class GeneratedGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEFAULT_GAME/'game').is_dir():
            raise unittest.SkipTest('game files not present')
        cls.hud=gui.hud(DEFAULT_GAME/'game')

    def test_braces_and_quotes_balance(self):
        self.assertEqual(self.hud.count('{'),self.hud.count('}'))
        self.assertEqual(self.hud.count('"')%2,0)

    def test_every_action_code_has_an_execute_and_a_check_state(self):
        for code,_ in enumerate(ACTIONS,1):
            self.assertIn(f'(CFixedPoint){code}\')',self.hud)

    def test_every_generated_callback_is_bracketed(self):
        texts=[*gui.windows(DEFAULT_GAME/'game').values(),gui.hud(DEFAULT_GAME/'game')]
        self.assertEqual([m for t in texts for m in re.findall(r'on_(?:start|finish) = "\[[^"]*"',t) if not m.endswith(']"')],[])

    def test_key_codes_are_unique_and_dense(self):
        codes=gui.key_codes(gui.key_table(DEFAULT_GAME/'game',()))
        self.assertEqual(sorted(codes.values()),list(range(1,len(codes)+1)))


class DataTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dump=DEFAULT_DATA/'profiles'/'mini'/'logs'/'data_types'
        if not dump.is_dir():
            raise unittest.SkipTest('game datatype dump not present')
        text='\n'.join(f.read_text(encoding='utf-8',errors='replace') for f in dump.glob('data_types_*.txt'))
        cls.types={m[1] for m in re.finditer(r'^([A-Z]\w*)\nDefinition type: Type',text,re.M)}
        cls.functions={m[1].split('(')[0].strip() for m in re.finditer(r'^([A-Z][\w.]*(?:\( [^)]*\))?)\nDefinition type: (?:Function|Promote)',text,re.M)}

    def test_every_cleanup_call_is_a_void_callback(self):
        text='\n'.join(f.read_text(encoding='utf-8',errors='replace') for f in (DEFAULT_DATA/'profiles'/'mini'/'logs'/'data_types').glob('data_types_*.txt'))
        returns={m[1]:m[2] for m in re.finditer(r'^([A-Z][\w.]*)(?:\( [^)]*\))?\nDefinition type: [\w ]+\nReturn type: (\S+)',text,re.M)}
        closers={call for text in gui.windows(DEFAULT_GAME/'game').values() for call in re.findall(r'name = interface_close [^}]*on_start = "\[([\w.]+)(?:\([\w.]*\))?\]"',text)}
        self.assertIn('PopupManager.HideTransportPlannerPopup',closers)
        for call in [*gui.AFTER,*closers]:
            self.assertEqual(returns.get(call),'void',call)

    def test_every_type_function_used_by_an_action_exists(self):
        for action in ACTIONS:
            for _,values in gui.variants(action):
                text=gui.fill(action.command+' '+action.valid+' '+action.context+' '+' '.join(d+' '+c for chain in (action.alternatives or (action.datamodels,)) for d,c in chain),values)
                for owner,member in re.findall(r'(?<![\w.])([A-Z]\w*)\.([A-Z]\w*)',text):
                    if owner in self.types:
                        self.assertIn(f'{owner}.{member}',self.functions,action.name)

    def test_every_typed_parameter_getter_exists_on_scope(self):
        for kind,(_,getter,_) in TYPES.items():
            self.assertIn(f'Scope.Get{getter}',self.functions,kind)


if __name__=='__main__':
    unittest.main()
