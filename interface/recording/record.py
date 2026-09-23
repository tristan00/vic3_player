from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import random
import re
import time

import numpy as np

from ..actions.catalogue import action_folders
from ..common import slot, timed
from ..runner.memory import LAYOUT, MONTH_STARTS
from ..script import alerts, blocks, body, building_methods, decisions, definitions, event_options, keys, production_methods, read, scalar
from .capture import (ALERT_SCOPES, BORROW_MAPS, RELEASE_MAPS, FORMABLE_MAPS, GROUPS, MESSAGE_MAPS, METRICS, PART, PROPOSAL_MAPS, UI_CHECKS, evaluable, method_block, metric_map,
                      map_data, missing_references, plain, province_colors)
from .geography import geometry, mini_world, vanilla_world
from .spec import VOCABULARIES
from .tables import Built, build

LOG=logging.getLogger('interface')
ENUM_SOURCES={'approval_state':'interest_group.approval_state','influence_type':'interest_group.influence_type',
              'influence_type_reason':'interest_group.influence_type_reason','civil_war_side':'interest_group.civil_war',
              'law_checkpoint_result':'law.enactment_last_checkpoint_result','formation_type':'formation.type','supply_priority':'formation.supply_priority',
              'managed_status':'political_movement.managed_status','shipping_lane_type':'shipping_lane.shipping_lane_type','war_goal_demand_type':'war_goal.demand_type',
              'war_goal_status':'war_goal.status','toll_rate':'strait.first_toll_rate','civil_war_type':'civil_war.type','battle_type':'battle.type',
              'battle_status':'battle.status','play_side':'front_side.play_side','ai_attitude':'ai_country_goal.attitude','hq_type':'hq.type',
              'tax_level':'country.tax_level','supply_ship_construction_level':'country.supply_ship_construction_level'}
BUDGET_LINES={('income',1):'income_taxes',('income',2):'poll_taxes',('income',7):'investment',('income',15):'market_fees',
              ('expense',1):'government_slaves',('expense',2):'government_goods',('expense',3):'government_wages',('expense',4):'military_slaves',
              ('expense',5):'military_goods',('expense',6):'military_wages',('expense',7):'construction_goods',('expense',8):'subsidies',
              ('expense',9):'subventions',('expense',10):'interest',('expense',17):'supply_ship_construction_goods',
              ('expense',18):'military_ship_construction_goods',('expense',19):'supply_ship_maintenance',('expense',20):'military_ship_maintenance',
              ('expense',21):'port_connection'}


class Capture:
    def __init__(self,tables,name,player,goods,windows):
        self.tables=tables
        self.name=name
        self.player=player
        self.goods=goods
        self.windows=windows


def put(tables,name,columns,rows):
    names=[column for column,_ in columns]
    tables[name]={column:[row[index] for row in rows] for index,column in enumerate(names)}


@timed
def record(game,store,phase):
    session=game.session()
    identity=f'{session["pid"]}:{session["created"]}'
    manifests=[Path(mod).parent/'manifest.json' for mod in session['mods']]
    world=next((path for path in manifests if path.is_file()),None)
    if store.session!=identity:
        if store.run_id is not None:
            raise RuntimeError('The game session changed within a run')
        store.session=identity
        register(game,session,world,store)
    reader=game.reader()
    started=time.perf_counter()
    nonce=random.randrange(1,10**6)
    reader.request_capture(nonce)
    reader.date()
    snapshot=reader.snapshot()
    player=reader.player()
    own=reader.holder()
    held=Held(own,nonce,reader.holders(sorted({ident(item) for name,items in own['lists'].items() if name.startswith('cap_possible_diplomatic_') for item in items})))
    label=lambda code:reader.names[code-1][1] if code else None
    tags={ident:label(code) for ident,code in zip(snapshot['country']['id'].tolist(),snapshot['country']['country_definition'].tolist())}
    living={slot(c) for c in snapshot['state']['country'].tolist()}-{-1}
    if player not in living:
        raise RuntimeError(f'The played country {tags.get(player)} no longer owns any state')
    windows=_event_options(reader)
    for table in ('event','event_target'):
        answered=~np.isin(snapshot[table]['id'].astype(np.int64)&0xffffff,list(windows))
        snapshot[table]={column:values[~answered] for column,values in snapshot[table].items()}
    tables={name:{column:values.tolist() for column,values in columns.items()} for name,columns in snapshot.items()}
    manifest=json.loads(world.read_text(encoding='utf-8')) if world else None
    colors=_scripted(tables,snapshot,held,tags,label,player,living,manifest,map_data(game.game_dir,manifest))
    _options(tables,snapshot,windows,label)
    constants,meta,open_windows=snapshot_meta(tables,label)
    rows=build(Capture(tables,label,player,reader.goods_codes.tolist(),open_windows),store.orders,colors)
    read_ms=(time.perf_counter()-started)*1000
    seq=store.write(Built(rows,constants,meta,colors),phase,datetime.now(timezone.utc),read_ms)
    return store.run_id,seq


