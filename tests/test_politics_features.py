from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from advisors.data.features import HistoryLookup, LiveLookup, NUMBERS, Samples, Versions, categories
from advisors.data.histograms import Histograms
from advisors.models.histogram import data as histogram
from advisors.models.row import features as row
from tests.memory_stored import Memory

FIELDS=['government_legitimacy','radicals_percent']
POPULATIONS=[[900,80,20,100],[800,150,50,300],[0,0,0,0]]


def historical(seq):
    constant=lambda values:SimpleNamespace(at=lambda *args:values)
    population=Samples.__new__(Samples)
    population.index={1:([0,4,8],POPULATIONS)}
    legitimacy=Versions.__new__(Versions)
    legitimacy.index={(1,(7,)):([0,4,6],[(35,),(80,),None]),(1,(9,)):([0],[(99,)])}
    empty=SimpleNamespace(at=lambda *args:None,live=lambda *args:[],by_run={})
    history=SimpleNamespace(player={1:7},terrain={1:{}},treasury=constant([100.,20.,5.]),population=population,politics=constant([0.]),
                            legitimacy=legitimacy,budget=empty,interest=1,sol=empty,construction=empty,gdp=empty,military=empty,
                            government=set(),army=set(),wars=empty,queue=empty,groups=empty,infamy=constant([0.]),policy=constant([0,0,0]))
    return HistoryLookup(history,1,seq)


def snapshot(seq):
    population=POPULATIONS[0 if seq<4 else 1 if seq<8 else 2]
    politics=[{'country':9,'government_legitimacy':99}]
    if seq<6:
        politics.append({'country':7,'government_legitimacy':35 if seq<4 else 80})
    value=Memory(7,{'player_treasury':[{'money':100.,'principal':20.,'balance_trend_current':5.}],
                    'player_population':[dict(zip(['lower_strata','middle_strata','upper_strata','radicals'],population))],
                    'player_politics':[{'power_delta_bureaucracy':0.}],
                    'player_policy':[{'tax_level':0,'government_wage_level':0,'military_wage_level':0}],
                    'country_history':[{'country':7,'country_rank':'major_power'},{'country':9,'country_rank':'minor_power'}],
                    'country_diplomacy':[{'country':7,'infamy':0.}],
                    'country_politics_report':politics})
    value.run_id,value.seq,value.ruleset_id=1,seq,1
    value.connection=Mock()
    value.connection.execute.return_value.fetchone.return_value=(1,)
    value.connection.execute.return_value.fetchall.return_value=[]
    return value


class PoliticsFeaturesTests(unittest.TestCase):
    def test_live_and_recorded_values_match_without_using_other_countries_or_future_snapshots(self):
        for seq,expected in [(0,[35,10]),(3,[35,10]),(4,[80,30]),(5,[80,30]),(6,[np.nan,30]),(8,[np.nan,np.nan])]:
            with self.subTest(seq=seq):
                live,past=LiveLookup(snapshot(seq)),historical(seq)
                np.testing.assert_allclose(live.numbers,past.numbers,equal_nan=True)
                found=dict(zip(NUMBERS,past.numbers))
                np.testing.assert_allclose([found[name] for name in FIELDS],expected,equal_nan=True)
                self.assertEqual(found['population'],1000 if seq<8 else 0)

    def test_both_catboost_encoders_use_the_same_numeric_values_for_training_and_live_decisions(self):
        snapshot_value=snapshot(4)
        live=LiveLookup(snapshot_value)
        past=historical(4)
        state=past.numbers+live.prices+live.institutions+live.tariffs+live.taxes
        data=SimpleNamespace(state=np.array([state],np.float32),categories=np.array([categories(live)],object),
                             actions=Histograms([[]]),held=Histograms([[]]),sizes=np.zeros((1,1),np.float32))
        encoder=histogram.Encoder(data.actions,data.held,{})
        with patch.object(histogram,'frame',wraps=histogram.frame) as encode,patch.object(histogram,'live_holdings',return_value=[]):
            training=histogram.pool(data,{})(np.array([0]),np.array([0]))
            decision=encoder.live(snapshot_value,[[]])
        trained_state=encode.call_args_list[0].args[0]
        live_state=encode.call_args_list[1].args[0]
        np.testing.assert_allclose(trained_state,live_state,equal_nan=True)
        self.assertEqual(training.get_feature_names(),decision.get_feature_names())
        numeric=dict(zip(histogram.STATE,state))
        training_rows=row.frame([{**row.context(SimpleNamespace(state=live)),**numeric,'action':'form_army'}])
        decision_rows=row.live(snapshot_value,[('form_army',{'option':30})])
        for name,expected in zip(FIELDS,[80.,30.]):
            with self.subTest(feature=name):
                index=training.get_feature_names().index(name)
                self.assertEqual(live_state[0,index],expected)
                self.assertNotIn(index,training.get_cat_feature_indices())
                self.assertIn(name,row.NUMERIC)
                self.assertNotIn(name,row.CATEGORICAL)
                self.assertEqual(training_rows[name].iloc[0],expected)
                self.assertEqual(decision_rows[name].iloc[0],expected)


if __name__=='__main__':
    unittest.main()
