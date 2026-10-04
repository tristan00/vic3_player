from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from interface.world.characters import scripts
from interface.world.generate import _rewrites


class CharacterTests(unittest.TestCase):
    def test_uniform_draw_imports_native_eligibility_and_preserves_native_hooks(self):
        with TemporaryDirectory() as directory:
            game=Path(directory)
            (game/'common/ideologies').mkdir(parents=True)
            (game/'common/on_actions').mkdir(parents=True)
            (game/'gui').mkdir()
            (game/'gui/generate_character.gui').write_text('item = { container = { datacontext = "[Character.GetCountry]" } }')
            (game/'gui/ingame_hud.gui').write_text('widget = { name = "ingame_hud" }')
            (game/'common/ideologies/test.txt').write_text('''ideology_child = { character_ideology = yes }
ideology_example = { character_ideology = yes country_trigger = { has_technology_researched = feminism game_date > 1900.1.1 }
non_interest_group_leader_trigger = { interest_group ?= { native_valid_trigger = yes } }
non_interest_group_leader_weight = { value = 0.1 } }
ideology_other = { character_ideology = yes country_trigger = { has_global_variable = invented } }
ideology_ig = { lawgroup_example = { law_a = approve } }''')
            (game/'common/on_actions/00_code_on_actions.txt').write_text('''on_game_started = { effect = { native_start = yes } }
on_game_started_after_lobby = { effect = { native_lobby = yes } }
on_character_creation = { effect = { native_creation = yes } }
on_character_became_adult = { effect = { native_adult = yes } }
on_character_spawned_in_pool = { effect = { native_pool = yes } }
on_character_recruitment = { effect = { native_recruitment = yes } }
on_character_death = { effect = { native_death = yes } }''')
            files={'common/history/global/interface.txt':'GLOBAL = { native_history = yes }'}
            scripts(game,files)
            effect=files['common/scripted_effects/interface_ideologies.txt']
            self.assertIn('chance = owner.var:interface_ideology_uniformity',effect)
            self.assertIn('owner = {  has_technology_researched = feminism game_date > 1900.1.1  }',effect)
            self.assertIn('interest_group ?= { native_valid_trigger = yes }',effect)
            self.assertIn('has_global_variable = invented',effect)
            self.assertNotIn('ideology_child',effect)
            self.assertNotIn('ideology_ig',effect)
            self.assertNotIn('value = 0.1',effect)
            self.assertEqual(effect.count('1 = { trigger ='),2)
            hooks=files['common/on_actions/00_code_on_actions.txt']
            self.assertEqual(hooks.count('interface_uniform_ideology = yes'),6)
            self.assertEqual(hooks.count('every_character = { interface_uniform_ideology = yes }'),2)
            self.assertNotIn('every_scope_character',hooks)
            self.assertIn('native_start = yes',hooks)
            self.assertIn('native_lobby = yes',hooks)
            self.assertIn('native_pool = yes',hooks)
            self.assertIn('native_recruitment = yes',hooks)
            self.assertIn('GuiScope.SetRoot(Character.MakeScope)',files['gui/generate_character.gui'])
            self.assertIn('AccessPlayer.AccessGeneralsOffer',files['gui/ingame_hud.gui'])
            self.assertIn('AccessPlayer.AccessAdmiralsOffer',files['gui/ingame_hud.gui'])
            self.assertIn('native_creation = yes',hooks)
            self.assertIn('native_adult = yes',hooks)
            self.assertIn('native_death = yes',hooks)
            self.assertIn('native_history = yes',files['common/history/global/interface.txt'])

    def test_character_home_references_are_rewritten_even_without_scoped_references(self):
        with TemporaryDirectory() as directory:
            game=Path(directory)
            folder=game/'common/character_templates'
            folder.mkdir(parents=True)
            (folder/'home.txt').write_text('person = { home_region = STATE_MISSING }')
            (folder/'donor.txt').write_text('person_two = { home_region = s:STATE_MISSING usage = { country_trigger = { this = c:FRA } } }')
            files=_rewrites(game,[],[],{}, {'XAA'},{'FRA':'XAA'})
            self.assertIn('home_region = random',files['common/character_templates/home.txt'])
            text=files['common/character_templates/donor.txt']
            self.assertNotIn('STATE_MISSING',text)
            self.assertNotIn('c:FRA',text)
            self.assertIn('this = c:XAA',text)
