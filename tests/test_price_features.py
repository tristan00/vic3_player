import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from advisors.data.features import GOODS, PRICES, HistoryLookup, Versions, WorldPrices, prices

FIRST,SECOND,THIRD=GOODS[:3]


def samples(rows):
    connection=Mock()
    connection.execute.return_value.fetchall.return_value=rows
    return WorldPrices(connection,[7,8])


class PriceFeaturesTests(unittest.TestCase):
    def test_every_good_has_its_price_and_its_price_above_the_world_price(self):
        self.assertEqual(PRICES,[f'price.{goods}' for goods in GOODS]+[f'price_above_world.{goods}' for goods in GOODS])
        found=prices({FIRST:30.,SECOND:20.},{FIRST:25.,THIRD:9.})
        self.assertEqual(len(found),len(PRICES))
        ours,above=found[:len(GOODS)],found[len(GOODS):]
        self.assertEqual((ours[0],ours[1],above[0]),(30.,20.,5.))
        self.assertTrue(math.isnan(above[1]) and math.isnan(ours[2]) and math.isnan(above[2]))

    def test_the_world_price_is_the_latest_sample_at_or_before_the_snapshot(self):
        world=samples([(7,FIRST,0,10.),(7,FIRST,4,12.),(7,SECOND,4,50.),(8,FIRST,2,99.)])
        self.assertEqual(world.at(7,0),{FIRST:10.})
        self.assertEqual(world.at(7,3),{FIRST:10.})
        self.assertEqual(world.at(7,5),{FIRST:12.,SECOND:50.})
        self.assertEqual(world.at(8,1),{})
        self.assertEqual(world.at(9,5),{})

    def test_a_recorded_pause_compares_the_players_market_with_the_world(self):
        markets,goods=Versions.__new__(Versions),Versions.__new__(Versions)
        markets.index={(7,(1,)):([0],[(3,)])}
        goods.index={(7,(3,FIRST)):([0,4],[(30.,),(40.,)]),(7,(5,FIRST)):([0],[(1.,)])}
        goods.by_run={7:[(3,FIRST),(5,FIRST)]}
        history=SimpleNamespace(player={7:1},terrain={7:{}},markets=markets,goods=goods,world=samples([(7,FIRST,0,10.),(7,FIRST,4,12.)]))
        early,late=HistoryLookup(history,7,2).prices,HistoryLookup(history,7,4).prices
        self.assertEqual((early[0],early[len(GOODS)],late[0],late[len(GOODS)]),(30.,20.,40.,28.))


if __name__=='__main__':
    unittest.main()