def snapshot_meta(tables,label):
    state=tables.pop('game_state')
    control=tables.pop('time_control')
    ui=tables.pop('ui_open')
    windows=tables.pop('ui_window',{'name':[]})
    player=tables.pop('player')
    rules=tables.pop('game_rule_setting')
    if state['id']!=[0] or player['id']!=[0] or len(ui['panel'])!=1 or len(control['paused'])>1 or set(rules['id'])-{0}:
        raise RuntimeError('The game state, player, UI or time control capture is not a single row')
    ordered=sorted(zip(rules['ord'],rules['setting']))
    if [o for o,_ in ordered]!=list(range(len(ordered))):
        raise RuntimeError('Game rule ords are not dense')
    constants={'player_country':player['country'][0],'game_speed':state['speed'][0],'first_start':bool(state['first_start'][0]),
               'custom_rng_seed':label(state['custom_rng_seed'][0]),'game_rules':[label(setting) for _,setting in ordered]}
    meta={'game_date':state['date'][0],'local_date_time':state['local_date_time'][0],
          'paused':bool(control['paused'][0]) if control['paused'] else None,'speed':control['speed'][0] if control['paused'] else None,
          'ui_panel_open':bool(ui['panel'][0]),'ui_interaction_open':bool(ui['interaction'][0]),'ui_map_list_open':bool(ui['map_list'][0])}
    return constants,meta,windows['name']


def rule_settings(root,mods):
    return list(dict.fromkeys(setting for _,text in read(root,'common/game_rules',mods) for setting,_ in blocks(body(text))))


def message_groups(root,mods):
    return list(dict.fromkeys(group for _,text in read(root,'common/messages',mods) if (group:=scalar(text,'group'))))


