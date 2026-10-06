import math
from types import SimpleNamespace
import unittest

from advisors.catalogue import NAVAL, PARAMS, SECTORS, SITED
from advisors.data.features import PEOPLE, SITE, HistoryLookup, Latest, Versions, located, site
from advisors.data.histograms import entries
from advisors.models.row import features as row

SECTOR=next(iter(SECTORS))
PORT=next(iter(NAVAL))


class Lookup:
    player=1
    sites={(3,'building_port'):[10.,20.,8.,2.,.5,1000.,.25],(4,'building_port'):[30.,40.,6.,0.,.25,3000.,.75],(5,'building_farm'):[1.,2.,3.,4.,.1,50.,.01]}
    terrain={}

    def home(self,ident):
        return {9:5}.get(ident)

    def building(self,ident):
        return {9:'building_farm'}.get(ident)

    def state(self,state):
        return None,1

    def site(self,state,kind):
        return self.sites.get((state,kind),[float('nan')]*len(SITE))


def versions(index):
    found=Versions.__new__(Versions)
    found.index=index
    found.by_run={}
    for run,key in index:
        found.by_run.setdefault(run,[]).append(key)
    return found


class SiteFeaturesTests(unittest.TestCase):
    def test_building_method_and_downsize_acts_are_the_three_sited_kinds(self):
        self.assertEqual(set(SITED.values()),{'build','method','downsize'})
        self.assertLessEqual(set(SITED),set(PARAMS))
        self.assertEqual({name for name,kind in SITED.items() if kind=='build'},{*SECTORS,*NAVAL})
        self.assertTrue(all({'state','building'}&{param for param,_ in PARAMS[name]} for name in SITED))

    def test_a_site_lists_the_seven_values_and_marks_what_is_unknown(self):
        self.assertEqual(len(SITE),7)
        self.assertEqual(site([100,20,5,40,9],8.5,3,.25,.125),[9.,40.,8.5,3.,.25,125.,.125])
        self.assertTrue(all(math.isnan(value) for value in site(None,None,None,None,None)))

    def test_an_act_is_located_by_its_building_or_by_its_state_and_building_type(self):
        lookup=Lookup()
        self.assertEqual(located('downsize_building',{'building':9},lookup),(5,'building_farm'))
        self.assertEqual(located(SECTOR,{'state':3,'building_type':'building_port'},lookup),(3,'building_port'))
        self.assertEqual(located(PORT,{'state':3},lookup),(3,NAVAL[PORT]))
        self.assertEqual(located('reset_methods_statewide',{'state':3},lookup),(3,None))

    def test_a_batch_carries_one_averaged_set_per_kind_of_sited_act(self):
        batch=[(SECTOR,{'state':3,'building_type':'building_port'}),(SECTOR,{'state':4,'building_type':'building_port'}),('downsize_building',{'building':9}),
               ('raise_tax_level',{})]
        found={(name,kind):value for name,kind,value in entries(batch,Lookup()) if name in SITE}
        self.assertEqual({kind for _,kind in found},{'build','downsize'})
        self.assertEqual([found[name,'build'] for name in SITE],[20.,30.,7.,1.,.375,2000.,.5])
        self.assertEqual([found[name,'downsize'] for name in SITE],Lookup.sites[5,'building_farm'])
        unknown=entries([(SECTOR,{'state':8,'building_type':'building_port'})],Lookup())
        self.assertFalse([name for name,_,_ in unknown if name in SITE])

    def test_one_action_row_carries_the_site_of_a_sited_act_only(self):
        self.assertLessEqual(set(SITE),set(row.NUMERIC))
        point=SimpleNamespace(state=Lookup(),entity=lambda table,ident:None,traits=lambda character:[],hours=0)
        found=row.action_features('downsize_building',{'building':9},point)
        self.assertEqual([found[name] for name in SITE],Lookup.sites[5,'building_farm'])
        self.assertFalse(set(SITE)&set(row.action_features('raise_tax_level',{},point)))

    def test_a_recorded_pause_reads_the_state_as_it_stood_then(self):
        people=Latest.__new__(Latest)
        people.index={(7,3):([0,4],[[100,20,5,40,9],[200,20,5,50,0]])}
        buildings=versions({(7,(1,)):([0],[('building_port',3,2)]),(7,(2,)):([0,4],[('building_port',3,1),None]),(7,(3,)):([0],[('building_farm',3,6)])})
        report=lambda values:versions({(7,(3,)):([0,4],[(value,) for value in values])})
        history=SimpleNamespace(player={7:1},terrain={7:{}},people=people,buildings=buildings,living=report([8.,9.]),literate=report([.25,.5]),shares=report([.125,.25]))
        self.assertEqual(PEOPLE[3:],['subsisting_workforce','unemployed_workforce'])
        early,late=HistoryLookup(history,7,2),HistoryLookup(history,7,4)
        self.assertEqual(early.site(3,'building_port'),[9.,40.,8.,3.,.25,125.,.125])
        self.assertEqual(late.site(3,'building_port'),[0.,50.,9.,2.,.5,225.,.25])
        self.assertTrue(math.isnan(late.site(3,None)[3]))
        self.assertEqual((early.home(2),late.home(2),late.home(3)),(3,None,3))
        self.assertTrue(all(math.isnan(value) for value in late.site(6,'building_port')[:3]))


if __name__=='__main__':
    unittest.main()
