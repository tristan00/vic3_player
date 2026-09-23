import importlib
import json
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np

from interface.common import DEFAULT_GAME
from interface.recording import capture
from interface.runner.memory import LAYOUT

record=importlib.import_module('interface.recording.record')
tables=importlib.import_module('interface.recording.tables')

BASELINE=json.loads((Path(__file__).parent/'coverage_baseline.json').read_text(encoding='utf-8'))
PLAYER=(5,1)
STATE=(76,2)
OBJECT=(11,3)
STATE_LISTS=('cap_obj_state','cap_obj_player_state','cap_treaty_port','cap_decree_','cap_supply_','cap_alert_')
COUNTRY_LISTS=('cap_obj_country','cap_adjacent','cap_bloc_leader','cap_expelled_','cap_diplomatic_')


EMPTY=9


class Filled(dict):
    def __init__(self,count,**columns):
        super().__init__(columns)
        self.count=count

    def __missing__(self,column):
        return [EMPTY if column in ('custom_name','name') else 1]*self.count


def target(name):
    return STATE if name.startswith(STATE_LISTS) else PLAYER if name.startswith(COUNTRY_LISTS) else OBJECT


def value(kind,field):
    if kind=='scope':
        return ('flag','1')
    if kind=='text':
        return ('flag','January 1, 1836' if field=='established' else 'x')
    if kind=='object':
        return STATE
    if kind in ('above','below'):
        return ('value',0.0)
    return ('value',1.0)


def synthetic(body,world):
    lists,maps={},{}
    for name,item in re.findall(r'add_to_variable_list = \{ name = (cap_\w+) target = (\S+) \}',body):
        lists.setdefault(name,[('flag',item[5:]) if item.startswith('flag:') else target(name)])
    lists['cap_province']=[(8,index) for index,_ in enumerate(capture.province_colors(capture.map_data(DEFAULT_GAME,world)))]
    lists['cap_open']=[('flag','window')]
    variables={'cap_seq':('value',7.0),'cap_message_count':('value',1.0),'cap_proposal_count':('value',1.0),
               **{f'cap_ui_{name}':('value',0.0) for name,_ in capture.UI_CHECKS},
               **{name:('value',1.0) for name in re.findall(r'change_variable = \{ name = (cap_alert_\w+)',body)}}
    for group in capture.groups():
        key=PLAYER if group.source is None else lists[group.source][0]
        for field,_,kind in group.fields:
            if group.key:
                maps.setdefault(group.maps[field],{})[key]=value(kind,field)
            else:
                variables[group.maps[field]]=value(kind,field)
    maps['cap_country_type']={PLAYER:('flag','recognized')}
    maps['cap_country_rank']={PLAYER:('flag','great_power')}
    maps['cap_owning_company']={PLAYER:OBJECT}
    maps['cap_province_color']={item:('flag',color) for item,color in zip(lists['cap_province'],capture.province_colors(capture.map_data(DEFAULT_GAME,world)))}
    maps['cap_province_state']={item:STATE for item in lists['cap_province']}
    maps['cap_province_controller']={item:PLAYER for item in lists['cap_province']}
    for name in capture.BORROW_MAPS:
        maps[name]={('flag','3|0'):('flag','Never') if name=='cap_borrow_name' else ('value',1.0)}
    for name in capture.RELEASE_MAPS:
        maps[name]={('flag','0'):('flag','Flanders') if name=='cap_release_name' else ('value',1.0)}
    for name in capture.FORMABLE_MAPS:
        maps[name]={('flag','0'):('flag','Germany') if name=='cap_formable_name' else ('value',1.0)}
    for name in capture.MESSAGE_MAPS+capture.PROPOSAL_MAPS:
        maps[name]={('value',1.0):PLAYER if name=='cap_proposal_actor' else ('flag','x')}
    picks={5:{'variables':{},'lists':{name:[STATE] for name in set(re.findall(r'name = (capd_\w+)',body))},'maps':{}}}
    return record.Held({'variables':variables,'lists':lists,'maps':maps},7,picks)


def world(directory):
    (directory/'map_data').mkdir()
    (directory/'map_data/province_terrains.txt').write_text('x000001="plains"\nx000002="ocean"\n',encoding='utf-8-sig')
    (directory/'map_data/default.map').write_text('sea_starts = { x000002 }\n',encoding='utf-8-sig')
    return {'mod':str(directory),'states':[],'countries':[]}


