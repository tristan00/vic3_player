import re

from ..common import timed, timed_often
from ..script import event_namespaces, keys
from .catalogue import ACTIONS, EVENT_WINDOW, KEYS, PROPOSALS, SHIP_PAGE, SHIP_PAGES, TRANSPORT_PLANNER, TYPES


PAD='\n'.join('debug_log = "INTERFACE|pad|'+'x'*180+'"' for _ in range(25))


VAR="GetPlayer.MakeScope.Var('{}')"
SCRIPTED="GetScriptedGui('{}').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).End)"
SLOTS=4
VARIABLES=('interface_action','interface_mode','interface_seq','interface_key','interface_choice','interface_n0','interface_n1','interface_flip')+tuple(f'interface_p{i}' for i in range(SLOTS))
KEY="GetVariableSystem.Get('interface_key')"


@timed_often
def equal(name,value):
    return f"EqualTo_CFixedPoint({VAR.format(name)}.GetValue, '(CFixedPoint){value}')"


@timed_often
def number(name):
    return f"FixedPointToInt({VAR.format(name)}.GetValue)"


@timed_often
def conjunction(*conditions):
    conditions=[c for c in conditions if c]
    return conditions[0] if len(conditions)==1 else f'And({conditions[0]}, {conjunction(*conditions[1:])})'


@timed_often
def split(param):
    name,_,kind=param.partition(':')
    return name,kind or (name if name in TYPES or name in KEYS else None)


@timed_often
def bindings(action):
    values={};slot=0
    for param in action.params:
        name,kind=split(param)
        if kind in TYPES:
            values[name]=VAR.format(f'interface_p{slot}')+'.Get'+TYPES[kind][1];slot+=1
        elif kind in KEYS:
            values[name]=KEY
        elif kind=='event':
            values[name]=f"Concatenate3({KEY}, '.', ToString_int32({number('interface_n1')}))"
        elif kind=='int':
            values[name]=number('interface_n0')
        elif kind=='choice':
            values[name]='{'+name+'}'
        else:
            raise ValueError(f'{action.name}: unknown parameter {param}')
    if slot>SLOTS:
        raise ValueError(f'{action.name}: more than {SLOTS} object parameters')
    return values


@timed_often
def fill(text,values):
    for name,value in values.items():
        text=text.replace('{'+name+'}',value)
    return text


@timed_often
def needs_key(action):
    return any(split(param)[1] in {*KEYS,'event'} for param in action.params)


@timed_often
def variants(action):
    values=bindings(action)
    choice=next((split(p)[0] for p in action.params if split(p)[1]=='choice'),None)
    if choice is None:
        return [(None,values)]
    return [(index,{**values,choice:value}) for index,value in enumerate(action.choices)]


@timed_often
def result(command,valid,why=''):
    check=valid or f'IsValid({command})'
    desc=chr(39)*2 if valid else f"Concatenate(GetDesc({command}), {why})" if why else f'GetDesc({command})'
    return [f"GetVariableSystem.Set('interface_action_valid', Select_CString({check}, '1', '0'))",
            f"GetVariableSystem.Set('interface_action_desc', {desc})"]


CLEAN=('PopupManager.ClosePopups','InformationPanelBar.ClosePanel','RightClickMenuManager.Close')
AFTER=('MapListPanelManager.ResetActiveMapInteraction','MapListPanelManager.CloseCurrentPanel','CloseAllTooltips',*CLEAN)


FIRED=f"ToString_int32({number('interface_seq')})"
UNFIRED=f"Not(EqualTo_string(GetVariableSystem.Get('interface_fired'), {FIRED}))"


@timed_often
def after(event):
    return [call for call in AFTER if not event or call!='PopupManager.ClosePopups']


