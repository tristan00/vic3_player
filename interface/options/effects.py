from ..actions.catalogue import ACCESS_PERMISSIONS, ACCESS_STATUSES, LEVELS, TOLL_LEVELS
from ..common import timed_often
from .available import (SLOT, TARIFF_CODES, armies, bloc_principles, changing, colonies, construction_paused, construction_queue, cooling, diplomatic_possible,
                        enacting_laws, event_options, formation_report, formation_setting, home_region, in_default, in_force, incorporation, involved, issued_decrees, latest_design,
                        leaning, metric, monopolies, own_templates, ownership_classes, play_members, player_blocs, player_value, power_bloc_members, principal, private_levels,
                        privatization_requested, queued_buildings, recruitable, selected_units, setting, ship_paused, ship_queues, state_regions, strait_sides, strait_value,
                        definition, journal_button, shown_buttons, pact_terms,
                        technologies, trade_level)


@timed_often
def levels(s):
    return {ident:count for ident,_,count in s.buildings()}


@timed_often
def methods(s):
    return {ident:set(active) for ident,active in s.grouped('building_production_method_active','building,production_method').items()}


@timed_often
def place(s,state,building_type):
    queue=construction_queue(s)
    return queue.index((state,building_type)) if (state,building_type) in queue else None


@timed_often
def queued_last(b,a,state,building_type):
    queue=construction_queue(a)
    previous=[item for item in construction_queue(b) if item in queue]
    item=(state,building_type)
    return item in previous and queue.index(item)==max(queue.index(other) for other in previous)


@timed_often
def members(s,building_type,state,ownership):
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    return [ident for ident,kind,_ in s.buildings() if kind==building_type and located.get(ident)==state and (ownership=='any' or ownership in classes.get(ident,()))]


@timed_often
def subsidy(s):
    return s.map('building','building,subsidized')


@timed_often
def privately_held(s,group):
    held=private_levels(s)
    return sum(held.get(ident,0) for ident in group)


@timed_often
def policy(column):
    return lambda b,a,level:player_value(a,'player_policy',column)==LEVELS.index(level)


@timed_often
def trade(direction,kind):
    return lambda b,a,goods,level:trade_level(a,direction,goods)==TARIFF_CODES[kind][level]


@timed_often
def taxed(s):
    return {goods for goods, in s.rows('player_taxed_goods','goods')}


@timed_often
def strait_side(s,strait,state=None):
    return [side for owned,side,held in strait_sides(s) if owned==strait and state in (None,held)]


@timed_often
def managed(s,movement):
    return s.map('political_movement','political_movement,managed_status').get(movement)


@timed_often
def governing(s,group):
    return bool(s.map('interest_group','interest_group,in_government').get(group))


@timed_often
def between(s,country,kind):
    return {ident for ident,first,second,found in s.rows('pact','pact,first_country,second_country,pact_type') if found==kind and {first,second}=={s.player,country}}


@timed_often
def joined(b,a,country,diplomatic_action,**picked):
    reverse=definition(b,'common/diplomatic_actions',diplomatic_action,'reverse_pact')
    diplomatic_action=reverse[0] if reverse else diplomatic_action
    return bool(between(a,country,diplomatic_action)-between(b,country,diplomatic_action))


@timed_often
def acted(b,a,country,diplomatic_action,**picked):
    return (joined(b,a,country,diplomatic_action)
            or (country,diplomatic_action) in diplomatic_possible(b) and (country,diplomatic_action) not in diplomatic_possible(a))


@timed_often
def broken(b,a,country,diplomatic_action):
    two_sided=pact_terms()[diplomatic_action][2] is not None
    ours={ident for ident,first,second,kind in b.rows('pact','pact,first_country,second_country,pact_type')
          if kind==diplomatic_action and (first==b.player and second==country or two_sided and first==country and second==b.player)}
    return bool(ours) and not ours&between(a,country,diplomatic_action)


@timed_often
def pressed_journal(b,a,journal_entry,button):
    picked=journal_button(b,journal_entry,button)
    if picked is None:
        return False
    entry,name=picked
    if name in ('je_government_petition_go_away_button','negotiation_go_away_button'):
        return name not in shown_buttons(a,entry)
    if name=='caudillo_decree_button':
        return bool(a.rows('country_timed_modifier','modifier',country=a.player,modifier='caudillo_rule_by_decree_modifier'))
    return False


@timed_often
def owner(s,state):
    return s.map('state','state,country').get(state)


