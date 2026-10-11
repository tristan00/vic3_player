from collections import namedtuple
from functools import cached_property

from advisors import catalogue as C
from interface.actions.catalogue import ACCESS_PERMISSIONS, ACCESS_STATUSES, LEVELS, TOLL_LEVELS
from interface.common import evidence, timed, timed_often
from interface.options.available import PROMOTED, SUPPRESSED, TARIFF_CODES, changing, enacting_laws, monopolies, player_value, privatization_requested, strait_sides, strait_value, trade_level

Choice=namedtuple('Choice','params commands')
DUTY={code:(kind,level) for kind,levels in TARIFF_CODES.items() for level,code in levels.items()}
ARTICLES=(('offer_treaty_article','us'),('demand_treaty_article','them'),('agree_treaty_article','both'))
GOODS_ARTICLES=(('offer_goods_treaty_article','us'),('demand_goods_treaty_article','them'))
DEALS=('diplomatic_action','diplomatic_action_obligation')
ESTABLISHED={act:action for acts in C.ESTABLISHED.values() for act,action in acts.items()}
ENDED={act:actions for acts in C.ENDED.values() for act,actions in acts.items()}
DEALT=frozenset({*ESTABLISHED.values(),C.MEMBERSHIP})
SIDES=(('offer','us'),('demand','them'),('agree','both'))
STATE_PICKS=('diplomatic_action_first_state','diplomatic_action_second_state')
PLAIN={'downsize_building':('downsize',),'raise_subsidies':('subsidies_on',),'lower_subsidies':('subsidies_off',),'nationalise_building':('nationalize',),
       'raise_subsidies_statewide':('subset_subsidies_on_state',),'lower_subsidies_statewide':('subset_subsidies_off_state',),'buy_out_statewide':('bulk_nationalize_state',),
       'expropriate_statewide':('bulk_expropriate_state',),'switch_methods_statewide':('bulk_switch_production_method_state',),
       'reset_methods_statewide':('reset_production_methods',),'reset_building_methods':('reset_building_production_methods',),
       'relocate_national_capital':('move_capital',),'relocate_market_capital':('move_market_capital',),
       'grant_charter_for_building_type':('grant_building_charter',),'revoke_charter_for_building_type':('revoke_building_charter',),
       'grant_charter_for_region':('grant_region_charter',),'revoke_charter_for_region':('revoke_region_charter',),
       'disband_one_unit':('disband_unit',),'cancel_queued_ship_for_fleet':('cancel_ship_for',),'refit_fleet_in_port':('retrofit_fleet_and_station',),
       'refit_every_fleet_in_port':('retrofit_all_and_station',),'refit_ship':('retrofit_ship',),'cancel_ship_refit':('cancel_retrofit_ship',),
       'rebuild_ship_to_design':('change_ship_template',),'form_fleet':('create_fleet',),'divide_army':('split_army',),'divide_fleet':('split_fleet',),
       'combine_armies':('merge_armies',),'combine_fleets':('merge_fleets',),'move_ships':('transfer_ships',),'move_ship':('transfer_ship',),
       'change_fleet_mission':('change_naval_mission_type',),'change_fleet_mission_area':('toggle_naval_mission_region',),'station_fleet_in_state':('station_fleet',),
       'rebase_fleet':('rehome_fleet',),'defend_against_invasion_at_sea':('defend_invasion_fleet',),'appoint_flagship':('assign_flagship',),
       'dismiss_flagship':('unassign_flagship',),'demand_liberation':('start_play_liberation',),'add_demand_on_country':('add_war_goal_country',),
       'add_demand_for_state':('add_war_goal_state',),'add_liberation_demand':('add_war_goal_liberation',),'add_article_demand':('add_war_goal_article',),
       **{f'add_{kind}_article_demand':(f'add_{kind}_war_goal',) for kind in C.ARTICLE_INPUTS},'sway_with_state':('offer_sway_state',),
       'sway_with_subject':('offer_sway_subject',),'sway_with_pact':('offer_sway_pact','offer_sway_subjection'),'sway_with_war_goal':('offer_sway_goal_country',),
       'sway_with_state_war_goal':('offer_sway_goal_state',),**{f'sway_with_{kind}_article':(f'offer_sway_{kind}_article',) for kind in C.ARTICLE_INPUTS},
       'halt_construction_queue':('pause_construction','pause_all_construction'),'restart_construction_queue':('resume_construction','resume_all_construction'),
       'halt_construction_sector':('pause_construction_output',),'restart_construction_sector':('resume_construction_output',),
       'halt_shipbuilding':('pause_ship_construction',),'restart_shipbuilding':('resume_ship_construction',),'cancel_queued_research':('dequeue_research',),
       'raise_building_priority':('raise_queue_item','first_queue_item'),'lower_building_priority':('lower_queue_item','last_queue_item'),
       'raise_ship_priority':('raise_ship_item','first_ship_item'),'lower_ship_priority':('lower_ship_item','last_ship_item'),'cancel_ship_order':('cancel_ship_item',),
       'establish_company':('create_company',),'disband_company':('remove_company',),'raise_state_decrees':('issue_decree',),'lower_state_decrees':('remove_decree',),
       'found_power_bloc':('form_power_bloc',),'leave_bloc':('leave_power_bloc',),'remove_bloc_member':('kick_from_power_bloc',),'replace_bloc_principle':('replace_principle',),
       'make_demand_primary':('make_primary_demand',),'sway_country':('offer_sway',),'sway_ally':('offer_sway_ally',),'back_initiator':('support_initiator',),'back_target':('support_target',),
       'lean_towards_initiator':('lean_initiator',),'lean_towards_target':('lean_target',),'stay_on_the_fence':('stay_on_fence',),'stay_neutral':('declare_neutrality',),
       'withdraw_from_confrontation':('back_down',),'surrender_war':('capitulate',),'establish_colony':('colonize',),'give_up_colony':('abandon_colony',),
       'raise_incorporation':('incorporate',),'lower_incorporation':('unincorporate',),
       'disband_battalions':('disband_regulars',),'mobilise_army':('mobilize','mobilize_selected'),'mobilise_all_armies':('mobilize_all',),
       'call_up_conscripts':('activate_conscription_center',),'raise_army_conscripts':('raise_conscripts','raise_conscripts_selected'),
       'demobilise_army':('demobilize','demobilize_selected'),'demobilise_all_armies':('demobilize_all',),'send_conscripts_home':('disband_conscripts',),
       'queue_ship':('build_ship',),'queue_ship_for_fleet':('build_ship_for',),'cancel_queued_ship':('cancel_ship',),'scrap_ship':('decommission_ship',),
       'switch_building_method':('switch_production_method',),'enact_new_law':('enact_law',),'negotiate_over_law':('negotiate',),'impose_law_on_subject':('impose_law',),
       'repeal_law_amendment':('repeal_amendment',),'upgrade_regular_units':('upgrade_regulars',),
       'upgrade_conscript_units':('upgrade_conscripts',),'set_standard_unit_type':('set_default_unit_type',),'upgrade_every_unit':('upgrade_all_units',),
       'design_ship':('design_ship_template',),'redesign_ship':('edit_ship_template',),'set_standard_ship_design':('set_default_ship_template',),
       'set_fleet_ship_design':('set_fleet_ship_template',),'scrap_ship_design':('delete_ship_template',),'refit_fleet':('retrofit_fleet',),
       'cancel_fleet_refit':('cancel_retrofit_fleet',),'refit_every_fleet':('retrofit_all',),'cancel_every_refit':('cancel_retrofit_all',),
       'form_army':('create_army',),'move_battalions':('transfer_battalions',),'recruit_commander':('hire_commander',),'recruit_commander_for':('hire_commander_for',),
       'give_command':('assign_commander',),'take_away_command':('unassign_commander',),'promote_officer':('promote_commander',),'station_army':('station_formation',),
       'station_army_at_headquarters':('station_selected',),
       'rehome_army':('rehome_formation',),'send_to_front':('deploy_to_front','deploy_selected_to_front'),'defend_against_invasion':('defend_invasion',),
       'set_objective':('set_strategic_objective',),'clear_objective':('cancel_strategic_objective_selected',),'give_order':('commander_order',),
       'start_fleet_mission':('start_naval_mission','start_naval_mission_selected'),'end_fleet_mission':('end_naval_mission','end_naval_mission_selected'),
       'plan_invasion':('plan_land_invasion',),'plan_seaborne_invasion':('plan_naval_invasion',),'call_off_invasion':('cancel_invasion',),'embark_troops':('embark_formation',),
       'land_troops':('disembark',),'set_army_supply_priority':('set_supply_priority',),'set_army_lending':('set_borrow_setting',),
       'send_new_ships_to_fleet':('set_default_construction_fleet',),'send_new_ships_to_reserve':('clear_default_construction_fleet',),'recall_fleet_for_repairs':('recall_fleet',),
       'offer_peace':('propose_peace',),
       'offer_white_peace':('white_peace',),'accept_peace_offer':('toggle_accept_peace',),'take_national_decision':('take_decision',),
       'take_journal_option':('press_journal_button',),'default_on_debt':('declare_bankruptcy',),'toggle_decision_alert':('toggle_ignore_decision',),
       'interact_with_character':('character_interaction',),'agree_to_treaty':('accept_treaty',),'refuse_treaty':('decline_treaty',),'concede_demand':('accept_demand',),
       'refuse_demand':('reject_demand',),'accept_proposal':('accept_action_proposal',),'decline_proposal':('decline_action_proposal',),
       'accept_call_to_side':('accept_sway',),'decline_call_to_side':('reject_sway',),'answer_event':('choose_event_option',)}