@timed_often
def states(code,action,chain,index,values):
    command=fill(action.command,values)
    valid=fill(action.valid,values) if action.valid else ''
    match=[fill(condition,values) for _,condition in chain if condition]
    base=conjunction(equal('interface_action',code),equal('interface_choice',index) if index is not None else '',
                     "GetVariableSystem.Exists('interface_key_ready')" if needs_key(action) else '',
                     f"GetVariableSystem.Exists('{stage_flag(len(action.stages)-1)}')" if action.stages else "GetVariableSystem.Exists('interface_map_go')" if action.start else '',*match)
    clear=["GetVariableSystem.Clear('interface_key_ready')","GetVariableSystem.Clear('interface_overseas')",*(["GetVariableSystem.Clear('interface_map_go')"] if action.start else []),
           *[f"GetVariableSystem.Clear('{flag(number)}')" for number in range(len(action.stages)) for flag in (stage_flag,armed_flag)]]
    done=[f"GetVariableSystem.Set('interface_clean', '{'event' if action.window==EVENT_WINDOW else 'all'}')",*action.cleanup,*after(True)]
    start=[*clear,*([] if action.window or action.start else CLEAN)]
    if action.transport:
        start=[*start,"GetVariableSystem.Set('interface_transport', '1')"]
    if valid:
        variants=((1,valid,[*start,"GetVariableSystem.Set('interface_action_valid', '1')","GetVariableSystem.Set('interface_action_desc', '')",command,*done]),
                  (1,f'Not({valid})',[*start,"GetVariableSystem.Set('interface_action_valid', '0')",f"GetVariableSystem.Set('interface_action_desc', {action.why or chr(39)*2})",*done]),
                  (2,'',start+result(command,valid,fill(action.why,values))+done))
    else:
        overseas=["GetVariableSystem.Set('interface_overseas', '1')"] if action.overseas else []
        variants=((1,'',start+result(command,valid,fill(action.why,values))+[f'Execute({command})',*overseas,*done]),
                  (2,'',start+result(command,valid,fill(action.why,values))+done))
    out=[]
    if action.overseas:
        listing,needs,opener=action.overseas
        out.append(f'flowcontainer = {{ datamodel = "[{listing}]" item = {{ widget = {{ size = {{ 0 0 }} state = {{ name = interface_overseas_{code} '
                   f'trigger_when = "[{conjunction(equal("interface_action",code),*match,"GetVariableSystem.Exists(\'interface_overseas\')",f"Not(IsValid({command}))",needs)}]" '
                   f'on_start = "[GetVariableSystem.Clear(\'interface_overseas\')]" on_start = "[{opener}]" }} }} }} }}')
    for number,(mode,condition,calls) in enumerate(variants):
        body=' '.join(f'on_start = "[{call}]"' for call in [f"GetVariableSystem.Set('interface_fired', {FIRED})",*calls])
        for flip in (0,1):
            out.append(f'state = {{ name = action_{code}_{index}_{number}_{flip} trigger_when = "[{conjunction(base,equal("interface_mode",mode),equal("interface_flip",flip),UNFIRED,condition)}]" {body} }}')
    return out


@timed_often
def wrap(code,action,chain,values,inner):
    if not chain and not action.context:
        return inner
    for datamodel,_ in reversed(chain):
        if datamodel.startswith('@'):
            inner=f'widget = {{ size = {{ 0 0 }} datacontext = "[{fill(datamodel[1:],values)}]"\n{inner}\n}}'
        else:
            inner=f'flowcontainer = {{ datamodel = "[{fill(datamodel,values)}]" item = {{ widget = {{ size = {{ 0 0 }}\n{inner}\n}} }} }}'
    context=fill(action.context,values)
    return (f'widget = {{ size = {{ 0 0 }} visible = "[{equal("interface_action",code)}]"\n'
            +'widget = { size = { 0 0 }'+(f' datacontext = "[{context}]"' if context else '')+f'\n{inner}\n}}\n}}')


@timed_often
def start_widgets():
    widgets=[]
    for code,action in enumerate(ACTIONS,1):
        if not action.start:
            continue
        commands,chains=action.start
        for chain in chains:
            for index,values in variants(action):
                base=conjunction(equal('interface_action',code),equal('interface_choice',index) if index is not None else '',
                                 *[fill(condition,values) for _,condition in chain if condition])
                inner=('widget = { size = { 0 0 }\n'+'\n'.join(f'state = {{ name = start_{code}_{index}_{mode}_{flip} trigger_when = "[{conjunction(base,equal("interface_mode",mode),equal("interface_flip",flip))}]" duration = 0.3 '
                                                               f'on_start = "[GetVariableSystem.Clear(\'interface_map_go\')]" '
                                                               +' '.join(f'on_start = "[{call}]"' for call in CLEAN)+' '
                                                               +' '.join(f'on_start = "[{fill(command,values)}]"' for command in commands)+' '
                                                               f'on_finish = "[GetVariableSystem.Set(\'interface_map_go\', \'1\')]" }}' for mode in (1,2) for flip in (0,1))+'\n}')
                widgets.append(wrap(code,action,chain,values,inner))
    return widgets


