from collections import namedtuple
from functools import cached_property

from advisors import catalogue as C
from interface.actions.catalogue import LEVELS
from interface.common import timed, timed_often
from interface.options.available import PROMOTED, SUPPRESSED, TARIFF_CODES, enacting_laws, monopolies, player_value, privatization_requested, trade_level

Choice=namedtuple('Choice','params commands')
DUTY={code:(kind,level) for kind,levels in TARIFF_CODES.items() for level,code in levels.items()}
ARTICLES=(('offer_treaty_article','us'),('demand_treaty_article','them'),('agree_treaty_article','both'))
GOODS_ARTICLES=(('offer_goods_treaty_article','us'),('demand_goods_treaty_article','them'))
DIPLOMACY={'raise_embargoes':'embargo','improve_relations':'increase_relations','damage_relations':'damage_relations','declare_rivalry':'rivalry',
           'expel_diplomats':'expel_diplomats','invite_to_power_bloc':'invite_to_power_bloc','lower_subject_autonomy':'da_decrease_autonomy',
           'raise_subject_payments':'raise_payments','raise_subject_autonomy':'da_increase_autonomy_of_subject','lower_subject_payments':'decrease_payments',
           'exempt_subject_from_service':'exempt_from_service','grant_subject_own_market':'grant_own_market'}
PLAIN={'downsize_building':('downsize',),'raise_subsidies':('subsidies_on',),'lower_subsidies':('subsidies_off',),'nationalise_building':('nationalize',),
       'establish_company':('create_company',),'disband_company':('remove_company',),'raise_state_decrees':('issue_decree',),'lower_state_decrees':('remove_decree',),
       'found_power_bloc':('form_power_bloc',),'leave_bloc':('leave_power_bloc',),'remove_bloc_member':('kick_from_power_bloc',),'make_demand_primary':('make_primary_demand',),
       'withdraw_from_confrontation':('back_down',),'surrender_war':('capitulate',),'establish_colony':('colonize',),'give_up_colony':('abandon_colony',),
       'disband_battalions':('disband_regulars',),'mobilise_army':('mobilize','mobilize_selected'),'mobilise_all_armies':('mobilize_all',),
       'call_up_conscripts':('activate_conscription_center',),'raise_army_conscripts':('raise_conscripts','raise_conscripts_selected'),
       'demobilise_army':('demobilize','demobilize_selected'),'demobilise_all_armies':('demobilize_all',),'send_conscripts_home':('disband_conscripts',),
       'queue_ship':('build_ship',),'queue_ship_for_fleet':('build_ship_for',),'cancel_queued_ship':('cancel_ship',),'scrap_ship':('decommission_ship',),
       'change_production_method':('switch_production_method',),'incorporate_state':('incorporate',),'upgrade_regular_units':('upgrade_regulars',),
       'upgrade_conscript_units':('upgrade_conscripts',),'set_standard_unit_type':('set_default_unit_type',),'upgrade_every_unit':('upgrade_all_units',),
       'form_army':('create_army',),'move_battalions':('transfer_battalions',),'recruit_commander':('hire_commander',),'recruit_commander_for':('hire_commander_for',),
       'give_command':('assign_commander',),'take_away_command':('unassign_commander',),'station_army':('station_formation',),'station_army_at_headquarters':('station_selected',),
       'rehome_army':('rehome_formation',),'send_to_front':('deploy_to_front','deploy_selected_to_front'),'defend_against_invasion':('defend_invasion',),
       'set_objective':('set_strategic_objective',),'clear_objective':('cancel_strategic_objective_selected',),'give_order':('commander_order',),
       'start_fleet_mission':('start_naval_mission','start_naval_mission_selected'),'end_fleet_mission':('end_naval_mission','end_naval_mission_selected'),
       'call_off_invasion':('cancel_invasion',),'land_troops':('disembark',),'set_army_supply_priority':('set_supply_priority',),'offer_peace':('propose_peace',),
       'offer_white_peace':('white_peace',),'accept_peace_offer':('toggle_accept_peace',),'take_national_decision':('take_decision',),
       'take_journal_option':('press_journal_button',),'agree_to_treaty':('accept_treaty',),'refuse_treaty':('decline_treaty',),'concede_demand':('accept_demand',),
       'refuse_demand':('reject_demand',),'accept_proposal':('accept_action_proposal',),'decline_proposal':('decline_action_proposal',),
       'accept_call_to_side':('accept_sway',),'decline_call_to_side':('reject_sway',),'answer_event':('choose_event_option',)}