REFUSALS={'refuse_treaty':'decline_treaty','refuse_demand':'reject_demand','decline_proposal':'decline_action_proposal','decline_call_to_side':'reject_sway'}
QUICK='quick_decline_proposal'
LOOP_COMMANDS=frozenset({'pause','unpause','set_speed'})


class Context:
    @timed_often
    def __init__(self,snapshot,options):
        self.s=snapshot
        self.o=options

    @cached_property
    @timed_often
    def kinds(self):
        return self.s.map('building','building,building_type')

    @cached_property
    @timed_often
    def located(self):
        return self.s.map('building','building,state')

    @cached_property
    @timed_often
    def articles(self):
        held={}
        for treaty,kind in self.s.rows('treaty_article','treaty,treaty_article_type'):
            held.setdefault(treaty,set()).add(kind)
        return held

    @cached_property
    @timed_often
    def investments(self):
        return dict(self.s.rows('institution','institution,investment',country=self.s.player))

    @cached_property
    @timed_often
    def fleets(self):
        return set(self.s.formations('fleet'))

    @cached_property
    @timed_often
    def blocs(self):
        return self.s.map('country','country,power_bloc')

    @cached_property
    @timed_often
    def sides(self):
        return {(strait,state):side for strait,side,state in strait_sides(self.s)}