STAGE=0.15


@timed_often
def listed(chain):
    return tuple((datamodel,condition) for datamodel,condition in chain if datamodel)


@timed_often
def stage_flag(number):
    return f'interface_stage{number}'


@timed_often
def armed_flag(number):
    return f'interface_armed{number}'


MAX_STAGES=max(len(action.stages) for action in ACTIONS)


STAGE_TIMERS=' '.join(f'state = {{ name = interface_stage_timer_{number} trigger_when = "[GetVariableSystem.Exists(\'{armed_flag(number)}\')]" duration = {STAGE} '
                      f'on_finish = "[GetVariableSystem.Clear(\'{armed_flag(number)}\')]" on_finish = "[GetVariableSystem.Set(\'{stage_flag(number)}\', \'1\')]" }}'
                      for number in range(MAX_STAGES))


@timed_often
def stage_widget(code,action,index,values,number,chain,calls):
    gate=stage_flag(number-1) if number else 'interface_map_go'
    base=conjunction(equal('interface_action',code),equal('interface_choice',index) if index is not None else '',f"GetVariableSystem.Exists('{gate}')",
                     f"Not(GetVariableSystem.Exists('{armed_flag(number)}'))",f"Not(GetVariableSystem.Exists('{stage_flag(number)}'))",
                     *[fill(condition,values) for _,condition in chain if condition])
    starts=' '.join(f'on_start = "[{fill(call,values)}]"' for call in calls(values))
    states=[f'state = {{ name = stage_{code}_{index}_{number}_{mode}_{flip} trigger_when = "[{conjunction(base,equal("interface_mode",mode),equal("interface_flip",flip))}]" '
            f'{starts} on_start = "[GetVariableSystem.Set(\'{armed_flag(number)}\', \'1\')]" }}' for mode in (1,2) for flip in (0,1)]
    return wrap(code,action,listed(chain),values,'widget = { size = { 0 0 }\n'+'\n'.join(states)+'\n}')


@timed_often
def action_widgets(windowed):
    widgets=[]
    for code,action in enumerate(ACTIONS,1):
        if bool(action.window)!=windowed:
            continue
        for chain in action.alternatives or (action.datamodels,):
            for index,values in variants(action):
                inner='widget = { size = { 0 0 }\n'+'\n'.join(states(code,action,chain,index,values))+'\n}'
                if not windowed:
                    widgets.append(wrap(code,action,chain,values,inner))
                    continue
                if action.stages or action.context:
                    widgets+=[(window,stage_widget(code,action,index,values,number,stage_chain,calls))
                              for number,(window,stage_chain,calls) in enumerate(action.stages)]
                    inner=wrap(code,action,listed(chain),values,inner)
                widgets.append((action.window,inner))
    return widgets


@timed_often
def key_table(game_dir,mods):
    return {**{kind:keys(game_dir,folder,mods) for kind,folder in KEYS.items()},'event_namespace':event_namespaces(game_dir,mods)}


@timed_often
def key_widgets(table):
    widgets=[];offset=0
    for kind,names in table.items():
        for index,name in enumerate(names,offset+1):
            widgets.append(f'widget = {{ size = {{ 0 0 }} state = {{ name = key_{index} trigger_when = "[{equal("interface_key",index)}]" '
                           f'on_start = "[GetVariableSystem.Set(\'interface_key\', \'{name}\')]" on_start = "[GetVariableSystem.Set(\'interface_key_ready\', \'1\')]" }} }}')
        offset+=len(names)
    return widgets


@timed_often
def key_codes(table):
    codes={};offset=0
    for kind,names in table.items():
        codes.update({(kind,name):index for index,name in enumerate(names,offset+1)})
        offset+=len(names)
    return codes


CONFIRM_ANSWERS=(('onclick = "[PopupManager.AnswerYes(ConfirmationWindow.Self)]"','PopupManager.AnswerYes(ConfirmationWindow.Self)'),
                 ('onclick = "[ProductionMethodConfirmationPopup.Continue]"','ProductionMethodConfirmationPopup.Continue'),
                 ('onclick = "[PopupManager.CloseMessage(PlayerMessageItem.AccessSelf)]"','PopupManager.CloseMessage(PlayerMessageItem.AccessSelf)'))


