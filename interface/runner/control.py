import shutil
import uuid

from ..actions import gui as action_gui
from ..common import timed, write_json, write_script
from ..recording.capture import UI_CHECKS, capture_body, capture_guis, capture_widgets
from ..script import read, scalar


PAD=action_gui.PAD


DUMP=f'''namespace = interface
interface.1 = {{ type = country_event hidden = yes immediate = {{
debug_log = "INTERFACE|state|request=[GetVariableSystem.Get('interface_request')]|player=[GetMetaPlayer.GetPlayedOrObservedCountry.GetTagName]|observer=[IsObserver]|paused=[TimeKeeper.IsPaused]|menu=[IsPauseMenuShown]|date=[TimeKeeper.GetCurrentDate.GetString]"
every_country = {{
debug_log = "INTERFACE|country|tag=[THIS.GetCountry.GetTagName]|population=[THIS.GetCountry.GetTotalPopulation]|government=[THIS.GetCountry.GetGovernment.GetName]|religion=[THIS.GetCountry.GetStateReligion.GetName]|ruler=[THIS.GetCountry.GetRuler.GetFullNameNoFormatting]|battalions=[THIS.GetCountry.GetBattalions]|literacy=[THIS.GetCountry.GetTotalLiteracyRate]"
every_active_law = {{ debug_log = "INTERFACE|law|owner=[PREV.GetCountry.GetTagName]|name=[THIS.GetLaw.GetNameNoFormatting]" }}
every_scope_state = {{
debug_log = "INTERFACE|region|id=[THIS.GetState.GetStateRegion.GetID]|owner=[THIS.GetState.GetOwner.GetTagName]|provinces=[THIS.GetState.GetNumProvinces]|population=[THIS.GetState.GetPopulationSize]|incorporated=[THIS.GetState.IsIncorporated]|infrastructure=[THIS.GetState.GetInfrastructure]|infrastructure_usage=[THIS.GetState.GetInfrastructureUsage]|market_access=[THIS.GetState.GetMarketAccess]|world_market_access=[THIS.GetState.GetWorldMarketAccess]|isolated=[THIS.GetState.IsIsolatedFromMarket]|market_hub=[THIS.GetState.IsWorldMarketHub]"
every_scope_building = {{ debug_log = "INTERFACE|building|state=[PREV.GetState.GetStateRegion.GetID]|type=[THIS.GetBuilding.GetBuildingType.GetKey]|levels=[THIS.GetBuilding.GetTotalLevels]" }}
}} }}
debug_log = "INTERFACE|end|[GetVariableSystem.Get('interface_request')]"
{PAD}
}} }}
'''


RESTARTS=(5,15,30,60,120)


SPEED=5


STATE="GetScriptedGui('interface_state').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)"


START="GetScriptedGui('interface_start').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)"


CAPTURE_TRIGGER="GreaterThan_CFixedPoint(GetPlayer.MakeScope.Var('interface_capture').GetValue, '(CFixedPoint)0')"


READ_TRIGGER="EqualTo_CFixedPoint(GetPlayer.MakeScope.Var('interface_capture').GetValue, '(CFixedPoint)1')"


SAVE_TRIGGER="EqualTo_CFixedPoint(GetPlayer.MakeScope.Var('interface_capture').GetValue, '(CFixedPoint)2')"