@timed_often
def articles(s):
    return set(s.rows('treaty_article','treaty,treaty_article_type,source_country,target_country'))


@timed_often
def drafted(b,a,country,article,givers):
    sides={'us':(a.player,country),'them':(country,a.player),'both':(None,None)}[givers]
    signers={treaty:{first,second} for treaty,first,second in a.rows('treaty','treaty,first_country,second_country')}
    return any(kind==article and (source,target)==sides and signers.get(treaty)=={a.player,country} for treaty,kind,source,target in articles(a)-articles(b))


@timed_often
def proposal(givers):
    return lambda b,a,country,treaty_article,**inputs:drafted(b,a,country,treaty_article,givers)


@timed_often
def parties(s,treaty):
    return next(((first,second) for ident,first,second in s.rows('treaty','treaty,first_country,second_country') if ident==treaty),None)


@timed_often
def other(s,treaty):
    pair=parties(s,treaty)
    return None if pair is None else pair[1] if pair[0]==s.player else pair[0]


@timed_often
def amended(givers):
    return lambda b,a,treaty,treaty_article:drafted(b,a,other(b,treaty),treaty_article,givers)


@timed_often
def redrafted(b,a,treaty,treaty_article):
    pair=parties(b,treaty)
    known={ident for ident, in b.rows('treaty','treaty')}
    return any(ident not in known and {first,second}==set(pair) for ident,first,second in a.rows('treaty','treaty,first_country,second_country'))


@timed_often
def answered(kind):
    return lambda b,a,country:not a.rows('player_proposal','country',country=country,kind=kind)


@timed_often
def plays(s):
    return {ident:(initiator,target,kind) for ident,initiator,target,kind in s.rows('diplomatic_play','diplomatic_play,initiator,target,diplomatic_play_type')}


@timed_often
def started(b,a,target,diplomatic_play_type):
    return any(ident not in plays(b) and row==(a.player,target,diplomatic_play_type) for ident,row in plays(a).items())


@timed_often
def goals(s):
    return set(s.rows('war_goal','diplomatic_play,war_goal_type,holder,target_country,target_state'))


@timed_often
def demanded(b,a,diplomatic_play,war_goal_type,holder=None,country=None,state=None,**inputs):
    return any(play==diplomatic_play and kind==war_goal_type and keeper==(a.player if holder is None else holder) and (country is None or target==country) and (state is None or spot==state)
               for play,kind,keeper,target,spot in goals(a)-goals(b))


@timed_often
def pressed(s,diplomatic_play,war_goal_type,country):
    return next(((pressing,demand) for play,kind,holder,target,pressing,demand in s.rows('war_goal','diplomatic_play,war_goal_type,holder,target_country,pressed,demand_type')
                 if (play,kind,holder,target)==(diplomatic_play,war_goal_type,s.player,country)),None)


@timed_often
def maneuvers(s,play):
    row=next(((initiator,ours,theirs) for ident,initiator,ours,theirs in s.rows('diplomatic_play','diplomatic_play,initiator,initiator_maneuvers,target_maneuvers') if ident==play),None)
    return None if row is None else row[1] if row[0]==s.player else row[2]


@timed_often
def swayed(b,a,diplomatic_play,country,**offer):
    return maneuvers(a,diplomatic_play) is not None and maneuvers(b,diplomatic_play) is not None and maneuvers(a,diplomatic_play)<maneuvers(b,diplomatic_play)


@timed_often
def companies(s):
    return {kind for kind, in s.rows('company','company_type',country=s.player)}


@timed_often
def ignored(s):
    return {name for name, in s.rows('player_ignored_decision','decision')}


@timed_often
def units(s,formation,combat_unit_type=None):
    return [unit for unit,kind in s.rows('combat_unit','combat_unit,combat_unit_type',formation=formation) if combat_unit_type in (None,kind)]


@timed_often
def raised(s,kind):
    return [ident for ident, in s.rows('formation','formation',country=s.player,formation_type=kind,dead=False)]


@timed_often
def standing(s,formation):
    return formation in armies(s,True) and not formation_report(s,formation,'demobilizing')


@timed_often
def mobilizing(s,formation):
    return formation in armies(s,True) or any(progress for progress, in s.rows('combat_unit','mobilization',formation=formation))


@timed_often
def ships(s,fleet):
    return [ship for ship, in s.rows('ship','ship',fleet=fleet)]


@timed_often
def heading(s,formation):
    return {s.map('formation_status','formation,target_location').get(formation),s.map('formation_status','formation,current_location').get(formation)}


