import importlib
import re
import unittest

from interface.common import DEFAULT_GAME
from interface.recording import capture

record=importlib.import_module('interface.recording.record')


def truncated(value,part):
    quotient=abs(value)//part*(1 if value>=0 else -1)
    return quotient,value-quotient*part


def parts(value,count):
    result=[]
    for index in range(count):
        if index==count-1:
            result.append(value)
        else:
            value,remainder=truncated(value,capture.PART)
            result.append(remainder)
    return result


def held(variables=None,lists=None,maps=None,seq=7):
    return record.Held({'variables':{'cap_seq':('value',float(seq)),**(variables or {})},'lists':lists or {},'maps':maps or {}},7,{})


class IntegerPartTests(unittest.TestCase):
    def test_every_integer_is_rebuilt_exactly_from_its_parts(self):
        for count,values in ((2,(0,1,-1,65535,65536,-65536,-70000,2**31-1,-2**31)),(3,(2**40+5,-(2**35)-3,4_000_000_000,-1))):
            for value in values:
                maps={f'cap_x__p{index}':{(5,1):('flag',str(part))} for index,part in enumerate(parts(value,count))}
                self.assertEqual(held(maps=maps).column('cap_x'),{(5,1):('value',float(value))},value)

    def test_the_generated_parts_follow_the_rebuilt_order(self):
        generated=capture.integer_parts('X','int64')
        self.assertEqual(len(generated),capture.INTEGER_PARTS['int64'])
        self.assertIn("Modulo_int64(X,'(int64)65536')",generated[0])
        self.assertIn("Modulo_int64(Divide_int64(X,'(int64)65536'),'(int64)65536')",generated[1])
        self.assertIn("Divide_int64(Divide_int64(X,'(int64)65536'),'(int64)65536')",generated[2])

    def test_parts_covering_different_objects_are_rejected(self):
        maps={'cap_x__p0':{(5,1):('flag','1')},'cap_x__p1':{(5,2):('flag','0')}}
        with self.assertRaises(RuntimeError):
            held(maps=maps).column('cap_x')


class HolderTests(unittest.TestCase):
    def test_a_holder_from_another_request_is_rejected(self):
        with self.assertRaises(RuntimeError):
            record.Held({'variables':{'cap_seq':('value',6.0)},'lists':{},'maps':{}},7,{})

    def test_an_object_missing_a_field_is_rejected(self):
        maps={'cap_building_auto_expand':{(11,3):('value',1.0)}}
        with self.assertRaises(RuntimeError):
            held(maps=maps).fields('building',[(11,3)],('auto_expand','output_paused'))

    def test_counted_maps_must_hold_every_counted_entry(self):
        maps={name:{('value',1.0):('flag','x')} for name in capture.MESSAGE_MAPS}
        with self.assertRaises(RuntimeError):
            record._counted(held({'cap_message_count':('value',2.0)},maps=maps),capture.MESSAGE_MAPS,'cap_message_count')

    def test_a_repeated_message_feed_keeps_one_copy_without_markup(self):
        rows=[('Feb 1','battle','Battle won','We won'),('Feb 2','tech','\x15tooltippable_name \x15tooltip:dw_1,wJ=,DATA,T Urban Planning\x15!\x15! spreading','x')]*2
        maps={name:{('value',float(index+1)):('flag',row[column]) for index,row in enumerate(rows)} for column,name in enumerate(capture.MESSAGE_MAPS)}
        self.assertEqual(record._messages(held({'cap_message_count':('value',4.0)},maps=maps)),
                         [(0,'Feb 1','battle','Battle won','We won'),(1,'Feb 2','tech','Urban Planning spreading','x')])

    def test_a_list_item_of_the_wrong_kind_is_rejected(self):
        with self.assertRaises(RuntimeError):
            held(lists={'cap_method':[(5,1)]}).flags('cap_method')


class GeneratedCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DEFAULT_GAME/'game').is_dir():
            raise unittest.SkipTest('game install not present')
        cls.body=capture.capture_body(DEFAULT_GAME,'XAA')

    def test_every_container_written_is_cleared_at_the_start_of_each_capture(self):
        cleared=set(re.findall(r'clear_variable_(?:list|map) = (cap_\w+)',self.body))|set(re.findall(r'set_variable = \{ name = (cap_\w+) value = 0 \}',self.body))
        written=set(re.findall(r'add_to_variable_(?:list|map) = \{ name = (cap_\w+)',self.body+capture.capture_guis()))
        written|=set(re.findall(r'change_variable = \{ name = (cap_\w+)',self.body+capture.capture_guis()))
        self.assertEqual(written-cleared,set())

    def test_every_map_name_is_used_by_one_field_only(self):
        names=[name for group in capture.groups() for name in group.maps.values()]
        self.assertEqual(len(names),len(set(names)))

    def test_every_scripted_gui_the_widgets_call_is_defined(self):
        called=set(re.findall(r"GetScriptedGui\('(cap_\w+)'\)",capture.capture_widgets()))
        defined=set(re.findall(r'^(cap_\w+) = \{',capture.capture_guis(),re.M))
        self.assertEqual(called-defined,set())


if __name__=='__main__':
    unittest.main()