REFUSALS={'refuse_treaty':'decline_treaty','refuse_demand':'reject_demand','decline_proposal':'decline_action_proposal','decline_call_to_side':'reject_sway'}
QUICK='quick_decline_proposal'


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
    def law_types(self):
        return self.s.map('law','law,law_type')

    @cached_property
    @timed_often
    def enacting(self):
        return {C.LAW_CATEGORY[C.LAW_GROUP[self.law_types[law]]] for law in enacting_laws(self.s)}

    @cached_property
    @timed_often
    def investments(self):
        return dict(self.s.rows('institution','institution,investment',country=self.s.player))

    @cached_property
    @timed_often
    def armies(self):
        return set(self.s.formations('army'))

    @cached_property
    @timed_often
    def blocs(self):
        return self.s.map('country','country,power_bloc')


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
def governing(c,mode):
    return merged([single('reform_government',option,'interest_group') for option in c.o['reform_government'] if option['mode']==mode],
                  [Choice({'interest_group':option['member']},[('reform_government_party',option)]) for option in c.o['reform_government_party'] if option['mode']==mode])


@timed_often
def movement(c,action,status,wanted):
    managed=c.s.map('political_movement','political_movement,managed_status',country=c.s.player)
    return [single(action,option) for option in c.o[action] if (managed[option['political_movement']]==status)==wanted]


@timed_often
def diplomatic(c,name):
    return [Choice({'country':option['country']},[('diplomatic_action',option)]) for option in c.o['diplomatic_action'] if option['diplomatic_action']==name]


@timed_often
def proposed(c,names,commands):
    return merged(*[[single(action,option,giver=giver) for option in c.o[action] if option['treaty_article'] in names] for action,giver in commands])


@timed_often
def withdrawn(c,security):
    wanted=set(C.SECURITY if security else C.COMMERCIAL+C.COMMERCIAL_GOODS)
    return [single('withdraw_treaty',option) for option in c.o['withdraw_treaty']
            if c.articles[option['treaty']]&wanted and (security or not c.articles[option['treaty']]&set(C.SECURITY))]


@timed_often
def joining(c):
    asked=[Choice({'power_bloc':c.blocs[option['country']]},[(action,option)]) for action,key in (('offer_treaty_article','treaty_article'),('diplomatic_action','diplomatic_action'))
           for option in c.o[action] if option[key]=='join_power_bloc' and c.blocs[option['country']] is not None]
    return merged(plain(c,'request_join_power_bloc'),asked)


@timed_often
def inviting(c):
    return merged(diplomatic(c,'invite_to_power_bloc'),
                  [single('demand_treaty_article',option,'country') for option in c.o['demand_treaty_article'] if option['treaty_article']=='join_power_bloc'])


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
    return [single('disband_formation',option) for option in c.o['disband_formation'] if (option['military_formation'] in c.armies)==army]


@timed_often
def pressed(c,wanted):
    held={(play,kind,target) for play,kind,target,holder,flag in c.s.rows('war_goal','diplomatic_play,war_goal_type,target_country,holder,pressed') if holder==c.s.player and flag}
    return [single('toggle_press_war_goal',option) for option in c.o['toggle_press_war_goal']
            if ((option['diplomatic_play'],option['war_goal_type'],option['country']) in held)==wanted]


@timed_often
def lawful(c,action,category):
    return [single(action,option) for option in c.o[action] if C.LAW_CATEGORY[C.LAW_GROUP[c.law_types[option['law']]]]==category]


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