@timed_often
def options(s,formation):
    return set(s.grouped('formation_mobilization_option','formation,mobilization_option').get(formation,()))


@timed_often
def upgrading(s):
    return set(s.rows('formation_upgrade_unit_type','formation,combat_unit_type'))


@timed_often
def mission(s,fleet):
    return s.map('naval_mission','naval_mission,naval_mission_type').get(s.map('formation_status','formation,naval_mission').get(fleet))


@timed_often
def orders(s):
    queues=ship_queues(s)
    return {ident:index for ident,index,queue in s.rows('ship_construction','ship_construction,list_index,queue') if queue in queues}


@timed_often
def order(s,index):
    return next((ident for ident,position in orders(s).items() if position==index),None)


@timed_often
def moved(compare):
    return lambda b,a,index:order(b,index) in orders(a) and compare(orders(a)[order(b,index)],index,orders(a).values())


@timed_often
def template(s,ship_type,index):
    return own_templates(s).get((ship_type,index))


@timed_often
def designs(s,ship_type):
    return [found for (kind,_),found in own_templates(s).items() if kind==ship_type]


@timed_often
def charters(s):
    return sorted(s.rows('charter','company,company_charter_type'))


@timed_often
def granted(b,a,company,charter,**place):
    return charters(a).count((company,charter))>charters(b).count((company,charter))


@timed_often
def revoked(b,a,company,charter,**place):
    return charters(a).count((company,charter))<charters(b).count((company,charter))


@timed_often
def post(s,character,column):
    return s.map('character','character,'+column).get(character)


@timed_often
def figure(s,character):
    return (s.rows('character','noble,country,interest_group,ideology,order_type,rank,formation,assigned_state',character=character),
            sorted(s.rows('character_assigned_role','character_role',character=character)),sorted(s.rows('character_assigned_trait','character_trait',character=character)),
            sorted(s.rows('character_timed_modifier','modifier',character=character)))


@timed_often
def queued(s,building_type,state):
    return (state,building_type) in construction_queue(s)


