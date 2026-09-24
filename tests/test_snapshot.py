import struct
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import numpy as np

from interface.options.available import RULES, trade_level
from tests.memory_stored import Memory
from interface.runner.memory import Reader, HEAP_LOW, visible_columns
from interface.script import event_options


class SnapshotTests(unittest.TestCase):
    def test_static_unsigned_and_unaligned_wide_fields(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.base=0x7ff700000000
        reader.tables={'global':{'root':[],'offset':4096,'size':16,
            'fields':{'seed':['u',0],'wide':['w',4],'count':['u',12]}}}
        raw=struct.pack('<IQI',0xffffffff,12345678901,0x80000001)
        def read(address,size):
            self.assertEqual(address,reader.base+4096)
            return raw[:size]
        reader.read=read
        rows,children=reader.table('global')
        self.assertEqual(rows['seed'].tolist(),[4294967295])
        self.assertEqual(rows['wide'].tolist(),[12345678901])
        self.assertEqual(rows['count'].tolist(),[2147483649])
        self.assertEqual(children,{})

    def test_scope_values_keep_full_width_and_only_decode_flags(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.key_columns=set()
        address=HEAP_LOW+4096
        raw=b''.join(struct.pack('<iiq',kind,0,value) for kind,value in
                     [(1,12345678901),(1,-9876543210),(3,14372),(0,0)])
        reader.read=lambda start,size:raw[start-address:start-address+size]
        observed=[]
        def tokens(values):
            observed.extend(values.tolist())
            return np.full(len(values),9,dtype=np.int32)
        reader.tokens=tokens
        heads=np.array([[address,(4<<32)|4]],dtype=np.int64)
        rows=reader.vector('scope',np.array([7],dtype=np.int32),heads,0,12,16,
                           {'type':['i',0],'value':['w',8],'flag':['optional_token',8,'type',[3]]})
        self.assertEqual(rows['value'].tolist(),[12345678901,-9876543210,14372,0])
        self.assertEqual(rows['flag'].tolist(),[0,0,9,0])
        self.assertEqual(observed,[14372])

    def test_conditional_keys_do_not_dereference_inactive_union_members(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.key_columns=set()
        address=HEAP_LOW+4096
        raw=struct.pack('<iiQiiQ',3,0,HEAP_LOW+8192,0,0,HEAP_LOW+12288)
        reader.read=lambda start,size:raw[start-address:start-address+size]
        observed=[]
        def codes(kind,values):
            observed.extend(values.tolist())
            return np.where(values!=0,9,0).astype(np.int32)
        reader.codes=codes
        heads=np.array([[address,(2<<32)|2]],dtype=np.int64)
        rows=reader.vector('spending',np.array([7],dtype=np.int32),heads,0,12,16,
                           {'type':['i',0],'goods':['goods',8,'type',[3]]})
        self.assertEqual(observed,[HEAP_LOW+8192,0])
        self.assertEqual(rows['goods'].tolist(),[9,0])

    def test_adjacent_byte_flags_keep_distinct_values(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        address=HEAP_LOW+4096
        raw=bytes([0,1,0,1,1,0,1,0])
        reader.read=lambda start,size:raw[start-address:start-address+size]
        heads=np.array([[address,(1<<32)|1]],dtype=np.int64)
        rows=reader.vector('flags',np.array([7],dtype=np.int32),heads,0,12,8,
                           {str(index):['b',index] for index in range(8)})
        self.assertEqual([int(rows[str(index)][0]) for index in range(8)],list(raw))

    def test_packed_boolean_hash_ignores_empty_and_deleted_entries(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        address=HEAP_LOW+4096
        raw=struct.pack('<12i',0,99,1,1,4,1,255,33,1,1,3,0)
        reader.read=lambda start,size:raw[start-address:start-address+size]
        heads=np.array([[address,(3<<32)|2,0]],dtype=np.int64)
        rows=reader.vector('ports',np.array([7],dtype=np.int32),heads,0,12,12,
                           {'state':['i',4],'value':['b',8]},None,-1,None,0)
        self.assertEqual(rows['state'].tolist(),[4,3])
        self.assertEqual(rows['value'].tolist(),[1,0])

    def event_reader(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.base=0x140000000
        reader.tables={'event':{'rva':1}}
        data={}
        def write(address,raw):
            data.update({address+index:value for index,value in enumerate(raw)})
        pointers=[HEAP_LOW+index*0x10000 for index in range(1,10)]
        write(reader.base+0x592d0e0,struct.pack('<Q',pointers[0]))
        for index,offset in enumerate((0x10,0x20,0x1df0)):
            write(pointers[index]+offset,struct.pack('<Q',pointers[index+1]))
        write(pointers[2],struct.pack('<Q',reader.base+0x45ae328))
        write(pointers[3]+0x10,struct.pack('<QII',pointers[4],1,1))
        write(pointers[4],struct.pack('<Q',pointers[5]))
        write(pointers[5],struct.pack('<Q',reader.base+0x45b9ad8))
        write(pointers[5]+0x88,struct.pack('<Q',pointers[6]))
        write(pointers[6]+16,struct.pack('<I',0x2000007))
        write(pointers[7]+8,struct.pack('<I',0x2000007))
        write(pointers[7]+24,struct.pack('<Q',pointers[7]+0x1000))
        write(pointers[7]+0x1148,struct.pack('<II',4,4))
        write(pointers[5]+0x110,struct.pack('<QII',pointers[8],3,3))
        for index,(ordinal,enabled,default) in enumerate(((0,1,1),(2,0,0),(3,1,0))):
            raw=bytearray(88)
            struct.pack_into('<QI',raw,0,pointers[5],ordinal)
            struct.pack_into('<QQ',raw,32,0,15)
            struct.pack_into('<QQ',raw,64,0,15)
            struct.pack_into('<BB',raw,81,enabled,default)
            write(pointers[8]+index*88,raw)
        reader.read=lambda address,size:bytes(data[address+index] for index in range(size))
        reader.objects=lambda rva:(0,np.array([7],dtype=np.int32),np.array([pointers[7]],dtype=np.int64))
        return reader,write,pointers

    def test_hidden_event_option_does_not_shift_native_identity(self):
        reader,_,_=self.event_reader()
        self.assertEqual(reader.event_options(),{7:[(0,0,1,1,'',''),(1,-1,0,0,None,None),(2,1,0,0,'',''),(3,2,1,0,'','')]})

    def test_event_window_cannot_reuse_an_expired_instance(self):
        reader,write,pointers=self.event_reader()
        write(pointers[7]+8,struct.pack('<I',0x3000007))
        with self.assertRaisesRegex(RuntimeError,'expired event instance'):
            reader.event_options()

    def test_large_sparse_hash_keeps_live_entries(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        address=HEAP_LOW+4096
        raw=bytearray(8192*24)
        struct.pack_into('<Qqq',raw,7000*24,1<<32,77,9)
        reader.read=lambda start,size:bytes(raw[start-address:start-address+size])
        heads=np.array([[address,(8191<<32)|1,0]],dtype=np.int64)
        rows=reader.vector('values',np.array([4],dtype=np.int32),heads,0,12,24,{'value':['i',8]},None,-1)
        self.assertEqual(rows['value'].tolist(),[77])

    def test_nonempty_container_with_invalid_pointer_fails(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        heads=np.array([[0,(1<<32)|1]],dtype=np.int64)
        with self.assertRaises(RuntimeError):
            reader.vector('values',np.array([4],dtype=np.int32),heads,0,12,4,{})

    def test_named_country_vector_preserves_identity_and_empty_schema(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        address=HEAP_LOW+4096
        raw=struct.pack('<ii',16777219,1)
        reader.read=lambda start,size:raw[start-address:start-address+size]
        heads=np.array([[address,(2<<32)|2],[0,0]],dtype=np.int64)
        rows=reader.vector('permissions',np.array([22,23],dtype=np.int32),heads,0,12,4,{'country':['i',0]})
        self.assertEqual(rows['id'].tolist(),[22,22])
        self.assertEqual(rows['country'].tolist(),[16777219,1])
        empty=reader.vector('permissions',np.array([23],dtype=np.int32),heads[1:],0,12,4,{'country':['i',0]})
        self.assertEqual(set(empty),{'id','ord','country'})
        self.assertEqual(empty['country'].dtype,np.dtype('int32'))

    def test_mod_event_replacement_removes_obsolete_options(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            game=root/'game'
            mod=root/'mod'
            (game/'events').mkdir(parents=True)
            (mod/'events').mkdir(parents=True)
            (game/'events/original.txt').write_text('sample.1 = { option = { name = old_a } option = { name = old_b } }')
            (mod/'events/replacement.txt').write_text('sample.1 = { option = { name = new default_option = yes } }')
            self.assertEqual(event_options(game,[mod]),[('sample.1',0,'new',0,1)])

    def test_hash_overflow_ignores_uninitialized_padding(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        address=HEAP_LOW+4096
        raw=struct.pack('<Qqq',1<<32,77,9)+bytes(24)
        reader.read=lambda start,size:raw[start-address:start-address+size]
        heads=np.array([[address,(0<<32)|1,0x3f666666fa4d0901]],dtype=np.int64)
        rows=reader.vector('values',np.array([4],dtype=np.int32),heads,0,12,24,
                           {'value':['i',8]},None,-1)
        self.assertEqual(rows['id'].tolist(),[4])
        self.assertEqual(rows['value'].tolist(),[77])

    def test_empty_manager_keeps_its_columns_and_child_tables(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.tables={'example':{'rva':16,'size':24,'fields':{'amount':['q',0]},'keys':{},
                                 'vectors':{'example_children':[8,20,4,{}]}}}
        reader.objects=lambda rva:(0,np.array([],dtype=np.int32),np.array([],dtype=np.int64))
        parent,children=reader.table('example')
        self.assertEqual(set(parent),{'id','amount'})
        self.assertEqual(set(children['example_children']),{'id','ord','value'})
        self.assertEqual(parent['amount'].dtype,np.dtype('float64'))

    def test_packed_vector_preserves_adjacent_twelve_byte_records(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        address=HEAP_LOW+4096
        raw=struct.pack('<6i',7,19,100,8,23,200)
        reader.read=lambda start,size: (raw+bytes(8))[start-address:start-address+size]
        heads=np.array([[address,(2<<32)|2]],dtype=np.int64)
        result=reader.vector('crew',np.array([3],dtype=np.int32),heads,0,12,12,
                             {'index':['i',0],'state':['i',4],'crew':['i',8]})
        self.assertEqual(result['index'].tolist(),[7,8])
        self.assertEqual(result['state'].tolist(),[19,23])
        self.assertEqual(result['crew'].tolist(),[100,200])

    def test_column_reads_only_chunks_containing_requested_slots(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        pointers={16:100,100:1000,124:2000}
        reader.word=pointers.__getitem__
        calls=[]
        def read(address,size):
            calls.append((address,size))
            return np.full(size//4,address,dtype='<i4').tobytes()
        reader.read=read
        values=reader.column(0,16,4,np.array([3075,2],dtype=np.int32))
        self.assertEqual(values[:,0].tolist(),[2012,1008])
        self.assertEqual(calls,[(1008,4),(2012,4)])

    def test_four_byte_column_at_end_of_record(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.column=lambda *args:np.array([[11,-1]],dtype=np.int32)
        values=reader.columns('example',{'columns':{'value':[0,8,'i',4]}},0,np.array([0]))
        self.assertEqual(values['value'].tolist(),[-1])

    def test_large_integer_field_preserves_all_sixty_four_bits(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.tables={'example':{'rva':16,'size':8,'fields':{'population':['w',0]}}}
        reader.objects=lambda rva:(0,np.array([3],dtype=np.int32),np.array([HEAP_LOW+4096],dtype=np.int64))
        reader.read=lambda address,size:struct.pack('<q',5000000001)
        rows,_=reader.table('example')
        self.assertEqual(rows['population'].tolist(),[5000000001])
        self.assertEqual(rows['population'].dtype,np.dtype('int64'))

    def test_unreadable_live_object_fails_instead_of_becoming_zero(self):
        reader=Reader.__new__(Reader)
        reader.array=lambda start,size,reader=reader:np.frombuffer(bytes(reader.read(start,size)),dtype='<i8')
        reader.read=MagicMock(side_effect=OSError('unreadable'))
        with self.assertRaises(OSError):
            reader.gather(np.array([HEAP_LOW+4096],dtype=np.int64),16)


PLAYER=(1<<24)|7
OTHER=(2<<24)|8


def snapshot(definitions=None,**tables):
    return Memory(PLAYER,tables,definitions)


class RuleTests(unittest.TestCase):
    def test_tax_levels_offer_every_level_but_the_current_one(self):
        s=snapshot(player_policy=[{'tax_level':1}])
        self.assertEqual([option['level'] for option in RULES['set_tax_level'](s)],['VeryLow','Medium','High','VeryHigh'])

    def test_construction_pause_follows_the_public_metric_of_the_player(self):
        paused=snapshot(country_construction_report=[{'country':PLAYER,'is_construction_paused':True},{'country':OTHER,'is_construction_paused':False}],
                        player_treasury=[{'in_default':False}])
        self.assertEqual(RULES['pause_construction'](paused),[])
        self.assertEqual(RULES['resume_construction'](paused),[{}])
        running=snapshot(country_construction_report=[{'country':PLAYER,'is_construction_paused':False}],player_treasury=[{'in_default':False}])
        self.assertEqual(RULES['pause_construction'](running),[{}])

    def test_queue_items_follow_positions_of_the_government_queue(self):
        s=snapshot(player_construction_queue_item=[
            {'private':False,'position':1,'state':OTHER,'building_type':'building_farm'},
            {'private':False,'position':0,'state':PLAYER,'building_type':'building_mine'},
            {'private':True,'position':0,'state':PLAYER,'building_type':'building_port'}])
        self.assertEqual(RULES['cancel_queue_item'](s),[{'state':PLAYER,'building_type':'building_mine'},{'state':OTHER,'building_type':'building_farm'}])
        self.assertEqual(RULES['raise_queue_item'](s),[{'state':OTHER,'building_type':'building_farm'}])

    def test_borrow_settings_offer_unselected_positions_of_own_formations(self):
        s=snapshot(formation_history=[{'formation':5,'country':PLAYER},{'formation':6,'country':OTHER}],
                   formation_borrow_setting=[{'formation':5,'name':'Never','position':0,'selected':True},
                                             {'formation':5,'name':'Always','position':1,'selected':False},
                                             {'formation':6,'name':'Always','position':1,'selected':False}])
        self.assertEqual(RULES['set_borrow_setting'](s),[{'military_formation':5,'index':1}])

    def test_event_options_are_the_enabled_visible_positions(self):
        s=snapshot(event_history=[{'event':9,'event_type':'sample.1'}],
                   event_option=[{'event':9,'option':0,'enabled':True,'visible_position':0},{'event':9,'option':1,'enabled':True,'visible_position':None},
                                 {'event':9,'option':2,'enabled':False,'visible_position':1},{'event':9,'option':3,'enabled':True,'visible_position':2}])
        self.assertEqual(RULES['choose_event_option'](s),[{'event':'sample.1','option':0},{'event':'sample.1','option':2}])

    def test_formable_and_releasable_indexes_follow_list_positions(self):
        s=snapshot(player_formable_country=[{'name':'Italy','position':1,'formable':True,'ignored':False},
                                            {'name':'Germany','position':0,'formable':False,'ignored':False}],
                   player_releasable_country=[{'name':'Flanders','position':0,'possible':True}])
        self.assertEqual(RULES['form_country'](s),[{'index':1}])
        self.assertEqual(RULES['toggle_ignore_formable'](s),[{'index':0},{'index':1}])
        self.assertEqual(RULES['release_country'](s),[{'index':0}])

    def test_fleet_recall_needs_a_damaged_fleet_at_sea(self):
        s=snapshot(formation_history=[{'formation':5,'country':PLAYER,'formation_type':1},{'formation':6,'country':PLAYER,'formation_type':1}],
                   ship_history=[{'ship':1,'fleet':5},{'ship':2,'fleet':6}],
                   formation_report=[{'formation':5,'docked':False,'recalled':False,'hit_points_percent':.5},
                                      {'formation':6,'docked':True,'recalled':False,'hit_points_percent':.5}])
        self.assertEqual(RULES['recall_fleet'](s),[{'military_formation':5}])

    def test_strait_settings_follow_the_owned_shore_and_the_cooldown(self):
        straits=lambda **changes:snapshot(definitions={'common/strait_definitions':{'strait_gibraltar':{'tolls_require_full_control':['yes'],'total_block_requires_full_control':['yes']},'strait_bosporus':{}}},
                                          player_policy=[{'can_toll_straits':True,'can_close_straits':True,**changes.pop('policy',{})}],
                                          state_history=changes.pop('states',[{'state':1,'country':PLAYER},{'state':2,'country':OTHER},{'state':3,'country':PLAYER},{'state':4,'country':PLAYER}]),
                                          strait_endpoint=[{'strait':10,'first_state':1,'second_state':2},{'strait':11,'first_state':3,'second_state':4}],
                                          strait_history=[{'strait':10,'strait_definition':'strait_gibraltar','first_toll_rate':1,'second_toll_rate':1,'first_access_status':0,'first_access_permissions':0,
                                                           'second_access_status':0,'second_access_permissions':0},
                                                          {'strait':11,'strait_definition':'strait_bosporus','first_toll_rate':1,'second_toll_rate':0,'first_access_status':1,'first_access_permissions':1,
                                                           'second_access_status':0,'second_access_permissions':0,**changes.pop('bosporus',{})}],**changes)
        s=straits()
        self.assertEqual(RULES['set_strait_toll'](s),[{'strait':11,'level':'NoTolls'},{'strait':11,'level':'MediumTolls'},{'strait':11,'level':'HighTolls'}])
        self.assertEqual(RULES['set_strait_access'](s),[{'strait':10,'state':1,'access':'NoMilitary'},{'strait':11,'state':3,'access':'Open'},{'strait':11,'state':3,'access':'Closed'}])
        self.assertEqual(RULES['set_strait_allowed'](s),[{'strait':11,'state':3,'allowed':'OnlyAllies'},{'strait':11,'state':3,'allowed':'OnlyController'}])
        self.assertEqual(RULES['set_strait_access'](straits(policy={'can_close_straits':False})),[{'strait':11,'state':3,'access':'Open'}])
        self.assertEqual(RULES['set_strait_toll'](straits(policy={'can_toll_straits':False})),[])
        recent=straits(bosporus={'first_last_toll_rate_change':1000-24,'first_last_access_change':1000-24})
        self.assertEqual(RULES['set_strait_toll'](recent),[])
        self.assertEqual(RULES['set_strait_access'](recent),[{'strait':10,'state':1,'access':'NoMilitary'}])
        self.assertEqual(len(RULES['set_strait_allowed'](recent)),2)
        old=straits(bosporus={'first_last_toll_rate_change':1000-200*24,'first_last_access_change':1000-200*24})
        self.assertEqual(len(RULES['set_strait_toll'](old)),3)
        occupied=straits(occupation_history=[{'state':3,'controller':OTHER}])
        self.assertEqual(RULES['set_strait_access'](occupied),[{'strait':10,'state':1,'access':'NoMilitary'},{'strait':11,'state':4,'access':'NoMilitary'},{'strait':11,'state':4,'access':'Closed'}])
        shared=straits(states=[{'state':1,'country':PLAYER},{'state':2,'country':OTHER},{'state':3,'country':OTHER},{'state':4,'country':OTHER}])
        self.assertEqual(RULES['set_strait_toll'](shared),[])
        self.assertEqual(RULES['set_strait_access'](shared),[{'strait':10,'state':1,'access':'NoMilitary'}])

    def test_ship_designs_offer_unlocked_modifications_absent_from_own_templates(self):
        definitions={'common/ship_types':{'ship_type_frigate':{'unlocking_technologies':[],'ship_group':['ship_group_light_ships'],
                                                              'modifications':['ship_mod_slot_armor = { mod_a mod_b } ship_mod_slot_utility_1 = { util_a } ship_mod_slot_guns = { mod_c mod_d }']}},
                     'common/ship_modifications':{'mod_a':{},'mod_b':{'unlocking_technologies':['tech_x']},'mod_c':{},'mod_d':{'unlocking_technologies':['tech_y','tech_z']},'util_a':{}},
                     'common/ship_modification_slots':{'ship_mod_slot_armor':{},'ship_mod_slot_guns':{},'ship_mod_slot_utility_1':{'utility':['yes']}},
                     'common/technology/technologies':{'tech_x':{},'tech_y':{},'tech_z':{}}}
        s=snapshot(definitions=definitions,country_research_history=[{'country_research':3,'country':PLAYER,'researching':None}],
                   country_research_acquired=[{'country_research':3,'technology':'tech_z'}],
                   ship_template_history=[{'ship_template':9,'country':PLAYER,'ship_type':'ship_type_frigate'}],
                   ship_template_version_list=[{'ship_template':9,'position':0,'ship_template_version':21},{'ship_template':9,'position':1,'ship_template_version':22}],
                   ship_template_version_modification=[{'ship_template_version':21,'position':0,'ship_modification':'mod_c'},{'ship_template_version':22,'position':0,'ship_modification':'mod_a'}])
        self.assertEqual(RULES['design_ship_template'](s),[{'ship_type':'ship_type_frigate','ship_modification':'mod_c'},{'ship_type':'ship_type_frigate','ship_modification':'mod_d'}])

    def test_retrofit_offers_follow_the_fleet_report(self):
        s=snapshot(formation_history=[{'formation':5,'country':PLAYER,'formation_type':1},{'formation':6,'country':PLAYER,'formation_type':1},{'formation':7,'country':PLAYER,'formation_type':1}],
                   ship_history=[{'ship':1,'fleet':5},{'ship':2,'fleet':6},{'ship':3,'fleet':7}],
                   formation_report=[{'formation':5,'retrofittable':2,'retrofitting':False},{'formation':6,'retrofittable':0,'retrofitting':False},{'formation':7,'retrofittable':1,'retrofitting':True}])
        self.assertEqual(RULES['retrofit_fleet'](s),[{'military_formation':5}])
        self.assertEqual(RULES['cancel_retrofit_fleet'](s),[{'military_formation':7}])
        self.assertEqual(RULES['retrofit_all'](s),[{}])
        self.assertEqual(RULES['cancel_retrofit_all'](s),[{}])
        idle=snapshot(formation_history=[{'formation':6,'country':PLAYER,'formation_type':1}],ship_history=[{'ship':2,'fleet':6}],formation_report=[{'formation':6,'retrofittable':0,'retrofitting':False}])
        self.assertEqual(RULES['retrofit_all'](idle),[])
        self.assertEqual(RULES['cancel_retrofit_all'](idle),[])

    def test_tariff_level_reads_the_player_tariff_by_direction(self):
        s=snapshot(player_tariff=[{'direction':'import','goods':'grain','level':5},{'direction':'export','goods':'grain','level':1}])
        self.assertEqual(trade_level(s,'import','grain'),5)
        self.assertEqual(trade_level(s,'export','grain'),1)
        self.assertEqual(trade_level(s,'import','wood'),3)


if __name__=='__main__':
    unittest.main()


class DecodeFilterTests(unittest.TestCase):
    def reader(self,decoded):
        reader=Reader.__new__(Reader)
        reader.tables={'global_rng':{},'country':{}}
        reader.key_columns=set()
        reader.visible=visible_columns()
        reader.table=lambda name,visible=None:(decoded.append(name),({'id':np.array([1],dtype=np.int64)},{}))[1]
        reader.player=lambda:1
        return reader

    def test_decode_returns_every_table_including_hidden_ones(self):
        self.assertEqual(set(self.reader([]).decode()),{'global_rng','country'})

    def test_snapshot_applies_the_visibility_manifest(self):
        published=self.reader([]).snapshot()
        self.assertIn('country',published)
        self.assertNotIn('global_rng',published)

    def test_snapshot_never_decodes_hidden_tables(self):
        decoded=[]
        self.reader(decoded).snapshot()
        self.assertEqual(decoded,['country'])
