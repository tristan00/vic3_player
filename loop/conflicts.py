from interface.actions.catalogue import BY_NAME
from interface.common import timed_often
from interface.options.available import (BLOC_INFLUENCE, CHARTER_COST, DEFAULT_TAX_COST, MAX_MONOPOLIES, MONOPOLY_COST, MOVEMENT_COST, article_cost,
                                        authority, bulk_subset, chartered, definition, free_charters, metric, money, monopolies, nationalization_cost,
                                        ownership_classes, pact_cost_multiplier, private_levels, ship_kinds, stated)


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
RESEARCH={'research','queue_research','dequeue_research'}
POLICIES={'set_tax_level','set_government_wages','set_military_wages','set_supply_ship_construction'}
DIPLOMACY={'diplomatic_action','diplomatic_action_first_state','diplomatic_action_second_state','diplomatic_action_states'}
CONSTRUCTION_QUEUE=QUEUE|{'build','cancel_construction'}


@timed_often
def context(snapshot):
    return {**{('building_site',i):(s,k) for i,s,k in snapshot.rows('building','building,state,building_type')},
            **{('ship',s):('military_formation',f) for s,f in snapshot.rows('ship','ship,fleet') if f is not None},
            **{('ship_type',s):k for s,k in ship_kinds(snapshot).items()},
            **{('combat_unit',i):f for i,f in snapshot.rows('combat_unit','combat_unit,formation')},
            **{('method_group',(k,m)):g for k,g,m in snapshot.methods},
            **{('ownership',i):k for i,k in ownership_classes(snapshot).items()},
            **{('treaty',t):('country',b if a==snapshot.player else a) for t,a,b in snapshot.rows('treaty','treaty,first_country,second_country')}}


@timed_often
def changes(name,params,links):
    found=set()
    buildings=([params['building']] if 'building' in params else
               [ident for (key,ident),site in links.items() if key=='building_site' and site[0]==params.get('state')
                and site[1]==params.get('building_type',site[1]) and (params.get('ownership','any')=='any' or params['ownership'] in links.get(('ownership',ident),()))])
    if 'production_method' in params:
        found.update(('building_method',i,links.get(('method_group',(links.get(('building_site',i),(None,None))[1],params['production_method'])),params['production_method'])) for i in buildings)
    if name in ('reset_production_methods','reset_building_production_methods'):
        found.update(('building_method',i,group) for i in buildings for (key,kind),group in links.items()
                     if key=='method_group' and kind[0]==links.get(('building_site',i),(None,None))[1])
    if 'subsidies' in name:
        found.update(('building_subsidy',i) for i in buildings)
    if name in ('nationalize','bulk_nationalize_state','bulk_expropriate_state','toggle_privatization'):
        found.update(('building_ownership',i) for i in buildings)
    if name.startswith(('set_import_','set_export_')):
        found.add(('trade_policy',name.split('_')[1],params['goods']))
    if name in ('toggle_bolster_movement','toggle_suppress_movement'):
        found.add(('movement_policy',params['political_movement']))
    if name in ('issue_decree','remove_decree'):
        found.add(('state_decrees',params['state']))
    if name in ('reform_government','reform_government_party'):
        found.add(('government',))
    if name in ('move_capital','move_market_capital'):
        found.add((name,))
    if name in ('form_power_bloc','request_join_power_bloc','leave_power_bloc'):
        found.add(('bloc_membership',))
    if name in ('form_power_bloc','request_join_power_bloc','leave_power_bloc','pick_principle','replace_principle','upgrade_principle'):
        found.add(('bloc_principles',))
    if name=='toggle_monopoly':
        found.add(('monopoly',params['building_type']))
    if name=='set_borrow_setting':
        found.add(('formation_borrow_setting',params['military_formation']))
    if name=='character_interaction' and stated('common/character_interactions',params['interaction'],'cooldown'):
        found.add(('interaction_cooldown',params['interaction']))
    if name.startswith(('retrofit_','cancel_retrofit_')) or name in ('change_ship_template','decommission_ship'):
        ships=([params['ship']] if 'ship' in params else [i for (key,i),formation in links.items() if key=='ship'
                and (params.get('military_formation') is None or formation[1]==params['military_formation'])])
        found.update(('ship_refit',i) for i in ships)
        found.update(('ship_templates',links[('ship_type',i)]) for i in ships if ('ship_type',i) in links)
    if name=='set_fleet_ship_template':
        found.update(('ship_refit',i) for (key,i),formation in links.items() if key=='ship' and formation[1]==params['military_formation'])
    if name in ('build_ship','build_ship_for','cancel_ship','cancel_ship_for'):
        found.add(('ship_templates',params['ship_type']))
    if name in ('disband_regulars','disband_conscripts','transfer_battalions'):
        found.update(('object','combat_unit',i) for (key,i),formation in links.items() if key=='combat_unit' and formation==params.get('military_formation'))
    if name=='set_default_unit_type':
        found.add(('default_unit_type',params['military_formation'],*stated('common/combat_unit_types',params['combat_unit_type'],'group')))
    return found


@timed_often
def resources(snapshot):
    return {'authority':max(0,authority(snapshot)),'influence':max(0,metric(snapshot,"GetPowerDelta('influence')")),
            'money':max(0,money(snapshot)),'monopolies':max(0,MAX_MONOPOLIES-len(monopolies(snapshot))),'charters':free_charters(snapshot)}


