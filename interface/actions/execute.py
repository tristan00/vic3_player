import logging
from pathlib import Path
import re
import struct
import time

from ..common import evidence, progress, slot, timed, timed_often
from ..timing import span
from ..recording.capture import plain
from ..runner.memory import SCALE
from ..script import keys
from .catalogue import BY_NAME, KEYS, TYPES
from .gui import ABORT, VARIABLES, key_codes, key_table, split

PRIME=.1
TABLES={'military_formation':'formation'}
IDENTITY_OFFSETS={'building':16,'country':24}
LIMIT=5
POLL=.005
ABORT_LIMIT=1


@timed_often
def verification(text,done):
    if text.count(done)!=1:
        raise RuntimeError(evidence(done=done,count=text.count(done)))
    payload=re.split(r'\n(?=\[\d\d:\d\d:\d\d\])',text.split(done,1)[1],maxsplit=1)[0]
    valid,separator,desc=payload.partition('|')
    if not separator or valid not in ('0','1'):
        raise RuntimeError(evidence(done=done,payload=payload[:200]))
    transport=re.findall(r'INTERFACE\|transport\|'+re.escape(done.split('|')[2])+r'\|([^\r\n]*)',text)
    if transport:
        outcome=transport[-1]
        if not any(outcome==prefix or outcome.startswith(prefix+' ') for prefix in ('started','refused','no fleet')):
            raise RuntimeError(evidence(outcome=outcome))
        valid='1' if outcome=='started' or outcome.startswith('started ') else '0'
        desc='transport '+outcome
    return valid=='1',plain(desc)


class Executor:
    @timed_often
    def __init__(self,game):
        self.game=game
        self.mods=[mod for mod in game.session()['mods'] if (Path(mod).parent/'manifest.json').is_file()]
        self.indexes={}
        self.codes=key_codes(key_table(game.game_dir/'game',self.mods))
        self.flips={}

    @timed_often
    def index(self,kind,name):
        folder=TYPES[kind][2]
        if folder not in self.indexes:
            self.indexes[folder]={key:position for position,key in enumerate(keys(self.game.game_dir/'game',folder,self.mods))}
        return self.indexes[folder][name]

    @timed_often
    def identity(self,kind,ident):
        reader=self.game.reader()
        database=reader.word(reader.base+reader.tables[TABLES.get(kind,kind)]['rva'])
        table,capacity=struct.unpack('<QI',reader.read(database+0x20,12))
        if not 0<=ident<capacity:
            raise LookupError(evidence(kind=kind,ident=ident,capacity=capacity))
        pointer=struct.unpack('<Q',reader.read(table+ident*16+8,8))[0]
        if not pointer:
            raise LookupError(evidence(kind=kind,ident=ident))
        identity=struct.unpack('<I',reader.read(pointer+IDENTITY_OFFSETS.get(kind,8),4))[0]
        if identity&0xffffff!=ident:
            raise LookupError(evidence(kind=kind,ident=ident,identity=hex(identity)))
        return identity

    @timed_often
    def encode(self,action,params):
        if set(params)!=({split(p)[0] for p in action.params}):
            raise ValueError(evidence(name=action.name,takes=action.params,got=sorted(params)))
        values={'interface_choice':0,'interface_key':0,'interface_n0':0,'interface_n1':0}
        slots=[]
        for param in action.params:
            name,kind=split(param)
            value=params[name]
            if kind in TYPES:
                code,_,folder=TYPES[kind]
                slots.append((code,self.index(kind,value) if folder else self.identity(kind,slot(value))))
            elif kind in KEYS:
                values['interface_key']=self.codes[kind,value]
            elif kind=='event':
                namespace,_,ordinal=value.rpartition('.')
                values['interface_key']=self.codes['event_namespace',namespace]
                values['interface_n1']=int(ordinal)
            elif kind=='int':
                values['interface_n0']=int(value)
            elif kind=='choice':
                values['interface_choice']=action.choices.index(value)
        return values,slots

    @timed_often
    def answer(self,reader,mark,done,started):
        while time.monotonic()-started<LIMIT:
            progress('executor')
            reader.check()
            text=self.game.log_since(mark)
            if done in text and '\n' in text.rsplit(done,1)[1]:
                return text
            time.sleep(POLL)

    @timed
    def run(self,name,check=False,**params):
        action=BY_NAME[name]
        values,slots=self.encode(action,params)
        reader=self.game.reader()
        addresses=reader.variables(VARIABLES)
        previous=struct.unpack('<q',reader.read(addresses['interface_seq']+24,8))[0]//SCALE
        seq=previous%(2**31-1)+1
        writes=[]
        for index,(code,ident) in enumerate(slots):
            writes+=[(f'interface_p{index}',16,struct.pack('<I',code)),(f'interface_p{index}',24,struct.pack('<q',ident))]
        key=(name,tuple(sorted(params.items())))
        self.flips[key]=flip=self.flips.get(key,0)^1
        for variable,value in (*values.items(),('interface_seq',seq),('interface_mode',0),('interface_action',list(BY_NAME).index(name)+1)):
            writes.append((variable,24,struct.pack('<q',value*SCALE)))
        mark=self.game.log_mark()
        started=time.monotonic()
        done=f'INTERFACE|action|{seq}|'
        with span('interface.actions.execute.Executor.dispatch','interface') as dispatch:
            reader.write_variables(writes)
            with span('interface.actions.execute.Executor.prime','interface',logging.DEBUG):
                time.sleep(PRIME)
            reader.write_variables([(variable,24,struct.pack('<q',value*SCALE)) for variable,value in (('interface_mode',2 if check else 1),('interface_flip',flip))])
            text=self.answer(reader,mark,done,started)
            if text is not None:
                valid,desc=verification(text,done)
                return {'action':name,'valid':valid,'desc':desc,'ms':round(dispatch.ms)}
        self.abort(reader,mark,done)
        raise LookupError(evidence(name=name,params=params))

    @timed_often
    def abort(self,reader,mark,done):
        reader.write_variables([('interface_mode',24,struct.pack('<q',ABORT*SCALE))])
        aborted=time.monotonic()
        while done not in self.game.log_since(mark) and time.monotonic()-aborted<ABORT_LIMIT:
            progress('executor abort')
            reader.check()
            time.sleep(POLL)
        reader.write_variables([('interface_action',24,struct.pack('<q',0))])