@timed
def register(game,session,world,store):
    root=game.game_dir/'game'
    mods=session['mods']
    manifest=json.loads(world.read_text(encoding='utf-8')) if world else None
    options=event_options(root,mods)
    rows=definitions(root,mods)
    folders={folder for names in VOCABULARIES.values() if names for folder in names}|{folder for folder,*_ in rows}|set(action_folders().values())
    members={}
    for folder in sorted(folders):
        if folder=='events':
            members[folder]=list(dict.fromkeys(event for event,*_ in options))
        elif folder=='common/game_rules':
            members[folder]=rule_settings(root,mods)
        elif folder=='common/messages':
            members[folder]=message_groups(root,mods)
        else:
            members[folder]=keys(root,folder,mods)
    members['common/buildings']+=['building_'+company for company in members['common/company_types'] if 'building_'+company not in members['common/buildings']]
    for folder,name,*_ in rows:
        if name not in members[folder]:
            members[folder].append(name)
    positions={}
    table=[]
    for folder,name,field,value in rows:
        position=positions.get((folder,name,field),0)
        positions[folder,name,field]=position+1
        table.append((folder,name,field,position,value))
    methods=building_methods(root,mods)
    dlc=sorted(folder.name.split('_',1)[1] for folder in (root/'dlc').iterdir() if '_' in folder.name)
    gaps=([('alert_unevaluated',name,f'{context}: '+('no script iterator for this context' if context not in ALERT_SCOPES
                                                    else 'trigger needs a saved scope the evaluator does not push'))
           for name,context,valid in alerts(root,mods) if not evaluable(context,valid)]
          +[('production_method_undetermined',name,'no gate block') for name,gates in production_methods(root,mods) if method_block(name,gates) is None]
          +[('script_absent_reference',name,f'decision {part}: {kind} {key}') for name,shown,possible in decisions(root,mods)
            for part,trigger in (('is_shown',shown),('possible',possible)) for kind,key in missing_references(trigger,manifest)]
          +[('script_absent_reference',name,f'alert: {kind} {key}') for name,context,valid in alerts(root,mods) if evaluable(context,valid)
            for kind,key in missing_references(valid,manifest)])
    gaps=sorted(set(gaps))
    enums={enum:{int(value):name for value,name in LAYOUT['enums'][source].items() if isinstance(name,str)} for enum,source in ENUM_SOURCES.items()}
    enums['scope_type']={int(value):name for value,name in LAYOUT['scope_types'].items()}
    enums['tariff_level']={int(value):name for value,name in LAYOUT['tariff_levels'].items()}
    lines=[(direction,line,name) for (direction,line),name in BUDGET_LINES.items()]
    identity=hashlib.sha256(repr((members,table,options,methods,dlc,gaps)).encode('utf-8')).digest()
    store.ruleset(identity,members,table,options,methods,dlc,gaps,enums,lines)
    store.orders=members
    store.definitions=table
    store.methods=methods
    store.dlc=dlc
    source=mini_world(world) if world else vanilla_world(root)
    world_identity,files,regions,assets=source
    provinces,adjacencies=geometry(files,regions)
    store.world(world_identity,provinces,adjacencies,assets)


class Held:
    def __init__(self,held,nonce,picks):
        self.variables,self.lists,self.maps=held['variables'],held['lists'],held['maps']
        self.picks=picks
        if self.variables.get('cap_seq')!=('value',nonce):
            raise RuntimeError(f'The capture holder carries request {self.variables.get("cap_seq")}, not {nonce}')

    def listed(self,name):
        return self.lists.get(name,[])

    def prefixed(self,prefix):
        return {name[len(prefix):]:items for name,items in self.lists.items() if name.startswith(prefix)}

    def flags(self,name):
        return [text(item) for item in self.listed(name)]

    def objects(self,name):
        return [ident(item) for item in self.listed(name)]

    def mapped(self,name):
        return self.maps.get(name,{})

    def column(self,name):
        if name in self.maps:
            return self.maps[name]
        parts=[self.maps[f'{name}__p{index}'] for index in range(3) if f'{name}__p{index}' in self.maps]
        if any(set(part)!=set(parts[0]) for part in parts):
            raise RuntimeError(f'The integer parts of {name} cover different objects')
        return {key:('value',float(sum(int(text(part[key]))*PART**index for index,part in enumerate(parts)))) for key in (parts[0] if parts else {})}

    def fields(self,name,objects,fields):
        values={field:self.column(f'cap_{name}_{field}') for field in fields}
        rows=[]
        for item in objects:
            missing=[field for field,found in values.items() if item not in found]
            if missing:
                raise RuntimeError(f'Capture group {name} lacks {missing} for object {item}')
            rows.append((ident(item),*(values[field][item] for field in fields)))
        return rows


def number(item):
    if item[0]!='value':
        raise RuntimeError(f'Expected a number, found {item}')
    return item[1]


def flag(item):
    return int(number(item))


def text(item):
    if item[0]!='flag':
        raise RuntimeError(f'Expected text, found {item}')
    return item[1]


def ident(item):
    if item[0] in ('flag','value'):
        raise RuntimeError(f'Expected an object, found {item}')
    return item[1]


MONTH_NAMES=('January','February','March','April','May','June','July','August','September','October','November','December')


def game_hours(text):
    month,day,year=re.fullmatch(r'\s*(\w+) (\d+), (\d+)\s*',text).groups()
    return ((int(year)+5000)*365+MONTH_STARTS[MONTH_NAMES.index(month)]+int(day)-1)*24


