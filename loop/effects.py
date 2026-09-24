import collections
from interface.actions.catalogue import ACCESS_PERMISSIONS, ACCESS_STATUSES, LEVELS, TOLL_LEVELS
from interface.options.available import COUNTRY_OWNER, metric, overlords, subject_pairs, own_templates, latest_design, in_default, journal_button, shown_buttons, ownership_classes, TARIFF_CODES, bulk_subset, private_levels, privatizable, privatization_requested, PRIVATIZATION_REQUESTED, enacting_laws, hq_regions, live_goals, my_ships, pressed_in, ship_paused, trade_level
from interface.recording.spec import TABLE

SLOT=0xFFFFFF


def value(snapshot,table,column,ident):
    stored=table+'_history' if table+'_history' in TABLE else table
    return snapshot.map(table,f'{TABLE[stored].owner},{column}').get(ident)


def members(snapshot,table,ident,column):
    return set(snapshot.grouped(table,f'{TABLE[table].owner},{column}').get(ident,()))


def research_row(snapshot):
    return next(ident for ident, in snapshot.rows('country_research','country_research',country=snapshot.player))


def researching(snapshot):
    return value(snapshot,'country_research','researching',research_row(snapshot))


def queued(snapshot):
    return members(snapshot,'country_research_queued',research_row(snapshot),'technology')


def queue(snapshot):
    return [(state,kind) for _,state,kind in sorted(snapshot.rows('player_construction_queue_item','position,state,building_type',private=False))]


def common(items,other):
    left=collections.Counter(other)
    kept=[]
    for item in items:
        if left[item]:
            left[item]-=1
            kept.append(item)
    return kept


def site(snapshot,building):
    return snapshot.rows('building','state,building_type',building=building)[0]


def moved(target):
    def test(a,b,p,n):
        before,after=queue(a),queue(b)
        item=(p['state'],p['building_type'])
        if item not in before or item not in after:
            return None
        index=before.index(item)
        before.pop(index)
        goal=target(index,len(before))
        before.insert(goal,item)
        passed=before[min(index,goal):max(index,goal)+1]
        if any(other not in after for other in passed):
            return None
        return common(before,after)==common(after,before)
    return test


def hours(snapshot):
    return snapshot.hours


def formables(snapshot):
    return [name for _,name in sorted(snapshot.rows('player_formable_country','position,name'))]


def formable_ord(after,before,index):
    names=formables(before)
    name=names[index] if index<len(names) else None
    return next((ord for ord,found in enumerate(formables(after)) if found==name),None)


def ignoring(snapshot,index):
    flags=[ignored for _,ignored in sorted(snapshot.rows('player_formable_country','position,ignored'))]
    return flags[index] if index is not None and index<len(flags) else None


def template_flags(snapshot,p):
    template=own_templates(snapshot).get((p['ship_type'],p['index']))
    return snapshot.map('ship_template_private','ship_template,flags').get(template,0)


def retrofitting_fleets(snapshot):
    return sum(1 for flag, in snapshot.rows('formation_report','retrofitting') if flag)


def strait_becomes(column,target):
    return lambda a,b,p,n:any(value(a,'strait',f'{side}_{column}',p[n])!=value(b,'strait',f'{side}_{column}',p[n])==target(p) for side in ('first','second'))


def changed(table,column):
    return lambda a,b,p,name:value(b,table,column,p[name])!=value(a,table,column,p[name])


def equals(table,column,expected):
    return lambda a,b,p,name:value(a,table,column,p[name])!=expected and value(b,table,column,p[name])==expected


def becomes(get,target):
    return lambda a,b,p,n:get(a,p,n)!=target(p) and get(b,p,n)==target(p)


def count(snapshot,table,mine):
    return len(snapshot.rows(table,table,**({'country':snapshot.player} if mine else {})))


def fewer(table,mine=False):
    return lambda a,b,p,name:count(b,table,mine)<count(a,table,mine)


def more(table,mine=False):
    return lambda a,b,p,name:count(b,table,mine)>count(a,table,mine)


def policy(column,expected):
    return becomes(lambda s,p,n:s.rows('player_policy',column)[0][0],expected)


def construction_paused(expected):
    return becomes(lambda s,p,n:value(s,'country_construction_report','is_construction_paused',s.player),lambda p:expected)


def roles(snapshot,play):
    return {role for role, in snapshot.rows('diplomatic_play_country','role',diplomatic_play=play,country=snapshot.player)}


def side(snapshot,play):
    return {index for index,role in enumerate(('initiator','target')) if role in roles(snapshot,play)}


