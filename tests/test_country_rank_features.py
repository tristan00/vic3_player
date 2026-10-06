from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from advisors.data.features import CATEGORIES, LAWS, NONE, HistoryLookup, LiveLookup, Versions, categories
from advisors.data.histograms import Histograms
from advisors.models.boosting import Regressor
from advisors.models.histogram import data as histogram
from advisors.models.row import features as row
from advisors.models.row.model import Model, pool

RANK='player.country_rank'
RANKS=['major_power','great_power','unrecognized_major_power']
ACTION=('form_army',{'option':30})


def lookup(rank):
    return SimpleNamespace(player=7,country=lambda ident:{7:rank,9:'minor_power'}[ident],laws=[NONE]*len(LAWS),
                           numbers=[0.]*len(histogram.NUMBERS),prices=[0.]*len(histogram.PRICES),
                           institutions=[0.]*len(histogram.INSTITUTIONS),tariffs=[0.]*len(histogram.TARIFFS),taxes=[0.]*len(histogram.TAXES))


class CountryRankFeaturesTests(unittest.TestCase):
    def test_live_and_historical_player_rank_follow_the_snapshot_without_future_leakage(self):
        countries=Versions.__new__(Versions)
        countries.index={(1,(7,)):([0,4,8,12],[(rank,) for rank in [*RANKS,None]]),
                         (1,(9,)):([0],[('minor_power',)]),(2,(7,)):([0],[('insignificant_power',)])}
        laws=Versions.__new__(Versions)
        laws.index={}
        laws.by_run={}
        history=SimpleNamespace(player={1:7,2:7},terrain={1:{},2:{}},countries=countries,law_rows=laws)
        for run,seq,expected in [(1,0,RANKS[0]),(1,3,RANKS[0]),(1,4,RANKS[1]),(1,7,RANKS[1]),
                                 (1,8,RANKS[2]),(1,12,NONE),(2,0,'insignificant_power')]:
            with self.subTest(run=run,seq=seq):
                historical=HistoryLookup(history,run,seq)
                live=LiveLookup.__new__(LiveLookup)
                live.player=7
                live.countries={7:None if expected==NONE else expected,9:'minor_power'}
                live.laws=[NONE]*len(LAWS)
                self.assertEqual(dict(zip(CATEGORIES,categories(historical)))[RANK],expected)
                self.assertEqual(categories(live),categories(historical))

    def test_both_models_learn_rank_as_a_category_and_match_live_encoding(self):
        lookups=[lookup(rank) for rank in RANKS]*4
        targets=np.tile([-1.,0.,1.],4)
        points=[SimpleNamespace(state=state) for state in lookups]
        rows=row.frame([{**row.context(point),**row.action_features(*ACTION,point)} for point in points])
        row_pool=pool(rows,targets)
        self.assertIn(rows.columns.get_loc(RANK),row_pool.get_cat_feature_indices())
        self.assertEqual(rows[RANK].tolist(),RANKS*4)
        self.assertNotIn(RANK,row.NUMERIC)
        data=SimpleNamespace(state=np.zeros((12,len(histogram.STATE)),np.float32),
                             categories=np.array([categories(state) for state in lookups],object),
                             actions=Histograms([[] for _ in lookups]),held=Histograms([[] for _ in lookups]),sizes=np.ones((12,1),np.float32))
        indices=np.arange(12)
        histogram_pool=histogram.pool(data,{})(indices,indices,targets)
        self.assertIn(histogram_pool.get_feature_names().index(RANK),histogram_pool.get_cat_feature_indices())
        params={'iterations':8,'depth':2,'learning_rate':.5,'one_hot_max_size':10,'thread_count':1,'allow_writing_files':False}
        row_model=Model(params).fit(rows,targets)
        histogram_model=Regressor(params).fit(histogram_pool)
        self.assertGreater(np.ptp(row_model.predict(rows)),.5)
        self.assertGreater(np.ptp(histogram_model.predict(histogram_pool)),.5)
        encoder=histogram.Encoder(data.actions,data.held,{})
        for index,state in enumerate(lookups[:3]):
            with self.subTest(rank=RANKS[index]):
                with patch.object(row,'Live',return_value=points[index]):
                    live_rows=row.live(object(),[ACTION])
                pd.testing.assert_frame_equal(live_rows.astype({name:str for name in row.CATEGORICAL}),
                                              rows.iloc[[index]].reset_index(drop=True).astype({name:str for name in row.CATEGORICAL}))
                with patch.object(histogram,'LiveLookup',return_value=state),patch.object(histogram,'live_holdings',return_value=[]):
                    live_pool=encoder.live(object(),[[ACTION]])
                np.testing.assert_array_equal(row_model.predict(live_rows),row_model.predict(rows)[index:index+1])
                np.testing.assert_array_equal(histogram_model.predict(live_pool),histogram_model.predict(histogram_pool)[index:index+1])


if __name__=='__main__':
    unittest.main()