@timed_often
def single(action,option,*names,**extra):
    return Choice({**{name:option[name] for name in (names or option)},**extra},[(action,option)])


@timed_often
def merged(*found):
    grouped={}
    for choice in (choice for choices in found for choice in choices):
        grouped.setdefault(tuple(sorted(choice.params.items(),key=str)),Choice(choice.params,[])).commands.extend(choice.commands)
    return list(grouped.values())


@timed_often
def plain(c,*actions):
    return merged(*[[single(action,option) for option in c.o[action]] for action in actions])


@timed_often
def build(c,kinds):
    return [single('build',option) for option in c.o['build'] if option['building_type'] in kinds]


@timed_often
def sited(c,kind):
    return [single('build',option,'state') for option in c.o['build'] if option['building_type']==kind]


@timed_often
def cancelled(c):
    return merged(plain(c,'cancel_queue_item'),
                  [Choice({'state':c.located[option['building']],'building_type':c.kinds[option['building']]},[('cancel_construction',option)]) for option in c.o['cancel_construction']])


@timed_often
def step(c,action,column,change):
    current=player_value(c.s,'player_policy',column)
    return [Choice({},[(action,option)]) for option in c.o[action] if LEVELS.index(option['level'])==current+change]


@timed_often
def duty(c,direction,change):
    offered={(kind,option['goods'],option['level']) for kind in TARIFF_CODES for option in c.o[f'set_{direction}_{kind}']}
    found=[]
    for goods in sorted({goods for _,goods,_ in offered}):
        position=trade_level(c.s,direction,goods)+change
        if position in DUTY and (DUTY[position][0],goods,DUTY[position][1]) in offered:
            kind,level=DUTY[position]
            found.append(Choice({'goods':goods},[(f'set_{direction}_{kind}',{'goods':goods,'level':level})]))
    return found