CAPTURE_WIDGET=lambda tag:('widget = { size = { 0 0 } state = { name = capture_pause '
                'trigger_when = "[And('+CAPTURE_TRIGGER+', Not(TimeKeeper.IsPaused))]" '
                'on_start = "[TimeKeeper.TogglePause]" } }\n'
                'widget = { size = { 0 0 } state = { name = capture_read '
                'trigger_when = "[And('+READ_TRIGGER+', TimeKeeper.IsPaused)]" '
                f'on_start = "[ExecuteConsoleCommand(\'event interface_capture.1 {tag}\')]" '
                '} '
                'state = { name = capture_idle trigger_when = "[And(Not('+CAPTURE_TRIGGER+'), EqualTo_CFixedPoint(GetPlayer.MakeScope.Var(\'interface_capture_done\').GetValue, \'(CFixedPoint)1\'))]" '
                'on_start = "[GetVariableSystem.Set(\'interface_ui_probe\', \'1\')]" '
                'on_start = "[PdxGuiTriggerAllAnimations(\'capture_prepare_events\')]" } }\n'
                'widget = { size = { 0 0 } state = { name = capture_prepare_events duration = 0.02 '
                'on_finish = "[PdxGuiTriggerAllAnimations(\'capture_values\')]" '
                'on_finish = "[PdxGuiTriggerAllAnimations(\'capture_pending_event\')]" '
                'on_finish = "[PdxGuiTriggerAllAnimations(\'capture_message\')]" '
                'on_finish = "[PdxGuiTriggerAllAnimations(\'capture_ack\')]" } }\n'
                'widget = { size = { 0 0 } state = { name = capture_ack duration = 0.05 '
                'on_finish = "[PdxGuiTriggerAllAnimations(\'capture_finish\')]" } }\n'
                'widget = { size = { 0 0 } state = { name = capture_finish duration = 0.001 '
                'on_finish = "[GetVariableSystem.Clear(\'interface_ui_probe\')]" '
                'on_finish = "[GetScriptedGui(\'interface_capture_ready\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)]" } }\n'
                'widget = { size = { 0 0 } state = { name = capture_save_menu '
                'trigger_when = "[And('+SAVE_TRIGGER+', Not(IsPauseMenuShown))]" '
                'on_start = "[ToggleMainMenu]" } }\n'
                'widget = { size = { 0 0 } state = { name = capture_save duration = 0.3 '
                'trigger_when = "[And('+SAVE_TRIGGER+', IsPauseMenuShown)]" '
                'on_start = "[PdxGuiTriggerAllAnimations(\'interface_open_save\')]" '
                'on_finish = "[PdxGuiTriggerAllAnimations(\'interface_do_save\')]" '
                'on_finish = "[GetScriptedGui(\'interface_save_ready\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)]" } }\n')


MESSAGE_WIDGET=('flowcontainer = { datamodel = "[MessageFeedHandler.GetItems]" item = { widget = { size = { 0 0 } '
                'datacontext = "[FeedMessageItem.GetPlayerMessageItem]" state = { name = capture_message duration = 0.001 '
                'on_finish = "[GetScriptedGui(\'cap_message\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope)'
                '.AddScope(\'date\',MakeScopeFlag(PlayerMessageItem.GetDate)).AddScope(\'type\',MakeScopeFlag(PlayerMessageItem.GetMessageGroupTag))'
                '.AddScope(\'name\',MakeScopeFlag(PlayerMessageItem.GetName)).AddScope(\'text\',MakeScopeFlag(PlayerMessageItem.GetDescription)).End)]" } } } }\n')


UI_WIDGET=('widget = { size = { 0 0 } state = { name = capture_message duration = 0.001 '
           'on_finish = "[GetScriptedGui(\'cap_ui\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope)'
           +''.join(f".AddScope('{name}',MakeScopeValue(Select_CFixedPoint({check},'(CFixedPoint)1','(CFixedPoint)0')))" for name,check in UI_CHECKS)
           +'.End)]" } }\n')


TRANSPORT_GUI=('interface_transport = { scope = country effect = { debug_log = "INTERFACE|transport|[THIS.GetCountry.MakeScope.Var(\'interface_seq\').GetValue|0]'
               '|[GetVariableSystem.Get(\'interface_transport_result\')]" } }\n')


def request(tag,token):
    return [f"GetVariableSystem.Set('interface_request','{token}')",f"ExecuteConsoleCommand('event interface.1 {tag}')"]


CONSOLE_GAP=2


def widget(actions):
    timed=[]
    delay=.15
    for action in actions:
        timed.append((round(delay,2),action))
        delay+=CONSOLE_GAP if 'ExecuteConsoleCommand' in action else .5
    timed+=[(delay,START) for delay in RESTARTS if START in actions]
    states='\n'.join(f'widget = {{ state = {{ name = execute trigger_on_create = yes duration = {delay} on_finish = "[{action}]" }} }}' for delay,action in timed)
    return f'widget = {{ name = interface_ctrl size = {{ 100% 100% }} layer = top alwaystransparent = yes\n{states}\n}}\n'


@timed
def event_capture_widget(game,mods=()):
    categories={'enactment','negotiation','revolution'}|{value for _,content in read(game/'game','events',mods) if (value:=scalar(content,'category'))}
    items=''.join('flowcontainer = { datamodel = "[AccessPlayer.GetEventsByCategory(\''+category+'\')]" '
                  'item = { widget = { size = { 0 0 } state = { name = capture_pending_event duration = 0.001 '
                  'on_finish = "[PopupManager.OpenEvent(Event.AccessSelf)]" } } } }\n' for category in sorted(categories))
    general='flowcontainer = { datamodel = "[Outliner.AccessCategory(\'situations\').GetSubEntries]" item = { widget = { size = { 0 0 } datacontext = "[OutlinerEntry.AccessSituation]" state = { name = capture_pending_event duration = 0.001 on_finish = "[PopupManager.OpenEvent(Event.AccessSelf)]" } } } }\n'
    return general+items


