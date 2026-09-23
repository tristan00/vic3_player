import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import struct
import time
import weakref

import numpy as np

from ..common import DEFAULT_GAME, timed
from ..script import read, scalar
from ..visibility import Visibility

LAYOUT=json.loads((Path(__file__).parent/'layout.json').read_text())
VISIBILITY=Visibility()
RUN_GAP=1<<16
SCALE=100000
IDENTITY_OFFSETS={'building':16,'country':24}
CONTROL_VARIABLES=('interface_capture','interface_capture_done','interface_capture_seq')
CHUNK=1024
HEAP_LOW,HEAP_HIGH=0x10000000000,0x7f0000000000
MONTH_STARTS=[0,31,59,90,120,151,181,212,243,273,304,334]

kernel=ctypes.WinDLL('kernel32',use_last_error=True)
psapi=ctypes.WinDLL('psapi',use_last_error=True)
kernel.OpenProcess.restype=wintypes.HANDLE
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
kernel.ReadProcessMemory.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
kernel.WriteProcessMemory.argtypes=kernel.ReadProcessMemory.argtypes
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
psapi.EnumProcessModules.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]


def outputs(name,spec):
    names=[name]
    for group in ('vectors','nested_vectors','arrays','column_arrays','column_vectors','column_goods','vector_goods','goods_arrays'):
        names+=list(spec.get(group,{}))
    names+=[name+'_province_range']*('province_runs' in spec)+['state_pop_need']*('pop_needs' in spec)+['market_goods']*('goods' in spec)
    names+=[name+'_list',name+'_list_item']*('variable_lists' in spec)
    names+=[child for trend in spec.get('trends',{}) for child in (name+'_'+trend,name+'_'+trend+'_channel')]
    return names


def visible_columns():
    visible={}
    pending=[name for name,spec in VISIBILITY.tables.items() if spec['disposition']!='drop']
    while pending:
        name=pending.pop()
        spec=VISIBILITY.tables[name]
        owner=spec.get('owner',('all',))
        dropped=set(spec.get('drop',()))-({owner[1]} if owner[0]=='column' else set())-{'id'}
        visible[name]=dropped if spec['disposition']!='drop' else set()
        if owner[0]=='via' and owner[1] not in visible:
            pending.append(owner[1])
    return visible