@timed_often
def toggle(c,action,held,wanted,*names):
    return [single(action,option) for option in c.o[action] if (tuple(option[name] for name in names) in held)==wanted]


@timed_often
def invested(c,change):
    return [single('set_institution_level',option,'institution') for option in c.o['set_institution_level'] if option['level']==c.investments[option['institution']]+change]


@timed_often
def halted(c,rising):
    return [single('stop_institution_change',option) for option in c.o['stop_institution_change']
            if (changing(c.s)[option['institution']]>c.investments[option['institution']])==rising]


@timed_often
def governing(c,mode):
    return merged([single('reform_government',option,'interest_group') for option in c.o['reform_government'] if option['mode']==mode],
                  [Choice({'interest_group':option['member']},[('reform_government_party',option)]) for option in c.o['reform_government_party'] if option['mode']==mode])


@timed_often
def movement(c,action,status,wanted):
    managed=c.s.map('political_movement','political_movement,managed_status',country=c.s.player)
    return [single(action,option) for option in c.o[action] if (managed[option['political_movement']]==status)==wanted]


@timed_often
def diplomatic(c,name):
    return merged([Choice({'country':option['country']},[(action,option)]) for action in DEALS for option in c.o[action] if option['diplomatic_action']==name])


@timed_often
def broken(c,names):
    return [single('break_pact',option,'country') for option in c.o['break_pact'] if option['diplomatic_action'] in names]


@timed_often
def standing(c):
    named={name for names in ENDED.values() for name in names}
    return [single('break_pact',option) for option in c.o['break_pact'] if option['diplomatic_action'] not in named]


@timed_often
def filed(article):
    return ('security' if article in C.SECURITY else 'commercial' if article in C.COMMERCIAL+C.COMMERCIAL_GOODS else 'bloc' if article in (*C.BLOC_ARTICLES,C.MEMBERSHIP)
            else 'diplomatic')


@timed_often
def proposed(c,kind):
    return merged(*[[single(action,option,giver=giver) for option in c.o[action] if option['treaty_article']!=C.MEMBERSHIP and filed(option['treaty_article'])==kind]
                    for action,giver in ARTICLES])


@timed_often
def termed(c,kind,form):
    return merged(*[[single(f'{verb}_{form}_treaty_article',option,giver=giver) for option in c.o[f'{verb}_{form}_treaty_article'] if filed(option['treaty_article'])==kind]
                    for verb,giver in SIDES])


@timed_often
def pressing(c,kind,action):
    return [single(action,option) for option in c.o[action] if filed(option['treaty_article'])==kind]


@timed_often
def amending(c,kind,form):
    return merged(*[[single(f'{form}{verb}_treaty_article',option,giver=giver) for option in c.o[f'{form}{verb}_treaty_article'] if filed(option['treaty_article'])==kind]
                    for verb,giver in SIDES])


@timed_often
def supplied(c,kind):
    return merged(*[[single(f'{verb}_{kind}_treaty_article',option,giver=giver) for option in c.o[f'{verb}_{kind}_treaty_article']] for verb,giver in SIDES[:2]])


@timed_often
def ceded(c,action,commands=STATE_PICKS):
    return merged(*[[Choice({'country':option['country'],'state':option['state']},[(command,option)]) for option in c.o[command] if option['diplomatic_action']==action]
                    for command in commands])


@timed_often
def swapped(c):
    return merged([Choice({'country':option['country'],'given':option['given'],'taken':option['taken']},[('diplomatic_action_states',option)])
                   for option in c.o['diplomatic_action_states']])


