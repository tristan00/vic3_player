import base64, ctypes, json, subprocess, time
from contextlib import nullcontext
from pathlib import Path
import psutil
from ..common import DEFAULT_DATA, DEFAULT_GAME, timed, write_json
from .memory import Process, Reader, kernel
from .tail import LogTail

FAST={'Graphics':{'quality':'low','resolution':'1280x720','display_mode':'windowed','setting_framerate_cap':'120','vsync':False,
      'shader_quality':'low','texture_quality':'low','texture_streaming':False,'shadowmap_resolution':'disabled','anti_aliasing':'DISABLED',
      'anisotropic_filtering':'DISABLED','refraction_quality':'disabled','mapobject_quality':'low','buildings_cutoff':True,'mesh_lod_bias':'low',
      'mesh_lod_fade':False,'bloom_quality':'low','animated_portraits':False,'portraits_ssao':False,'portrait_render_scale':'none'},
      'Audio':{'volume.bus:/':0},'GUI':{'scale':'1'},'game':{'pause_on_event':False}}

@timed
def _spawn(arguments,directory,*,visible=False):
    command=subprocess.list2cmdline(arguments).replace("'","''")
    script=("$ErrorActionPreference='Stop'; $startup=New-CimInstance Win32_ProcessStartup -ClientOnly "
            f"-Property @{{ShowWindow=[uint16]{int(visible)}}}; "
            "$result=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
            f"@{{CommandLine='{command}';CurrentDirectory='{str(directory).replace(chr(39),chr(39)*2)}';ProcessStartupInformation=$startup}}; "
            "if ($result.ReturnValue -ne 0) { throw $result.ReturnValue }; $result.ProcessId")
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
                           base64.b64encode(script.encode('utf-16-le')).decode()],capture_output=True,text=True,
                          creationflags=subprocess.CREATE_NO_WINDOW,timeout=30,check=True)
    return psutil.Process(int(result.stdout))

@timed
def patch_harvest(pid):
    expected=bytes.fromhex('453bcb7d21418bc39941f7f9418bcc85d20f95c103c88bc399f7f9458bc485d2410f94c0eb0a')
    kernel.VirtualProtectEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.c_void_p]
    kernel.FlushInstructionCache.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
    process=Process(pid,0x438)
    try:
        address=process.base+0xe7c89c
        found=ctypes.create_string_buffer(len(expected))
        if not kernel.ReadProcessMemory(process.handle,address,found,len(expected),None) or found.raw!=expected:
            raise RuntimeError('Unsupported small-map harvest code signature')
        old=ctypes.c_ulong()
        if not kernel.VirtualProtectEx(process.handle,address+3,1,0x40,ctypes.byref(old)): raise ctypes.WinError()
        try:
            if not kernel.WriteProcessMemory(process.handle,address+3,b'\xeb',1,None): raise ctypes.WinError()
            if not kernel.FlushInstructionCache(process.handle,address+3,1): raise ctypes.WinError()
        finally:
            if not kernel.VirtualProtectEx(process.handle,address+3,1,old.value,ctypes.byref(old)): raise ctypes.WinError()
    finally:
        process.close()

def process(identity):
    try:
        found=psutil.Process(identity['pid'])
        return found if found.create_time()==identity['created'] and found.is_running() else None
    except (KeyError,psutil.NoSuchProcess):
        return None

class GameInterface:
    def __init__(self,profile='actions',game_dir=DEFAULT_GAME,data_dir=DEFAULT_DATA,quarterly_pause=True):
        self.game_dir,self.data_dir=Path(game_dir),Path(data_dir)
        self.profile=self.data_dir/'profiles'/profile
        self.session_file=self.profile/'interface_session.json'
        self.quarterly_pause=quarterly_pause
        self._reader=self.tail=None

    def session(self): return json.loads(self.session_file.read_text(encoding='utf-8'))

    def reader(self):
        if self._reader is None:
            self._reader=Reader(self.session()['pid'],self.game_dir,self.session()['mods'])
        self._reader.check()
        return self._reader

    def log_mark(self): return self.tail.mark()

    def log_since(self,mark): return self.tail.after(mark)

    @timed
    def close(self):
        owned=process(self.session()) if self.session_file.exists() else None
        try:
            if owned:
                owned.kill()
                owned.wait(timeout=10)
        except psutil.NoSuchProcess:
            pass
        for resource in (self._reader,self.tail):
            if resource is not None: resource.close()
        self._reader=self.tail=None

    @timed
    def campaign(self,tag,world,lock=nullcontext):
        from .control import prepare
        from ..world.buildings import loaded
        from ..world.relationships import loaded as relationships
        if any((p.info['name'] or '').lower()=='victoria3.exe' for p in psutil.process_iter(['name'])):
            raise RuntimeError('Victoria 3 is already running')
        manifest=json.loads(Path(world).read_text(encoding='utf-8')) if world else None
        mods=([manifest['mod']] if manifest else [])+[str(prepare(self,tag,manifest))]
        settings=self.profile/'pdx_settings.json'
        configured=json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {}
        for section,values in FAST.items():
            configured.setdefault(section,{}).update(values)
        write_json(settings,configured)
        write_json(self.profile/'content_load.json',{'enabledMods':[{'path':Path(m).as_posix()} for m in mods],'disabledDLC':[],'enabledUGC':[]})
        exe=self.game_dir/'binaries/victoria3.exe'
        started=time.time()
        with lock():
            process=_spawn([str(exe),'-gdpr-compliant','-skip','-nosounds','-userdir='+self.profile.as_posix(),'-start_tag='+tag],exe.parent,visible=True)
            write_json(self.session_file,dict(pid=process.pid,created=process.create_time(),started=started,mods=mods))
        self.tail=LogTail(self.profile/'logs',self.profile/'debug_store.log',time.strftime('%H:%M:%S',time.localtime(started)))
        deadline=time.monotonic()+20
        while manifest and len(manifest['states'])<360:
            try:
                patch_harvest(process.pid)
                break
            except OSError:
                if time.monotonic()>deadline: raise
                time.sleep(.05)
        token=json.loads((self.data_dir/'control'/self.profile.name/'session.json').read_text())['startup_token']
        deadline=time.monotonic()+180
        while 'INTERFACE|end|'+token not in self.log_since(0):
            if not process.is_running() or time.monotonic()>deadline:
                raise RuntimeError('The game did not initialize')
            time.sleep(.1)
        reader=self.reader()
        countries,_=reader.table('country')
        code=countries['country_definition'][countries['id'].tolist().index(reader.player())]
        if reader.names[int(code)-1][1]!=tag:
            raise RuntimeError('The game loaded a different player')
        for name,check,errors in (('opening_buildings',loaded,'differences'),('opening_relationships',relationships,'errors')):
            report=check(reader,manifest)
            write_json(Path(world).parent/(name+'.json'),report)
            if report[errors]: raise RuntimeError(f'{name}: {report[errors]}')
