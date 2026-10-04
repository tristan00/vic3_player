import copy
from dataclasses import replace
from pathlib import Path
import unittest

import numpy as np

from advisors.models.entity_graph.source import keys, labels, replay
from interface.recording.spec import TABLE


def table(name,rows):
    spec=TABLE[name]
    return {tuple(row.get(key) for key in keys(spec)):tuple(row.get(col.name) for col in spec.columns) for row in rows}


def fixture():
    rows={
        'country_history':[{'country':1,'capital':11,'market':9}],
        'state_history':[{'state':11,'country':1},{'state':12,'country':1}],
        'building_history':[{'building':21,'state':11,'levels':2}],
        'market_history':[{'market':9,'owner':1}],
        'pop_history':[{'pop':31,'location':11,'workplace':21,'culture':8,'pop_type':3,'religion':4},
                       {'pop':32,'location':11,'workplace':21,'culture':8,'pop_type':3,'religion':4}],
        'pop_status':[{'pop':31,'workforce':10,'dependents':5,'wealth':10},
                      {'pop':32,'workforce':20,'dependents':10,'wealth':20}],
        'culture_history':[{'culture':8}],
        'province_history':[{'province':101,'state':11,'controller':1},{'province':102,'state':12,'controller':1}],
        'formation_history':[{'formation':41,'country':1,'supply_hub':11}],
        'combat_unit_history':[{'combat_unit':51,'country':1,'formation':41,'building':21,'manpower':100}],
        'character_history':[{'character':61,'country':1,'formation':41,'culture':8}],
        'market_goods':[{'market':9,'goods':5,'price':30,'sell_orders':20,'buy_orders':10}],
        'state_goods':[{'state':11,'goods':5,'local_price':25,'production':20,'consumption':10}],
        'building_goods':[{'building':21,'goods':5,'input':0,'output':20}]
    }
    snap={name:table(name,values) for name,values in rows.items()}
    data={'run':1,'player':1,'dates':{0:0,2:24},'states':{0:snap,2:copy.deepcopy(snap)},
          'geography':{'provinces':[(101,1,'plains',20,10,20),(102,2,'hills',30,20,30)],'adjacency':[(101,102,4)]}}
    task={'run':1,'seq':2,'hour':24,'history':[0,2],'actions':[('subsidize_building',{'building':21}),('create_army',{'option':30})]}
    vocabulary={'pop_type':{3:'laborers'},'religion':{4:'test_religion'},'goods':{5:'grain'}}
    return data,task,vocabulary


class EntityGraphTests(unittest.TestCase):
    def test_replay_respects_sequence_deletions_and_never_uses_later_values(self):
        values=replay([(0,3,True,7),(2,3,True,8),(4,3,False,None),(6,3,True,9)],1,True,[0,1,2,5])
        self.assertEqual(values,{0:{(3,):(7,)},1:{(3,):(7,)},2:{(3,):(8,)},5:{}})

    def test_labels_use_before_sequence_baseline_and_mask_run_end(self):
        dates={0:0,1:0,2:90*24,3:180*24}
        series={kind:[(0,100),(1,200),(2,300),(3,400)] for kind in ('gdp','population','sol','stock')}
        base,y,mask,age=labels(0,dates,series)
        np.testing.assert_array_equal(base,[100]*4)
        np.testing.assert_allclose(y[:2,0],np.log([3,4]))
        np.testing.assert_array_equal(mask[:,0],[True,True,False,False,False])


if __name__=='__main__':
    unittest.main()
