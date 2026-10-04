from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np
from catboost import CatBoostRegressor

from advisors.models.histogram import data as pickers
from advisors.catalogue import LAW_ACTIONS, PARTY_ACTIONS
from advisors.data.features import HistoryLookup, KINDS, LEADER_ACTIONS, Leaders, LiveLookup, Versions
from advisors.data.histograms import Histograms, LEADER_IDEOLOGIES, LEADER_TRAITS, LEADERS, entries
from tests.memory_stored import Memory


class LeaderFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.groups={1:(7,20,11),2:(7,20,12),3:(7,None,13),4:(8,20,14),5:(7,None,None),6:(7,None,16)}
        self.characters={11:'royalist',12:'reformer',13:'royalist',14:'communist',15:'radical',16:None}
        self.traits=[(11,'charismatic'),(11,'ambitious'),(12,'charismatic'),(13,'cautious'),(14,'cruel'),(15,'reckless'),(16,'brave')]
        self.leaders=Leaders(7,self.groups,self.characters,self.traits,[(1,30,.1),(3,30,.2),(4,30,.3),(2,31,.1),(2,30,0)],{50:7,51:8})
        self.lookup=SimpleNamespace(leaders=self.leaders.at,typed=lambda kind,ident:f'{kind}_{ident}',character=self.characters.get)

    def political(self,batch):
        return [row for row in entries(batch,self.lookup) if row[0] in LEADERS]

    def test_group_actions_read_the_target_leader_and_keep_action_types_separate(self):
        found=self.political([('negotiate_with_interest_group',{'interest_group':1}),('invite_to_government',{'interest_group':2})])
        self.assertEqual(found,[(LEADER_IDEOLOGIES,'negotiate_with_interest_group.royalist',1),(LEADER_TRAITS,'negotiate_with_interest_group.ambitious',1),
                                (LEADER_TRAITS,'negotiate_with_interest_group.charismatic',1),
                                (LEADER_IDEOLOGIES,'invite_to_government.reformer',1),(LEADER_TRAITS,'invite_to_government.charismatic',1)])

    def test_party_reform_includes_every_member_but_no_foreign_party_or_unaffiliated_group(self):
        for action in PARTY_ACTIONS:
            with self.subTest(action=action):
                found=self.leaders.at(action,{'member':1})
                self.assertEqual(found,[('royalist',['ambitious','charismatic']),('reformer',['charismatic'])])
                self.assertEqual(self.leaders.at(action,{'member':3}),[])
                self.assertEqual(self.leaders.at(action,{'member':99}),[])
                histogram=Histograms([self.political([(action,{'member':1})])])
                self.assertEqual(histogram.counts[0,histogram.column[LEADER_TRAITS,f'{action}.charismatic']],2)

    def test_law_actions_include_all_player_group_leaders_once(self):
        for action in LAW_ACTIONS:
            with self.subTest(action=action):
                params={param:50 for param,_ in KINDS[action]}
                found=self.political([(action,params)])
                histogram=Histograms([found])
                self.assertEqual(histogram.counts[0,histogram.column[LEADER_IDEOLOGIES,f'{action}.royalist']],2)
                self.assertEqual(sum(weight for name,_,weight in found if name==LEADER_IDEOLOGIES),3)
                self.assertEqual(sum(weight for name,_,weight in found if name==LEADER_TRAITS),5)
                self.assertFalse(any('communist' in value or 'radical' in value for _,value,_ in found))

    def test_imposed_laws_use_the_subject_country_and_unknown_laws_stay_missing(self):
        self.assertEqual(self.leaders.at('impose_law',{'law':51}),[('communist',['cruel'])])
        self.assertEqual(self.leaders.at('impose_law',{'law':99}),[])

    def test_shared_leaders_and_repeated_traits_count_once_per_action(self):
        leaders=Leaders(7,{**self.groups,7:(7,None,11)},self.characters,self.traits+[(11,'ambitious')],[],{50:7})
        self.assertEqual(leaders.at('enact_trade_policy',{'law':50}),self.leaders.at('enact_trade_policy',{'law':50}))

    def test_movement_actions_include_only_its_player_group_supporters(self):
        for action in ('bolster_movement','stop_bolstering_movement','suppress_movement','stop_suppressing_movement'):
            with self.subTest(action=action):
                self.assertEqual(self.leaders.at(action,{'political_movement':30}),[('royalist',['ambitious','charismatic']),('royalist',['cautious'])])
                self.assertEqual(self.leaders.at(action,{'political_movement':99}),[])

    def test_character_actions_include_only_characters_who_actually_lead_a_group(self):
        actions=[action for action,params in KINDS.items() if any(kind=='character' for _,kind in params)]
        for action in actions:
            with self.subTest(action=action):
                params={param:11 if kind=='character' else 'order' if kind=='commander_order_type' else 'interaction' if kind=='interaction' else 50
                        for param,kind in KINDS[action]}
                found=self.political([(action,params)])
                self.assertIn((LEADER_IDEOLOGIES,f'{action}.royalist',1),found)
                self.assertIn((LEADER_TRAITS,f'{action}.charismatic',1),found)
                params['character']=15
                self.assertEqual(self.political([(action,params)]),[])

    def test_missing_leaders_and_ideologies_do_not_invent_bins_or_lose_known_traits(self):
        for group in (5,99):
            self.assertEqual(self.political([('negotiate_with_interest_group',{'interest_group':group})]),[])
        self.assertEqual(self.political([('negotiate_with_interest_group',{'interest_group':6})]),[(LEADER_TRAITS,'negotiate_with_interest_group.brave',1)])
        del self.characters[11]
        self.assertEqual(self.political([('negotiate_with_interest_group',{'interest_group':1})]),[])

    def test_unrelated_actions_do_not_load_leaders(self):
        lookup=SimpleNamespace(leaders=Mock(side_effect=AssertionError('unrelated action')))
        self.assertEqual(entries([('raise_taxes',{'level':'high'})],lookup),[('action','raise_taxes',1),('raise_taxes.level','level=high',1)])
        self.assertNotIn('raise_taxes',LEADER_ACTIONS)

    def test_repeated_actions_sum_and_selected_leader_bins_reach_catboost(self):
        batch=[('negotiate_with_interest_group',{'interest_group':1})]
        acted=[self.political(batch),self.political(batch*2),self.political([('negotiate_with_interest_group',{'interest_group':2})]),[]]
        actions=Histograms(acted)
        sizes={name:len(bins) for name,bins in actions.bins.items()}
        selected=actions.selected(sizes)
        self.assertEqual(len(selected),actions.total)
        np.testing.assert_array_equal(actions.count(acted,selected),actions.counts)
        self.assertEqual(actions.counts[1,actions.column[LEADER_IDEOLOGIES,'negotiate_with_interest_group.royalist']],2)
        self.assertFalse(actions.counts[-1].any())
        self.assertFalse(actions.count([[(LEADER_TRAITS,'negotiate_with_interest_group.unseen',1)]],selected).any())
        data=SimpleNamespace(state=np.zeros((4,len(pickers.STATE)),np.float32),laws=np.full((4,len(pickers.LAWS)),'none',object),
                             sizes=np.ones((4,1),np.float32),actions=actions,held=Histograms([[],[],[],[]]))
        rows=np.arange(4)
        pool=pickers.pool(data,sizes)(rows,rows,np.array([1.,2.,3.,0.]))
        model=CatBoostRegressor(iterations=3,depth=2,thread_count=1,verbose=False,allow_writing_files=False).fit(pool)
        self.assertTrue(set(actions.labels(sizes))<=set(model.feature_names_))
        self.assertTrue(np.isfinite(model.predict(pool)).all())


