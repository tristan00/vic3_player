import base64
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import uuid

import psutil

from ..common import DEFAULT_DATA, DEFAULT_GAME, GameCrashed, progress, timed, write_json, write_script, timed_often
from .tail import LogTail

FAST={'Graphics':{'quality':'low','resolution':'1280x720','display_mode':'windowed','setting_framerate_cap':'120','vsync':False,
                  'shader_quality':'low','texture_quality':'low','texture_streaming':False,'shadowmap_resolution':'disabled','anti_aliasing':'DISABLED',
                  'anisotropic_filtering':'DISABLED','refraction_quality':'disabled','mapobject_quality':'low','buildings_cutoff':True,'mesh_lod_bias':'low',
                  'mesh_lod_fade':False,'bloom_quality':'low','animated_portraits':False,'portraits_ssao':False,
                  'portrait_render_scale':'none'},
      'Audio':{'volume.bus:/':0},'GUI':{'scale':'1'},'game':{'pause_on_event':False}}


HARVEST_OFFSET=0xe7c89c


HARVEST_CODE=bytes.fromhex('453bcb7d21418bc39941f7f9418bcc85d20f95c103c88bc399f7f9458bc485d2410f94c0eb0a')


VANILLA_STATES=360


LOADING_HOURS=(5000+9000)*365*24


@timed
def _spawn(arguments,directory,*,visible=False):
    command=subprocess.list2cmdline(arguments).replace("'","''")
    directory=str(directory).replace("'","''")
    script=("$ErrorActionPreference='Stop'; $launchStartup=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly "
            f"-Property @{{ShowWindow=[uint16]{int(visible)}}}; "
            "$launchResult=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
            f"@{{CommandLine='{command}';CurrentDirectory='{directory}';ProcessStartupInformation=$launchStartup}}; "
            "if ($launchResult.ReturnValue -ne 0) { throw ('Process creation failed: '+$launchResult.ReturnValue) }; $launchResult.ProcessId")
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    shell=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+30
    while shell.poll() is None:
        progress('_spawn')
        if time.monotonic()>deadline:
            shell.kill()
            raise TimeoutError('PowerShell did not spawn the process within 30 s')
        time.sleep(.05)
    out,err=shell.communicate()
    if shell.returncode:
        raise RuntimeError(f'PowerShell failed to spawn the process: {err.strip()}')
    return psutil.Process(int(out))


@timed
def _patch_harvest(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.ReadProcessMemory.argtypes=kernel.WriteProcessMemory.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
    kernel.VirtualProtectEx.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    kernel.FlushInstructionCache.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_size_t]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.EnumProcessModules.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    def check(ok):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
    handle=kernel.OpenProcess(0x438,False,pid)
    check(handle)
    try:
        modules=(wintypes.HMODULE*1024)();needed=wintypes.DWORD()
        found=ctypes.create_string_buffer(len(HARVEST_CODE))
        deadline=time.monotonic()+20
        while not (psapi.EnumProcessModules(handle,modules,ctypes.sizeof(modules),ctypes.byref(needed))
                   and modules[0] and kernel.ReadProcessMemory(handle,modules[0]+HARVEST_OFFSET,found,len(HARVEST_CODE),None)):
            if time.monotonic()>deadline:
                raise ctypes.WinError(ctypes.get_last_error())
            time.sleep(.05)
        address=modules[0]+HARVEST_OFFSET
        if found.raw!=HARVEST_CODE:
            raise RuntimeError('Unsupported game build: small-map harvest code signature differs')
        old=wintypes.DWORD()
        check(kernel.VirtualProtectEx(handle,address+3,1,0x40,ctypes.byref(old)))
        check(kernel.WriteProcessMemory(handle,address+3,b'\xeb',1,None))
        check(kernel.FlushInstructionCache(handle,address+3,1))
        check(kernel.VirtualProtectEx(handle,address+3,1,old.value,ctypes.byref(old)))
    finally:
        kernel.CloseHandle(handle)


