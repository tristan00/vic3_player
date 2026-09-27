from pathlib import Path
import random
import re
import struct
import time

from ..common import progress, slot, timed
from ..timing import span
from ..recording.capture import plain
from ..runner.memory import SCALE
from ..script import keys
from .catalogue import BY_NAME, KEYS, TYPES
from .gui import ABORT, VARIABLES, key_codes, key_table, split

GAP=.05
CYCLE=.3
PRIME=.1
TABLES={'military_formation':'formation'}
IDENTITY_OFFSETS={'building':16,'country':24}
LIMIT=5
ABORT_LIMIT=1


class Executor:
    def __init__(self,game):
        self.game=game
        self.mods=[mod for mod in game.session()['mods'] if (Path(mod).parent/'manifest.json').is_file()]
        self.indexes={}
        self.codes=key_codes(key_table(game.game_dir/'game',self.mods))
        self.last=0
        self.started=0
        self.flips={}

    def index(self,kind,name):
        folder=TYPES[kind][2]
        if folder not in self.indexes:
            self.indexes[folder]={key:position for position,key in enumerate(keys(self.game.game_dir/'game',folder,self.mods))}
        return self.indexes[folder][name]

    def identity(self,kind,ident):
        reader=self.game.reader()
        database=reader.word(reader.base+reader.tables[TABLES.get(kind,kind)]['rva'])
        table,capacity=struct.unpack('<QI',reader.read(database+0x20,12))
        if not 0<=ident<capacity:
            raise LookupError(f'{kind} {ident} is outside the game database')
        pointer=struct.unpack('<Q',reader.read(table+ident*16+8,8))[0]
        if not pointer:
            raise LookupError(f'{kind} {ident} no longer exists')
        identity=struct.unpack('<I',reader.read(pointer+IDENTITY_OFFSETS.get(kind,8),4))[0]
        if identity&0xffffff!=ident:
            raise LookupError(f'{kind} {ident} resolves to identity {identity:#x}')
        return identity

    def encode(self,action,params):
        if set(params)!=({split(p)[0] for p in action.params}):
            raise ValueError(f'{action.name} takes {action.params}, got {sorted(params)}')
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

    @timed
    def run(self,name,check=False,**params):
        action=BY_NAME[name]
        values,slots=self.encode(action,params)
        reader=self.game.reader()
        addresses=reader.variables(VARIABLES)
        seq=random.randrange(1,10**6)
        writes=[]
        for index,(code,ident) in enumerate(slots):
            writes+=[(addresses[f'interface_p{index}']+16,struct.pack('<I',code)),(addresses[f'interface_p{index}']+24,struct.pack('<q',ident))]
        key=(name,tuple(sorted(params.items())))
        self.flips[key]=flip=self.flips.get(key,0)^1
        for variable,value in (*values.items(),('interface_seq',seq),('interface_mode',0),('interface_action',list(BY_NAME).index(name)+1)):
            writes.append((addresses[variable]+24,struct.pack('<q',value*SCALE)))
        time.sleep(max(0,self.last+GAP-time.monotonic(),self.started+CYCLE-time.monotonic()))
        started=self.started=time.monotonic()
        done=f'INTERFACE|action|{seq}|'
        with span('interface.actions.execute.Executor.dispatch','interface') as dispatch:
            reader.write(writes)
            time.sleep(PRIME)
            reader.write([(addresses[variable]+24,struct.pack('<q',value*SCALE)) for variable,value in (('interface_mode',2 if check else 1),('interface_flip',flip))])
            while time.monotonic()-started<LIMIT:
                progress('executor')
                reader.check()
                text=self.game.log()
                if done in text:
                    self.last=time.monotonic()
                    valid,_,desc=re.split(r'\n(?=\[\d\d:\d\d:\d\d\])',text.rsplit(done,1)[1],maxsplit=1)[0].partition('|')
                    transport=re.findall(rf'INTERFACE\|transport\|{seq}\|(\w+)',text)
                    if transport and transport[-1]=='started':
                        valid,desc='1','transport started'
                    return {'action':name,'valid':valid=='1','desc':plain(desc),'ms':round(dispatch.ms)}
                time.sleep(.005)
        reader.write([(addresses['interface_mode']+24,struct.pack('<q',ABORT*SCALE))])
        aborted=time.monotonic()
        while done not in self.game.log() and time.monotonic()-aborted<ABORT_LIMIT:
            progress('executor abort')
            reader.check()
            time.sleep(.005)
        reader.write([(addresses['interface_action']+24,struct.pack('<q',0))])
        self.last=time.monotonic()
        raise LookupError(f'{name}: no game object matched {params}')
