from types import SimpleNamespace
import unittest

from advisors.data.features import GOODS, NUMBERS, POLICY, TAXES, HistoryLookup, Versions, spent, taxes

FIRST,SECOND,THIRD=GOODS[:3]


class PolicyFeaturesTests(unittest.TestCase):
    def test_every_good_has_a_flag_for_its_consumption_tax(self):
        self.assertEqual(TAXES,[f'consumption_tax.{goods}' for goods in GOODS])
        found=taxes({FIRST,THIRD})
        self.assertEqual(len(found),len(TAXES))
        self.assertEqual((found[:3],sum(found)),([1.,0.,1.],2.))

    def test_the_three_levels_and_government_spending_are_numbers(self):
        self.assertEqual(NUMBERS[-5:],['government_spending','government_spending_gdp']+POLICY)
        self.assertEqual(POLICY,['tax_level','government_wage_level','military_wage_level'])

    def test_spending_sums_only_the_expense_lines_asked_for(self):
        budget=[('expense',1,5.),('expense',2,7.),('expense',4,100.),('income',1,1000.)]
        self.assertEqual((spent(budget,{1,2,3}),spent(budget,{4}),spent(budget,set())),(12.,100.,0))

    def test_a_recorded_pause_knows_which_goods_were_taxed_then(self):
        taxed=Versions.__new__(Versions)
        taxed.index={(7,(FIRST,)):([0,4],[(),None]),(7,(SECOND,)):([2],[()]),(8,(THIRD,)):([0],[()])}
        taxed.by_run={7:[(FIRST,),(SECOND,)],8:[(THIRD,)]}
        history=SimpleNamespace(player={7:1,8:1},terrain={7:{},8:{}},taxed=taxed)
        at=lambda run,seq:HistoryLookup(history,run,seq).taxes[:3]
        self.assertEqual((at(7,1),at(7,3),at(7,5),at(8,0)),([1.,0.,0.],[1.,1.,0.],[0.,1.,0.],[0.,0.,1.]))


if __name__=='__main__':
    unittest.main()