class GameInterface:
    @timed_often
    def __init__(self,profile='default',game_dir=DEFAULT_GAME,data_dir=DEFAULT_DATA,quarterly_pause=False):
        self.game_dir=Path(game_dir).resolve()
        self.data_dir=Path(data_dir).resolve()
        self.profile=self.data_dir/'profiles'/profile
        self.exe=self.game_dir/'binaries/victoria3.exe'
        self.session_file=self.profile/'interface_session.json'
        self.saves=self.profile/'save games'
        self.since=''
        self.quarterly_pause=quarterly_pause

    @timed_often
    def session(self):
        return json.loads(self.session_file.read_text(encoding='utf-8'))

    @timed_often
    def process(self):
        if not self.session_file.exists():
            return None
        session=self.session()
        try:
            process=psutil.Process(session['pid'])
            return process if abs(process.create_time()-session['created'])<.01 else None
        except psutil.NoSuchProcess:
            return None

    @timed_often
    def _running(self):
        if not self.session_file.exists():
            raise RuntimeError('This profile was never launched')
        process=self.process()
        if process is None:
            raise GameCrashed(f'The game process {self.session()["pid"]} is gone')
        guard=self.session()['guard']
        try:
            alive=abs(psutil.Process(guard['pid']).create_time()-guard['created'])<.01
        except psutil.NoSuchProcess:
            alive=False
        if not alive:
            self.close()
            raise RuntimeError(f'The GPU guard {guard["pid"]} is gone, so the unguarded game was closed')
        return process

    @timed
    def settings(self,changes=None):
        path=self.profile/'pdx_settings.json'
        current=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
        if changes:
            if self.process():
                raise RuntimeError('Close this profile before changing startup settings')
            for section,values in changes.items():
                current.setdefault(section,{}).update(values)
            write_json(path,current)
        return current

    @timed_often
    def fast_settings(self):
        return self.settings(FAST)

    @timed
    def launch(self,mods=(),arguments=(),debug=True):
        running=[p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='victoria3.exe']
        if running:
            raise RuntimeError(f'Victoria 3 is already running (PID {running}); only one game instance is allowed')
        mods=[str(Path(m).resolve()) for m in mods]
        write_json(self.profile/'content_load.json',{'enabledMods':[{'path':Path(m).as_posix()} for m in mods],'disabledDLC':[],'enabledUGC':[]})
        self.fast_settings()
        arguments=[str(self.exe),'-gdpr-compliant',*(['-debug_mode'] if debug else []),'-skip','-nosounds','-userdir='+self.profile.as_posix(),*arguments]
        started=time.time()
        self.since=time.strftime('%H:%M:%S',time.localtime(started))
        process=_spawn(arguments,self.exe.parent,visible=True)
        guard=_spawn([sys.executable,'-m','interface.runner.guard',str(process.pid),repr(process.create_time()),str(self.profile/'gpu_guard.log')],Path(__file__).resolve().parents[2])
        session={'pid':process.pid,'created':process.create_time(),'guard':{'pid':guard.pid,'created':guard.create_time()},'started':started,'arguments':arguments,'mods':mods}
        write_json(self.session_file,session)
        if 'tail' in self.__dict__:
            self.__dict__.pop('tail').close()
        manifests=[Path(m).parent/'manifest.json' for m in mods]
        if any(p.is_file() and len(json.loads(p.read_text(encoding='utf-8'))['states'])<VANILLA_STATES for p in manifests):
            try:
                _patch_harvest(process.pid)
            except Exception:
                self.close()
                raise
        return session

    @timed
    def close(self):
        process=self.process()
        if process:
            process.terminate()
            deadline=time.monotonic()+90
            while process.is_running() and time.monotonic()<deadline:
                progress('close')
                time.sleep(.1)
        return {'closed':process is not None}

    @timed_often
    def log(self):
        return self.log_since(0)

    @timed_often
    def tailing(self):
        if 'tail' not in self.__dict__:
            self.tail=LogTail(self.profile/'logs',self.profile/'debug_store.log',self.since)
        return self.tail

    @timed_often
    def log_mark(self):
        return self.tailing().mark()

    @timed_often
    def log_since(self,mark):
        return self.tailing().after(mark)

    @timed_often
    def check(self,quiet):
        self._running()
        self.log()
        if self.tail.fatal:
            raise RuntimeError(f'The game refused a command: {self.tail.fatal}')
        if self.tail.quiet()>quiet:
            raise RuntimeError(f'The game log has not grown for {self.tail.quiet():.0f}s; see {self.profile/"logs"}')

    @timed
    def _wait(self,text,timeout):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            progress('_wait')
            self.check(timeout)
            if text in self.log():
                return
            time.sleep(.2)
        raise TimeoutError(f'Timed out waiting for {text!r}; see {self.profile/"logs"}')

    @timed_often
    def _dispatch(self,actions):
        from .control import widget
        self._running()
        write_script(self.data_dir/'control'/self.profile.name/'gui/interface_ctrl.gui',widget(actions))

    @timed_often
    def _state(self,token):
        lines=self.log().splitlines()
        start=next(i for i,line in enumerate(lines) if 'INTERFACE|state|request='+token in line)
        result={'country':[],'law':[],'region':[],'building':[]}
        for line in lines[start:]:
            kind,_,fields=line.partition('INTERFACE|')[2].partition('|')
            if kind=='end':
                break
            row=dict(part.split('=',1) for part in fields.split('|') if '=' in part)
            if kind=='state':
                result.update(row)
            elif kind in result:
                result[kind].append(row)
        return result

    @timed
    def snapshot(self,tag,timeout=15,pause=True):
        from .control import request
        if pause:
            self.pause(timeout)
        token=uuid.uuid4().hex
        self._dispatch(request(tag,token))
        self._wait('INTERFACE|end|'+token,timeout)
        return self._state(token)

    @timed_often
    def paused(self,timeout=15):
        from .control import STATE
        token=uuid.uuid4().hex
        self._dispatch([f"GetVariableSystem.Set('interface_request','{token}')",STATE])
        self._wait(f'INTERFACE|paused|{token}|',timeout)
        return self.log().split(f'INTERFACE|paused|{token}|',1)[1][:1]=='1'

    @timed
    def pause(self,timeout=15):
        for _ in range(4):
            if self.paused(timeout):
                return
            self._dispatch(['TimeKeeper.TogglePause'])
            time.sleep(.5)
        raise RuntimeError('The game did not pause')

    @timed_often
    def reader(self):
        from .memory import Reader
        process=self._running()
        identity=(process.pid,process.create_time())
        if getattr(self,'_reader_identity',None)!=identity:
            reader=Reader(process.pid,self.game_dir,self.session()['mods'])
            if hasattr(self,'_reader'):
                self._reader.close()
            self._reader,self._reader_identity=reader,identity
        self._reader.check()
        return self._reader

    @timed
    def campaign(self,tag,world=None,timeout=180,wait=True,debug=True,actions=()):
        from .control import prepare
        manifest=json.loads(Path(world).read_text(encoding='utf-8')) if world else None
        if manifest and tag not in {c['tag'] for c in manifest['countries']}:
            raise ValueError('The requested country is absent from the world')
        if manifest and any('buildings' not in state for state in manifest['states']):
            raise ValueError('Regenerate this world: its manifest has no opening building expectations')
        mods=([manifest['mod']] if manifest else [])+[prepare(self,tag,manifest,actions)]
        session=self.launch(mods,['-start_tag='+tag],debug)
        if not wait:
            return {**session,'ready':False}
        return {**session,**self.campaign_ready(tag,world,timeout)}

    @timed
    def campaign_ready(self,tag,world=None,timeout=180):
        manifest=json.loads(Path(world).read_text(encoding='utf-8')) if world else None
        ready=self.ready(tag,timeout)
        if manifest:
            from ..world.buildings import loaded
            from ..world.relationships import loaded as relationships
            fidelity=loaded(self.reader(),manifest)
            write_json(Path(world).parent/'opening_buildings.json',fidelity)
            if fidelity['differences']:
                raise RuntimeError(f'Opening buildings differ from requested levels: {fidelity["differences"]}')
            links=relationships(self.reader(),manifest)
            write_json(Path(world).parent/'opening_relationships.json',links)
            if links['errors']:
                raise RuntimeError(f'Opening relationships are inconsistent: {links["errors"]}')
            ready['building_levels']=fidelity['actual_levels']
        return ready

    @timed
    def _started(self):
        reader=self.reader()
        hours,date=reader.date()
        if hours>=LOADING_HOURS or not len(reader.objects(reader.tables['country']['rva'])[1]):
            return None
        reader.control_targets()
        return reader,date

    @timed
    def ready(self,tag,timeout=180):
        deadline=time.monotonic()+timeout
        reason=None
        while True:
            progress('ready')
            self.check(timeout)
            try:
                started=self._started()
            except (OSError,RuntimeError,IndexError) as error:
                started,reason=None,error
            if started is not None:
                reader,date=started
                rows,_=reader.table('country')
                index=rows['id'].tolist().index(reader.player())
                actual=reader.names[int(rows['country_definition'][index])-1][1]
                if tag is not None and actual!=tag:
                    raise RuntimeError(f'The game is playing {actual} but the control mod is scoped to {tag}, '
                                       f'so nothing would be captured for the played country; '
                                       f'restart with campaign({actual!r}) or re-save under the current tag')
                token=json.loads((self.data_dir/'control'/self.profile.name/'session.json').read_text(encoding='utf-8'))['startup_token']
                self._wait('INTERFACE|end|'+token,max(1,deadline-time.monotonic()))
                return {'ready':True,'date':date,'tag':actual,
                        'uptime_seconds':round(time.time()-self.session()['started'],3)}
            if time.monotonic()>deadline:
                raise TimeoutError(f'The control mod did not initialize within {timeout}s '
                                   f'(last attempt: {type(reason).__name__}: {reason}); see {self.profile/"logs"}')
            time.sleep(.5)

    @timed
    def save(self,name,tag,timeout=60):
        target=self.saves/(name+'.v3')
        if target.exists():
            raise FileExistsError(target)
        reader=self.reader()
        reader.request_capture(random.randrange(1,10**6),timeout=min(timeout,5))
        date=reader.date()[1]
        before={p:p.stat().st_mtime_ns for p in self.saves.glob('*.v3')}
        reader.request_capture(random.randrange(1,10**6),timeout=min(timeout,5),save=True)
        deadline=time.monotonic()+timeout;size=None
        while time.monotonic()<deadline:
            self._running()
            changed=[p for p in self.saves.glob('*.v3') if p.stat().st_mtime_ns!=before.get(p)]
            if changed and size and changed[0].stat().st_size==size:
                changed[0].rename(target)
                write_json(target.with_suffix('.interface.json'),{'mods':self.session()['mods'],'tag':tag,'date':date})
                return {'path':str(target),'bytes':size}
            size=changed[0].stat().st_size if changed else None
            time.sleep(1)
        raise TimeoutError(f'Save did not complete; see {self.profile/"logs"}')

    @timed
    def load(self,path,timeout=180,wait=True):
        from .control import prepare
        path=Path(path).resolve()
        if path.parent!=self.saves.resolve():
            raise ValueError('Load a save from the save games directory of this profile')
        sidecar=json.loads(path.with_suffix('.interface.json').read_text(encoding='utf-8'))
        self.close()
        manifests=[Path(m).parent/'manifest.json' for m in sidecar['mods']]
        world=next((json.loads(p.read_text(encoding='utf-8')) for p in manifests if p.is_file()),None)
        control=prepare(self,sidecar['tag'],world)
        mods=[m for m in sidecar['mods'] if Path(m)!=control]+[control]
        session=self.launch(mods,['-loadsave='+path.stem])
        return {**session,**(self.ready(sidecar['tag'],timeout) if wait else {'ready':False})}