@timed
def _metrics(held,kind,groups,owners):
    rows=[]
    for group in groups:
        for name in GROUPS[group]:
            found=held.column(metric_map(kind,name))
            if METRICS[kind][name]=='float':
                outside=[key for bound in ('above','below') for key,value in held.column(metric_map(kind,name+'__'+bound)).items() if number(value)]
                if outside:
                    raise RuntimeError(f'{kind} metric {name} left its captured range for {outside[:5]}')
            keys={ident(key) for key in found}
            if not owners[group]<=keys or keys-owners['allowed_'+group]:
                raise RuntimeError(f'Incomplete {group} metric {name}: missing {sorted(owners[group]-keys)[:5]}, '
                                   f'unexpected {sorted(keys-owners["allowed_"+group])[:5]}')
            rows+=[(ident(key),name,number(value)) for key,value in found.items()]
    return rows


@timed
def _scripted(tables,snapshot,held,tags,label,player,living,world,maps):
    countries={slot(c) for c in snapshot['country']['id'].tolist()}
    states={int(s)&0xffffff for s,owner in zip(snapshot['state']['id'].tolist(),snapshot['state']['country'].tolist()) if slot(owner)!=-1}
    owners={'public':living,'allowed_public':countries,'player':{player},'allowed_player':{player},'state':states,'allowed_state':states}
    put(tables,'country_metric',[('tag','text'),('name','text'),('value','float8'),('country','int4')],
               sorted((tags[country],name,value,country) for country,name,value in _metrics(held,'country',('public','player'),owners)))
    put(tables,'state_metric',[('state','int4'),('name','text'),('value','float8')],sorted(_metrics(held,'state',('state',),owners)))
    expected=set(province_colors(maps))
    provinces=held.listed('cap_province')
    painted={ident(province):text(color) for province,color in held.mapped('cap_province_color').items()}
    if len(provinces)!=len(expected) or set(painted.values())!=expected or {ident(p) for p in provinces}!=set(painted):
        raise RuntimeError(f'Incomplete provinces: expected {len(expected)} colours, captured {len(provinces)} provinces and {len(painted)} colours')
    located,controlled=held.mapped('cap_province_state'),held.mapped('cap_province_controller')
    put(tables,'province_state',[('province','int4'),('state','int4'),('controller_country','int4')],
        [(ident(province),ident(located[province]) if province in located else -1,ident(controlled[province]) if province in controlled else -1)
         for province in provinces])
    colors={province:int(color[1:],16) for province,color in painted.items()}
    possible,unevaluable=set(held.flags('cap_decision_possible')),set(held.flags('cap_decision_unevaluable'))
    put(tables,'decision',[('decision','text'),('takeable','int4')],
               sorted((name,None if name in unevaluable else int(name in possible)) for name in set(held.flags('cap_decision'))))
    put(tables,'production_method_available',[('production_method','text')],sorted((key,) for key in set(held.flags('cap_method'))))
    put(tables,'diplomatic_action_possible',[('country','int4'),('action','text')],
               sorted({(ident(item),action) for action,items in held.prefixed('cap_possible_diplomatic_').items() for item in items}))
    put(tables,'diplomatic_action_state_pick',[('country','int4'),('action','text'),('side','text'),('state','int4')],
               sorted({(country,name.split('_',2)[2],name.split('_',2)[1],ident(item)) for country,target in held.picks.items()
                       for name,items in target['lists'].items() if name.startswith('capd_') for item in items}))
    put(tables,'diplomatic_action_shown',[('country','int4'),('action','text')],
               sorted({(ident(item),action) for action,items in held.prefixed('cap_diplomatic_').items() for item in items}))
    put(tables,'building_setting',[('building','int4'),('auto_expand','int4'),('output_paused','int4'),('monopoly','int4'),('privatizable','int4')],
               sorted((building,*map(flag,values)) for building,*values in
                      held.fields('building',held.listed('cap_obj_building'),('auto_expand','output_paused','monopoly','privatizable'))))
    formations=held.fields('formation',held.listed('cap_obj_formation'),
                           ('default_fleet','demobilizing','invading','embarked','docked','recalled','hit_points_percent','deployable','name'))
    put(tables,'formation_setting',[('formation','int4'),('default_fleet','int4'),('demobilizing','int4'),('invading','int4'),('embarked','int4'),
                                                     ('docked','int4'),('recalled','int4'),('hit_points_percent','float8')],
               sorted((formation,*map(flag,values[:6]),number(values[6])) for formation,*values in formations))
    put(tables,'formation_deployable',[('formation','int4')],sorted((formation,) for formation,*values in formations if flag(values[7])))
    put(tables,'formation_name',[('formation','int4'),('name','text')],sorted((formation,plain(text(values[8]))) for formation,*values in formations))
    put(tables,'state_goods_supply',[('state','int4'),('goods','text')],
               sorted({(ident(item),goods) for goods,items in held.prefixed('cap_supply_').items() for item in items}))
    put(tables,'decree_active',[('state','int4'),('decree_type','text')],
               sorted({(ident(item),kind) for kind,items in held.prefixed('cap_decree_').items() for item in items}))
    put(tables,'country_monopoly',[('building_type','text')],sorted((kind,) for kind in set(held.flags('cap_monopoly'))))
    put(tables,'character_popularity',[('character','int4'),('popularity','float8')],
               sorted((character,number(value)) for character,value in held.fields('character',held.listed('cap_obj_character'),('popularity',))))
    put(tables,'character_formation',[('character','int4'),('has_formation','int4')],
               sorted((character,flag(value)) for character,value in held.fields('character',held.listed('cap_obj_character'),('has_formation',))))
    put(tables,'decree_state_valid',[('state','int4'),('decree_type','text')],
               sorted({(ident(item),kind) for kind,items in held.prefixed('cap_valid_decree_').items() for item in items}))
    put(tables,'interest_group_negotiation',[('interest_group','int4'),('amenability','float8'),('negotiated','int4')],
               sorted((group,number(amenability),flag(negotiated)) for group,amenability,negotiated in
                      held.fields('interest_group',held.listed('cap_obj_interest_group'),('amenability','negotiated'))))
    put(tables,'state_setting',[('state','int4'),('colonization_paused','int4')],
               sorted((state,flag(paused)) for state,paused in held.fields('player_state',held.listed('cap_obj_player_state'),('colonization_paused',))))
    law_types=dict(zip((int(i)&0xffffff for i in snapshot['law']['id'].tolist()),snapshot['law']['law'].tolist()))
    put(tables,'law_chance',[('law','text'),('chance','float8')],
               sorted({(label(law_types[law]),number(chance)) for law,chance in held.fields('law',held.listed('cap_obj_law'),('chance',))}))
    put(tables,'diplomats_expelled',[('country','int4'),('direction','text')],
               sorted({(country,direction) for direction in ('by','of') for country in held.objects('cap_expelled_'+direction)}))
    put(tables,'obligation',[('country','int4'),('direction','text')],
               sorted({(country,direction) for direction in ('owes_player','player_owes') for country in held.objects('cap_'+direction)}))
    put(tables,'country_adjacent',[('country','int4')],sorted({(country,) for country in held.objects('cap_adjacent')}))
    put(tables,'power_bloc_leader',[('country','int4')],sorted({(country,) for country in held.objects('cap_bloc_leader')}))
    put(tables,'bloc_mandates',[('mandates','int4')],
               [(flag(count),) for _,count in held.fields('power_bloc',held.listed('cap_obj_power_bloc'),('mandates',))])
    put(tables,'treaty_port_potential',[('state','int4')],sorted({(state,) for state in held.objects('cap_treaty_port')}))
    put(tables,'country_rank',[('country','int4'),('country_rank','text')],
               sorted((ident(key),text(value)) for key,value in held.mapped('cap_country_rank').items()))
    put(tables,'country_type',[('country','int4'),('country_type','text')],
               sorted((ident(key),text(value)) for key,value in held.mapped('cap_country_type').items()))
    company_types=dict(zip((int(i)&0xffffff for i in snapshot['company']['id'].tolist()),snapshot['company']['company_type'].tolist()))
    put(tables,'company_charter',[('company_type','text'),('investment','int4'),('trade','int4'),('established','int4')],
               sorted((label(company_types[company]),flag(investment),flag(trade),game_hours(text(established))) for company,investment,trade,established in
                      held.fields('company',held.listed('cap_obj_company'),('investment','trade','established'))))
    put(tables,'treaty_enforced_on_player',[('first_country','int4'),('second_country','int4')],
               sorted({(ident(first),ident(second)) for _,first,second in held.fields('treaty',held.listed('cap_obj_treaty_enforced'),('first','second'))}))
    put(tables,'invasion',[('front','int4'),('invader','int4'),('invaded','int4'),('state','int4'),('ended','int4')],
               sorted({(ident(front),ident(invader),ident(invaded),ident(state),flag(ended)) for _,front,invader,invaded,state,ended in
                       held.fields('invasion',held.listed('cap_obj_invasion'),('front','invader','invaded','state','ended'))}))
    company_countries=dict(zip((int(i)&0xffffff for i in snapshot['company']['id'].tolist()),(slot(c) for c in snapshot['company']['country'].tolist())))
    put(tables,'company_owns_country',[('company_type','text'),('country','int4'),('owned_country','int4')],
               sorted({(label(company_types[ident(company)]),company_countries[ident(company)],ident(country)) for country,company in held.mapped('cap_owning_company').items()}))
    put(tables,'journal_button_shown',[('journal_entry','text'),('button','text')],
               sorted({(entry,text(item)) for entry,items in held.prefixed('cap_button_').items() for item in items}))
    put(tables,'interaction_possible',[('character','int4'),('interaction','text')],
               sorted({(ident(item),interaction) for interaction,items in held.prefixed('cap_possible_interaction_').items() for item in items}))
    put(tables,'interaction_shown',[('character','int4'),('interaction','text')],
               sorted({(ident(item),interaction) for interaction,items in held.prefixed('cap_interaction_').items() for item in items}))
    entries=snapshot['journal_entry']
    entry_types=dict(zip((int(i)&0xffffff for i in entries['id'].tolist()),entries['journal_entry_type'].tolist()))
    put(tables,'journal_progress',[('journal','text'),('progress','float8'),('goal','float8'),('percent','float8')],
               sorted((label(entry_types[entry]),number(progress),number(goal),number(percent)) for entry,progress,goal,percent in
                      held.fields('journal',held.listed('cap_obj_journal'),('progress','goal','percent'))))
    put(tables,'objective',[('objective','text')],sorted((key,) for key in set(held.flags('cap_objective'))))
    put(tables,'subgoal_completed',[('subgoal','text')],sorted((key,) for key in set(held.flags('cap_subgoal'))))
    counted=[(name[len('cap_alert_'):],-1,int(number(value))) for name,value in held.variables.items() if name.startswith('cap_alert_') and number(value)]
    located=[(name,ident(item),1) for name,items in held.prefixed('cap_alert_').items() for item in items]
    put(tables,'alert',[('alert','text'),('state','int4'),('instances','int4')],sorted(counted+located))
    known={slot(front) for front in snapshot['front']['id'].tolist()} if 'front' in snapshot else set()
    fronts=[(front,number(advantage)) for front,advantage,shown in held.fields('front',held.listed('cap_obj_front'),('advantage','shown')) if flag(shown)]
    if {front for front,_ in fronts}-known:
        raise RuntimeError(f'Front advantage captured for fronts absent from the snapshot: {sorted({front for front,_ in fronts}-known)}')
    put(tables,'front_advantage',[('front','int4'),('advantage','float8')],sorted(fronts))
    put(tables,'time_control',[('paused','int4'),('speed','int4')],
               [(flag(held.variables['cap_time_paused']),int(text(held.variables['cap_time_speed__p0']))+PART*int(text(held.variables['cap_time_speed__p1'])))])
    put(tables,'market_goods_consumed_by',[('goods','text'),('consumer','text')],
               sorted({(goods,consumer) for consumer in ('government','military') for goods in held.flags('cap_consumed_'+consumer)}))
    put(tables,'strait_endpoint',[('strait','int4'),('first_state','int4'),('second_state','int4'),('strait_type','text')],
               sorted((strait,ident(first),ident(second),text(kind)) for strait,first,second,kind in held.fields('strait',held.listed('cap_obj_strait'),('first','second','type'))))
    put(tables,'strait_power',[('power','text')],sorted((power,) for power in set(held.flags('cap_strait_power'))))
    put(tables,'ui_open',[(name,'int4') for name,_ in UI_CHECKS],[tuple(flag(held.variables['cap_ui_'+name]) for name,_ in UI_CHECKS)])
    put(tables,'ui_window',[('name','text')],sorted((name,) for name in set(held.flags('cap_open'))))
    put(tables,'proposal_shown',[('country','int4'),('kind','text')],
               sorted({(ident(actor),text(kind)) for actor,kind in _counted(held,PROPOSAL_MAPS,'cap_proposal_count')}))
    names,ignored,formable=(held.mapped(name) for name in FORMABLE_MAPS)
    if set(names)!=set(ignored) or set(names)!=set(formable):
        raise RuntimeError('The formable-country maps cover different entries')
    put(tables,'formable_country',[('ord','int4'),('name','text'),('ignored','int4'),('formable','int4')],
               sorted((int(text(key)),plain(text(name)),flag(ignored[key]),flag(formable[key])) for key,name in names.items()))
    borrow_names,borrow_selected=(held.mapped(name) for name in BORROW_MAPS)
    if set(borrow_names)!=set(borrow_selected):
        raise RuntimeError('The borrow-setting maps cover different entries')
    put(tables,'formation_borrow_setting',[('formation','int4'),('ord','int4'),('name','text'),('selected','int4')],
               sorted((slot(int(text(key).split('|')[0])),int(text(key).split('|')[1]),plain(text(name)),flag(borrow_selected[key])) for key,name in borrow_names.items()))
    release_names,release_possible=(held.mapped(name) for name in RELEASE_MAPS)
    if set(release_names)!=set(release_possible):
        raise RuntimeError('The releasable-country maps cover different entries')
    put(tables,'releasable_country',[('ord','int4'),('name','text'),('possible','int4')],
               sorted((int(text(key)),plain(text(name)),flag(release_possible[key])) for key,name in release_names.items()))
    put(tables,'message_feed',[('ord','int4'),('date','text'),('type','text'),('name','text'),('description','text')],_messages(held))
    return colors