@timed_often
def cost(snapshot,name,params):
    needed={}
    if name=='issue_decree':
        needed['authority']=float(next(iter(definition(snapshot,'common/decrees',params['decree'],'cost')),0))
    if name=='toggle_consumption_tax' and not snapshot.rows('player_taxed_goods','goods',goods=params['goods']):
        needed['authority']=float(next(iter(definition(snapshot,'common/goods',params['goods'],'consumption_tax_cost')),DEFAULT_TAX_COST))
    if name in ('toggle_bolster_movement','toggle_suppress_movement') and snapshot.map('political_movement','political_movement,managed_status').get(params['political_movement']) is None:
        needed['authority']=MOVEMENT_COST
    if name=='toggle_monopoly' and params['building_type'] not in monopolies(snapshot):
        needed.update(authority=MONOPOLY_COST,monopolies=1)
    if name in ('grant_building_charter','grant_region_charter') or name=='toggle_charter' and (params['company'],params['charter']) not in chartered(snapshot):
        needed.update({'charters':1} if free_charters(snapshot) else {'authority':CHARTER_COST})
    if name=='character_interaction' and params['interaction'] in ('patronize','ostracize','retire_daimyo','grant_peerage'):
        interaction=params['interaction']
        needed['authority']=25 if interaction=='grant_peerage' else 100
        if interaction=='patronize' and any(trait in ('opium_addiction','alcoholic','cocaine_addiction','expensive_tastes')
                                          for trait, in snapshot.rows('character_assigned_trait','character_trait',character=params['character'])):
            needed['authority']+=50
    if name=='nationalize':
        needed['money']=nationalization_cost(snapshot,params['building'])*params['levels']
    if name=='bulk_nationalize_state':
        levels=private_levels(snapshot)
        needed['money']=sum(nationalization_cost(snapshot,i)*levels.get(i,0) for i in bulk_subset(snapshot,**params))
    if name in DIPLOMACY|{'diplomatic_action_obligation'}:
        needed['influence']=float(next(iter(definition(snapshot,'common/diplomatic_actions',params['diplomatic_action'],'pact_cost')),0))*pact_cost_multiplier(snapshot,params['country'],params['diplomatic_action'])
    if 'treaty_article' in params and 'country' in params and name.startswith(('offer_','demand_','agree_','work_out_','exchange_','threaten_')) and 'sway' not in name:
        source,target=(params['country'],snapshot.player) if name.startswith(('demand_','work_out_','threaten_')) else (snapshot.player,params['country'])
        needed['influence']=article_cost(snapshot,params['treaty_article'],source,target)
        if name=='exchange_treaty_articles':
            needed['influence']+=article_cost(snapshot,params['demand'],params['country'],snapshot.player)
    if name=='form_power_bloc':
        needed['influence']=BLOC_INFLUENCE
    return needed


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
    found={('command',name,tuple(sorted(params.items())))}|negotiations(name,params,links)|changes(name,params,links)
    if name in RESEARCH:
        found.add(('research_technology',params['technology']))
    if name=='research':
        found.add(('research_reset',))
    if name=='dequeue_research':
        found.add(('research_queue',))
    if name in POLICIES:
        found.add(('policy',name))
    if name in DIPLOMACY:
        found.add(('diplomatic_proposal',params['country']))
    if 'character' in params:
        found.add(('character_change',params['character']))
    if name in ('assign_commander','hire_commander_for'):
        found.add(('commander_assignment',params['military_formation']))
    if name in CONSTRUCTION_QUEUE:
        found.add(('construction_queue',))
    if name in QUEUE-{'cancel_queue_item'}:
        found.add(('queue_order',))
    if 'ship_type' in params and ('index' in params or name=='design_ship_template'):
        found.add(('ship_templates',params['ship_type']))
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
        found.update({('conscriptions',formation),('conscriptions',)})
    if name in QUEUE or name=='build':
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
    if name in DELETES:
        kind=DELETES[name]
        found.add(('used',kind,params[kind]))
    if name in ('merge_armies','merge_fleets'):
        found.add(('used','military_formation',params['source']))
    return found


@timed_often
def invalidates(name,params,links={}):
    name,params=canonical(name,params)
    found={('command',name,tuple(sorted(params.items())))}|negotiations(name,params,links)|changes(name,params,links)
    for spec in BY_NAME[name].params:
        key,_,kind=spec.partition(':')
        if (kind or key) not in ('int','choice'):
            found.add(('used',kind or key,params[key]))
    if name in RESEARCH:
        found.update({('research_reset',),('research_technology',params['technology'])})
    if name=='research':
        found.add(('research_queue',))
    if name in POLICIES:
        found.add(('policy',name))
    if name in DIPLOMACY:
        found.add(('diplomatic_proposal',params['country']))
    if 'character' in params:
        found.add(('character_change',params['character']))
    if name in ('assign_commander','hire_commander_for'):
        found.add(('commander_assignment',params['military_formation']))
    if name in CONSTRUCTION_QUEUE:
        found.add(('queue_order',))
    if name in QUEUE-{'cancel_queue_item'}:
        found.add(('construction_queue',))
    if 'ship_type' in params and ('index' in params or name=='design_ship_template'):
        found.add(('ship_templates',params['ship_type']))
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
        found.update({('conscriptions',formation),('demobilize',formation),('demobilize',)})
    if name=='demobilize':
        found.add(('conscriptions',formation))
    if name=='demobilize_all':
        found.add(('conscriptions',))
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