@timed_often
def confirm_answer(call):
    return f'state = {{ name = interface_confirm_answer trigger_on_create = yes duration = 0.02 on_finish = "[{call}]" }}'


CLEAN_DELAY=.1
MAX_SHIP_PAGES=10
ABORT=3
TRANSPORT_WAIT=.3
TRANSPORT_EXPIRE=.5
TRANSPORTING="GetVariableSystem.Exists('interface_transport')"
TRANSPORT_LOG=SCRIPTED.format('interface_transport')
PICK_FLEET=('flowcontainer = { datamodel = "[TransportPlannerPopup.GetFleetsForTransport]" item = { widget = { size = { 0 0 } '
            f'state = {{ name = interface_pick_fleet trigger_when = "[And({TRANSPORTING}, And(Not(TransportPlannerPopup.HasSelectedFleet), '
            'IsValid(TransportPlannerPopup.GetTransportCommand(MilitaryFormation.Self))))]" '
            'on_start = "[TransportPlannerPopup.OnSelectedFleet(MilitaryFormation.AccessSelf)]" } } } }')
START_TRANSPORT=(f'state = {{ name = interface_start_transport trigger_when = "[And({TRANSPORTING}, TransportPlannerPopup.HasSelectedFleet)]" '
                 "on_start = \"[GetVariableSystem.Set('interface_transport_result', Concatenate(Select_CString(IsValid(TransportPlannerPopup.StartTransport), 'started ', 'refused '), TransportPlannerPopup.GetCommandValidityDesc))]\" "
                 f'on_start = "[Execute(TransportPlannerPopup.StartTransport)]" on_start = "[{TRANSPORT_LOG}]" '
                 "on_start = \"[GetVariableSystem.Clear('interface_transport')]\" }")
NO_FLEET=(f'state = {{ name = interface_transport_timeout trigger_when = "[{TRANSPORTING}]" duration = {TRANSPORT_WAIT} '
          f"on_finish = \"[GetVariableSystem.Set('interface_transport_result', Select_CString({TRANSPORTING}, Concatenate('no fleet ', TransportPlannerPopup.GetCommandValidityDesc), GetVariableSystem.Get('interface_transport_result')))]\" "
          f'on_finish = "[{TRANSPORT_LOG}]" on_finish = "[GetVariableSystem.Clear(\'interface_transport\')]" }}')
TRANSPORT_WIDGET='widget = { size = { 0 0 }\n'+PICK_FLEET+'\n'+START_TRANSPORT+'\n'+NO_FLEET+'\n}'


@timed_often
def ship_navigation():
    codes=[equal('interface_action',code) for code,action in enumerate(ACTIONS,1) if action.name.endswith('_ship_item')]
    shipping=codes[-1]
    for code in reversed(codes[:-1]):
        shipping=f'Or({code}, {shipping})'
    page='ConstructionPanel.AccessCurrentMilitaryShipConstructionQueuePage'
    target=f"Add_int32(Divide_int32({number('interface_n0')}, '(int32){SHIP_PAGE}'), '(int32)1')"
    states=[]
    for current in range(MAX_SHIP_PAGES+1):
        for step,compare in (('Next','LessThan_int32'),('Prev','GreaterThan_int32')):
            trigger=conjunction(shipping,"GetVariableSystem.Exists('interface_stage0')",f"EqualTo_int32({page}, '(int32){current}')",f'{compare}({page}, {target})')
            states.append(f'state = {{ name = interface_ship_page_{step}_{current} trigger_when = "[{trigger}]" on_start = "[ConstructionPanel.{step}MilitaryShipConstructionQueuePage]" }}')
    return 'widget = { size = { 0 0 } '+' '.join(states)+' }'


@timed_often
def deferred_state(kind,event):
    calls=[*after(event),"GetVariableSystem.Clear('interface_clean')",SCRIPTED.format('interface_action_done')]
    return (f"state = {{ name = interface_clean_{kind} trigger_when = \"[And(EqualTo_string(GetVariableSystem.Get('interface_clean'), '{kind}'), Not({TRANSPORTING}))]\" duration = {CLEAN_DELAY} "
            +' '.join(f'on_finish = "[{call}]"' for call in calls)+' }')