class LeaderHistoryTests(unittest.TestCase):
    def versions(self,rows):
        table=Versions.__new__(Versions)
        table.index={(4,key):([seq for seq,_ in values],[value for _,value in values]) for key,values in rows.items()}
        table.by_run={4:list(rows)}
        return table

    def test_live_and_history_match_through_leader_changes_removed_traits_and_deleted_groups(self):
        history=SimpleNamespace(player={4:7},terrain={4:{}},
                                groups=self.versions({(1,):[(1,(7,20,11)),(5,(7,20,12)),(9,None)],(2,):[(1,(7,20,13))]}),
                                characters=self.versions({(11,):[(1,('royalist',)),(7,('radical',))],(12,):[(5,('reformer',))],(13,):[(1,(None,)),(8,None)]}),
                                traits=self.versions({(11,'ambitious'):[(1,()),(4,None)],(11,'brave'):[(4,())],(12,'charismatic'):[(5,())],(13,'cautious'):[(1,())]}),
                                movements=self.versions({(1,30):[(1,(.1,)),(3,(0.,)),(5,(.1,)),(6,None)],(2,30):[(1,(.2,))]}),
                                law_rows=self.versions({(50,):[(1,('serfdom',7,False))]}))
        batches=[[('negotiate_with_interest_group',{'interest_group':1})],[('invite_party_to_government',{'member':1})],
                 [('enact_trade_policy',{'law':50})],[('suppress_movement',{'political_movement':30})],[('character_interaction',{'character':11,'interaction':'exile_character'})]]
        expected={0:[],1:[('royalist',['ambitious'])],4:[('royalist',['brave'])],5:[('reformer',['charismatic'])],7:[('reformer',['charismatic'])],8:[('reformer',['charismatic'])],9:[]}
        for seq,wanted in expected.items():
            with self.subTest(seq=seq):
                past=HistoryLookup(history,4,seq)
                tables={}
                for name,table,columns in [('interest_group_history',history.groups,['interest_group','country','party','leader']),
                                           ('character_history',history.characters,['character','ideology']),
                                           ('law_history',history.law_rows,['law','law_type','country','active']),
                                           ('character_assigned_trait',history.traits,['character','character_trait']),
                                           ('interest_group_movement_support',history.movements,['interest_group','political_movement','clout'])]:
                    tables[name]=[dict(zip(columns,(*key,*found))) for key in table.by_run[4] if (found:=table.at(4,key,seq)) is not None]
                snapshot=Memory(7,tables)
                live=LiveLookup.__new__(LiveLookup)
                live.player=7
                live.snapshot=snapshot
                live.characters=snapshot.map('character','character,ideology')
                live.typed=past.typed=lambda kind,ident:f'{kind}_{ident}'
                self.assertEqual(past.leaders('negotiate_with_interest_group',{'interest_group':1}),wanted)
                self.assertIs(live.leadership,live.leadership)
                self.assertIs(past.leadership,past.leadership)
                for batch in batches:
                    self.assertEqual(entries(batch,live),entries(batch,past))
                if seq==4:
                    self.assertEqual(past.leaders('suppress_movement',{'political_movement':30}),[(None,['cautious'])])
                if seq>=6:
                    self.assertNotIn(('reformer',['charismatic']),past.leaders('suppress_movement',{'political_movement':30}))


if __name__=='__main__':
    unittest.main()
