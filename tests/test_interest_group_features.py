from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from advisors.data.features import GROUP_FEATURES, INTEREST_GROUPS, Latest, LiveLookup, NUMBERS, Versions, categories
from advisors.data.histograms import Histograms
from advisors.models.histogram import data as histogram
from advisors.models.row import features as row
from tests.test_politics_features import historical, snapshot

CLOUT=[0.,.05,.1,.15,.2,.25,.125,.125]
APPROVAL=[-15,-8,-2,0,4,9,14,19]


def lookups(seq):
    past=historical(seq)
    groups=Versions.__new__(Versions)
    groups.index={}
    groups.by_run={1:[]}
    stats=Latest.__new__(Latest)
    stats.index={}
    live=snapshot(seq)
    live.given['interest_group_history']=[]
    live.given['interest_group_stats']=[]
    expected=[]
    for i,kind in enumerate(INTEREST_GROUPS):
        group=10+i
        first=(7,None,None,kind,bool(i%2))
        second=(7,None,None,kind,not first[-1])
        third=None if i==0 else (9,*second[1:]) if i==1 else second
        groups.index[1,(group,)]=([0,4,8],[first,second,third])
        groups.by_run[1].append((group,))
        initial=[CLOUT[i],APPROVAL[i]]
        later=[CLOUT[i]/2,-APPROVAL[i]]
        stats.index[1,group]=([4],[later]) if i==2 else ([0],[initial]) if i==7 else ([0,4],[initial,later])
        present=seq<8 or i!=0
        owner=9 if seq>=8 and i==1 else 7
        government=first[-1] if seq<4 else second[-1]
        ratings=[np.nan,np.nan] if seq<4 and i==2 else initial if seq<4 or i==7 else later
        if present:
            live.given['interest_group_history'].append({'interest_group':group,'country':owner,'interest_group_type':kind,'in_government':government})
        if not (seq<4 and i==2):
            live.given['interest_group_stats'].append({'interest_group':group,'clout':ratings[0],'approval':ratings[1]})
        expected.extend([*ratings,float(government)] if present and owner==7 else [np.nan]*3)
        foreign=100+i
        groups.index[1,(foreign,)]=([0],[(9,None,None,kind,True)])
        groups.by_run[1].append((foreign,))
        stats.index[1,foreign]=([0],[[.99,-19]])
        live.given['interest_group_history'].append({'interest_group':foreign,'country':9,'interest_group_type':kind,'in_government':True})
        live.given['interest_group_stats'].append({'interest_group':foreign,'clout':.99,'approval':-19})
    past.h.groups=groups
    past.h.group_stats=stats
    return live,past,expected


class InterestGroupFeaturesTests(unittest.TestCase):
    def test_all_groups_follow_ownership_membership_and_stats_at_the_decision_snapshot(self):
        self.assertEqual(len(INTEREST_GROUPS),8)
        self.assertEqual(len(GROUP_FEATURES),24)
        for seq in (0,3,4,7,8,12):
            with self.subTest(seq=seq):
                source,past,expected=lookups(seq)
                live=LiveLookup(source)
                np.testing.assert_allclose(live.numbers,past.numbers,equal_nan=True)
                features=dict(zip(NUMBERS,past.numbers))
                np.testing.assert_allclose([features[name] for name in GROUP_FEATURES],expected,equal_nan=True)
                if seq<4:
                    self.assertEqual(features[GROUP_FEATURES[0]],0.)
                    self.assertEqual(features[GROUP_FEATURES[2]],0.)
                    self.assertTrue(np.isnan(features[GROUP_FEATURES[6]]))
                    self.assertEqual(features[GROUP_FEATURES[8]],0.)

    def test_both_catboost_encoders_always_include_all_twenty_four_numeric_features(self):
        source,past,expected=lookups(4)
        live=LiveLookup(source)
        state=past.numbers+live.prices+live.institutions+live.tariffs+live.taxes
        data=SimpleNamespace(state=np.array([state],np.float32),categories=np.array([categories(live)],object),
                             actions=Histograms([[]]),held=Histograms([[]]),sizes=np.ones((1,1),np.float32))
        encoder=histogram.Encoder(data.actions,data.held,{})
        with patch.object(histogram,'frame',wraps=histogram.frame) as encode,patch.object(histogram,'live_holdings',return_value=[]):
            training=histogram.pool(data,{})(np.array([0]),np.array([0]))
            decision=encoder.live(source,[[('form_army',{'option':30})]])
        trained_state=encode.call_args_list[0].args[0]
        live_state=encode.call_args_list[1].args[0]
        np.testing.assert_allclose(trained_state,live_state,equal_nan=True)
        self.assertEqual(training.get_feature_names(),decision.get_feature_names())
        numeric=dict(zip(histogram.STATE,state))
        training_rows=row.frame([{**row.context(SimpleNamespace(state=live)),**numeric,'action':'form_army'}])
        decision_rows=row.live(source,[('form_army',{'option':30})])
        for name,value in zip(GROUP_FEATURES,expected):
            with self.subTest(feature=name):
                index=training.get_feature_names().index(name)
                self.assertEqual(training.get_feature_names().count(name),1)
                self.assertNotIn(index,training.get_cat_feature_indices())
                self.assertIn(name,row.NUMERIC)
                self.assertNotIn(name,row.CATEGORICAL)
                self.assertAlmostEqual(float(live_state[0,index]),value,places=6)
                self.assertAlmostEqual(float(training_rows[name].iloc[0]),value,places=6)
                self.assertAlmostEqual(float(decision_rows[name].iloc[0]),value,places=6)


if __name__=='__main__':
    unittest.main()