def mobilized(snapshot):
    mine={ident for ident, in snapshot.rows('formation','formation',country=snapshot.player)}
    return {ident:flag for ident,flag in snapshot.rows('formation_status','formation,mobilized') if ident in mine}


def conscripts(snapshot,p):
    centers={ident for ident, in snapshot.rows('building','building',state=p['state'])}
    return sorted((unit,building) for unit,building in snapshot.rows('combat_unit','combat_unit,building',formation=p['military_formation']) if building in centers)


def proposing(snapshot,actor,kind=None):
    shown={kind for kind, in snapshot.rows('player_proposal','kind',country=actor)}
    return bool(shown) if kind is None else kind in shown


def held_goals(snapshot,play):
    return sum(1 for goal_play, in snapshot.rows('war_goal','diplomatic_play',holder=snapshot.player) if goal_play==play)


def units(snapshot,formation,kind):
    return sum(1 for unit, in snapshot.rows('combat_unit','combat_unit_type',formation=formation) if unit==kind)


def button_hidden(a,b,p):
    pressed=journal_button(a,p['journal_entry'],p['button'])
    return (pressed is not None and p['journal_entry'] in b.map('journal_entry','journal_entry,journal_entry_type')
            and pressed[1] not in shown_buttons(b,pressed[0]))


def country_state(snapshot):
    player=snapshot.player
    return (set(snapshot.rows('country_timed_modifier','modifier,start_date',country=player)),
            set(snapshot.rows('journal_entry','journal_entry,journal_entry_type',country=player)),
            set(snapshot.rows('law','law,active',country=player)),
            money_of(snapshot))


def money_of(snapshot):
    return snapshot.rows('player_treasury','money')[0][0]


def maneuvers(snapshot,play):
    return next((initiator_maneuvers if snapshot.player==initiator else target_maneuvers for initiator,initiator_maneuvers,target_maneuvers
                 in snapshot.rows('diplomatic_play','initiator,initiator_maneuvers,target_maneuvers',diplomatic_play=play)),0)


def goal_status(snapshot,p):
    return {status for play,kind,target,status in live_goals(snapshot,'war_goal_type,target_country,pressed')
            if play==p['diplomatic_play'] and kind==p['war_goal_type'] and target==p['country']}


def flags(snapshot,table,column,key,buildings,mask=-1):
    values=snapshot.map(table,f'{key},{column}')
    return [bool((values.get(ident) or 0)&mask) for ident in buildings]


def bulk_toggle(table,column,key='building',target=None,eligible=lambda s,ident:True,mask=-1):
    def check(a,b,p,n):
        subset=[ident for ident in bulk_subset(a,p['building_type'],None,'any') if eligible(a,ident)]
        before,after=flags(a,table,column,key,subset,mask),flags(b,table,column,key,subset,mask)
        if target is None:
            return bool(subset) and len(set(after))==1 and after!=before
        return bool(subset) and after!=before and all(value==target for value in after)
    return check


def methods(snapshot,building):
    return members(snapshot,'building_production_method_active',building,'production_method')


def bulk_method(a,b,p,n):
    subset=bulk_subset(a,p['building_type'],p.get('state'),p['ownership'])
    others=[ident for ident in bulk_subset(a,p['building_type'],None,'any') if ident not in subset]
    return (bool(subset) and any(p['production_method'] not in methods(a,ident) for ident in subset)
            and all(p['production_method'] in methods(b,ident) for ident in subset) and all(methods(a,ident)==methods(b,ident) for ident in others))


def subset_setting(table,column,key,target):
    def check(a,b,p,n):
        subset=bulk_subset(a,p['building_type'],p.get('state'),p['ownership'])
        known=ownership_classes(a)
        others=[ident for ident in bulk_subset(a,p['building_type'],None,'any') if ident not in subset and (p['ownership']=='any' or ident in known)]
        return (bool(subset) and flags(a,table,column,key,subset)!=flags(b,table,column,key,subset)
                and all(value==target for value in flags(b,table,column,key,subset)) and flags(a,table,column,key,others)==flags(b,table,column,key,others))
    return check


def home_region(snapshot,formation):
    home=value(snapshot,'formation_private','home_hq',formation)
    return next((region for hq,(_,region) in hq_regions(snapshot).items() if home is not None and hq==home),None)


def ownerships(snapshot,building):
    return set(snapshot.rows('building_ownership','building_ownership,levels,owner',building=building))


def pacts(snapshot):
    return set(snapshot.rows('pact','first_country,second_country,pact_type'))


def plays(snapshot):
    return set(snapshot.rows('diplomatic_play','diplomatic_play'))


