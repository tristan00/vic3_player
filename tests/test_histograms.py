import unittest
from types import SimpleNamespace

import numpy as np

from advisors import pickers
from advisors.histograms import ACTION, APPROVAL, BUILDINGS, CLOUT, GOVERNING, IDEOLOGIES, METHODS, PEOPLE, ROLES, Histograms, Holdings, country, entries
from advisors.tune import decode, space

LOOKUP=SimpleNamespace(player=1,terrain={},state=lambda state:(None,None),building=lambda ident:None,typed=lambda kind,ident:None,character=lambda ident:None,
                       country=lambda ident:None)


class Table:
    def __init__(self,rows):
        self.rows=rows
        self.by_run={1:list(rows)}

    def at(self,run,key,seq):
        return self.rows[key]


class EntriesTests(unittest.TestCase):
    def test_each_action_counts_its_type_and_each_parameter_it_carries(self):
        found=entries([('set_tax_level',{'level':'High'}),('set_tax_level',{'level':'Low'})],LOOKUP)
        self.assertEqual([name for name,_,_ in found],[ACTION,'set_tax_level.level',ACTION,'set_tax_level.level'])
        self.assertEqual(len({value for name,value,_ in found if name!=ACTION}),2)


class HoldingsTests(unittest.TestCase):
    def test_levels_are_counted_for_buildings_in_the_player_states_only(self):
        holdings=Holdings.__new__(Holdings)
        holdings.buildings=Table({(1,):('farm',10,4),(2,):('mine',20,2),(3,):None})
        holdings.methods=Table({(1,'tools'):(),(2,'picks'):(),(1,'old'):None})
        holdings.groups=Table({(1,):('landowners',7,True),(2,):('devout',8,True),(3,):('unions',7,False)})
        holdings.stats=SimpleNamespace(at=lambda run,group,seq:{1:[.6,5.0],2:[.3,1.0]}.get(group))
        holdings.characters=Table({(1,):(7,'royalist'),(2,):(8,'radical'),(3,):None})
        holdings.roles=Table({(1,'ruler'):(),(1,'general'):(),(2,'ruler'):(),(1,'old'):None})
        holdings.people=SimpleNamespace(at=lambda run,seq:[60,30,10,20,5])
        lookup=SimpleNamespace(run=1,seq=5,player=7,state=lambda state:(None,7 if state==10 else 8))
        self.assertEqual(holdings.at(lookup),[(BUILDINGS,'farm',4),(METHODS,'tools',4),(CLOUT,'landowners',.6),(APPROVAL,'landowners',5.0),(GOVERNING,'landowners',1.0),
                                              (IDEOLOGIES,'royalist',1),(ROLES,'ruler',1),(ROLES,'general',1),
                                              (PEOPLE,'lower_strata',.6),(PEOPLE,'middle_strata',.3),(PEOPLE,'upper_strata',.1),(PEOPLE,'radicals',.2),(PEOPLE,'loyalists',.05)])

    def test_the_country_histograms_are_included_whole_beside_the_tuned_design(self):
        histograms=Histograms([country([('landowners',True,.6,5.0),('devout',False,.3,-2.0)],['royalist',None],['ruler'],[60,30,10,20,5])])
        self.assertEqual(len(histograms.columns(pickers.SIZES)),2+2+2+2+1+5)
        self.assertEqual(len(histograms.labels(pickers.SIZES)),14)
        self.assertEqual({name:size for name,size in pickers.SIZES.items() if name in pickers.DESIGN['sizes']},pickers.DESIGN['sizes'])


class HistogramTests(unittest.TestCase):
    def setUp(self):
        self.histograms=Histograms([[('a','x',1),('a','x',1),('b','p',3)],[('a','y',1),('a','x',1)],[('a','x',1)]])
        self.bins={name:len(found) for name,found in self.histograms.bins.items()}

    def test_bins_are_ordered_by_how_many_pauses_hold_them(self):
        self.assertEqual(self.histograms.bins,{'a':['x','y'],'b':['p']})
        self.assertEqual(self.histograms.counts.tolist(),[[2,0,3],[1,1,0],[1,0,0]])

    def test_columns_keep_the_most_common_bins_of_included_histograms(self):
        self.assertEqual(self.histograms.columns({'a':1,'b':1}),[0,2])
        self.assertEqual(self.histograms.columns({'a':2}),[0,1])

    def test_a_size_beyond_the_bins_seen_keeps_every_bin_of_that_histogram(self):
        sizes={'a':9,'b':9,'missing':4}
        self.assertEqual(self.histograms.columns(sizes),[0,1,2])
        self.assertEqual(self.histograms.labels(sizes),['a=x','a=y','b=p'])

    def test_the_centre_of_the_space_is_production_settings_with_every_histogram_whole(self):
        low,high,names=space(self.bins)
        params,sizes=decode(np.zeros(len(low)),self.bins)
        self.assertEqual(params,{name:pickers.PARAMS[name] for name in params})
        self.assertEqual(sizes,{'a':2,'b':1})
        self.assertTrue((low<=0).all() and (high>=0).all())

    def test_the_corners_of_the_space_decode_to_valid_settings(self):
        low,high,_=space(self.bins)
        self.assertEqual(decode(low,self.bins)[1],{})
        params,sizes=decode(high,self.bins)
        self.assertEqual((params['depth'],params['iterations'],params['one_hot_max_size'],sizes),(10,400,32,{'a':2,'b':1}))


if __name__=='__main__':
    unittest.main()