@timed
def prepare(game,tag,world,extra=()):
    mod=game.data_dir/'control'/game.profile.name
    token=uuid.uuid4().hex
    shutil.rmtree(mod,ignore_errors=True)
    camera=[]
    if world:
        width,height=world['width'],world['height']
        camera=["ExecuteConsoleCommand('Camera.ForceDisableWrap yes')",
                f"ExecuteConsoleCommand('Camera.SetTransform {width/2} 0 {height/2} {max(width*.65,height*1.2)} 85 0')"]
    actions=[START,'MapListPanelManager.ToggleFailedOptions','MapListPanelManager.ToggleInvalidOptions',f"TimeKeeper.SetGameSpeed('(int32){SPEED-1}')"]+camera+list(extra)+request(tag,token)
    gui=game.game_dir/'game/gui'
    hud=(gui/'ingame_hud.gui').read_text(encoding='utf-8-sig')
    write_script(mod/'gui/ingame_hud.gui',hud.replace('name = "ingame_hud"','name = "ingame_hud"\n'+widget(actions)+CAPTURE_WIDGET(tag)+UI_WIDGET+capture_widgets()+event_capture_widget(game.game_dir,[world['mod']] if world else [])
                                                                          +action_gui.hud(game.game_dir/'game',[world['mod']] if world else []),1))
    write_script(mod/'gui/scripted_widgets/interface.txt','gui/interface_ctrl.gui = interface_ctrl\n')
    write_script(mod/'gui/interface_ctrl.gui',widget([]))
    for filename,animation,command in [('frontend_ingame_menu.gui','interface_open_save','PauseMenu.Save'),
                                       ('window_save_game.gui','interface_do_save','SaveGameWindow.Save')]:
        source=(gui/'frontend'/filename).read_text(encoding='utf-8-sig')
        index=source.index('window = {')+len('window = {')
        write_script(mod/'gui/frontend'/filename,source[:index]+f'\n state = {{ name = {animation} duration = 0.1 on_finish = "[{command}]" }}\n'+source[index:])
    for path,text in action_gui.windows(game.game_dir/'game').items():
        write_script(mod/path,text)
    feed=(gui/'notifications.gui').read_text(encoding='utf-8-sig')
    write_script(mod/'gui/notifications.gui',feed.replace('name = "message_feed_widget"','name = "message_feed_widget"\n'+MESSAGE_WIDGET,1))
    injected=mod/'gui/map_markers.gui'
    markers=(injected if injected.is_file() else gui/'map_markers.gui').read_text(encoding='utf-8-sig')
    write_script(mod/'gui/map_markers.gui',markers.replace('name = "event_marker"','name = "event_marker"\nstate = { name = capture_pending_event duration = 0.001 on_finish = "[PopupManager.OpenEvent(EventMarker.AccessAnyEvent)]" }',1))
    write_script(mod/'events/interface.txt',DUMP)
    body=capture_body(game.game_dir,tag,world)
    write_script(mod/'events/c.txt','namespace = interface_capture\ninterface_capture.1 = { type = country_event hidden = yes immediate = {\n'
                 +body+'set_variable = { name = interface_capture_done value = 1 } set_variable = { name = interface_capture value = 0 }\n} }\n')
    write_script(mod/'common/scripted_guis/interface.txt','interface_start = { scope = country effect = { '
                 'if = { limit = { NOT = { has_variable = interface_capture } } '
                 'set_variable = { name = interface_capture value = 0 } set_variable = { name = interface_capture_done value = 0 } } '
                 'if = { limit = { NOT = { has_variable = interface_capture_seq } } '
                 'set_variable = { name = interface_capture_seq value = 0 } } '+action_gui.START+' } }\n'
                 'interface_state = { scope = country effect = { debug_log = "INTERFACE|paused|[GetVariableSystem.Get(\'interface_request\')]|[TimeKeeper.IsPaused]"\n'+PAD+'\n} }\n'
                 +capture_guis()+TRANSPORT_GUI+action_gui.DONE
                 +'interface_save_ready = { scope = country effect = { set_variable = { name = interface_capture value = 0 } set_variable = { name = interface_capture_done value = 2 } } }\n'
                 +'interface_capture_ready = { scope = country effect = { set_variable = { name = interface_capture_done value = 2 } } }\n')
    write_json(mod/'.metadata/metadata.json',{'name':'Programmatic interface','id':'local.interface.control','version':'1','supported_game_version':'1.13.*',
        'short_description':'Native callback transport','tags':[],'relationships':[],'game_custom_data':{'multiplayer_synchronized':True}})
    write_json(mod/'session.json',{'startup_token':token})
    return mod