def _counted(held,maps,counter):
    count=int(number(held.variables[counter]))
    keys=[('value',float(index)) for index in range(1,count+1)]
    columns=[held.mapped(name) for name in maps]
    for name,column in zip(maps,columns):
        if set(column)!=set(keys):
            raise RuntimeError(f'{name} holds {len(column)} entries but {count} were counted')
    return [tuple(column[key] for column in columns) for key in keys]


def _messages(held):
    rows=[(text(date),text(kind),plain(text(name)),plain(text(description))) for date,kind,name,description in _counted(held,MESSAGE_MAPS,'cap_message_count')]
    period=next(p for p in range(1,len(rows)+1) if len(rows)%p==0 and rows==rows[:p]*(len(rows)//p)) if rows else 0
    return [(index,*row) for index,row in enumerate(rows[:period])]


def _event_options(reader,timeout=1):
    deadline=time.monotonic()+timeout
    while True:
        try:
            return reader.event_options()
        except OSError:
            if time.monotonic()>deadline:
                raise
            time.sleep(.01)


@timed
def _options(tables,snapshot,captured,label):
    events={int(ident):label(int(key)) for ident,key in zip(snapshot['event']['id'],snapshot['event']['event_event'])}
    if not set(captured)<=set(events):
        raise RuntimeError(f'Pending-event windows for unknown events: {sorted(set(captured)-set(events))}')
    put(tables,'event_option_state',[('event','text'),('ord','int4'),('enabled','int4'),('id','int4'),
               ('visible','int4'),('default_option','int4'),('visible_ord','int4'),('text','text'),('description','text')],
               [(events[ident],ordinal,enabled,ident,int(visible>=0),default,visible,text and text.replace(chr(0),''),description and description.replace(chr(0),''))
                for ident,native in captured.items() for ordinal,visible,enabled,default,text,description in native])