DEFERRED_CLEAN=('widget = { size = { 0 0 } '+STAGE_TIMERS+' '+deferred_state('all',False)+' '+deferred_state('event',True)
                +f' state = {{ name = interface_transport_expire trigger_when = "[{TRANSPORTING}]" duration = {TRANSPORT_EXPIRE} '
                +"on_finish = \"[GetVariableSystem.Clear('interface_transport')]\" }"
                +f' state = {{ name = interface_abort trigger_when = "[{equal("interface_mode",ABORT)}]" on_start = "[GetVariableSystem.Set(\'interface_clean\', \'all\')]" '
                +' '.join(f'on_start = "[GetVariableSystem.Clear(\'{flag(number)}\')]"' for number in range(MAX_STAGES) for flag in (stage_flag,armed_flag))+' } }')


@timed
def hud(game_dir,mods=()):
    return 'widget = { name = interface_actions size = { 0 0 }\n'+'\n'.join([DEFERRED_CLEAN,*key_widgets(key_table(game_dir,mods)),*action_widgets(False),*start_widgets()])+'\n}\n'


PROPOSAL_CAPTURE=('widget = { size = { 0 0 } state = { name = capture_message duration = 0.001 '
                  'on_finish = "[GetScriptedGui(\'cap_proposal\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).AddScope(\'actor\',Proposal.GetActor.MakeScope)'
                  '.AddScope(\'kind\',MakeScopeFlag(Select_CString(Proposal.GetTreaty.IsValid, \'treaty\', '
                  'Select_CString(Proposal.GetDiplomaticDemand.IsValid, \'demand\', Select_CString(Proposal.GetDiplomaticPlay.IsValid, \'sway\', \'action_proposal\'))))).End)]" } }')


@timed
def windows(game_dir):
    injected={PROPOSALS:[PROPOSAL_CAPTURE],TRANSPORT_PLANNER:[TRANSPORT_WIDGET],SHIP_PAGES:[ship_navigation()]}
    for (path,anchor),inner in action_widgets(True):
        injected.setdefault((path,anchor),[]).append(inner)
    files={}
    for (path,anchor),inners in injected.items():
        text=files.get(path) or (game_dir/path).read_text(encoding='utf-8-sig')
        if anchor.startswith('name = ') or anchor.startswith('datacontext = '):
            if text.count(anchor)!=1:
                raise RuntimeError(f'{path}: anchor {anchor!r} occurs {text.count(anchor)} times')
            files[path]=text.replace(anchor,anchor+'\n'+'\n'.join(inners))
            continue
        if anchor.startswith('onclick'):
            files[path]=text.replace(anchor,anchor+'\n'+'\n'.join(inners))
            continue
        if text.count(anchor)!=1:
            raise RuntimeError(f'{path}: anchor {anchor!r} occurs {text.count(anchor)} times')
        item=text.index('item = {',text.index(anchor))
        opener=text.index('{',text.index('=',item+len('item = {'))+1)+1
        files[path]=text[:opener]+'\n'+'\n'.join(inners)+'\n'+text[opener:]
    popups=files.get('gui/popups.gui') or (game_dir/'gui/popups.gui').read_text(encoding='utf-8-sig')
    for anchor,call in CONFIRM_ANSWERS:
        if anchor not in popups:
            raise RuntimeError(f'gui/popups.gui: anchor {anchor!r} missing')
        popups=popups.replace(anchor,anchor+'\n'+confirm_answer(call))
    files['gui/popups.gui']=popups
    return probed(game_dir,files)


UNPROBED_FILES={'cooltip.gui','tooltip.gui','map_markers.gui','map_notifications.gui','ingame_hud.gui','debug_menues.gui','color_blind_modes.gui',
                'textformatting.gui','goods_texticons.gui','eventwindow.gui','console.gui','custom_widgets.gui','ep2_japan_widgets.gui',
                'music_player_view.gui','error_deer.gui','minimap.gui','notifications.gui','credits_window.gui','modifier_debugger.gui',
                'ticktask_debugger.gui','window_component_library.gui','tutorial_highlight.gui','multiplayer_frontend.gui','multiplayer_lobby.gui'}
UNPROBED_DIRS=('frontend','settings','pdx_account','mapeditor')
UNPROBED_KEYS={'texticon','textformatting','template','local_template'}
MASK=re.compile(r'"(?:\\.|[^"\\])*"|#[^\n]*')
TOP=re.compile(r'"(?:\\.|[^"\\])*"|[{}]|(\w+)\s*=\s*\{')