def written():
    with tempfile.TemporaryDirectory() as directory:
        mini=world(Path(directory))
        held=synthetic(capture.capture_body(DEFAULT_GAME,'XAA'),mini)
        snapshot={'country':{'id':np.array([1]),'country_definition':np.array([1])},
                  'state':{'id':np.array([2]),'country':np.array([1])},
                  'law':{'id':np.array([3]),'law':np.array([1])},
                  'company':{'id':np.array([3]),'company_type':np.array([1]),'country':np.array([1])},
                  'journal_entry':{'id':np.array([3]),'journal_entry_type':np.array([1])},
                  'front':{'id':np.array([3])}}
        scripted={}
        colors=record._scripted(scripted,snapshot,held,{1:'AAA'},lambda code:'key',1,{1},mini,capture.map_data(DEFAULT_GAME,mini))
        return scripted,colors


def entities():
    three=lambda **columns:Filled(3,id=[1,2,3],ident=[1,2,3],**columns)
    one=lambda **columns:Filled(1,id=[3],ident=[3],**columns)
    lines=lambda:Filled(22,id=[1]*22,ord=list(range(22)),value=[1.0]*22)
    return {**{name:three(country=[1,1,1]) for name in ('country','state','front','character','formation','interest_group','power_bloc')},
            'building':three(state=[2,2,2]),'strait':three(),'law':three(country=[1,1,1],law=[1,1,2]),'company':one(country=[1],company_type=[2]),
            'journal_entry':one(country=[1],journal_entry_type=[2],scope_root_definition=[0]),'state_region':Filled(1,id=[1]),
            'world_market_price_trend_channel':Filled(1,id=[0],ord=[0],channel=[0],date=[1],index=[1]),
            'world_market_price_trend':Filled(1,id=[0],channel=[0],ord=[0],value=[1.0]),'country_private':Filled(1,id=[1]),
            'country_budget_weekly_income':lines(),'country_budget_weekly_expenses':lines(),
            'formation_position':Filled(6,id=[1,1,2,2,3,3],ord=[0,1]*3,value=[1.0]*6),
            **{name:Filled(1,id=[3]) for name in ('interest_group_private','character_private','formation_private','law_private')},
            'game_state':Filled(1,id=[0]),'player':Filled(1,id=[0],country=[1]),'game_rule_setting':{'id':[],'ord':[],'setting':[]}}


class Orders(dict):
    def __missing__(self,folder):
        return [f'{folder}_{index}' for index in range(64)]


def consumed(scripted,colors):
    names={0:None,EMPTY:'',1:'AAA'}
    for table in ('country_metric','state_metric'):
        scripted[table]['value']=[1.0]*len(scripted[table]['value'])
    shown,possible=scripted['diplomatic_action_shown'],scripted['diplomatic_action_possible']
    for column in ('country','action'):
        shown[column]=shown[column]+possible[column]
    captured={**entities(),**{name:dict(columns) for name,columns in scripted.items()}}
    label=lambda code:names.get(code,'key')
    _,_,windows=record.snapshot_meta(captured,label)
    rows=tables.build(record.Capture(captured,label,1,[1],windows),Orders(),colors)
    return set(captured)|{'game_state','time_control','ui_open','ui_window','player','game_rule_setting'},rows


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEFAULT_GAME/'game').is_dir():
            raise unittest.SkipTest('game install not present')
        cls.tables,cls.colors=written()

    def test_every_baseline_table_is_written_with_all_its_columns_and_rows(self):
        for table,columns in BASELINE['tables'].items():
            self.assertIn(table,sorted(self.tables),f'the recorder no longer writes {table}')
            self.assertLessEqual(set(columns),set(self.tables[table]),table)
            self.assertTrue(any(self.tables[table].values()),f'{table} received no rows from a complete capture')

    def test_every_baseline_table_reaches_a_stored_table(self):
        read,_=consumed(self.tables,self.colors)
        self.assertEqual(sorted(set(BASELINE['tables'])-read),[])

    def test_every_baseline_metric_is_listed_and_every_visible_one_is_captured(self):
        for scope,names in BASELINE['metrics'].items():
            self.assertLessEqual(set(names),set(capture.METRICS[scope]),scope)
        captured={('country',name) for name in capture.GROUPS['public']+capture.GROUPS['player']}|{('state',name) for name in capture.GROUPS['state']}
        visible={key for key,verdict in capture.VISIBILITY.verdicts.items() if verdict in ('ANY','DERIVED','OWN')}
        for scope,names in BASELINE['metrics'].items():
            for name in names:
                if f'{scope}|{name}' in visible:
                    self.assertIn((scope,name),captured,f'{scope}|{name}')

    def test_every_baseline_memory_field_is_still_decoded(self):
        for table,fields in BASELINE['layout'].items():
            self.assertIn(table,LAYOUT['tables'],table)
            self.assertLessEqual(set(fields),set(LAYOUT['tables'][table].get('fields',{})),table)


if __name__=='__main__':
    unittest.main()
