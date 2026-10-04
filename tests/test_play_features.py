from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

from advisors.catalogue import PLAY_ACTIONS
from advisors.data.features import HistoryLookup, LiveLookup, Versions, play_values, target_context, target_links
from advisors.data.histograms import Histograms, PLAY, PLAY_CONTEXT, entries


class PlayFeaturesTests(unittest.TestCase):
    def test_each_start_play_variant_uses_its_target(self):
        lookup=SimpleNamespace(player=1,terrain={},state=Mock(return_value=('region',7)),country=lambda country:'major_power',
                               play=Mock(return_value=[-50,2.,.5]),context=Mock(return_value=([1,10,20,1,2,0],[('play.pacts','outgoing.non_aggression')])) )
        for action in PLAY_ACTIONS:
            with self.subTest(action=action):
                params={'state':12} if action=='start_diplomatic_play_for_state' else {'country':7}
                params['diplomatic_play_type']='dp_conquer_state'
                found=entries([(action,params)],lookup)
                self.assertEqual([row for row in found if row[0] in PLAY],[(PLAY[0],action,-50),(PLAY[1],action,2.),(PLAY[2],action,.5)])
                lookup.play.assert_called_with(7)
                histogram=Histograms([found])
                labels=histogram.labels({name:len(bins) for name,bins in histogram.bins.items()})
                self.assertTrue(all(f'{name}={action}' in labels for name in PLAY))
                self.assertTrue(all(f'{name}={action}' in labels for name in PLAY_CONTEXT))
                self.assertIn(f'play.pacts={action}.outgoing.non_aggression',labels)
                lookup.context.assert_called_with(7,params.get('state'))

    def test_other_actions_do_not_read_target_features(self):
        lookup=SimpleNamespace(play=Mock(side_effect=AssertionError('not a play')))
        found=entries([('raise_taxes',{'level':'high'})],lookup)
        self.assertFalse(any(name in PLAY for name,_,_ in found))

    def test_ratios_are_player_over_target_and_unknown_values_remain_missing(self):
        self.assertEqual(play_values(0,200,100,25,50),[0,2.,.5])
        self.assertEqual(play_values(-75,0,100,-10,20),[-75,0.,-.5])
        self.assertTrue(all(np.isnan(play_values(None,200,0,None,50))))

    def test_history_uses_pre_action_versions_and_matches_live_values(self):
        def versions(values):
            table=Versions.__new__(Versions)
            table.index={(4,(country,)):([1,5],[(value,),(value*10,)]) for country,value in values.items()}
            return table
        history=SimpleNamespace(player={4:1},terrain={4:{}},countries=versions({1:1,7:2}),relations=versions({7:-30}),gdp=versions({1:200,7:100}),prestige=versions({1:25,7:50}))
        historical=HistoryLookup(history,4,3)
        live=LiveLookup.__new__(LiveLookup)
        live.player=1
        live.countries={1:1,7:2}
        kept={}
        def memo(key,load):
            if key not in kept:
                kept[key]=load()
            return kept[key]
        maps={'player_relation':{7:-30},'country_economy_report':{1:200,7:100},'country_diplomacy_report':{1:25,7:50}}
        live.snapshot=SimpleNamespace(memo=memo,map=Mock(side_effect=lambda table,columns:maps[table]))
        self.assertEqual(historical.play(7),[-30,2.,.5])
        self.assertEqual(live.play(7),historical.play(7))
        live.play(7)
        self.assertEqual(live.snapshot.map.call_count,3)
        self.assertTrue(all(np.isnan(historical.play(99))))
        history.relations.index[(4,(7,))]=([1,2],[(-30,),None])
        self.assertEqual(historical.play(7)[0],0)

    def test_truces_pacts_treaties_and_land_adjacency_are_specific_to_target(self):
        links=target_links(1,240,[(7,480,120),(8,None,264)],[(1,7,'non_aggression'),(7,1,'rivalry'),(8,9,'alliance')],
                           [(10,1,7,False,100),(11,1,7,True,100),(12,8,9,False,100),(13,1,7,False,None),(14,1,7,False,241)],
                           [(10,'defensive_pact',None,None),(10,'guarantee_independence',7,1),(11,'alliance',1,7),(12,'military_access',8,9),
                            (13,'pending_agreement',1,7),(14,'future_agreement',1,7)],
                           [(1,1),(2,7),(3,7),(4,8)],[(100,1),(101,2),(102,3),(103,None),(104,4)],
                           [(100,101),(101,100),(100,103),(103,104)])
        values,pacts=target_context(links,7,3)
        self.assertEqual(values,[1,10,0,1,1,0])
        self.assertEqual(target_context(links,7,2)[0][-1],1)
        self.assertEqual(target_context(links,8,4)[0],[1,0,1,0,0,0])
        self.assertEqual(pacts,[('play.pacts','incoming.rivalry'),('play.pacts','outgoing.non_aggression'),
                               ('play.treaty_articles','incoming.guarantee_independence'),('play.treaty_articles','mutual.defensive_pact')])
        self.assertEqual(target_context(links,9,None),([0,0,0,0,0,0],[]))
        self.assertTrue(all(np.isnan(target_context(links,None,None)[0])))

    def test_expired_truces_and_removed_land_ownership_do_not_count(self):
        links=target_links(1,480,[(7,480,479)],[],[],[],[(1,8),(2,7)],[(100,1),(101,2)],[(100,101)])
        self.assertEqual(target_context(links,7,2),([0,0,0,0,0,0],[]))


if __name__=='__main__':
    unittest.main()
