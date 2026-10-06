from interface.actions.catalogue import BY_NAME
from interface.common import timed_often


ALIASES={f'{name}_selected':name for name in ('mobilize','demobilize','raise_conscripts','start_naval_mission','end_naval_mission')}
ALIASES.update({'deploy_selected_to_front':'deploy_to_front','pause_all_construction':'pause_construction','resume_all_construction':'resume_construction',
                'diplomatic_action_obligation':'diplomatic_action','start_play_confirmed':'start_play_country'})
QUEUE={'cancel_queue_item','raise_queue_item','lower_queue_item','first_queue_item','last_queue_item'}
SHIP_QUEUE={'cancel_ship_item','raise_ship_item','lower_ship_item','first_ship_item','last_ship_item'}
MOVING={'station_formation','station_selected','rehome_formation','deploy_to_front','defend_invasion','station_fleet','rehome_fleet',
        'plan_land_invasion','plan_naval_invasion','embark_formation'}
SETTLED={'station_formation','station_selected','rehome_formation','plan_land_invasion','plan_naval_invasion','embark_formation',
         'toggle_mobilization_option','set_strategic_objective','cancel_strategic_objective_selected'}
DELETES={'disband_formation':'military_formation','decommission_ship':'ship','disband_unit':'combat_unit','withdraw_treaty':'treaty'}
PLAYS={'start_play_country','start_play_state','start_play_liberation'}
RELATIONS={'increase_relations','damage_relations'}


@timed_often
def negotiations(name,params,links):
    if name.startswith('amend_'):
        partner=links.get(('treaty',params['treaty']))
        return {('treaty_negotiation',partner[1])} if partner is not None else set()
    if name.endswith(('_treaty_article','_treaty_articles')) and 'country' in params:
        return {('treaty_negotiation',params['country'])}
    return set()


@timed_often
def canonical(name,params):
    name=ALIASES.get(name,name)
    keys={spec.split(':')[0] for spec in BY_NAME[name].params}
    return name,{key:value for key,value in params.items() if key in keys}


@timed_often
def targets(name,params,links={}):
    name,params=canonical(name,params)
    found={('command',name,tuple(sorted(params.items())))}|negotiations(name,params,links)
    if name=='diplomatic_action' and params['diplomatic_action'] in RELATIONS:
        found.add(('relations',params['country']))
    if name in PLAYS:
        found.add(('new_play',))
    if name.startswith('offer_sway'):
        found.add(('sway',params['diplomatic_play'],params['country']))
    for spec in BY_NAME[name].params:
        key,_,kind=spec.partition(':')
        if (kind or key) not in ('int','choice'):
            found.add(('object',kind or key,params[key]))
    formation=params.get('military_formation')
    if name in SETTLED:
        found.add(('settled',formation))
    if name in ('mobilize','mobilize_all','demobilize','demobilize_all'):
        operation=name.removesuffix('_all')
        found.add((operation,))
        if formation is not None:
            found.add((operation,formation))
    if name=='raise_conscripts':
        found.add(('conscriptions',formation))
    if name in QUEUE:
        found.add(('queued',params['state'],params['building_type']))
    if name=='cancel_construction':
        site=links.get(('building_site',params['building']))
        if site is not None:
            found.add(('queued',*site))
    if name in SHIP_QUEUE:
        found.add(('ship_queue_index',))
    if name in ('pause_construction','pause_ship_construction'):
        found.add(('construction_running',))
    if name=='resume_construction':
        found.add(('construction_paused',))
    if name in ('enact_law','cancel_enactment','negotiate'):
        found.add(('enactment',))
    if name=='negotiate':
        found.add(('negotiation',))
    return found


@timed_often
def invalidates(name,params,links={}):
    name,params=canonical(name,params)
    found={('command',name,tuple(sorted(params.items())))}|negotiations(name,params,links)
    if name=='diplomatic_action' and params['diplomatic_action'] in RELATIONS:
        found.add(('relations',params['country']))
    if name in ('merge_armies','merge_fleets'):
        found.add(('object','military_formation',params['source']))
    if name in PLAYS:
        found.add(('new_play',))
    if name.startswith('offer_sway'):
        found.add(('sway',params['diplomatic_play'],params['country']))
    formation=params.get('military_formation')
    if name in MOVING:
        found.add(('settled',formation))
    if name in ('mobilize','demobilize'):
        found.add((name,formation))
    if name in ('mobilize_all','demobilize_all'):
        found.add((name.removesuffix('_all'),))
    if name=='raise_conscripts':
        found.add(('conscriptions',formation))
    if name in ('build','cancel_queue_item'):
        found.add(('queued',params['state'],params['building_type']))
    if name=='cancel_construction':
        site=links.get(('building_site',params['building']))
        if site is not None:
            found.add(('queued',*site))
    if name in SHIP_QUEUE or name in ('cancel_ship','cancel_ship_for'):
        found.add(('ship_queue_index',))
    if name=='pause_construction':
        found.add(('construction_running',))
    if name=='resume_construction':
        found.add(('construction_paused',))
    if name in ('enact_law','cancel_enactment'):
        found.add(('enactment',))
    if name=='negotiate':
        found.add(('negotiation',))
    if name in DELETES:
        kind=DELETES[name]
        value=params[kind]
        found.add(('object',kind,value))
        if kind=='military_formation':
            found.update(('object',key,ident) for (key,ident),owner in links.items() if key=='ship' and owner==(kind,value))
    return found