RULES={
    **{name:(lambda c,kinds=kinds:build(c,kinds)) for name,kinds in C.SECTORS.items()},
    **{name:(lambda c,actions=actions:plain(c,*actions)) for name,actions in PLAIN.items()},
    **{name:(lambda c,action=action:diplomatic(c,action)) for name,action in DIPLOMACY.items()},
    'cancel_queued_construction':cancelled,
    'raise_construction_priority':lambda c:plain(c,'raise_queue_item','first_queue_item'),
    'lower_construction_priority':lambda c:plain(c,'lower_queue_item','last_queue_item'),
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
    'propose_commercial_article':lambda c:proposed(c,C.COMMERCIAL,ARTICLES),
    'propose_goods_article':lambda c:proposed(c,C.COMMERCIAL_GOODS,GOODS_ARTICLES),
    'lower_commercial_treaties':lambda c:withdrawn(c,False),
    'raise_tax_level':lambda c:step(c,'set_tax_level','tax_level',1),
    'lower_tax_level':lambda c:step(c,'set_tax_level','tax_level',-1),
    'raise_consumption_taxes':lambda c:toggle(c,'toggle_consumption_tax',set(c.s.rows('player_taxed_goods','goods')),False,'goods'),
    'lower_consumption_taxes':lambda c:toggle(c,'toggle_consumption_tax',set(c.s.rows('player_taxed_goods','goods')),True,'goods'),
    'raise_government_wages':lambda c:step(c,'set_government_wages','government_wage_level',1),
    'lower_government_wages':lambda c:step(c,'set_government_wages','government_wage_level',-1),
    'raise_military_wages':lambda c:step(c,'set_military_wages','military_wage_level',1),
    'lower_military_wages':lambda c:step(c,'set_military_wages','military_wage_level',-1),
    'raise_institutions':lambda c:invested(c,1),
    'lower_institutions':lambda c:invested(c,-1),
    'raise_government':lambda c:governing(c,'Potential'),
    'lower_government':lambda c:governing(c,'Staged'),
    'bolster_movement':lambda c:movement(c,'toggle_bolster_movement',PROMOTED,False),
    'stop_bolstering_movement':lambda c:movement(c,'toggle_bolster_movement',PROMOTED,True),
    'suppress_movement':lambda c:movement(c,'toggle_suppress_movement',SUPPRESSED,False),
    'stop_suppressing_movement':lambda c:movement(c,'toggle_suppress_movement',SUPPRESSED,True),
    'raise_security_treaties':lambda c:proposed(c,C.SECURITY,ARTICLES),
    'lower_security_treaties':lambda c:withdrawn(c,True),
    'ask_to_join_power_bloc':joining,
    'invite_to_power_bloc':inviting,
    'adopt_bloc_principle':lambda c:merged([single('pick_principle',option,'power_bloc_principle') for option in c.o['pick_principle']],plain(c,'upgrade_principle')),
    'demand_of_country':demanded,
    'demand_for_state':lambda c:plain(c,'start_play_state'),
    'add_demand':lambda c:[single('add_war_goal',option,'diplomatic_play','war_goal_type') for option in c.o['add_war_goal']],
    'resume_colony':lambda c:toggle(c,'toggle_pause_colonization',paused(c),True,'state'),
    'pause_colony':lambda c:toggle(c,'toggle_pause_colonization',paused(c),False,'state'),
    'raise_regular_army':recruited,
    'disband_army':lambda c:disbanded(c,True),
    'disband_fleet':lambda c:disbanded(c,False),
    'switch_on_mobilisation_option':lambda c:toggle(c,'toggle_mobilization_option',supported(c),False,'military_formation','mobilization_option'),
    'switch_off_mobilisation_option':lambda c:toggle(c,'toggle_mobilization_option',supported(c),True,'military_formation','mobilization_option'),
    'construct_naval_administration':lambda c:[single('build',option,'state') for option in c.o['build'] if option['building_type']==C.NAVAL_ADMINISTRATION],
    **{f'enact_{category}_law':(lambda c,category=category:lawful(c,'enact_law',category)) for category in C.LAW_CATEGORIES},
    **{f'negotiate_{category}_law':(lambda c,category=category:plain(c,'negotiate') if category in c.enacting else []) for category in C.LAW_CATEGORIES},
    **{f'research_{tree}_technology':(lambda c,tree=tree:researched(c,'research',tree)) for tree in C.TECHNOLOGY_TREES},
    **{f'queue_{tree}_technology':(lambda c,tree=tree:researched(c,'queue_research',tree)) for tree in C.TECHNOLOGY_TREES},
    'press_war_goal':lambda c:pressed(c,False),
    'drop_war_goal':lambda c:pressed(c,True),
}
UNOFFERED=frozenset(C.PARAMS)-frozenset(RULES)
LEFT_OUT=frozenset({'pause','unpause','set_speed','pause_construction','resume_construction','pause_all_construction','resume_all_construction','pause_construction_output',
                    'resume_construction_output','pause_ship_construction','resume_ship_construction','subset_subsidies_on_state','subset_subsidies_off_state',
                    'bulk_nationalize_state','bulk_switch_production_method_state','declare_bankruptcy','set_strait_toll','set_strait_access','set_strait_allowed',
                    'cancel_enactment','impose_law','repeal_amendment','stop_institution_change','dequeue_research','unincorporate','set_supply_ship_construction',
                    'set_default_construction_fleet','clear_default_construction_fleet','raise_ship_item','lower_ship_item','first_ship_item','last_ship_item',
                    'cancel_ship_item','recall_fleet','retrofit_fleet','cancel_retrofit_fleet','retrofit_all','cancel_retrofit_all','design_ship_template',
                    'edit_ship_template','set_default_ship_template','set_fleet_ship_template','delete_ship_template','set_formation_flag','set_borrow_setting',
                    'promote_commander','character_interaction','diplomatic_action_obligation','support_initiator','support_target','lean_initiator','lean_target',
                    'stay_on_fence','declare_neutrality','toggle_ignore_decision'})


@timed_often
def declined(offered,options):
    for option in options[QUICK]:
        waiting=[name for name in REFUSALS if any(choice.params==option for choice in offered.get(name,()))]
        if len(waiting)==1:
            next(choice for choice in offered[waiting[0]] if choice.params==option).commands.append((QUICK,option))


@timed
def offer(snapshot,options):
    context=Context(snapshot,options)
    offered={}
    for name,rule in RULES.items():
        found=rule(context)
        if found:
            declared={param for param,_ in C.PARAMS[name]}
            for choice in found:
                if set(choice.params)!=declared:
                    raise RuntimeError(f'{name} carries {sorted(choice.params)}, not {sorted(declared)}')
            offered[name]=found
    declined(offered,options)
    return offered