@timed_often
def traded(c):
    return merged(*[[single(action,option,giver=giver) for option in c.o[action]] for action,giver in GOODS_ARTICLES])


@timed_often
def withdrawn(c,kind):
    return [single('withdraw_treaty',option) for option in c.o['withdraw_treaty'] if min(map(filed,c.articles[option['treaty']]),key=C.FILING.index)==kind]


@timed_often
def joining(c):
    asked=[Choice({'power_bloc':c.blocs[option['country']]},[(action,option)]) for action,key in (('offer_treaty_article','treaty_article'),*((action,'diplomatic_action') for action in DEALS))
           for option in c.o[action] if option[key]==C.MEMBERSHIP and c.blocs[option['country']] is not None]
    return merged(plain(c,'request_join_power_bloc'),asked)


@timed_often
def inviting(c):
    return merged(diplomatic(c,'invite_to_power_bloc'),
                  [single('demand_treaty_article',option,'country') for option in c.o['demand_treaty_article'] if option['treaty_article']==C.MEMBERSHIP])


@timed_often
def demanded(c):
    confirmed={}
    for option in c.o['start_play_confirmed']:
        confirmed.setdefault((option['country'],option['diplomatic_play_type']),[]).append(('start_play_confirmed',option))
    return [Choice(dict(option),[('start_play_country',option),*confirmed.get((option['country'],option['diplomatic_play_type']),())]) for option in c.o['start_play_country']]


@timed_often
def recruited(c):
    return merged(plain(c,'recruit_from_formation'),
                  [Choice({'military_formation':option['military_formation'],'combat_unit_type':option['combat_unit_type'],'state':c.located[option['building']]},[('recruit',option)])
                   for option in c.o['recruit']])


@timed_often
def disbanded(c,army):
    return [single('disband_formation',option) for option in c.o['disband_formation'] if (option['military_formation'] in c.fleets)!=army]


@timed_often
def pressed(c,wanted):
    held={(play,kind,target) for play,kind,target,holder,flag in c.s.rows('war_goal','diplomatic_play,war_goal_type,target_country,holder,pressed') if holder==c.s.player and flag}
    return [single('toggle_press_war_goal',option) for option in c.o['toggle_press_war_goal']
            if ((option['diplomatic_play'],option['war_goal_type'],option['country']) in held)==wanted]


@timed_often
def researched(c,action,tree):
    return [single(action,option) for option in c.o[action] if C.TECHNOLOGY_TREE[option['technology']]==tree]


@timed_often
def paused(c):
    return set(c.s.rows('player_colonization_paused','state'))


@timed_often
def chartered(c):
    return {(company,kind) for _,company,kind in c.s.rows('charter','charter,company,company_charter_type')}


@timed_often
def supported(c):
    return set(c.s.rows('formation_mobilization_option','formation,mobilization_option'))


@timed_often
def tolled(c,change):
    sides={strait:side for (strait,_),side in c.sides.items()}
    return [single('set_strait_toll',option,'strait') for option in c.o['set_strait_toll']
            if TOLL_LEVELS.index(option['level'])==strait_value(c.s,option['strait'],f'{sides[option["strait"]]}_toll_rate')+change]


@timed_often
def passage(c,action,param,levels,column,first,change):
    return [single(action,option,'strait','state') for option in c.o[action]
            if levels.index(option[param])+first==strait_value(c.s,option['strait'],f'{c.sides[option["strait"],option["state"]]}_{column}')+change]


@timed_often
def abandoned(c):
    return [Choice({'law':law},[('cancel_enactment',option)]) for option in c.o['cancel_enactment'] for law in enacting_laws(c.s)]


