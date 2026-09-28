import unittest

from interface.recording.spec import EPOCH_DATE, TABLE
from interface.recording.tables import movement_modifiers, owning_types, ownership_owner

TYPES={10:'building_textile_mill',20:'building_manor_house',30:'building_financial_district',40:'building_company_basic_fabrics',
       50:'building_company_regional_headquarter',60:'building_farm',70:'building_regional_company_basic_fabrics',80:'building_company_basic_textiles'}
HEADQUARTERS={40:7}
OWNING=owning_types(['company_basic_fabrics','company_basic_textiles'])


class WarGoalTests(unittest.TestCase):
    def test_a_war_goal_outlives_its_diplomatic_play(self):
        optional={column.name:column.optional for column in TABLE['war_goal_history'].columns}
        self.assertTrue(optional['diplomatic_play'])
        self.assertFalse(optional['holder'] or optional['creator'] or optional['status'])


class OwnershipOwnerTests(unittest.TestCase):
    def owner(self,owner_type,owner):
        return ownership_owner(1,10,owner_type,owner,TYPES,HEADQUARTERS,OWNING)

    def test_each_owner_is_told_apart(self):
        self.assertEqual(self.owner(2,3),{'owner_kind':'country','owner_country':3,'owner_building':None,'owner_company':None})
        self.assertEqual(self.owner(1,10),{'owner_kind':'self','owner_country':None,'owner_building':10,'owner_company':None})
        self.assertEqual(self.owner(1,20)['owner_kind'],'manor_house')
        self.assertEqual(self.owner(1,30)['owner_kind'],'financial_district')
        self.assertEqual(self.owner(1,40),{'owner_kind':'company','owner_country':None,'owner_building':40,'owner_company':7})
        self.assertEqual(self.owner(1,70),{'owner_kind':'company_regional_headquarter','owner_country':None,'owner_building':70,'owner_company':None})

    def test_an_unknown_owner_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.owner(1,60)
        with self.assertRaises(RuntimeError):
            self.owner(3,10)
        with self.assertRaises(RuntimeError):
            self.owner(1,50)
        with self.assertRaises(RuntimeError):
            self.owner(1,80)


class MethodEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from interface.common import DEFAULT_GAME
        from interface.script import method_effects
        if not (DEFAULT_GAME/'game').exists():
            raise unittest.SkipTest('game files unavailable')
        cls.effects=method_effects(DEFAULT_GAME/'game')

    def test_every_table_is_keyed_uniquely(self):
        keys={'goods':4,'employment':3,'modifiers':4,'requirements':3,'ratios':2}
        for table,width in keys.items():
            rows=[row[:width] for row in self.effects[table]]
            self.assertEqual(len(rows),len(set(rows)),table)

    def test_simple_farming_matches_its_definition(self):
        self.assertIn(('pm_simple_farming','grain','output','workforce_scaled',20.0),self.effects['goods'])
        self.assertIn(('pm_simple_farming','laborers','level_scaled',4000.0),self.effects['employment'])
        self.assertIn(('pm_simple_farming','farmers','level_scaled',1000.0),self.effects['employment'])


class MovementModifierTests(unittest.TestCase):
    def test_a_modifier_held_twice_becomes_one_counted_row_with_the_latest_end(self):
        rows=movement_modifiers({0:[(7,100),(7,300),(8,50)]},{0:64},{7:'crushed',8:'other'}.get)
        self.assertEqual(rows,[{'political_movement':64,'modifier':'crushed','instances':2,'last_end_date':300},
                               {'political_movement':64,'modifier':'other','instances':1,'last_end_date':50}])

    def test_an_instance_without_an_end_keeps_the_modifier_open(self):
        rows=movement_modifiers({0:[(7,100),(7,EPOCH_DATE)]},{0:64},{7:'crushed'}.get)
        self.assertEqual(rows[0]['last_end_date'],EPOCH_DATE)


if __name__=='__main__':
    unittest.main()