def new_plays(a,b,kind,target):
    targets={target}|overlords(a,target)
    started=lambda s:{play for play,initiator,other,found in s.rows('diplomatic_play','diplomatic_play,initiator,target,diplomatic_play_type')
                      if initiator==s.player and other in targets and found==kind}
    return started(b)-started(a)


def released(a,b):
    existing={country for country, in a.rows('country','country')}
    mine=set(a.states())
    return {owner for state,owner in b.rows('state','state,country') if state in mine and owner not in existing}


def borrowed(snapshot,formation,index):
    return any(selected for position,selected in snapshot.rows('formation_borrow_setting','position,selected',formation=formation) if position==index)


def objective(snapshot,formation):
    found=value(snapshot,'formation_private','strategic_objective',formation)
    return None if found is None else found&SLOT


def interaction_state(snapshot,character):
    return (snapshot.rows('character','country,interest_group,noble,prominence,rank',character=character),snapshot.characters_roles(character),
            set(snapshot.rows('character_timed_modifier','modifier,instances',character=character)),snapshot.rows('character_status','popularity',character=character))


def relations(snapshot):
    return set(snapshot.rows('player_relation','country,relations,improve_relations'))


def relation_with(snapshot,country):
    return {row for row in relations(snapshot) if row[0]==country}


def bloc_principles(snapshot):
    bloc=value(snapshot,'country','power_bloc',snapshot.player)
    return {principle for owner,principle in snapshot.rows('power_bloc_adopted_principle','power_bloc,power_bloc_principle') if owner==bloc}


def relation_changed(a,b,country):
    return a.hours==b.hours and relation_with(a,country)!=relation_with(b,country)


def infamy(snapshot):
    return snapshot.map('country_diplomacy','country,infamy').get(snapshot.player)


def diplomatic_effect(a,b,p,n):
    if p['diplomatic_action']=='violate_sovereignty':
        return infamy(b)>infamy(a)
    return pair_pacts(a,p[n])!=pair_pacts(b,p[n]) or relation_changed(a,b,p[n])


def pair_pacts(snapshot,country):
    return {row for row in pacts(snapshot) if {row[0],row[1]}=={snapshot.player,country}}


def obligations_with(snapshot,country):
    return {row for row in snapshot.rows('player_obligation','country,direction') if row[0]==country}


def player_claims(snapshot):
    return set(snapshot.rows('country_claim','state_region',country=snapshot.player))


def colonies(snapshot):
    mine=set(snapshot.states())
    return {state:progress for state,progress in snapshot.rows('state_status','state,colony_progress') if state in mine}


SUBSET_EFFECTS={'subsidies_on':('building','subsidized','building',True),'subsidies_off':('building','subsidized','building',False),
                'auto_expand_on':('building_private','auto_expand','building',True),'auto_expand_off':('building_private','auto_expand','building',False)}


def bulk_nationalized(a,b,p,n):
    before,after=private_levels(a),private_levels(b)
    subset=[ident for ident in bulk_subset(a,p['building_type'],p.get('state'),p['ownership']) if before.get(ident)]
    others=[ident for ident in bulk_subset(a,p['building_type'],None,'any') if ident not in subset]
    return bool(subset) and not any(after.get(ident) for ident in subset) and all(before.get(ident,0)==after.get(ident,0) for ident in others)


BULK_EFFECTS={'subsidies':('building','subsidized'),'auto_expand':('building_private','auto_expand'),
              'privatization':('building','privatization_requested','building',None,lambda s,i:privatizable(s,i) or privatization_requested(s,i),PRIVATIZATION_REQUESTED),
              'remove_privatization':('building','privatization_requested','building',False,lambda s,i:True,PRIVATIZATION_REQUESTED)}