RULES={
    **{name:(lambda c,kinds=kinds:build(c,kinds)) for name,kinds in C.SECTORS.items()},
    **{name:(lambda c,kind=kind:sited(c,kind)) for name,kind in C.NAVAL.items()},
    **{name:(lambda c,actions=actions:plain(c,*actions)) for name,actions in PLAIN.items()},
    **{name:(lambda c,action=action:diplomatic(c,action)) for name,action in ESTABLISHED.items()},
    **{name:(lambda c,actions=actions:broken(c,actions)) for name,actions in ENDED.items()},
    C.OTHER_PACT:standing,
    'cancel_queued_construction':cancelled,
    'reserve_building_type_for_state':lambda c:toggle(c,'toggle_monopoly',{(kind,) for kind in monopolies(c.s)},False,'building_type'),
    'end_state_monopoly':lambda c:toggle(c,'toggle_monopoly',{(kind,) for kind in monopolies(c.s)},True,'building_type'),
    'withdraw_building_from_sale':lambda c:[single('toggle_privatization',option) for option in c.o['toggle_privatization'] if privatization_requested(c.s,option['building'])],
    'offer_building_for_sale':lambda c:[single('toggle_privatization',option) for option in c.o['toggle_privatization'] if not privatization_requested(c.s,option['building'])],
    'grant_charter':lambda c:toggle(c,'toggle_charter',chartered(c),False,'company','charter'),
    'revoke_charter':lambda c:toggle(c,'toggle_charter',chartered(c),True,'company','charter'),
    'raise_import_tariff':lambda c:duty(c,'import',1),
    'lower_import_tariff':lambda c:duty(c,'import',-1),
    'raise_export_tariff':lambda c:duty(c,'export',1),
    'lower_export_tariff':lambda c:duty(c,'export',-1),
    **{f'propose_{kind}_article':(lambda c,kind=kind:proposed(c,kind)) for kind in C.FILING},
    **{f'propose_{kind}_article_for_term':(lambda c,kind=kind:termed(c,kind,'timed')) for kind in C.FILING},
    **{f'propose_{kind}_article_with_obligation':(lambda c,kind=kind:termed(c,kind,'obliged')) for kind in C.FILING},
    **{f'demand_{kind}_article_under_threat':(lambda c,kind=kind:pressing(c,kind,'threaten_treaty_article')) for kind in C.FILING},
    **{f'demand_{kind}_article_made_acceptable':(lambda c,kind=kind:pressing(c,kind,'work_out_treaty_article')) for kind in C.FILING},
    **{f'exchange_{kind}_articles':(lambda c,kind=kind:pressing(c,kind,'exchange_treaty_articles')) for kind in C.FILING},
    **{f'add_{kind}_article_to_treaty':(lambda c,kind=kind:amending(c,kind,'amend_')) for kind in C.FILING},
    **{f'drop_{kind}_article_from_treaty':(lambda c,kind=kind:amending(c,kind,'amend_drop_')) for kind in C.FILING},
    **{f'withdraw_{kind}_treaty':(lambda c,kind=kind:withdrawn(c,kind)) for kind in C.FILING},
    **{name:(lambda c,kind=kind:supplied(c,kind)) for kind,(_,name,_) in C.INPUT_ACTS.items()},
    **{name:(lambda c,action=action:ceded(c,action)) for action,(_,name) in C.STATE_DEALS.items()},
    'give_state_in_trade':lambda c:ceded(c,C.STATE_TRADE,STATE_PICKS[:1]),
    'ask_state_in_trade':lambda c:ceded(c,C.STATE_TRADE,STATE_PICKS[1:]),
    'exchange_states':swapped,
    'propose_goods_article':traded,
    'raise_tax_level':lambda c:step(c,'set_tax_level','tax_level',1),
    'lower_tax_level':lambda c:step(c,'set_tax_level','tax_level',-1),
    'raise_consumption_taxes':lambda c:toggle(c,'toggle_consumption_tax',set(c.s.rows('player_taxed_goods','goods')),False,'goods'),
    'lower_consumption_taxes':lambda c:toggle(c,'toggle_consumption_tax',set(c.s.rows('player_taxed_goods','goods')),True,'goods'),
    'raise_government_wages':lambda c:step(c,'set_government_wages','government_wage_level',1),
    'lower_government_wages':lambda c:step(c,'set_government_wages','government_wage_level',-1),
    'raise_military_wages':lambda c:step(c,'set_military_wages','military_wage_level',1),
    'lower_military_wages':lambda c:step(c,'set_military_wages','military_wage_level',-1),
    'raise_institution_level':lambda c:invested(c,1),
    'lower_institution_level':lambda c:invested(c,-1),
    'cancel_institution_increase':lambda c:halted(c,True),
    'cancel_institution_decrease':lambda c:halted(c,False),
    'raise_government':lambda c:governing(c,'Potential'),
    'lower_government':lambda c:governing(c,'Staged'),
    'bolster_movement':lambda c:movement(c,'toggle_bolster_movement',PROMOTED,False),
    'stop_bolstering_movement':lambda c:movement(c,'toggle_bolster_movement',PROMOTED,True),
    'suppress_movement':lambda c:movement(c,'toggle_suppress_movement',SUPPRESSED,False),
    'stop_suppressing_movement':lambda c:movement(c,'toggle_suppress_movement',SUPPRESSED,True),
    'ask_to_join_power_bloc':joining,
    'invite_to_power_bloc':inviting,
    'adopt_bloc_principle':lambda c:merged([single('pick_principle',option,'power_bloc_principle') for option in c.o['pick_principle']],plain(c,'upgrade_principle')),
    'demand_of_country':demanded,
    'demand_for_state':lambda c:plain(c,'start_play_state'),
    'resume_colony':lambda c:toggle(c,'toggle_pause_colonization',paused(c),True,'state'),
    'pause_colony':lambda c:toggle(c,'toggle_pause_colonization',paused(c),False,'state'),
    'raise_regular_army':recruited,
    'disband_army':lambda c:disbanded(c,True),
    'disband_fleet':lambda c:disbanded(c,False),
    'switch_on_mobilisation_option':lambda c:toggle(c,'toggle_mobilization_option',supported(c),False,'military_formation','mobilization_option'),
    'switch_off_mobilisation_option':lambda c:toggle(c,'toggle_mobilization_option',supported(c),True,'military_formation','mobilization_option'),
    'raise_supply_ship_share':lambda c:step(c,'set_supply_ship_construction','supply_ship_construction_level',1),
    'lower_supply_ship_share':lambda c:step(c,'set_supply_ship_construction','supply_ship_construction_level',-1),
    'raise_strait_toll':lambda c:tolled(c,1),
    'lower_strait_toll':lambda c:tolled(c,-1),
    'tighten_strait_access':lambda c:passage(c,'set_strait_access','access',ACCESS_STATUSES,'access_status',0,1),
    'loosen_strait_access':lambda c:passage(c,'set_strait_access','access',ACCESS_STATUSES,'access_status',0,-1),
    'narrow_strait_passage':lambda c:passage(c,'set_strait_allowed','allowed',ACCESS_PERMISSIONS,'access_permissions',1,1),
    'widen_strait_passage':lambda c:passage(c,'set_strait_allowed','allowed',ACCESS_PERMISSIONS,'access_permissions',1,-1),
    'abandon_law_enactment':abandoned,
    **{f'research_{tree}_technology':(lambda c,tree=tree:researched(c,'research',tree)) for tree in C.TECHNOLOGY_TREES},
    **{f'queue_{tree}_technology':(lambda c,tree=tree:researched(c,'queue_research',tree)) for tree in C.TECHNOLOGY_TREES},
    'press_war_goal':lambda c:pressed(c,False),
    'drop_war_goal':lambda c:pressed(c,True),
}


@timed_often
def declined(offered,options):
    for option in options[QUICK]:
        waiting=[name for name in REFUSALS if any(choice.params==option for choice in offered.get(name,()))]
        if len(waiting)==1:
            next(choice for choice in offered[waiting[0]] if choice.params==option).commands.append((QUICK,option))


@timed_often
def undealt(options):
    return sorted({option['diplomatic_action'] for action in DEALS for option in options[action]}-DEALT)


@timed
def offer(snapshot,options):
    if undealt(options):
        raise RuntimeError(evidence(undealt=undealt(options)))
    context=Context(snapshot,options)
    offered={}
    for name,rule in RULES.items():
        found=rule(context)
        if found:
            declared={param for param,_ in C.PARAMS[name]}
            for choice in found:
                if set(choice.params)!=declared:
                    raise RuntimeError(evidence(name=name,params=sorted(choice.params),declared=sorted(declared)))
            offered[name]=found
    declined(offered,options)
    return offered
