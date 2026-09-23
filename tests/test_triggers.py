import unittest

from interface.common import DEFAULT_GAME
from tests.memory_stored import Memory
from interface.options.triggers import COMPARE, country_scope, evaluate, parse, unsupported
from interface.script import BLOCK_FIELDS, body, fields, read


class TriggerTests(unittest.TestCase):
    def test_parse_keeps_nesting_and_comparisons(self):
        nodes=parse('has_trait = brave OR = { a = b c ?= { value >= 0.5 } }')
        self.assertEqual(nodes[0],('has_trait','=','brave'))
        self.assertEqual(nodes[1][2][1],('c','?=',[('value','>=','0.5')]))
        self.assertTrue(COMPARE['>='](0.5,0.5))

    def test_every_captured_trigger_uses_supported_keys(self):
        for folder,wanted in BLOCK_FIELDS.items():
            for name,text in read(DEFAULT_GAME/'game',folder):
                for field,values in fields(body(text)):
                    if folder=='common/commander_orders' and field=='possible':
                        self.assertEqual(unsupported(parse(' '.join(values))),set(),f'{folder} {name}')


def journal_snapshot(player,entries):
    rows={'country_history':[{'country':country} for country in (7,9,4)],
          'journal_entry_history':[{'journal_entry':ident,'country':country,'journal_entry_type':kind,'active':active} for ident,country,kind,active,_ in entries],
          'journal_entry_involved_country':[{'journal_entry':ident,'country':member} for ident,*_,involved in entries for member in involved]}
    return Memory(player,rows)


class JournalTriggerTests(unittest.TestCase):
    def test_only_active_entries_count_including_global_ones_the_country_is_involved_in(self):
        s=journal_snapshot(7,[(1,None,'je_war',True,[7,9]),(2,7,'je_potential',False,[]),(3,7,'je_own',True,[])])
        held=lambda country,kind:evaluate(parse(f'has_journal_entry = {kind}'),country_scope(s,country))
        self.assertTrue(held(7,'je_war'))
        self.assertTrue(held(9,'je_war'))
        self.assertTrue(held(7,'je_own'))
        self.assertFalse(held(7,'je_potential'))
        self.assertFalse(held(4,'je_war'))

    def test_the_play_rule_uses_only_supported_triggers(self):
        rule=dict(read(DEFAULT_GAME/'game','common/scripted_rules'))['can_start_diplomatic_plays_against']
        self.assertEqual(unsupported(parse(body(rule))),set())