EFFECTS={
    'set_tax_level':(None,policy('tax_level',lambda p:LEVELS.index(p['level']))),
    'set_government_wages':(None,policy('government_wage_level',lambda p:LEVELS.index(p['level']))),
    'set_military_wages':(None,policy('military_wage_level',lambda p:LEVELS.index(p['level']))),
    'set_supply_ship_construction':(None,policy('supply_ship_construction_level',lambda p:LEVELS.index(p['level']))),
    'pause_construction':(None,construction_paused(True)),
    'resume_construction':(None,construction_paused(False)),
    'pause_all_construction':(None,construction_paused(True)),
    'resume_all_construction':(None,construction_paused(False)),
    'subsidies_on':('building',equals('building','subsidized',True)),
    'subsidies_off':('building',equals('building','subsidized',False)),
    'auto_expand_on':('building',equals('building_private','auto_expand',True)),
    'auto_expand_off':('building',equals('building_private','auto_expand',False)),
    'pause_construction_output':('building',equals('building_private','output_paused',True)),
    'resume_construction_output':('building',equals('building_private','output_paused',False)),
    'toggle_privatization':('building',changed('building','privatization_requested')),
    **{f'bulk_{name}':(None,bulk_toggle(*spec)) for name,spec in BULK_EFFECTS.items()},
    **{f'subset_{name}{suffix}':(None,subset_setting(*spec)) for name,spec in SUBSET_EFFECTS.items() for suffix in ('','_state')},
    'bulk_nationalize':(None,bulk_nationalized),'bulk_nationalize_state':(None,bulk_nationalized),
    'bulk_switch_production_method':(None,bulk_method),'bulk_switch_production_method_state':(None,bulk_method),
    'switch_production_method':('building',lambda a,b,p,n:p['production_method'] not in methods(a,p['building']) and p['production_method'] in methods(b,p['building'])),
    'downsize':('building',lambda a,b,p,n:value(a,'building','levels',p['building']) is not None
                and (value(b,'building','levels',p['building']) is None or value(b,'building','levels',p['building'])<value(a,'building','levels',p['building']))),
    'cancel_construction':('building',lambda a,b,p,n:queue(b).count(site(a,p[n]))<queue(a).count(site(a,p[n]))),
    'research':(None,lambda a,b,p,n:researching(a)!=p['technology'] and p['technology'] not in queued(a) and (researching(b)==p['technology'] or p['technology'] in queued(b))),
    'queue_research':(None,lambda a,b,p,n:p['technology'] not in queued(a) and p['technology'] in queued(b)),
    'dequeue_research':(None,lambda a,b,p,n:p['technology'] in queued(a) and p['technology'] not in queued(b)),
    'build':(None,lambda a,b,p,n:queue(b).count((p['state'],p['building_type']))>queue(a).count((p['state'],p['building_type']))),
    'enact_law':('law',lambda a,b,p,n:p['law'] not in enacting_laws(a) and p['law'] in enacting_laws(b)),
    'cancel_enactment':(None,lambda a,b,p,n:bool(enacting_laws(a)) and not enacting_laws(b)),
    'set_institution_level':('institution',lambda a,b,p,n:(value(b,'institution_private','target_investment',p[n]),value(b,'institution','investment',p[n]))
                             !=(value(a,'institution_private','target_investment',p[n]),value(a,'institution','investment',p[n]))),
    'issue_decree':(None,becomes(lambda s,p,n:(p['state'],p['decree']) in set(s.rows('player_active_decree','state,decree_type')),lambda p:True)),
    'remove_decree':(None,becomes(lambda s,p,n:(p['state'],p['decree']) in set(s.rows('player_active_decree','state,decree_type')),lambda p:False)),
    'toggle_consumption_tax':(None,lambda a,b,p,n:((p['goods'],) in a.rows('player_taxed_goods','goods'))!=((p['goods'],) in b.rows('player_taxed_goods','goods'))),
    'set_supply_priority':('military_formation',becomes(lambda s,p,n:value(s,'formation','supply_priority',p[n]),lambda p:('low','medium','high').index(p['level']))),
    'toggle_mobilization_option':('military_formation',lambda a,b,p,n:members(a,'formation_mobilization_option',p[n],'mobilization_option')
                                  !=members(b,'formation_mobilization_option',p[n],'mobilization_option')),
    'raise_conscripts':('military_formation',equals('formation_status','raised_conscripts',True)),
    'start_naval_mission':('military_formation',changed('formation_status','naval_mission')),
    'recruit_from_formation':(None,lambda a,b,p,n:units(b,p['military_formation'],p['combat_unit_type'])>units(a,p['military_formation'],p['combat_unit_type'])
                              or len(queue(b))>len(queue(a))),
    'activate_conscription_center':(None,lambda a,b,p,n:conscripts(b,p)!=conscripts(a,p) or None),
    'disembark':('military_formation',equals('formation_report','embarked',False)),
    'cancel_invasion':('military_formation',equals('formation_report','invading',False)),
    'upgrade_all_units':(None,lambda a,b,p,n:set(a.rows('formation_upgrade_unit_type','formation,combat_unit_type'))
                         !=set(b.rows('formation_upgrade_unit_type','formation,combat_unit_type'))),
    'create_army':(None,lambda a,b,p,n:len(b.rows('formation','formation',country=b.player,formation_type=0))>len(a.rows('formation','formation',country=a.player,formation_type=0))),
    'transfer_battalions':(None,lambda a,b,p,n:len(b.rows('combat_unit','combat_unit',formation=p['military_formation']))<len(a.rows('combat_unit','combat_unit',formation=p['military_formation']))
                           and len(b.rows('combat_unit','combat_unit',formation=p['target']))>len(a.rows('combat_unit','combat_unit',formation=p['target']))),
    'deploy_to_front':('military_formation',becomes(lambda s,p,n:value(s,'formation_status','target_location',p[n]),lambda p:p['front'])),
    'end_naval_mission':('military_formation',changed('formation_status','naval_mission')),
    'start_naval_mission_selected':('military_formation',changed('formation_status','naval_mission')),
    'end_naval_mission_selected':('military_formation',changed('formation_status','naval_mission')),
    'promote_commander':('character',changed('character','rank')),
    'commander_order':('character',changed('character','order_type')),
    'assign_commander':('character',becomes(lambda s,p,n:value(s,'character','formation',p['character']),lambda p:p['military_formation'])),
    'unassign_commander':('character',lambda a,b,p,n:value(a,'character','formation',p[n]) is not None and value(b,'character','formation',p[n]) is None),
    'hire_commander':('character',lambda a,b,p,n:value(b,'character_private','recruitable',p[n]) is False and value(b,'character','country',p[n])==b.player),
    'toggle_bolster_movement':('political_movement',changed('political_movement','managed_status')),
    'toggle_suppress_movement':('political_movement',changed('political_movement','managed_status')),
    'withdraw_treaty':('treaty',equals('treaty','withdrawn',True)),
    'disband_formation':('military_formation',lambda a,b,p,n:value(a,'formation','dead',p[n]) is False and value(b,'formation','dead',p[n]) is not False),
    'build_ship':(None,lambda a,b,p,n:my_ships(b).count(p['ship_type'])>my_ships(a).count(p['ship_type'])),
    'cancel_ship':(None,lambda a,b,p,n:my_ships(b).count(p['ship_type'])<my_ships(a).count(p['ship_type'])),
    'decommission_ship':('ship',lambda a,b,p,n:value(b,'ship','fleet',p[n])!=value(a,'ship','fleet',p[n])),
    'pause_ship_construction':(None,lambda a,b,p,n:not ship_paused(a) and ship_paused(b)),
    'resume_ship_construction':(None,lambda a,b,p,n:ship_paused(a) and not ship_paused(b)),
    'create_company':(None,more('company',True)),
    'remove_company':(None,fewer('company',True)),
    'toggle_charter':('company',lambda a,b,p,n:set(a.rows('company','company,investment_charter,trade_charter',country=a.player))
                      !=set(b.rows('company','company,investment_charter,trade_charter',country=b.player))),
    'incorporate':('state',changed('state_status','incorporation')),
    'unincorporate':('state',equals('state_status','incorporation',0)),
    'start_play_country':(None,lambda a,b,p,n:bool(new_plays(a,b,p['diplomatic_play_type'],p['country']))),
    'start_play_state':(None,lambda a,b,p,n:bool(new_plays(a,b,p['diplomatic_play_type'],value(a,'state','country',p['state'])))),
    'hire_commander_for':('character',becomes(lambda s,p,n:value(s,'character','formation',p['character']),lambda p:p['military_formation'])),
    'nationalize':('building',lambda a,b,p,n:ownerships(a,p[n])!=ownerships(b,p[n])),
    'upgrade_regulars':('military_formation',lambda a,b,p,n:members(a,'formation_upgrade_unit_type',p[n],'combat_unit_type')
                        !=members(b,'formation_upgrade_unit_type',p[n],'combat_unit_type')),
    'set_default_construction_fleet':('military_formation',equals('formation_report','default_fleet',True)),
    'clear_default_construction_fleet':(None,lambda a,b,p,n:any(flag for flag, in a.rows('formation_report','default_fleet'))
                                        and not any(flag for flag, in b.rows('formation_report','default_fleet'))),
    'toggle_monopoly':(None,lambda a,b,p,n:((p['building_type'],) in a.rows('player_monopoly','building_type'))
                       !=((p['building_type'],) in b.rows('player_monopoly','building_type'))),
    'character_interaction':('character',lambda a,b,p,n:interaction_state(a,p[n])!=interaction_state(b,p[n]) or None),
    'start_play_confirmed':(None,lambda a,b,p,n:bool(new_plays(a,b,p['diplomatic_play_type'],p['country'])) or (b.player,p['country']) in subject_pairs(b)-subject_pairs(a)),
    'diplomatic_action_state':('country',lambda a,b,p,n:player_claims(a)!=player_claims(b) if p['diplomatic_action']=='da_stake_colonial_claim'
                               else value(a,'state','country',p['state'])!=value(b,'state','country',p['state'])),
    'diplomatic_action_obligation':('country',lambda a,b,p,n:obligations_with(a,p[n])!=obligations_with(b,p[n]) or diplomatic_effect(a,b,p,n)),
    'diplomatic_action':('country',lambda a,b,p,n:(p[n],'of_player') in set(b.rows('player_diplomat_expulsion','country,direction'))
                         if p['diplomatic_action']=='expel_diplomats' else diplomatic_effect(a,b,p,n)),
    'make_primary_demand':(None,lambda a,b,p,n:maneuvers(b,p['diplomatic_play'])<maneuvers(a,p['diplomatic_play'])),
    'toggle_pause_colonization':('state',lambda a,b,p,n:((p[n],) in a.rows('player_colonization_paused','state'))!=((p[n],) in b.rows('player_colonization_paused','state'))),
    'set_default_unit_type':('military_formation',becomes(lambda s,p,n:p['combat_unit_type'] in members(s,'formation_selected_unit_type',p[n],'combat_unit_type'),lambda p:True)),
    'toggle_ignore_formable':(None,lambda a,b,p,n:ignoring(a,p['index'])!=ignoring(b,formable_ord(b,a,p['index']))),
    'release_country':(None,lambda a,b,p,n:bool(released(a,b))),
    'form_country':(None,lambda a,b,p,n:value(a,'country','country_definition',a.player)!=value(b,'country','country_definition',b.player)),
    'toggle_ignore_decision':(None,lambda a,b,p,n:((p['decision'],) in a.rows('player_ignored_decision','decision'))
                              !=((p['decision'],) in b.rows('player_ignored_decision','decision'))),
    'rehome_formation':('military_formation',lambda a,b,p,n:(home_region(a,p[n])!=p['strategic_region'] and home_region(b,p[n])==p['strategic_region'])
                        or (not value(a,'formation_private','travel_distance',p[n]) and bool(value(b,'formation_private','travel_distance',p[n])))),
    'cancel_queue_item':(None,lambda a,b,p,n:queue(b).count((p['state'],p['building_type']))<queue(a).count((p['state'],p['building_type']))),
    'raise_queue_item':(None,moved(lambda index,rest:index-1)),
    'lower_queue_item':(None,moved(lambda index,rest:index+1)),
    'first_queue_item':(None,moved(lambda index,rest:0)),
    'last_queue_item':(None,moved(lambda index,rest:rest)),
    **{f'set_{direction}_{kind}':(None,becomes(lambda s,p,n,direction=direction:trade_level(s,direction,p['goods']),lambda p,kind=kind:TARIFF_CODES[kind][p['level']]))
       for direction in ('import','export') for kind in ('tariff','subvention')},
    'pause':(None,lambda a,b,p,n:hours(b)==hours(a) and b.meta['paused'] is True),
    'unpause':(None,lambda a,b,p,n:hours(b)>hours(a)),
    'set_speed':(None,lambda a,b,p,n:None),
    **{name:('diplomatic_play',lambda a,b,p,n:side(a,p[n])!=side(b,p[n])) for name in ('support_initiator','support_target')},
    'stay_on_fence':('diplomatic_play',lambda a,b,p,n:len(set(a.rows('player_proposal','country,kind')))>len(set(b.rows('player_proposal','country,kind')))
                     and not roles(b,p[n])&{'initiator_ally','target_ally'}),
    'declare_neutrality':('diplomatic_play',lambda a,b,p,n:'interested' in roles(a,p[n]) and 'interested' not in roles(b,p[n])),
    **{f'lean_{side}':('diplomatic_play',lambda a,b,p,n,side=side:f'{side}_ally' not in roles(a,p[n]) and f'{side}_ally' in roles(b,p[n])) for side in ('initiator','target')},
    'back_down':('diplomatic_play',lambda a,b,p,n:value(a,'diplomatic_play','end_date',p[n])!=value(b,'diplomatic_play','end_date',p[n])),
    'add_war_goal':(None,lambda a,b,p,n:held_goals(b,p['diplomatic_play'])>held_goals(a,p['diplomatic_play'])),
    'toggle_press_war_goal':(None,lambda a,b,p,n:goal_status(a,p)!=goal_status(b,p)),
    'mobilize':('military_formation',lambda a,b,p,n:mobilized(a).get(p[n]) is False and mobilized(b).get(p[n]) is True),
    'demobilize':('military_formation',lambda a,b,p,n:mobilized(a).get(p[n]) is True and mobilized(b).get(p[n]) is False),
    'mobilize_all':(None,lambda a,b,p,n:sum(mobilized(b).values())>sum(mobilized(a).values())),
    'demobilize_all':(None,lambda a,b,p,n:sum(mobilized(b).values())<sum(mobilized(a).values())),
    'stop_institution_change':('institution',lambda a,b,p,n:bool(value(a,'institution_private','growth',p[n])) and not value(b,'institution_private','growth',p[n])),
    'white_peace':('war',lambda a,b,p,n:pressed_in(a,p[n]) and not pressed_in(b,p[n])),
    'propose_peace':('war',lambda a,b,p,n:value(a,'war','peace_proposer',p[n])!=a.player and value(b,'war','peace_proposer',p[n])==b.player),
    'recruit':('military_formation',lambda a,b,p,n:units(b,p[n],p['combat_unit_type'])>units(a,p[n],p['combat_unit_type'])),
    'disband_regulars':('military_formation',lambda a,b,p,n:units(b,p[n],p['combat_unit_type'])<units(a,p[n],p['combat_unit_type'])),
    'disband_conscripts':('military_formation',lambda a,b,p,n:units(b,p[n],p['combat_unit_type'])<units(a,p[n],p['combat_unit_type'])),
    'colonize':(None,lambda a,b,p,n:bool(set(colonies(b))-set(colonies(a)))),
    'impose_law':('law',lambda a,b,p,n:value(a,'law','imposer',p[n])!=a.player and value(b,'law','imposer',p[n])==b.player),
    'repeal_amendment':('amendment',lambda a,b,p,n:p[n] in {item for item, in a.rows('law_amendment','amendment')}
                        and p[n] not in {item for item, in b.rows('law_amendment','amendment')}),
    'pick_principle':(None,becomes(lambda s,p,n:p['power_bloc_principle'] in {kind for kind, in s.rows('power_bloc_adopted_principle','power_bloc_principle')},lambda p:True)),
    'upgrade_principle':(None,lambda a,b,p,n:bloc_principles(a)!=bloc_principles(b)),
    'request_join_power_bloc':(None,lambda a,b,p,n:value(a,'country','power_bloc',a.player)!=value(b,'country','power_bloc',b.player)
                               or set(a.rows('player_relation','country,relations'))!=set(b.rows('player_relation','country,relations'))),
    'negotiate':(None,lambda a,b,p,n:not metric(a,'IsNegotiating') and bool(metric(b,'IsNegotiating'))),
    'take_decision':(None,lambda a,b,p,n:(p['decision'],) in a.rows('player_decision','decision') and (p['decision'],) not in b.rows('player_decision','decision')),
    'press_journal_button':(None,lambda a,b,p,n:a.hours==b.hours and country_state(a)!=country_state(b) or button_hidden(a,b,p)),
    'declare_bankruptcy':(None,lambda a,b,p,n:in_default(a) and not in_default(b)),
    'design_ship_template':(None,more('ship_template',True)),
    'edit_ship_template':(None,lambda a,b,p,n:(template:=own_templates(a).get((p['ship_type'],p['index']))) is not None
                          and p['ship_modification'] not in latest_design(a,template) and p['ship_modification'] in latest_design(b,template)),
    'set_default_ship_template':(None,lambda a,b,p,n:not template_flags(a,p)&1 and template_flags(b,p)&1),
    'set_fleet_ship_template':(None,lambda a,b,p,n:(own_templates(a).get((p['ship_type'],p['index'])),p['military_formation']) not in set(a.rows('ship_template_fleet','ship_template,fleet'))
                               and (own_templates(b).get((p['ship_type'],p['index'])),p['military_formation']) in set(b.rows('ship_template_fleet','ship_template,fleet'))),
    'delete_ship_template':(None,lambda a,b,p,n:own_templates(a).get((p['ship_type'],p['index'])) is not None and own_templates(a)[p['ship_type'],p['index']] not in own_templates(b).values()),
    'retrofit_fleet':('military_formation',equals('formation_report','retrofitting',True)),
    'cancel_retrofit_fleet':('military_formation',equals('formation_report','retrofitting',False)),
    'retrofit_all':(None,lambda a,b,p,n:retrofitting_fleets(a)<retrofitting_fleets(b)),
    'cancel_retrofit_all':(None,lambda a,b,p,n:retrofitting_fleets(a)>retrofitting_fleets(b)),
    'set_strait_toll':('strait',strait_becomes('toll_rate',lambda p:TOLL_LEVELS.index(p['level']))),
    'set_strait_access':('strait',strait_becomes('access_status',lambda p:ACCESS_STATUSES.index(p['access']))),
    'set_strait_allowed':('strait',strait_becomes('access_permissions',lambda p:ACCESS_PERMISSIONS.index(p['allowed'])+1)),
    'build_ship_for':(None,lambda a,b,p,n:my_ships(b).count(p['ship_type'])>my_ships(a).count(p['ship_type'])),
    'capitulate':('war',lambda a,b,p,n:(a.player,) in a.rows('war_participant','country',war=p[n]) and (b.player,) not in b.rows('war_participant','country',war=p[n])),
    'toggle_accept_peace':('war',lambda a,b,p,n:value(a,'war','peace_proposer',p[n]) not in (None,a.player)
                           and (a.player,) in a.rows('war_participant','country',war=p[n]) and (b.player,) not in b.rows('war_participant','country',war=p[n])),
    'kick_from_power_bloc':('country',changed('country','power_bloc')),
    'reform_government':('interest_group',changed('interest_group','in_government')),
    'form_power_bloc':(None,lambda a,b,p,n:value(a,'country','power_bloc',a.player) is None and value(b,'country','power_bloc',b.player) is not None),
    'leave_power_bloc':(None,lambda a,b,p,n:value(a,'country','power_bloc',a.player) is not None and value(b,'country','power_bloc',b.player) is None),
    'abandon_colony':('state',lambda a,b,p,n:value(b,'state_status','colony_progress',p[n])!=value(a,'state_status','colony_progress',p[n])
                      or value(b,'state','country',p[n])!=b.player),
    **{f'{verb}_{kind}':('country',lambda a,b,p,n,kind=kind:proposing(a,p[n],None if kind=='proposal' else kind) and not proposing(b,p[n],None if kind=='proposal' else kind))
       for kind in ('treaty','demand','action_proposal','sway','proposal') for verb in ('accept','decline','reject','quick_decline')
       if f'{verb}_{kind}' in {'accept_treaty','decline_treaty','accept_demand','reject_demand','accept_action_proposal','decline_action_proposal','accept_sway',
                               'reject_sway','quick_decline_proposal'}},
    'set_borrow_setting':('military_formation',lambda a,b,p,n:not borrowed(a,p[n],p['index']) and borrowed(b,p[n],p['index'])),
    'cancel_strategic_objective_selected':('military_formation',lambda a,b,p,n:objective(a,p[n])==p['state']&SLOT and objective(b,p[n])!=p['state']&SLOT),
    'set_strategic_objective':('military_formation',becomes(lambda s,p,n:objective(s,p[n]),lambda p:p['state']&SLOT)),
    'station_formation':('military_formation',becomes(lambda s,p,n:value(s,'formation_status','target_location',p[n]),lambda p:p['state'])),
    'choose_event_option':(None,lambda a,b,p,n:p['event'] in {kind for kind, in a.rows('event','event_type')} and p['event'] not in {kind for kind, in b.rows('event','event_type')}),
}