CLOSER=re.compile(r'blockoverride "header_close_button"\s*\{\s*onclick = "\[([\w.]+(?:\([\w.]*\))?)\]"')
DISMISS=re.compile(r'onclick = "\[((?:PopupManager\.(?:Close|Hide)\w*|\w+\.Close)(?:\([\w.]*\))?)\]"')
NON_VOID_CLOSERS={'PopupManager.HideRecruitGeneral','PopupManager.HideRecruitAdmiral','PopupManager.HidePowerBlocPrincipleSelectionWindow','PopupManager.HideProposal(Proposal.AccessSelf)'}


@timed_often
def probe(label,closer):
    close=(f' state = {{ name = interface_close trigger_when = "[And(GetVariableSystem.Exists(\'interface_clean\'), Not({TRANSPORTING}))]" on_start = "[{closer}]" }}'
           if closer and closer not in NON_VOID_CLOSERS else '')
    return ('widget = { size = { 0 0 } state = { name = interface_probe trigger_when = "[GetVariableSystem.Exists(\'interface_ui_probe\')]" '
            f'on_start = "[GetScriptedGui(\'cap_open\').Execute(GuiScope.SetRoot(GetPlayer.MakeScope).AddScope(\'name\',MakeScopeFlag(\'{label}\')).End)]" }}'+close+' }')


@timed_often
def masked(text):
    return MASK.sub(lambda m:' '*len(m[0]) if m[0][0]=='#' else m[0],text)


@timed_often
def block_end(text,opener):
    depth=0
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|[{}]',text[opener:]):
        if m[0]=='{':
            depth+=1
        elif m[0]=='}':
            depth-=1
            if depth==0:
                return opener+m.start()
    return len(text)


@timed
def type_closers(root):
    closers={}
    for path in sorted(root.rglob('*.gui')):
        text=masked(path.read_text(encoding='utf-8-sig'))
        for m in re.finditer(r'\btype\s+(\w+)\s*=\s*\w+\s*\{',text):
            found=CLOSER.search(text,m.end(),block_end(text,m.end()-1))
            if found:
                closers[m[1]]=found[1]
    return closers


@timed_often
def top_blocks(text,closers):
    text=masked(text)
    depth=0;found=[];current=None
    for m in TOP.finditer(text):
        if m[1] is not None:
            header=text[m.end():text.find('{',m.end())]
            if depth==0 and m[1] not in UNPROBED_KEYS and not re.search(r'alwaystransparent\s*=\s*yes',header):
                name=re.search(r'name\s*=\s*"?(\w+)',header)
                current=[m.end(),name[1] if name else m[1],m[1]]
            depth+=1
        elif m[0]=='{':
            depth+=1
        elif m[0]=='}':
            depth-=1
            if depth==0 and current:
                closer=CLOSER.search(text,current[0],m.start()) or DISMISS.search(text,current[0],m.start())
                found.append((current[0],current[1],closer[1] if closer else closers.get(current[2])))
                current=None
    return found


@timed
def probed(game_dir,files):
    root=game_dir/'gui'
    closers=type_closers(root)
    for path in sorted(root.rglob('*.gui')):
        relative=path.relative_to(root)
        if path.name in UNPROBED_FILES or relative.parts[0].startswith(UNPROBED_DIRS):
            continue
        key='gui/'+relative.as_posix()
        text=files.get(key) or path.read_text(encoding='utf-8-sig')
        blocks=top_blocks(text,closers)
        if not blocks:
            continue
        for position,name,closer in reversed(blocks):
            text=text[:position]+'\n'+probe(f'{path.stem}.{name}',closer)+'\n'+text[position:]
        files[key]=text
    return files


DONE=('interface_action_done = { scope = country effect = { '
      'debug_log = "INTERFACE|action|[THIS.GetCountry.MakeScope.Var(\'interface_seq\').GetValue|0]|[GetVariableSystem.Get(\'interface_action_valid\')]|[GetVariableSystem.Get(\'interface_action_desc\')]" '
      'set_variable = { name = interface_action value = 0 } set_variable = { name = interface_key value = 0 }\n'+PAD+'\n} }\n')


START=' '.join(f'if = {{ limit = {{ NOT = {{ has_variable = {name} }} }} set_variable = {{ name = {name} value = {"capital" if name.startswith("interface_p") else 0} }} }}'
               for name in VARIABLES)