EFFECTS={
    'build':lambda b,a,state,building_type:(state,building_type) in construction_queue(a),
    'cancel_construction':lambda b,a,building:building not in queued_buildings(a),
    'downsize':lambda b,a,building:levels(a).get(building,0)<levels(b).get(building,0),
    'pause_construction':lambda b,a:construction_paused(a),
    'pause_all_construction':lambda b,a:construction_paused(a),
    'resume_construction':lambda b,a:not construction_paused(a),
    'resume_all_construction':lambda b,a:not construction_paused(a),
    'pause_construction_output':lambda b,a,building:bool(setting(a,building,'output_paused')),
    'resume_construction_output':lambda b,a,building:not setting(a,building,'output_paused'),
    'cancel_queue_item':lambda b,a,state,building_type:place(a,state,building_type) is None,
    'raise_queue_item':lambda b,a,state,building_type:place(a,state,building_type) is not None and place(a,state,building_type)<place(b,state,building_type),
    'first_queue_item':lambda b,a,state,building_type:place(a,state,building_type)==0,
    'lower_queue_item':lambda b,a,state,building_type:place(a,state,building_type) is not None and place(a,state,building_type)>place(b,state,building_type),
    'last_queue_item':queued_last,
    'nationalize':lambda b,a,building,levels:private_levels(a).get(building,0)<=private_levels(b).get(building,0)-levels,
    'toggle_privatization':lambda b,a,building:privatization_requested(a,building)!=privatization_requested(b,building),
    'toggle_monopoly':lambda b,a,building_type:(building_type in monopolies(a))!=(building_type in monopolies(b)),
    'subsidies_on':lambda b,a,building:bool(subsidy(a).get(building)),
    'subsidies_off':lambda b,a,building:not subsidy(a).get(building),
    'subset_subsidies_on_state':lambda b,a,building_type,state,ownership:bool(members(b,building_type,state,ownership)) and all(subsidy(a).get(i) for i in members(b,building_type,state,ownership)),
    'subset_subsidies_off_state':lambda b,a,building_type,state,ownership:not any(subsidy(a).get(i) for i in members(b,building_type,state,ownership)),
    'bulk_nationalize_state':lambda b,a,building_type,state,ownership:privately_held(a,members(b,building_type,state,ownership))<privately_held(b,members(b,building_type,state,ownership)),
    'bulk_expropriate_state':lambda b,a,building_type,state,ownership:privately_held(a,members(b,building_type,state,ownership))<privately_held(b,members(b,building_type,state,ownership)),
    'bulk_switch_production_method_state':lambda b,a,building_type,state,production_method,ownership:any(
        production_method in methods(a).get(i,()) and production_method not in methods(b).get(i,()) for i in members(b,building_type,state,ownership)),
    'switch_production_method':lambda b,a,building,production_method:production_method in methods(a).get(building,()),
    'reset_building_production_methods':lambda b,a,building:methods(a).get(building)!=methods(b).get(building),
    'reset_production_methods':lambda b,a,state:any(methods(a).get(ident)!=methods(b).get(ident) for ident,where in b.map('building','building,state').items() if where==state),
    'move_capital':lambda b,a,state:a.map('country','country,capital').get(a.player)==state,
    'move_market_capital':lambda b,a,state:a.map('country','country,market_capital').get(a.player)==state,
    'colonize':lambda b,a,state:len(colonies(a))>len(colonies(b)),
    'toggle_pause_colonization':lambda b,a,state:bool(a.rows('player_colonization_paused','state',state=state))!=bool(b.rows('player_colonization_paused','state',state=state)),
    'abandon_colony':lambda b,a,state:state not in colonies(a),
    'incorporate':lambda b,a,state:incorporation(a).get(state)!=incorporation(b).get(state),
    'unincorporate':lambda b,a,state:incorporation(a).get(state)==0,
    'set_tax_level':policy('tax_level'),
    'set_government_wages':policy('government_wage_level'),
    'set_military_wages':policy('military_wage_level'),
    'set_supply_ship_construction':policy('supply_ship_construction_level'),
    'toggle_consumption_tax':lambda b,a,goods:(goods in taxed(a))!=(goods in taxed(b)),
    'set_import_tariff':trade('import','tariff'),
    'set_export_tariff':trade('export','tariff'),
    'set_import_subvention':trade('import','subvention'),
    'set_export_subvention':trade('export','subvention'),
    'declare_bankruptcy':lambda b,a:not in_default(a),
    'set_strait_toll':lambda b,a,strait,level:any(strait_value(a,strait,f'{side}_toll_rate')==TOLL_LEVELS.index(level) for side in strait_side(a,strait)),
    'set_strait_access':lambda b,a,strait,state,access:any(strait_value(a,strait,f'{side}_access_status')==ACCESS_STATUSES.index(access) for side in strait_side(a,strait,state)),
    'set_strait_allowed':lambda b,a,strait,state,allowed:any(strait_value(a,strait,f'{side}_access_permissions')==ACCESS_PERMISSIONS.index(allowed)+1 for side in strait_side(a,strait,state)),
    'enact_law':lambda b,a,law:law in enacting_laws(a),
    'cancel_enactment':lambda b,a:not enacting_laws(a),
    'impose_law':lambda b,a,law:a.map('law','law,imposer').get(law) is not None,
    'repeal_amendment':lambda b,a,amendment:not a.rows('amendment','amendment',amendment=amendment),
    'toggle_bolster_movement':lambda b,a,political_movement:managed(a,political_movement)!=managed(b,political_movement),
    'toggle_suppress_movement':lambda b,a,political_movement:managed(a,political_movement)!=managed(b,political_movement),
    'negotiate':lambda b,a,interest_group:bool(a.map('interest_group_private','interest_group,negotiated').get(interest_group)) or bool(metric(a,'IsNegotiating')),
    'reform_government':lambda b,a,interest_group,mode:governing(a,interest_group)!=governing(b,interest_group),
    'reform_government_party':lambda b,a,member,mode:governing(a,member)!=governing(b,member),
    'set_institution_level':lambda b,a,institution,level:level in (a.map('institution','institution,investment').get(institution),changing(a).get(institution)),
    'stop_institution_change':lambda b,a,institution:institution not in changing(a),
    'issue_decree':lambda b,a,state,decree:(state,decree) in issued_decrees(a),
    'remove_decree':lambda b,a,state,decree:(state,decree) not in issued_decrees(a),
    'research':lambda b,a,technology:technology in technologies(a)[2],
    'queue_research':lambda b,a,technology:technology in technologies(a)[1],
    'dequeue_research':lambda b,a,technology:technology not in technologies(a)[1],
    'diplomatic_action':acted,
    'diplomatic_action_obligation':lambda b,a,country,diplomatic_action,obligation:acted(b,a,country,diplomatic_action),
    'diplomatic_action_first_state':lambda b,a,country,diplomatic_action,state,obligation:acted(b,a,country,diplomatic_action),
    'diplomatic_action_second_state':lambda b,a,country,diplomatic_action,state,obligation:acted(b,a,country,diplomatic_action),
    'diplomatic_action_states':lambda b,a,country,diplomatic_action,given,taken,obligation:acted(b,a,country,diplomatic_action),
    **{f'offer_{kind}treaty_article':proposal('us') for kind in ('','goods_','state_','region_','law_','subject_','ship_','monopoly_','money_','goods_amount_','timed_','obliged_')},
    **{f'demand_{kind}treaty_article':proposal('them') for kind in ('','goods_','state_','region_','law_','subject_','ship_','monopoly_','money_','goods_amount_','timed_','obliged_')},
    **{f'agree_{kind}treaty_article':proposal('both') for kind in ('','timed_','obliged_')},
    'threaten_treaty_article':proposal('them'),
    'work_out_treaty_article':proposal('them'),
    'exchange_treaty_articles':lambda b,a,country,treaty_article,demand:drafted(b,a,country,treaty_article,'us') and drafted(b,a,country,demand,'them'),
    'amend_offer_treaty_article':amended('us'),
    'amend_demand_treaty_article':amended('them'),
    'amend_agree_treaty_article':amended('both'),
    'amend_drop_offer_treaty_article':redrafted,
    'amend_drop_demand_treaty_article':redrafted,
    'amend_drop_agree_treaty_article':redrafted,
    'withdraw_treaty':lambda b,a,treaty:treaty not in in_force(a),
    'accept_treaty':answered('treaty'),
    'decline_treaty':answered('treaty'),
    'accept_demand':answered('demand'),
    'reject_demand':answered('demand'),
    'accept_action_proposal':answered('action_proposal'),
    'decline_action_proposal':answered('action_proposal'),
    'accept_sway':answered('sway'),
    'reject_sway':answered('sway'),
    'quick_decline_proposal':lambda b,a,country:not a.rows('player_proposal','country',country=country),
    'form_power_bloc':lambda b,a,power_bloc_identity,power_bloc_principle:bool(player_blocs(a)) and not player_blocs(b),
    'request_join_power_bloc':lambda b,a,power_bloc:player_blocs(a)=={power_bloc},
    'kick_from_power_bloc':lambda b,a,country:country not in power_bloc_members(a),
    'leave_power_bloc':lambda b,a:not player_blocs(a),
    'pick_principle':lambda b,a,slot,power_bloc_principle:power_bloc_principle in bloc_principles(a),
    'replace_principle':lambda b,a,slot,power_bloc_principle:power_bloc_principle in bloc_principles(a),
    'upgrade_principle':lambda b,a,power_bloc_principle:power_bloc_principle not in bloc_principles(a) and len(bloc_principles(a))==len(bloc_principles(b)),
    'break_pact':broken,
    'start_play_country':lambda b,a,country,diplomatic_play_type:started(b,a,country,diplomatic_play_type),
    'start_play_confirmed':lambda b,a,country,diplomatic_play_type,mode:started(b,a,country,diplomatic_play_type),
    'start_play_liberation':lambda b,a,country,country_definition,diplomatic_play_type:started(b,a,country,diplomatic_play_type),
    'start_play_state':lambda b,a,state,diplomatic_play_type:started(b,a,b.map('state','state,country').get(state),diplomatic_play_type),
    'support_initiator':lambda b,a,diplomatic_play:a.player in play_members(a).get((diplomatic_play,0),set()),
    'support_target':lambda b,a,diplomatic_play:a.player in play_members(a).get((diplomatic_play,1),set()),
    'lean_initiator':lambda b,a,diplomatic_play:diplomatic_play in leaning(a,'initiator'),
    'lean_target':lambda b,a,diplomatic_play:diplomatic_play in leaning(a,'target'),
    'stay_on_fence':lambda b,a,diplomatic_play:diplomatic_play not in leaning(a,'initiator')|leaning(a,'target'),
    'declare_neutrality':lambda b,a,diplomatic_play:diplomatic_play not in involved(a)[1],
    'back_down':lambda b,a,diplomatic_play:diplomatic_play not in principal(a),
    'toggle_press_war_goal':lambda b,a,diplomatic_play,war_goal_type,country:pressed(a,diplomatic_play,war_goal_type,country) is not None
                            and pressed(a,diplomatic_play,war_goal_type,country)[0]!=pressed(b,diplomatic_play,war_goal_type,country)[0],
    'make_primary_demand':lambda b,a,diplomatic_play,war_goal_type,country:pressed(a,diplomatic_play,war_goal_type,country) is not None
                          and pressed(a,diplomatic_play,war_goal_type,country)[1]!=pressed(b,diplomatic_play,war_goal_type,country)[1],
    **{name:swayed for name in ('offer_sway','offer_sway_ally','offer_sway_state','offer_sway_subject','offer_sway_pact','offer_sway_subjection','offer_sway_goal_country',
                                'offer_sway_goal_state','offer_sway_goods_article','offer_sway_state_article','offer_sway_region_article','offer_sway_law_article')},
    'add_war_goal_country':demanded,
    'add_war_goal_state':demanded,
    'add_war_goal_liberation':lambda b,a,diplomatic_play,war_goal_type,country,country_definition:demanded(b,a,diplomatic_play,war_goal_type,country=country),
    **{name:(lambda b,a,diplomatic_play,war_goal_type,country,treaty_article,**inputs:demanded(b,a,diplomatic_play,war_goal_type,country=country))
       for name in ('add_war_goal_article','add_goods_war_goal','add_state_war_goal','add_region_war_goal','add_law_war_goal')},
    'propose_peace':lambda b,a,war:a.map('war','war,peace_proposer').get(war)==a.player,
    'white_peace':lambda b,a,war:a.map('war','war,peace_proposer').get(war)==a.player,
    'capitulate':lambda b,a,war:war not in a.wars(),
    'create_company':lambda b,a,company_type:company_type in companies(a) and company_type not in companies(b),
    'remove_company':lambda b,a,company_type:company_type not in companies(a),
    'choose_event_option':lambda b,a,event,option:event not in {combo['event'] for combo in event_options(a)},
    'take_decision':lambda b,a,decision:a.map('player_decision','decision,takeable').get(decision) is not True,
    'toggle_ignore_decision':lambda b,a,decision:(decision in ignored(a))!=(decision in ignored(b)),
    'recruit':lambda b,a,building,military_formation,combat_unit_type:queued(a,'building_barrack',b.map('building','building,state').get(building)),
    'recruit_from_formation':lambda b,a,military_formation,combat_unit_type,state:queued(a,'building_barrack',state),
    'activate_conscription_center':lambda b,a,military_formation,combat_unit_type,state:queued(a,'building_conscription_center',state),
    **{name:(lambda b,a,military_formation:mobilizing(a,military_formation)) for name in ('mobilize','mobilize_selected')},
    **{name:(lambda b,a,military_formation:not standing(a,military_formation)) for name in ('demobilize','demobilize_selected')},
    **{name:(lambda b,a,military_formation:bool(a.map('formation_status','formation,raised_conscripts').get(military_formation))) for name in ('raise_conscripts','raise_conscripts_selected')},
    'mobilize_all':lambda b,a:len(armies(a,True))>len(armies(b,True)),
    'demobilize_all':lambda b,a:not any(standing(a,formation) for formation in armies(b,True)),
    'disband_formation':lambda b,a,military_formation:military_formation not in raised(a,0)+raised(a,1),
    'toggle_mobilization_option':lambda b,a,military_formation,mobilization_option:(mobilization_option in options(a,military_formation))!=(mobilization_option in options(b,military_formation)),
    'set_supply_priority':lambda b,a,military_formation,level:a.map('formation','formation,supply_priority').get(military_formation)==('low','medium','high').index(level),
    'disband_regulars':lambda b,a,military_formation,combat_unit_type:len(units(a,military_formation,combat_unit_type))<len(units(b,military_formation,combat_unit_type)),
    'disband_conscripts':lambda b,a,military_formation,combat_unit_type:len(units(a,military_formation,combat_unit_type))<len(units(b,military_formation,combat_unit_type)),
    'upgrade_regulars':lambda b,a,military_formation,combat_unit_type:(military_formation,combat_unit_type) in upgrading(a),
    'upgrade_conscripts':lambda b,a,military_formation,combat_unit_type:(military_formation,combat_unit_type) in upgrading(a),
    'upgrade_all_units':lambda b,a:len(upgrading(a))>len(upgrading(b)),
    'set_default_unit_type':lambda b,a,military_formation,combat_unit_type:combat_unit_type in selected_units(a,military_formation).values(),
    'station_formation':lambda b,a,military_formation,state:state in heading(a,military_formation),
    'station_selected':lambda b,a,military_formation,strategic_region:strategic_region in {state_regions(a).get(spot) for spot in heading(a,military_formation)},
    'rehome_formation':lambda b,a,military_formation,strategic_region:home_region(a,military_formation)==strategic_region,
    'create_army':lambda b,a,option:len(raised(a,0))>len(raised(b,0)),
    'create_fleet':lambda b,a,option:len(raised(a,1))>len(raised(b,1)),
    'split_army':lambda b,a,military_formation:len(raised(a,0))>len(raised(b,0)),
    'split_fleet':lambda b,a,military_formation:len(raised(a,1))>len(raised(b,1)),
    'transfer_battalions':lambda b,a,military_formation,target:len(units(a,target))>len(units(b,target)),
    'transfer_ships':lambda b,a,military_formation,target:len(ships(a,target))>len(ships(b,target)),
    'transfer_ship':lambda b,a,ship,target:a.map('ship','ship,fleet').get(ship)==target,
    'merge_armies':lambda b,a,military_formation,source:source not in raised(a,0),
    'merge_fleets':lambda b,a,military_formation,source:source not in raised(a,1),
    'disband_unit':lambda b,a,combat_unit:not a.rows('combat_unit','combat_unit',combat_unit=combat_unit),
    **{name:(lambda b,a,military_formation,front:a.map('formation_status','formation,target_location').get(military_formation)==front)
       for name in ('deploy_to_front','deploy_selected_to_front','defend_invasion','defend_invasion_fleet')},
    'set_borrow_setting':lambda b,a,military_formation,index:bool(a.rows('formation_borrow_setting','formation',formation=military_formation,position=index,selected=True)),
    'set_strategic_objective':lambda b,a,military_formation,state:formation_setting(a,military_formation,'strategic_objective') is not None
                              and formation_setting(a,military_formation,'strategic_objective')&SLOT==state&SLOT,
    'cancel_strategic_objective_selected':lambda b,a,military_formation,state:formation_setting(a,military_formation,'strategic_objective') is None,
    'disembark':lambda b,a,military_formation:not formation_report(a,military_formation,'embarked'),
    'embark_formation':lambda b,a,military_formation,fleet:bool(formation_report(a,military_formation,'embarked')) or a.map('formation','formation,attached_to_fleet').get(military_formation)==fleet,
    'cancel_invasion':lambda b,a,military_formation:not formation_report(a,military_formation,'invading'),
    'plan_land_invasion':lambda b,a,military_formation,state:bool(formation_report(a,military_formation,'invading')),
    'plan_naval_invasion':lambda b,a,military_formation,fleet,state:bool(formation_report(a,military_formation,'invading')),
    'commander_order':lambda b,a,character,commander_order_type:post(a,character,'order_type')==commander_order_type,
    'hire_commander':lambda b,a,character:character not in recruitable(a),
    'hire_commander_for':lambda b,a,character,military_formation:post(a,character,'formation')==military_formation,
    'promote_commander':lambda b,a,character:post(a,character,'rank')!=post(b,character,'rank'),
    'assign_commander':lambda b,a,character,military_formation:post(a,character,'formation')==military_formation,
    'unassign_commander':lambda b,a,character:post(a,character,'formation') is None,
    'character_interaction':lambda b,a,character,interaction:figure(a,character)!=figure(b,character) or interaction in cooling(a) and interaction not in cooling(b),
    **{name:(lambda b,a,military_formation,naval_mission_type:mission(a,military_formation)==naval_mission_type)
       for name in ('start_naval_mission','start_naval_mission_selected','change_naval_mission_type')},
    **{name:(lambda b,a,military_formation:mission(a,military_formation) is None) for name in ('end_naval_mission','end_naval_mission_selected')},
    'set_default_construction_fleet':lambda b,a,military_formation:bool(formation_report(a,military_formation,'default_fleet')),
    'clear_default_construction_fleet':lambda b,a:not a.rows('formation_report','formation',default_fleet=True),
    'decommission_ship':lambda b,a,ship:not a.rows('ship','ship',ship=ship),
    'build_ship':lambda b,a,ship_type:len(orders(a))>len(orders(b)),
    'build_ship_for':lambda b,a,ship_type,military_formation:len(orders(a))>len(orders(b)),
    'cancel_ship':lambda b,a,ship_type:len(orders(a))<len(orders(b)),
    'cancel_ship_for':lambda b,a,ship_type,military_formation:len(orders(a))<len(orders(b)),
    'cancel_ship_item':lambda b,a,index:order(b,index) not in orders(a),
    'raise_ship_item':moved(lambda now,was,every:now<was),
    'first_ship_item':moved(lambda now,was,every:now==min(every)),
    'lower_ship_item':moved(lambda now,was,every:now>was),
    'last_ship_item':moved(lambda now,was,every:now==max(every)),
    'station_fleet':lambda b,a,military_formation,state:state in heading(a,military_formation),
    'rehome_fleet':lambda b,a,military_formation,strategic_region:home_region(a,military_formation)==strategic_region,
    'recall_fleet':lambda b,a,military_formation:bool(formation_report(a,military_formation,'recalled')),
    **{name:(lambda b,a,military_formation:bool(formation_report(a,military_formation,'retrofitting'))) for name in ('retrofit_fleet','retrofit_fleet_and_station')},
    'cancel_retrofit_fleet':lambda b,a,military_formation:not formation_report(a,military_formation,'retrofitting'),
    **{name:(lambda b,a:len(a.rows('formation_report','formation',retrofitting=True))>len(b.rows('formation_report','formation',retrofitting=True))) for name in ('retrofit_all','retrofit_all_and_station')},
    'cancel_retrofit_all':lambda b,a:not a.rows('formation_report','formation',retrofitting=True),
    'change_ship_template':lambda b,a,ship,index:a.map('ship','ship,version').get(ship)!=b.map('ship','ship,version').get(ship),
    'set_default_ship_template':lambda b,a,ship_type,index:bool(a.map('ship_template_private','ship_template,flags').get(template(b,ship_type,index),0)&1),
    'set_fleet_ship_template':lambda b,a,ship_type,index,military_formation:bool(a.rows('ship_template_fleet','fleet',ship_template=template(b,ship_type,index),fleet=military_formation)),
    'delete_ship_template':lambda b,a,ship_type,index:template(b,ship_type,index) not in own_templates(a).values(),
    'design_ship_template':lambda b,a,ship_type,ship_modification:any(found not in designs(b,ship_type) and ship_modification in latest_design(a,found) for found in designs(a,ship_type)),
    'edit_ship_template':lambda b,a,ship_type,index,ship_modification:ship_modification in latest_design(a,template(b,ship_type,index)),
    'pause_ship_construction':lambda b,a:ship_paused(a),
    'resume_ship_construction':lambda b,a:not ship_paused(a),
    'toggle_charter':lambda b,a,company,charter:((company,charter) in charters(a))!=((company,charter) in charters(b)),
    'grant_building_charter':granted,
    'grant_region_charter':granted,
    'revoke_building_charter':revoked,
    'revoke_region_charter':revoked,
    'pause':lambda b,a:bool(a.meta['paused']),
    'unpause':lambda b,a:a.hours>b.hours,
    'press_journal_button':pressed_journal,
}
LATER={name:EFFECTS[name] for name in ('break_pact','disband_unit','decommission_ship','disband_formation','disband_regulars','disband_conscripts','repeal_amendment',
                                        'request_join_power_bloc','start_play_confirmed','withdraw_treaty','capitulate','remove_company','merge_armies','merge_fleets')}