def ship_positions(snapshot):
    queues={ident for ident, in snapshot.rows('ship_queue','ship_queue',country=snapshot.player)}
    return {ident:index for ident,index,queue in snapshot.rows('ship_construction','ship_construction,list_index,queue') if queue in queues}


def ship_moved(a,b,index,goal):
    before,after=ship_positions(a),ship_positions(b)
    item=next((ident for ident,position in before.items() if position==index),None)
    if goal is None:
        return item is not None and item not in after
    return item in after and after[item]==goal(index,max(after.values()))


EFFECTS.update({**{f'{name}_selected':EFFECTS[name] for name in ('mobilize','demobilize','raise_conscripts')},'deploy_selected_to_front':EFFECTS['deploy_to_front'],
                **{f'{verb}_ship_item':(None,lambda a,b,p,n,goal=goal:ship_moved(a,b,p['index'],goal)) for verb,goal in
                   (('raise',lambda i,last:i-1),('lower',lambda i,last:i+1),('first',lambda i,last:0),('last',lambda i,last:last),('cancel',None))},
                'defend_invasion':EFFECTS['deploy_to_front'],
                'recall_fleet':('military_formation',equals('formation_report','recalled',True)),
                'set_formation_flag':('military_formation',becomes(lambda s,p,n:value(s,'formation','flag',p[n]),lambda p:p['flag'])),
                'station_selected':('military_formation',changed('formation_status','target_location'))})


def verify(name,params,before,after):
    if name in EFFECTS:
        owner,test=EFFECTS[name]
        verdict=test(before,after,params,owner)
        return None if verdict is None else bool(verdict)
    return None