class Reader:
    def __init__(self,pid,game_dir=DEFAULT_GAME,mods=()):
        self.pid=pid
        self.handle=kernel.OpenProcess(0x410,False,pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._close=weakref.finalize(self,kernel.CloseHandle,self.handle)
        modules=(wintypes.HMODULE*1)();needed=wintypes.DWORD()
        if not psapi.EnumProcessModules(self.handle,modules,ctypes.sizeof(modules),ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not modules[0]:
            raise OSError(f'process {pid} has not loaded its executable yet')
        self.base=modules[0]
        self.tables=LAYOUT['tables']
        self.keys={}
        self.names=[]
        self.key_columns=set()
        self.visible=visible_columns()
        goods=list(dict(read(Path(game_dir)/'game','common/goods',mods)))
        categories={name:(scalar(content,'cultural_identity')=='yes',scalar(content,'religious_identity')=='yes')
                    for name,content in read(Path(game_dir)/'game','common/political_movement_categories',mods)}
        self.movement_identities={name:categories[scalar(content,'category')]
                                  for name,content in read(Path(game_dir)/'game','common/political_movements',mods)}
        self.names+=[('goods',name) for name in goods]
        self.goods_codes=np.arange(1,len(goods)+1,dtype=np.int32)
        self.scope_definition_codes={}
        for scope,(kind,directory) in LAYOUT.get('scope_definitions',{}).items():
            definitions=list(dict(read(Path(game_dir)/'game',directory,mods)))
            start=len(self.names)+1
            self.names.extend((kind,name) for name in definitions)
            self.scope_definition_codes[int(scope)]=np.arange(start,start+len(definitions),dtype=np.int32)
        for table,vtable in LAYOUT['database_vtable'].items():
            database=self.word(self.base+self.tables[table]['rva'])
            if self.word(database)-self.base!=vtable:
                raise RuntimeError(f'Unsupported game build: {table} database signature differs from layout {LAYOUT["version"]}')

    def close(self):
        self._close()
        self.handle=None

    def read(self,address,size):
        data=ctypes.create_string_buffer(size);count=ctypes.c_size_t()
        if not kernel.ReadProcessMemory(self.handle,address,data,size,ctypes.byref(count)) or count.value!=size:
            raise OSError(f'Cannot read {size} bytes at {address:#x}')
        return data.raw

    def array(self,address,size):
        data=np.empty(size//8,dtype='<i8');count=ctypes.c_size_t()
        if not kernel.ReadProcessMemory(self.handle,address,data.ctypes.data,size,ctypes.byref(count)) or count.value!=size:
            raise OSError(f'Cannot read {size} bytes at {address:#x}')
        return data

    def is_object(self,address,vtable):
        try:
            return address&7==0 and self.word(address)==vtable
        except OSError:
            return False

    def word(self,address):
        return struct.unpack('<Q',self.read(address,8))[0]

    @timed
    def event_options(self):
        pointer=self.word(self.base+0x592d0e0)
        for offset in (0x10,0x20):
            pointer=self.word(pointer+offset)
        if self.word(pointer)!=self.base+0x45ae328:
            raise RuntimeError('Unsupported ingame interface handler')
        manager=self.word(pointer+0x1df0)
        array,capacity,count=struct.unpack('<QII',self.read(manager+0x10,16))
        if count>capacity or count>100000:
            raise RuntimeError('Invalid pending-event window collection')
        _,ids,addresses=self.objects(self.tables['event']['rva'])
        live={int(ident):int(address) for ident,address in zip(ids,addresses)}
        result={}
        for (window,) in struct.iter_unpack('<Q',self.read(array,count*8) if count else b''):
            if self.word(window)!=self.base+0x45b9ad8:
                raise RuntimeError('Unsupported pending-event window')
            reference=self.word(window+0x88)
            identity=struct.unpack('<I',self.read(reference+16,4))[0]
            slot=identity&0xffffff
            if slot not in live or struct.unpack('<I',self.read(live[slot]+8,4))[0]!=identity:
                raise RuntimeError('Event window refers to an expired event instance')
            if slot in result:
                raise RuntimeError('Duplicate event window instance')
            options,capacity,count=struct.unpack('<QII',self.read(window+0x110,16))
            if count>capacity or count>10000:
                raise RuntimeError('Invalid event-option collection')
            rows=[]
            for index in range(count):
                option=options+index*88
                if self.word(option)!=window:
                    raise RuntimeError('Event option belongs to a different window')
                ordinal=struct.unpack('<I',self.read(option+8,4))[0]
                enabled,default=struct.unpack('<BB',self.read(option+81,2))
                if enabled>1 or default>1:
                    raise RuntimeError('Invalid native event-option flags')
                rows.append((ordinal,index,enabled,default,self.string(option+16),self.string(option+48)))
            if len({row[0] for row in rows})!=len(rows):
                raise RuntimeError('Duplicate native event-option identity')
            definition=self.word(live[slot]+24)
            capacity,total=struct.unpack('<II',self.read(definition+0x148,8))
            if total>capacity or total>10000:
                raise RuntimeError('Invalid native event-option definition collection')
            shown={row[0]:row for row in rows}
            if not shown.keys()<=set(range(total)):
                raise RuntimeError('Native event option has no matching definition')
            result[slot]=[shown.get(ordinal,(ordinal,-1,0,0,None,None)) for ordinal in range(total)]
        return result

    def variables(self,names):
        country=self.player()
        _,slots,addresses=self.objects(self.tables['country']['rva'])
        address=int(addresses[np.nonzero(slots==country)[0][0]])
        offset=self.tables['country']['vectors']['country_variable'][4]
        store=self.word(address+offset)
        pointer,capacity,count=struct.unpack('<QII',self.read(store+8,16))
        if count>capacity:
            raise RuntimeError('Invalid variable store')
        values=self.read(pointer,count*32)
        codes=self.tokens(np.array([struct.unpack_from('<I',values,index*32+8)[0] for index in range(count)],dtype=np.int64))
        found={self.names[int(code)-1][1]:pointer+index*32 for index,code in enumerate(codes) if self.names[int(code)-1][1] in names}
        if len(found)!=len(names):
            raise RuntimeError(f'The running control mod lacks variables {sorted(set(names)-set(found))}; restart the campaign with the current control mod')
        return found

    def item(self,kind,value):
        if kind==3:
            return ('flag',self.names[int(self.tokens(np.array([value],dtype=np.int64))[0])-1][1])
        if kind==1:
            return ('value',value/SCALE)
        return (int(kind),int(value)&0xffffff)

    @timed
    def holder(self):
        return self.holders([self.player()])[self.player()]

    @timed
    def holders(self,countries):
        _,slots,addresses=self.objects(self.tables['country']['rva'])
        return {country:self.held_at(int(addresses[np.nonzero(slots==country)[0][0]])) for country in countries}

    def held_at(self,address):
        spec=self.tables['country']
        name=lambda code:self.names[int(self.tokens(np.array([code],dtype=np.int64))[0])-1][1]
        store=self.word(address+spec['vectors']['country_variable'][4])
        if not store:
            return {'variables':{},'lists':{},'maps':{}}
        pointer,capacity,count=struct.unpack('<QII',self.read(store+8,16))
        if count>capacity:
            raise RuntimeError('Invalid variable store')
        raw=self.read(pointer,count*32) if count else b''
        variables={name(code):self.item(kind,value) for code,kind,value in
                   (struct.unpack_from('<I4xI4xq',raw,index*32+8) for index in range(count))}
        container=self.word(address+spec['variable_lists']['pointer'])
        pointer,capacity,count=struct.unpack('<QII',self.read(container,16)) if container else (0,0,0)
        if count>capacity:
            raise RuntimeError('Invalid variable list container')
        lists={}
        raw=self.read(pointer,count*64) if count else b''
        for index in range(count):
            code,items,size=struct.unpack_from('<I4xQ4xI',raw,index*64+8)
            entries=self.read(items,size*16) if size else b''
            lists[name(code)]=[self.item(*struct.unpack_from('<I4xq',entries,position*16)) for position in range(size)]
        container=self.word(address+spec['variable_maps']['pointer'])
        pointer,capacity,count=struct.unpack('<QII',self.read(container,16)) if container else (0,0,0)
        if count>capacity:
            raise RuntimeError('Invalid variable map container')
        maps={}
        raw=self.read(pointer,count*48) if count else b''
        for index in range(count):
            code,=struct.unpack_from('<I',raw,index*48)
            table,size,mask,overflow=struct.unpack_from('<QIIB',raw,index*48+16)
            if mask&(mask+1) or overflow>64:
                raise RuntimeError('Invalid variable map capacity')
            slots=self.read(table,(mask+1+overflow)*48)
            entries={}
            for position in range(mask+1+overflow):
                if slots[position*48+4]:
                    key_kind,key,value_kind,value=struct.unpack_from('<I4xqI4xq',slots,position*48+8)
                    entries[self.item(key_kind,key)]=self.item(value_kind,value)
            if len(entries)!=size:
                raise RuntimeError(f'Variable map {name(code)} holds {size} entries but {len(entries)} slots are occupied')
            maps[name(code)]=entries
        return {'variables':variables,'lists':lists,'maps':maps}

    def control_targets(self):
        return {name:address+24 for name,address in self.variables(CONTROL_VARIABLES).items()}

    def write(self,writes):
        handle=kernel.OpenProcess(0x28,False,self.pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for address,data in writes:
                written=ctypes.c_size_t()
                if not kernel.WriteProcessMemory(handle,address,data,len(data),ctypes.byref(written)) or written.value!=len(data):
                    raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(handle)

    @timed
    def request_capture(self,nonce,timeout=30,save=False):
        events,_=self.table('event')
        if any(not key or not self.names[int(key)-1][1] for key in events['event_event']):
            raise RuntimeError('Pending event has no loaded definition')
        targets=self.control_targets()
        self.write([(targets[name],struct.pack('<q',value)) for name,value in
                    (('interface_capture_seq',nonce*SCALE),('interface_capture_done',0),('interface_capture',200000 if save else 100000))])
        deadline=time.monotonic()+timeout
        while self.word(targets['interface_capture_done'])!=200000 or self.word(targets['interface_capture'])!=0:
            if time.monotonic()>deadline:
                raise TimeoutError('The game did not acknowledge the live capture request')
            time.sleep(.002)
            targets=self.control_targets()

    def gather(self,addresses,size):
        size=(size+7)&~7
        result=np.zeros((len(addresses),size//8),dtype='<i8')
        order=np.argsort(addresses)
        order=order[(addresses[order]>HEAP_LOW)&(addresses[order]<HEAP_HIGH)&(addresses[order]&7==0)]
        ordered=addresses[order]
        breaks=np.nonzero(np.diff(ordered)>RUN_GAP)[0]+1
        pending=[run for run in np.split(np.arange(len(ordered)),breaks) if len(run)]
        while pending:
            run=pending.pop()
            start=int(ordered[run[0]])
            try:
                data=self.array(start,int(ordered[run[-1]])-start+size)
            except OSError:
                if len(run)>1:
                    pending+=[run[:len(run)//2],run[len(run)//2:]]
                    continue
                raise
            index=((ordered[run]-start)//8)[:,None]+np.arange(size//8)[None,:]
            result[order[run]]=data[index]
        return result

    def objects(self,rva):
        database=self.word(self.base+rva)
        table,capacity=struct.unpack('<QI',self.read(database+0x20,12))
        entries=np.frombuffer(self.read(table,capacity*16),dtype='<u8')[1::2]
        slots=np.nonzero(entries)[0]
        return database,slots.astype(np.int32),entries[slots].astype(np.int64)

    def string(self,address):
        raw=self.read(address,32)
        size,capacity=struct.unpack_from('<QQ',raw,16)
        if size>1<<16 or capacity<size:
            raise OSError(f'No string at {address:#x}')
        return (self.read(struct.unpack_from('<Q',raw)[0],size) if capacity>=16 else raw[:size]).decode('utf-8','replace')

    def codes(self,kind,pointers,inner=0x18):
        if kind in LAYOUT.get('key_sentinels',{}):
            pointers=np.where(pointers==self.word(self.base+LAYOUT['key_sentinels'][kind]),0,pointers)
        if kind in LAYOUT['key_vtables']:
            vtable=self.base+LAYOUT['key_vtables'][kind]
            foreign={pointer for pointer in np.unique(pointers).tolist() if HEAP_LOW<pointer<HEAP_HIGH and not self.is_object(pointer,vtable)}
            pointers=np.where(np.isin(pointers,list(foreign)),0,pointers)
        unique=np.unique(pointers)
        for pointer in unique.tolist():
            if HEAP_LOW<pointer<HEAP_HIGH and pointer not in self.keys:
                self.names.append((kind,self.string(pointer+inner)))
                self.keys[pointer]=len(self.names)
        lookup=np.array([self.keys.get(p,0) for p in unique.tolist()],dtype=np.int32)
        return lookup[np.searchsorted(unique,pointers)]

    def tokens(self,values):
        table=self.word(self.base+LAYOUT['tokens'])
        values=values&0xFFFFFFFF
        unique=np.unique(values)
        for token in unique.tolist():
            if ('token',token) not in self.keys:
                self.names.append(('token',self.string(self.word(table+token*8))))
                self.keys['token',token]=len(self.names)
        lookup=np.array([self.keys['token',t] for t in unique.tolist()],dtype=np.int32)
        return lookup[np.searchsorted(unique,values)]

    def member(self,child,column,kind,values):
        if kind=='q':
            return values/100000
        if kind=='w':
            return values
        if kind=='i':
            return values.astype(np.int32)
        if kind=='u':
            return values&0xffffffff
        if kind=='b':
            return (values&0xff).astype(np.int32)
        if kind in ('h0','h1'):
            return ((values>>(16 if kind=='h1' else 0))&0xFFFF).astype(np.int32)
        self.key_columns.add((child,column))
        if kind=='optional_token':
            result=np.zeros(len(values),dtype=np.int32)
            present=values!=0
            result[present]=self.tokens(values[present])
            return result
        if kind=='string_pointer':
            return self.codes('string',values,0)
        return self.tokens(values) if kind=='token' else self.codes(kind,values)

    def scope_codes(self,kinds,values):
        result=np.zeros(len(values),dtype=np.int32)
        for kind,codes in self.scope_definition_codes.items():
            chosen=kinds==kind
            indexes=values[chosen]
            if np.any((indexes<0)|(indexes>=len(codes))):
                raise RuntimeError(f'Invalid scope definition index for type {kind}')
            result[chosen]=codes[indexes]
        return result

    def column(self,database,offset,stride,slots):
        if not len(slots):
            return np.empty((0,stride//4),dtype='<i4')
        table=self.word(database+offset)
        result=np.empty((len(slots),stride//4),dtype='<i4')
        for chunk in np.unique(slots//CHUNK):
            chosen=np.nonzero(slots//CHUNK==chunk)[0]
            positions=slots[chosen]%CHUNK
            first,last=int(positions.min()),int(positions.max())
            pointer=self.word(table+int(chunk)*8)
            size=(last-first+1)*stride
            data=np.frombuffer(self.read(pointer+first*stride,size) if pointer else bytes(size),dtype='<i4').reshape(-1,stride//4)
            result[chosen]=data[positions-first]
        return result

    def columns(self,name,spec,database,slots,arrays=None,skip=()):
        arrays={} if arrays is None else arrays
        result={}
        for column,(offset,stride,kind,inner) in spec.get('columns',{}).items():
            if column in skip:
                continue
            if offset not in arrays:
                arrays[offset]=self.column(database,offset,stride,slots)
            data=arrays[offset]
            if kind=='string':
                values=[]
                for row in data[:,inner//4:inner//4+8]:
                    raw=row.tobytes()
                    size,capacity=struct.unpack_from('<QQ',raw,16)
                    if size>1<<16 or capacity<size:
                        raise OSError('Invalid column string')
                    value=(self.read(struct.unpack_from('<Q',raw)[0],size) if capacity>=16 else raw[:size]).decode('utf-8','replace')
                    key=('string',value)
                    if key not in self.keys:
                        self.names.append(key)
                        self.keys[key]=len(self.names)
                    values.append(self.keys[key])
                result[column]=np.array(values,dtype=np.int32)
                self.key_columns.add((name,column))
            elif kind in ('i','d'):
                result[column]=data[:,inner//4].copy()
            else:
                wide=data[:,inner//4:inner//4+2].copy().view('<i8')[:,0]
                result[column]=self.member(name,column,kind,wide)
        return result

    def vector(self,child,slots,words,offset,count_offset,stride,members,hop=None,used=None,deref=None,flag_offset=4):
        heads=words if hop is None else self.gather(words[:,hop//8],count_offset+8)
        counts=heads.view('<i4')
        pointers=heads[:,offset//8];other=counts[:,(count_offset^4)//4]
        buckets=counts[:,count_offset//4]+(used is not None)
        sizes=buckets+(counts[:,count_offset//4+1]&0xff) if used is not None else buckets
        valid=(sizes>0)&(pointers>HEAP_LOW)&(pointers<HEAP_HIGH)&((sizes<=1<<24)&(buckets&(buckets-1)==0)&(other>0)&(other<=sizes)&(sizes>=buckets) if used is not None else sizes<=other)
        active=other>0 if used is not None else sizes>0
        if np.any(active&~valid):
            raise RuntimeError(f'Invalid {child} container for objects {slots[active&~valid].tolist()}')
        live=np.nonzero(valid)[0]
        width=int(sizes[live].max()) if len(live) else 0
        owner,position=np.nonzero(np.arange(width)[None,:]<sizes[live][:,None])
        rows={'id':slots[live][owner],'ord':position.astype(np.int32)}
        span=(stride+7)//8
        elements=np.zeros((len(live),width,span),dtype='<i8')
        for size in np.unique(sizes[live]).tolist():
            group=np.nonzero(sizes[live]==size)[0]
            block=self.gather(pointers[live][group],size*stride)
            if stride==4:
                block=block.view('<i4')[:,:size].astype('<i8')
            if stride%8 and stride!=4:
                packed=block.view(np.uint8)[:,:size*stride].reshape(len(group),size,stride)
                padded=np.zeros((len(group),size,span*8),dtype=np.uint8)
                padded[:,:,:stride]=packed
                elements[group,:size]=padded.view('<i8')
            else:
                elements[group,:size]=block.reshape(len(group),size,span)
        if stride==4:
            for column,(kind,inner) in (members or {'value':['i',0]}).items():
                if inner!=0:
                    raise ValueError(f'Invalid {child}.{column} offset {inner} for four-byte elements')
                rows[column]=self.member(child,column,kind,elements[owner,position,0])
            return rows
        if used is not None:
            key=elements[owner,position,max(used,0)//8]
            flag=(elements[owner,position,flag_offset//8]>>(8*(flag_offset%8)))&0xFF
            keep=(flag>0)&(flag<255)&((key>HEAP_LOW)&(key<HEAP_HIGH) if used>=0 else True)
            owner,position=owner[keep],position[keep]
            rows={'id':slots[live][owner],'ord':position.astype(np.int32)}
        picked=elements[owner,position] if deref is None else self.gather(elements[owner,position,0],deref)
        for column,(kind,inner,*condition) in members.items():
            if kind=='inline_string':
                addresses=pointers[live][owner]+position*stride if deref is None else elements[owner,position,0]
                rows[column]=self.codes('string',addresses+inner,0)
                self.key_columns.add((child,column))
                continue
            values=picked[:,inner//8]>>(8*(inner%8))
            if kind=='scope_definition':
                rows[column]=self.scope_codes(rows[condition[0]],values)
                self.key_columns.add((child,column))
                continue
            if condition:
                values=np.where(np.isin(rows[condition[0]],condition[1]),values,0)
            rows[column]=self.member(child,column,kind,values)
        return rows

    def pop_needs(self,slots,words,offset):
        groups=self.vector('',slots,words,offset,offset+0xc,40,{'group':['w',8],'needs':['w',0x10],'counts':['w',0x18]},None,8)
        index=np.arange(len(groups['id']),dtype=np.int32)
        needs=self.vector('',index,np.stack([groups['needs'],groups['counts']],1),0,0xc,40,{'map':['w',8],'counts':['w',0x10],'overflow':['w',0x18]})
        entry=np.arange(len(needs['id']),dtype=np.int32)
        weights=self.vector('state_pop_need',entry,np.stack([needs['map'],needs['counts'],needs['overflow']],1),0,0xc,24,
                            {'goods_type':['goods_type',8],'weight':['q',16]},None,8)
        need=needs['id'][weights['id']]
        self.key_columns.add(('state_pop_need','need_group'))
        return {'id':groups['id'][need],'need_group':self.codes('need_group',groups['group'][need]),'need':needs['ord'][weights['id']],
                'goods_type':weights['goods_type'],'weight':weights['weight']}

    def market_goods(self,spec,slots,words):
        count=len(self.goods_codes)
        rows={'id':np.repeat(slots,count),'goods':np.tile(self.goods_codes,len(slots))}
        for column,offset in spec['goods'].items():
            rows[column]=(self.gather(words[:,offset//8],count*8)/100000).ravel()
        self.key_columns.add(('market_goods','goods'))
        return rows

    def table(self,name,visible=None):
        spec=self.tables[name]
        if 'root' in spec:
            address=self.base
            for offset in spec['root']:
                address=self.word(address+offset)
            address+=spec.get('offset',0)
            database=0
            slots=np.array([0],dtype=np.int32)
            addresses=np.array([address],dtype=np.int64)
        else:
            database,slots,addresses=self.objects(spec['rva'])
        result={'id':slots}
        skip=(set() if visible is None else visible[name] if name in visible
              else {*spec['fields'],*spec.get('keys',{}),*spec.get('strings',{}),*spec.get('columns',{}),*(prefix+suffix for prefix in spec.get('scopes',{}) for suffix in ('_type','_value','_flag','_definition'))})
        want=lambda child:visible is None or child in visible
        members=lambda child,given:given if visible is None else {column:value for column,value in given.items()
                                                                   if column not in visible.get(child,set()) or any(len(v)>2 and v[2]==column for v in given.values())}
        words=(np.frombuffer(self.read(int(addresses[0]),(spec['size']+7)&~7),dtype='<i8').reshape(1,-1)
               if spec.get('root')==[] else self.gather(addresses,spec['size']))
        halves=words.view('<i4')
        octets=words.view(np.uint8)
        if database:
            offset=IDENTITY_OFFSETS.get(name,8)
            identity=halves[:,offset//4].copy()
            wrong=(identity&0xffffff)!=slots
            if np.any(wrong):
                raise RuntimeError(f'{name} identity at +{offset} does not hold the slot for objects {slots[wrong][:5].tolist()}')
            result['ident']=identity
        for column,(kind,offset,*bit) in spec['fields'].items():
            if column in skip:
                continue
            if kind in ('q','w') and offset%8:
                values=octets[:,offset:offset+8].copy().view('<i8')[:,0]
                result[column]=values/100000 if kind=='q' else values
                continue
            if kind=='u':
                result[column]=halves[:,offset//4].astype(np.int64)&0xffffffff
                continue
            result[column]=(words[:,offset//8]/100000 if kind=='q' else words[:,offset//8].copy() if kind=='w' else halves[:,offset//4].copy() if kind in 'id'
                            else (octets[:,offset].astype(np.int32)>>bit[0])&1 if bit else octets[:,offset].astype(np.int32))
        for column,(offset,kind,inner,*present) in spec.get('keys',{}).items():
            if column in skip:
                continue
            pointers=words[:,offset//8]
            if present:
                pointers=np.where(result[present[0]]!=-1,pointers,0)
            result[column]=self.codes(kind,pointers,inner)
            self.key_columns.add((name,column))
        for column,offset in spec.get('strings',{}).items():
            if column in skip:
                continue
            result[column]=self.codes('string',addresses+offset,0)
            self.key_columns.add((name,column))
        for prefix,(type_offset,value_offset) in spec.get('scopes',{}).items():
            if {prefix+suffix for suffix in ('_type','_value','_flag','_definition')}<=skip:
                continue
            kinds=halves[:,type_offset//4].copy()
            values=words[:,value_offset//8].copy()
            result[prefix+'_type']=kinds
            result[prefix+'_value']=values
            result[prefix+'_flag']=self.member(name,prefix+'_flag','optional_token',np.where(kinds==3,values,0))
            result[prefix+'_definition']=self.scope_codes(kinds,values)
            self.key_columns.add((name,prefix+'_definition'))
        if 'movement_identity' in spec:
            identities=[self.movement_identities[self.names[int(code)-1][1]] for code in result['movement_type']]
            for index,(column,offset) in enumerate(zip(('culture','religion'),spec['movement_identity'])):
                present=np.array([flags[index] for flags in identities],dtype=bool)
                result[column]=self.codes(column,np.where(present,words[:,offset//8],0),24)
                self.key_columns.add((name,column))
        arrays={}
        result.update(self.columns(name,spec,database,slots,arrays,skip))
        def column_data(offset,stride):
            if offset not in arrays:
                arrays[offset]=self.column(database,offset,stride,slots)
            return arrays[offset]
        children={child:self.vector(child,slots,words,*vector[:3],members(child,vector[3]),*vector[4:]) for child,vector in spec.get('vectors',{}).items() if want(child)}
        for child,nested in spec.get('nested_vectors',{}).items():
            if not want(child):
                continue
            outer=self.vector(child,slots,words,*nested['outer'])
            headers=[outer.pop('_pointer'),outer.pop('_counts')]
            if '_overflow' in outer:
                headers.append(outer.pop('_overflow'))
            heads=np.stack(headers,1)
            entries=self.vector(child,np.arange(len(outer['id']),dtype=np.int32),heads,*nested['inner'])
            owner=entries.pop('id')
            children[child]={'id':outer['id'][owner],'parent_ord':outer['ord'][owner],
                             **{column:values[owner] for column,values in outer.items() if column not in ('id','ord')},**entries}
        for child,(offset,length) in spec.get('arrays',{}).items():
            if not want(child):
                continue
            children[child]={'id':np.repeat(slots,length),'ord':np.tile(np.arange(length,dtype=np.int32),len(slots)),
                             'value':(words[:,offset//8:offset//8+length]/100000).ravel()}
        for child,(offset,length) in spec.get('column_arrays',{}).items():
            if not want(child):
                continue
            heads=column_data(offset,24).copy().view('<i8')
            blocks=np.where((heads[:,0]>HEAP_LOW)&(heads[:,0]<HEAP_HIGH)&(heads[:,0]&7==0)&(heads[:,1]&0xFFFFFFFF==length),heads[:,0],0)
            values=self.gather(blocks,length*8)/100000
            owner,position=np.nonzero(values)
            children[child]={'id':slots[owner],'ord':position.astype(np.int32),'value':values[owner,position]}
        for child,(offset,stride,*vector) in spec.get('column_vectors',{}).items():
            if not want(child):
                continue
            children[child]=self.vector(child,slots,column_data(offset,stride).copy().view('<i8'),*vector)
        for child,(offset,stride,inner) in spec.get('column_goods',{}).items():
            if not want(child):
                continue
            heads=column_data(offset,stride).copy().view('<i8')
            values=self.gather(heads[:,inner//8],len(self.goods_codes)*8)/100000
            mask=heads[:,(inner+24)//8]
            owner,good=np.nonzero((mask[:,None]>>np.arange(len(self.goods_codes)))&1)
            children[child]={'id':slots[owner],'goods':self.goods_codes[good],'value':values[owner,good]}
            self.key_columns.add((child,'goods'))
        for child,(offset,count_offset,stride,members,inner) in spec.get('vector_goods',{}).items():
            if not want(child):
                continue
            source=self.vector(child,slots,words,offset,count_offset,stride,
                               {**members,'_pointer':['w',inner+8],'_mask':['w',inner+32]})
            values=self.gather(source.pop('_pointer'),len(self.goods_codes)*8)/100000
            mask=source.pop('_mask')
            owner,good=np.nonzero((mask[:,None]>>np.arange(len(self.goods_codes)))&1)
            children[child]={**{column:entries[owner] for column,entries in source.items()},
                             'goods':self.goods_codes[good],'value':values[owner,good]}
            self.key_columns.add((child,'goods'))
        for child,offset in spec.get('goods_arrays',{}).items():
            if not want(child):
                continue
            values=self.gather(words[:,offset//8],len(self.goods_codes)*8)/100000
            owner,good=np.nonzero(values)
            children[child]={'id':slots[owner],'goods':self.goods_codes[good],'value':values[owner,good]}
            self.key_columns.add((child,'goods'))
        if 'province_runs' in spec and want(name+'_province_range'):
            offset=spec['province_runs']
            runs=self.vector('',slots,words,offset,offset+0xc,4,{})
            first=runs['value']&0xFFFF
            children[name+'_province_range']={'id':runs['id'],'ord':runs['ord'],'first_province':first,'last_province':first+((runs['value']>>16)&0xFFFF)}
        if 'pop_needs' in spec and want('state_pop_need'):
            children['state_pop_need']=self.pop_needs(slots,words,spec['pop_needs'])
        if 'variable_lists' in spec and (want(name+'_list') or want(name+'_list_item')):
            source=spec['variable_lists']
            if 'column' in source:
                offset,stride,inner=source['column']
                pointers=column_data(offset,stride)[:,inner//4:inner//4+2].copy().view('<i8')[:,0]
                heads=self.gather(pointers,16)
            elif 'pointer' in source:
                heads=self.gather(words[:,source['pointer']//8],16)
            else:
                heads=words
            lists=self.vector(name+'_list',slots,heads,0,12,64,
                              {'name':['token',8],'_items':['w',16],'_counts':['w',24],
                               '_durations':['w',40],'_duration_counts':['w',48]})
            index=np.arange(len(lists['id']),dtype=np.int32)
            entries=self.vector('',index,np.stack([lists.pop('_items'),lists.pop('_counts')],1),0,12,16,
                                {'type':['i',0],'value':['w',8],'flag':['optional_token',8,'type',[3]],'definition':['scope_definition',8,'type']})
            durations=self.vector('',index,np.stack([lists.pop('_durations'),lists.pop('_duration_counts')],1),0,12,4,{})
            if not np.array_equal(entries['id'],durations['id']) or not np.array_equal(entries['ord'],durations['ord']):
                raise RuntimeError(f'Invalid {name} variable list durations')
            children[name+'_list']=lists
            owner=entries['id']
            children[name+'_list_item']={'id':lists['id'][owner],'list_ord':lists['ord'][owner],'ord':entries['ord'],
                                        'type':entries['type'],'value':entries['value'],'flag':entries['flag'],'definition':entries['definition'],'expiry_tick':durations['value']}
            self.key_columns.add((name+'_list_item','flag'))
            self.key_columns.add((name+'_list_item','definition'))
        for trend,offset in spec.get('trends',{}).items():
            if not (want(name+'_'+trend) or want(name+'_'+trend+'_channel')):
                continue
            result[trend+'_sample_rate']=halves[:,(offset+8)//4].copy()
            result[trend+'_count']=halves[:,(offset+12)//4].copy()
            child=name+'_'+trend
            channels=self.vector(child,slots,words,offset+24,offset+36,64,
                                 {'channel':['i',8],'date':['i',24],'index':['i',32],
                                  '_pointer':['w',40],'_counts':['w',48]},None,-1)
            heads=np.stack([channels.pop('_pointer'),channels.pop('_counts')],1)
            children[child+'_channel']=channels
            values=self.vector(child,np.arange(len(channels['id']),dtype=np.int32),heads,0,12,8,{'value':['q',0]})
            owner=values['id']
            children[child]={'id':channels['id'][owner],'channel':channels['channel'][owner],
                             'ord':values['ord'],'value':values['value']}
        if 'goods' in spec and want('market_goods'):
            children['market_goods']=self.market_goods(spec,slots,words)
        return result,children

    def date(self):
        rva,offset=LAYOUT['date']
        hours=struct.unpack('<i',self.read(self.word(self.base+rva)+offset,4))[0]
        days,hour=divmod(hours,24)
        year,day=divmod(days,365)
        month=next(m for m in range(12,0,-1) if day>=MONTH_STARTS[m-1])
        return hours,f'{year-5000}.{month}.{day-MONTH_STARTS[month-1]+1}.{hour}'

    def player(self):
        rows,_=self.table('player')
        return int(rows['country'][0])&0xffffff

    def alive(self):
        rows,_=self.table('state',{'state':set(self.tables['state']['fields'])-{'country'}})
        return self.player() in {int(country)&0xffffff for country in rows['country'].tolist()}

    def _decode(self,roots,visible=None):
        result={}
        for name in roots:
            rows,children=self.table(name,visible)
            result[name]=rows
            result.update(children)
        return result

    @timed
    def decode(self):
        return self._decode(self.tables)

    def needed_roots(self):
        return [root for root,spec in self.tables.items() if set(outputs(root,spec))&set(self.visible)]

    @timed
    def snapshot(self):
        result=VISIBILITY.apply(self._decode(self.needed_roots(),self.visible),self.player())
        for name in result:
            base,sep,_=name.rpartition('_private')
            if sep and not _:
                self.key_columns|={(name,column) for table,column in list(self.key_columns) if table==base}
        return result