LATER.update({name:joined for name in ('diplomatic_action','diplomatic_action_obligation')})
LATER.update({'diplomatic_action_first_state':lambda b,a,country,diplomatic_action,state,obligation:joined(b,a,country,diplomatic_action) or owner(a,state)==country,
              'diplomatic_action_second_state':lambda b,a,country,diplomatic_action,state,obligation:joined(b,a,country,diplomatic_action) or owner(a,state)==a.player,
              'diplomatic_action_states':lambda b,a,country,diplomatic_action,given,taken,obligation:joined(b,a,country,diplomatic_action)
                                         or owner(a,given)==country and owner(a,taken)==a.player})
LATER.update({name:(lambda b,a,war:war not in a.wars()) for name in ('propose_peace','white_peace')})
UNSEEN={'set_speed':'a snapshot is taken paused and records no speed',
        'toggle_naval_mission_region':'the regions of a naval mission are not recorded',
        'assign_flagship':'which ship is the flagship is not recorded',
        'unassign_flagship':'which ship is the flagship is not recorded',
        'retrofit_ship':'the refit of a single ship is not recorded',
        'cancel_retrofit_ship':'the refit of a single ship is not recorded',
        'toggle_accept_peace':'our answer to a peace offer is not recorded'}


@timed_often
def held(checks,name,before,after,params):
    return name in checks and bool(checks[name](before,after,**params)) and not checks[name](before,before,**params)


@timed_often
def took_effect(name,before,after,params):
    return held(EFFECTS,name,before,after,params)


@timed_often
def took_effect_later(name,before,later,params):
    return held(LATER,name,before,later,params)
