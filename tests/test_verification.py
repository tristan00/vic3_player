import unittest
import struct
from unittest.mock import MagicMock, call, patch

from interface.actions.execute import Executor, PRIME, SCALE, verification
from interface.actions import gui
from interface.actions.catalogue import ACTIONS
from interface.runner.memory import Reader


class VerificationTests(unittest.TestCase):
    def test_key_binding_resets_during_dispatch_before_an_identical_request(self):
        widget=gui.key_widgets({'decree':['decree_road_maintenance']})[0]
        self.assertIn(gui.conjunction(gui.equal('interface_key',1),gui.equal('interface_mode',0)),widget)
        self.assertIn("GetVariableSystem.Set('interface_key_ready', '1')",widget)

    def test_variable_writes_resolve_relocated_storage_while_suspended(self):
        reader=Reader.__new__(Reader)
        reader.pid=123
        state={'base':1000,'suspended':False}
        def suspend():
            state['base']+=1000
            state['suspended']=True
        def resume():
            state['suspended']=False
        def variables(names):
            self.assertTrue(state['suspended'])
            return {name:state['base'] for name in names}
        def write(writes):
            self.assertTrue(state['suspended'])
            self.assertEqual(writes,[(state['base']+24,b'value')])
        reader.variables=MagicMock(side_effect=variables)
        reader.write=MagicMock(side_effect=write)
        with patch('interface.runner.memory.psutil.Process') as process:
            process.return_value.suspend.side_effect=suspend
            process.return_value.resume.side_effect=resume
            reader.write_variables([('interface_mode',24,b'value')])
            reader.write_variables([('interface_mode',24,b'value')])
            self.assertEqual(process.return_value.resume.call_count,2)
        self.assertFalse(state['suspended'])
        self.assertEqual(reader.variables.call_count,2)

    def test_variable_write_failures_always_resume_the_game(self):
        for stage in ('variables','write'):
            reader=Reader.__new__(Reader)
            reader.pid=123
            reader.variables=MagicMock(return_value={'interface_mode':1000})
            reader.write=MagicMock()
            getattr(reader,stage).side_effect=RuntimeError('failed')
            with patch('interface.runner.memory.psutil.Process') as process:
                with self.assertRaisesRegex(RuntimeError,'failed'):
                    reader.write_variables([('interface_mode',24,b'value')])
                process.return_value.resume.assert_called_once()

    def test_capture_requests_use_protected_variable_writes(self):
        reader=Reader.__new__(Reader)
        reader.table=MagicMock(return_value=({'event_event':[]},{}))
        reader.write=MagicMock()
        reader.write_variables=MagicMock()
        reader.control_targets=MagicMock(return_value={'interface_capture_done':1000})
        reader.captured=MagicMock()
        reader.request_capture(42)
        reader.write.assert_not_called()
        reader.write_variables.assert_called_once_with([
            ('interface_capture_seq',24,struct.pack('<q',42*SCALE)),
            ('interface_capture_done',24,struct.pack('<q',0)),
            ('interface_capture',24,struct.pack('<q',SCALE))])
        reader.captured.assert_called_once()

    def test_dispatch_and_abort_never_reuse_variable_addresses(self):
        reader=MagicMock()
        reader.variables.return_value={name:64*index for index,name in enumerate(gui.VARIABLES)}
        reader.read.return_value=struct.pack('<q',123*SCALE)
        executor=Executor.__new__(Executor)
        executor.game=MagicMock()
        executor.game.reader.return_value=reader
        executor.game.log_since.return_value='INTERFACE|action|124|0|\n'
        executor.flips={}
        executor.answer=MagicMock(return_value=None)
        with patch('interface.actions.execute.time.sleep'):
            with self.assertRaises(LookupError):
                executor.run('pause')
        reader.write.assert_not_called()
        self.assertEqual(reader.write_variables.call_count,4)
        writes=[call.args[0] for call in reader.write_variables.call_args_list]
        self.assertEqual(writes[2],[('interface_mode',24,struct.pack('<q',3*SCALE))])
        self.assertEqual(writes[3],[('interface_action',24,struct.pack('<q',0))])

    def test_requests_advance_the_native_sequence_without_random_collisions(self):
        reader=MagicMock()
        addresses={name:64*index for index,name in enumerate(gui.VARIABLES)}
        reader.variables.return_value=addresses
        values={'seq':123}
        reader.read.side_effect=lambda address,size:struct.pack('<q',values['seq']*SCALE)
        sequences=[]
        def write(writes):
            for name,offset,data in writes:
                if name=='interface_seq':
                    values['seq']=struct.unpack('<q',data)[0]//SCALE
                    sequences.append(values['seq'])
        reader.write_variables.side_effect=write
        executor=Executor.__new__(Executor)
        executor.game=MagicMock()
        executor.game.reader.return_value=reader
        executor.game.log_since.side_effect=lambda mark:f"INTERFACE|action|{values['seq']}|1|\n"
        executor.flips={}
        with patch('interface.actions.execute.time.sleep') as sleep:
            self.assertTrue(executor.run('pause')['valid'])
            self.assertTrue(executor.run('pause')['valid'])
        self.assertEqual(sleep.call_args_list,[call(PRIME),call(PRIME)])
        self.assertEqual(sequences,[124,125])

    def test_native_validity_is_preserved(self):
        self.assertEqual(verification('INTERFACE|action|7|1|\n','INTERFACE|action|7|'),(True,''))
        self.assertEqual(verification('INTERFACE|action|7|0|insufficient funds\n','INTERFACE|action|7|'),(False,'insufficient funds'))

    def test_missing_malformed_or_duplicate_results_cannot_be_recorded_as_done(self):
        for text in ('INTERFACE|action|8|1|\n','INTERFACE|action|7||\n','INTERFACE|action|7|yes|\n',
                     'INTERFACE|action|7|1\n','INTERFACE|action|7|1|\nINTERFACE|action|7|1|\n'):
            with self.subTest(text=text),self.assertRaises(RuntimeError):
                verification(text,'INTERFACE|action|7|')

    def test_transport_refusal_overrides_the_valid_popup_opener(self):
        for result in ('refused not enough flotillas','no fleet no valid fleet'):
            text=f'INTERFACE|transport|7|{result}\n[00:00:01] INTERFACE|action|7|1|\n'
            valid,desc=verification(text,'INTERFACE|action|7|')
            self.assertFalse(valid)
            self.assertEqual(desc,'transport '+result)

    def test_only_matching_transport_verification_can_override_a_result(self):
        text='INTERFACE|transport|6|started\n[00:00:01] INTERFACE|action|7|0|blocked\n'
        self.assertEqual(verification(text,'INTERFACE|action|7|'),(False,'blocked'))
        text='INTERFACE|transport|7|started\n[00:00:01] INTERFACE|action|7|0|blocked\n'
        self.assertEqual(verification(text,'INTERFACE|action|7|'),(True,'transport started'))

    def test_unknown_transport_result_is_a_verification_error(self):
        with self.assertRaisesRegex(RuntimeError,'Malformed transport'):
            verification('INTERFACE|transport|7|\n[00:00:01] INTERFACE|action|7|1|\n','INTERFACE|action|7|')

    def test_each_execute_and_check_variant_sets_validity_before_cleanup(self):
        for code,action in enumerate(ACTIONS,1):
            for index,values in gui.variants(action):
                for chain in action.alternatives or (action.datamodels,):
                    states=gui.states(code,action,chain,index,values)
                    states=[state for state in states if state.startswith('state =')]
                    self.assertEqual(len(states),6 if action.valid else 4,action.name)
                    for state in states:
                        self.assertIn("GetVariableSystem.Set('interface_action_valid'",state,action.name)
                        self.assertLess(state.index("GetVariableSystem.Set('interface_action_valid'"),state.index("GetVariableSystem.Set('interface_clean'"),action.name)


if __name__=='__main__':
    unittest.main()
