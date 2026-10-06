from collections import namedtuple

from interface.common import DEFAULT_GAME
from interface.script import body, fields, read

Action=namedtuple('Action','name domain params lever')
Lever=namedtuple('Lever','name domain acts')

GAME=DEFAULT_GAME/'game'
LAW_GROUP={name:dict(fields(body(text)))['group'][0] for name,text in read(GAME,'common/laws')}
LAW_CATEGORY={name:dict(fields(body(text)))['law_group_category'][0] for name,text in read(GAME,'common/law_groups')}
LAW_GROUPS=list(LAW_CATEGORY)
INSTITUTIONS=[name for name,_ in read(GAME,'common/institutions')]
TECHNOLOGY_TREE={name:dict(fields(body(text)))['category'][0] for name,text in read(GAME,'common/technology/technologies')}
TECHNOLOGY_TREES=('production','military','society')
BUILDINGS={name:dict(fields(body(text))) for name,text in read(GAME,'common/buildings')}
DUTIES=('max_subvention','high_subvention','low_subvention','none','low_tariff','high_tariff','max_tariff')
ENTITIES=('amendment','building','character','combat_unit','company','country','diplomatic_play','institution','interest_group','journal_entry','law','military_formation','political_movement',
          'power_bloc','ship','state','strait','treaty','war')
CONSTRUCT,QUEUE,RAISE,LOWER,SINGLE,ANSWER='construct','queue','raise','lower','single','answer'

STATE=('state','state')
BUILDING=('building','building')
KIND=('building_type','building_type')
GOODS=('goods','goods')
COUNTRY=('country','country')
TREATY=('treaty','treaty')
LAW=('law','law')
AMENDMENT=('amendment','amendment')
GROUP=('interest_group','interest_group')
MOVEMENT=('political_movement','political_movement')
CHARACTER=('character','character')
INTERACTION=('interaction','character_interaction')
FORMATION=('military_formation','military_formation')
FLEET=('fleet','military_formation')
UNIT=('combat_unit_type','combat_unit_type')
PLAY=('diplomatic_play','diplomatic_play')
PLAY_TYPE=('diplomatic_play_type','diplomatic_play_type')
GOAL=('war_goal_type','war_goal_type')
WAR=('war','war')
ARTICLE=('treaty_article','treaty_article')
PACT=('diplomatic_action','diplomatic_action')
GIVER=('giver','choice')
OWNERSHIP=('ownership','choice')
METHOD=('production_method','production_method')
DECREE=('decree','decree')
INSTITUTION=('institution','institution')
TECHNOLOGY=('technology','technology')
COMPANY=('company','company')
COMPANY_TYPE=('company_type','company_type')
CHARTER=('charter','charter')
BLOC=('power_bloc','power_bloc')
IDENTITY=('power_bloc_identity','power_bloc_identity')
PRINCIPLE=('power_bloc_principle','power_bloc_principle')
SHIP=('ship','ship')
SHIP_TYPE=('ship_type','ship_type')
MODIFICATION=('ship_modification','ship_modification')
STRAIT=('strait','strait')
OPTION=('mobilization_option','mobilization_option')
ORDER=('commander_order_type','commander_order_type')
MISSION=('naval_mission_type','naval_mission_type')
REGION=('strategic_region','strategic_region')
DECISION=('decision','decision')
ENTRY=('journal_entry','journal_entry')
EVENT=('event','event')
INDEX=('index','int')
SLOT=('slot','int')
BUILD=(STATE,KIND)
NATION=(COUNTRY,)
TROOPS=(FORMATION,UNIT)
WHOLE_STATE=(STATE,KIND,OWNERSHIP)
DESIGN=(SHIP_TYPE,INDEX)
PROPOSAL=(COUNTRY,ARTICLE,GIVER)
PASSAGE=(STRAIT,STATE)
UNIT_ID=('combat_unit','combat_unit')
TARGET=('target','military_formation')
SOURCE=('source','military_formation')
SHARE=('share','choice')
SUBJECT=('subject','country')
HOLDER=('holder','country')
DEFINITION=('country_definition','country_definition')
FRONT=('front','int')
AMENDED=(TREATY,ARTICLE,GIVER)
COMMITMENT=('commitment','law')


def grouped(*groups):
    return tuple(name for name,found in BUILDINGS.items() if found['building_group'][0] in groups and found.get('buildable')!=['no'])


SECTORS={'construct_construction_capacity':('building_construction_sector',),
         'construct_infrastructure':('building_railway','building_port',*grouped('bg_canals')),
         'construct_food_production':('building_rye_farm','building_wheat_farm','building_rice_farm','building_maize_farm','building_millet_farm','building_vineyard',
                                      'building_livestock_ranch'),
         'construct_plantations':('building_coffee_plantation','building_cotton_plantation','building_dye_plantation','building_opium_plantation','building_tea_plantation',
                                  'building_tobacco_plantation','building_sugar_plantation','building_banana_plantation','building_silk_plantation'),
         'construct_raw_materials':('building_coal_mine','building_iron_mine','building_lead_mine','building_sulfur_mine','building_gold_mine','building_logging_camp',
                                    'building_fishing_wharf','building_whaling_station','building_oil_rig','building_rubber_plantation'),
         'construct_consumer_goods':('building_food_industry','building_textile_mill','building_furniture_manufactory',*grouped('bg_arts','bg_skyscraper')),
         'construct_industrial_goods':('building_tooling_workshop','building_paper_mill','building_glassworks','building_steel_mill','building_motor_industry',
                                       'building_chemical_plant','building_explosives_factory','building_synthetics_plant','building_electrics_industry',
                                       'building_automotive_industry','building_shipyard','building_power_plant'),
         'construct_military_goods':('building_arms_industry','building_artillery_foundry','building_munition_plant'),
         'construct_trade_capacity':('building_trade_center',),
         'construct_bureaucracy':('building_government_administration',),
         'construct_innovation':('building_university',),
         'construct_monuments':grouped('bg_monuments')}
NAVAL={'construct_naval_administration':'building_naval_administration','construct_naval_fortification':'building_naval_fortification'}
COMMERCIAL=('trade_privilege','transit_rights','foreign_investment_rights','acquire_monopoly_for_company','take_on_debt','money_transfer','toll_exemption','no_tolls','strait_access',
            'no_strait_closure')
COMMERCIAL_GOODS=('goods_transfer','no_tariffs','no_subventions','prohibit_trade_with_global_market')
SECURITY=('alliance','defensive_pact','guarantee_independence','support_independence','military_access','military_assistance','non_piracy_agreement','abandon_piracy')
BLOC_ARTICLES=('host_power_bloc_embassy',)
MEMBERSHIP='join_power_bloc'
GIVERS=('us','them','both')
FILING=('security','commercial','bloc','diplomatic')
FILED={'security':'security_treaties','commercial':'commercial_treaties','bloc':'power_bloc','diplomatic':'relations'}
TERMS={'for_term':(('days','choice'),),'with_obligation':(('obligation','choice'),)}
PRESSED=('under_threat','made_acceptable')
INPUT_ACTS={'state':('diplomatic','propose_state_article',(STATE,)),'region':('diplomatic','propose_region_article',(REGION,)),
            'law':('diplomatic','propose_law_commitment',(COMMITMENT,)),
            'subject':('diplomatic','propose_subject_transfer',(SUBJECT,)),'ship':('diplomatic','propose_ship_transfer',(SHIP,)),
            'monopoly':('commercial','propose_company_monopoly',(COMPANY,KIND)),'money':('commercial','propose_money_transfer',(SHARE,)),
            'goods_amount':('commercial','propose_goods_quantity_article',(GOODS,SHARE))}
STATE_DEALS={'grant_state':('lower_hold_over_subjects','grant_state_to_subject'),'take_state':('raise_hold_over_subjects','take_state_from_subject'),
             'demand_state':('petition_overlord','ask_overlord_for_state'),'da_stake_colonial_claim':('raise_colonies','stake_colonial_claim')}
STATE_TRADE='trade_states'
ARTICLE_INPUTS={'goods':GOODS,'state':STATE,'region':REGION,'law':COMMITMENT}


def proposing(kind):
    return ((f'propose_{kind}_article',PROPOSAL),*((f'propose_{kind}_article_{term}',(COUNTRY,ARTICLE,*extra,GIVER)) for term,extra in TERMS.items()),
            *((f'demand_{kind}_article_{way}',(COUNTRY,ARTICLE)) for way in PRESSED),(f'exchange_{kind}_articles',(COUNTRY,ARTICLE,('demand','choice'))),
            (f'add_{kind}_article_to_treaty',AMENDED),*((name,(COUNTRY,ARTICLE,*extra,GIVER)) for filed,name,extra in INPUT_ACTS.values() if filed==kind))


def retracting(kind):
    return ((f'withdraw_{kind}_treaty',(TREATY,)),(f'drop_{kind}_article_from_treaty',AMENDED))


def state_deals(lever):
    return tuple((name,(COUNTRY,STATE)) for home,name in STATE_DEALS.values() if home==lever)
SUBJECT_PACTS=('protectorate','puppet','dominion','personal_union','vassal','tributary','colony','chartered_company','crown_land')
ESTABLISHED={'raise_relations':{'improve_relations':'increase_relations','forgive_obligation':'redeem_obligation','fund_lobby':'fund_lobbies'},
             'lower_relations':{'damage_relations':'damage_relations','declare_rivalry':'rivalry','expel_diplomats':'expel_diplomats','violate_neutrality':'violate_sovereignty',
                                'support_separatists':'support_separatism','stage_coup':'orchestrate_coup'},
             'raise_embargoes':{'raise_embargoes':'embargo'},
             'raise_power_bloc':{'invite_to_power_bloc':'invite_to_power_bloc','subjugate_bloc_member':'force_become_subject','force_bloc_regime_change':'force_regime_change',
                                 'force_bloc_religion':'force_state_religion','add_bloc_culture':'add_power_bloc_culture'},
             'raise_hold_over_subjects':{'lower_subject_autonomy':'da_decrease_autonomy','raise_subject_payments':'raise_payments','appoint_colonial_governor':'da_appoint_colonial_governor',
                                         'evangelise_subject':'da_evangelize','change_subject_culture':'da_change_culture','enforce_subject_military_access':'enforce_military_access',
                                         'annex_lapsed_subject':'invoke_doctrine_of_lapse'},
             'lower_hold_over_subjects':{'raise_subject_autonomy':'da_increase_autonomy_of_subject','lower_subject_payments':'decrease_payments',
                                         'exempt_subject_from_service':'exempt_from_service','grant_subject_own_market':'grant_own_market','support_subject_regime':'da_support_regime',
                                         'share_knowledge_with_subject':'da_knowledge_sharing','grant_subject_investment_rights':'da_overlord_grant_investment_rights'},
             'petition_overlord':{'ask_for_autonomy':'da_increase_autonomy_of_self','ask_for_regime_support':'da_request_support_regime',
                                  'ask_for_knowledge_sharing':'da_request_knowledge_sharing','ask_for_market_control':'request_market_control',
                                  'ask_for_investment_rights':'da_subject_request_investment_rights','ask_for_colonial_governor':'da_request_colonial_governor'}}
ENDED={'lower_embargoes':{'lower_embargoes':('embargo',)},
       'raise_relations':{'stop_damaging_relations':('damage_relations',),'end_rivalry':('rivalry',),'stop_supporting_separatists':('support_separatism',),'call_off_coup':('orchestrate_coup',)},
       'lower_relations':{'stop_improving_relations':('increase_relations',),'stop_funding_lobby':('fund_lobbies',)},
       'raise_hold_over_subjects':{'end_service_exemption':('exempt_from_service',),'take_back_subject_market':('grant_own_market',),'end_payment_relief':('decrease_payments',),
                                   'stop_supporting_subject_regime':('da_support_regime',),'stop_sharing_knowledge':('da_knowledge_sharing',),
                                   'withdraw_subject_investment_rights':('da_overlord_grant_investment_rights',)},
       'lower_hold_over_subjects':{'grant_independence':SUBJECT_PACTS,'end_raised_payments':('raise_payments',),'stop_evangelising_subject':('da_evangelize',)},
       'petition_overlord':{'return_market_control':('request_market_control',)}}
OTHER_PACT='end_standing_pact'


def pair(name,more,less):
    return [Lever(f'raise_{name}',RAISE,more),Lever(f'lower_{name}',LOWER,less)]


def alone(name,domain,params=()):
    return Lever(name,domain,((name,params),))


def both(name,params=()):
    return pair(name,((f'raise_{name}',params),),((f'lower_{name}',params),))


def dealt(lever,table=ESTABLISHED):
    return tuple((name,NATION) for name in table.get(lever,()))


def dealings(name,more=(),less=()):
    return pair(name,(*dealt(f'raise_{name}'),*dealt(f'raise_{name}',ENDED),*state_deals(f'raise_{name}'),*more),
                (*dealt(f'lower_{name}'),*dealt(f'lower_{name}',ENDED),*state_deals(f'lower_{name}'),*less))


LEVERS=[
    *[alone(name,CONSTRUCT,BUILD) for name in SECTORS],
    alone('cancel_queued_construction',QUEUE,BUILD),
    Lever('raise_construction_priority',QUEUE,(('raise_building_priority',BUILD),('raise_ship_priority',(INDEX,)))),
    Lever('lower_construction_priority',QUEUE,(('lower_building_priority',BUILD),('lower_ship_priority',(INDEX,)))),
    alone('downsize_building',QUEUE,(BUILDING,)),
    Lever('halt_construction',QUEUE,(('halt_construction_queue',()),('halt_construction_sector',(BUILDING,)),('halt_shipbuilding',()))),
    Lever('restart_construction',QUEUE,(('restart_construction_queue',()),('restart_construction_sector',(BUILDING,)),('restart_shipbuilding',()))),
    alone('cancel_queued_research',QUEUE,(TECHNOLOGY,)),
    *both('subsidies',(BUILDING,)),
    *both('subsidies_statewide',WHOLE_STATE),
    *pair('state_ownership',(('nationalise_building',(BUILDING,('levels','int'))),('reserve_building_type_for_state',(KIND,)),('withdraw_building_from_sale',(BUILDING,))),
          (('offer_building_for_sale',(BUILDING,)),('end_state_monopoly',(KIND,)))),
    *pair('companies_and_charters',(('establish_company',(COMPANY_TYPE,)),('grant_charter',(COMPANY,CHARTER)),('grant_charter_for_building_type',(COMPANY,CHARTER,KIND)),
                                    ('grant_charter_for_region',(COMPANY,CHARTER,STATE))),
          (('disband_company',(COMPANY_TYPE,)),('revoke_charter',(COMPANY,CHARTER)),('revoke_charter_for_building_type',(COMPANY,CHARTER,KIND)),
           ('revoke_charter_for_region',(COMPANY,CHARTER,STATE)))),
    *both('import_tariff',(GOODS,)),
    *both('export_tariff',(GOODS,)),
    *pair('commercial_treaties',(*proposing('commercial'),('propose_goods_article',(COUNTRY,ARTICLE,GOODS,GIVER))),retracting('commercial')),
    *dealings('embargoes'),
    *both('tax_level'),
    *both('consumption_taxes',(GOODS,)),
    *both('government_wages'),
    *both('military_wages'),
    *pair('institutions',(('raise_institution_level',(INSTITUTION,)),('cancel_institution_decrease',(INSTITUTION,))),
          (('lower_institution_level',(INSTITUTION,)),('cancel_institution_increase',(INSTITUTION,)))),
    *both('state_decrees',(STATE,DECREE)),
    *both('government',(GROUP,)),
    *pair('political_movements',(('bolster_movement',(MOVEMENT,)),('stop_suppressing_movement',(MOVEMENT,))),
          (('suppress_movement',(MOVEMENT,)),('stop_bolstering_movement',(MOVEMENT,)))),
    *dealings('relations',((OTHER_PACT,(COUNTRY,PACT)),*proposing('diplomatic')),retracting('diplomatic')),
    *pair('security_treaties',proposing('security'),retracting('security')),
    *dealings('power_bloc',(('found_power_bloc',(IDENTITY,PRINCIPLE)),('ask_to_join_power_bloc',(BLOC,)),('adopt_bloc_principle',(PRINCIPLE,)),
                            ('replace_bloc_principle',(SLOT,PRINCIPLE)),*proposing('bloc')),
               (('leave_bloc',()),('remove_bloc_member',NATION),*retracting('bloc'))),
    *dealings('hold_over_subjects'),
    *pair('confrontations',(('demand_of_country',(COUNTRY,PLAY_TYPE)),('demand_for_state',(STATE,PLAY_TYPE)),('demand_liberation',(COUNTRY,PLAY_TYPE,DEFINITION)),
                            ('add_demand_on_country',(PLAY,GOAL,HOLDER,COUNTRY)),('add_demand_for_state',(PLAY,GOAL,HOLDER,STATE)),
                            ('add_liberation_demand',(PLAY,GOAL,COUNTRY,DEFINITION)),('add_article_demand',(PLAY,GOAL,COUNTRY,ARTICLE)),
                            *((f'add_{kind}_article_demand',(PLAY,GOAL,COUNTRY,ARTICLE,param)) for kind,param in ARTICLE_INPUTS.items()),
                            ('make_demand_primary',(PLAY,GOAL,COUNTRY)),('sway_country',(PLAY,COUNTRY)),('sway_ally',(PLAY,COUNTRY)),('sway_with_state',(PLAY,COUNTRY,STATE)),
                            ('sway_with_subject',(PLAY,COUNTRY,SUBJECT)),('sway_with_pact',(PLAY,COUNTRY,PACT)),
                            ('sway_with_war_goal',(PLAY,COUNTRY,GOAL,('target','country'))),('sway_with_state_war_goal',(PLAY,COUNTRY,GOAL,STATE)),
                            *((f'sway_with_{kind}_article',(PLAY,COUNTRY,GOAL,ARTICLE,param)) for kind,param in ARTICLE_INPUTS.items()),
                            ('back_initiator',(PLAY,)),('back_target',(PLAY,)),('lean_towards_initiator',(PLAY,)),('lean_towards_target',(PLAY,))),
          (('withdraw_from_confrontation',(PLAY,)),('surrender_war',(WAR,)),('stay_on_the_fence',(PLAY,)),('stay_neutral',(PLAY,)))),
    *pair('colonies',(('establish_colony',(STATE,)),('resume_colony',(STATE,)),*state_deals('raise_colonies')),(('pause_colony',(STATE,)),('give_up_colony',(STATE,)))),
    *both('incorporation',(STATE,)),
    *pair('regular_army',(('raise_regular_army',(FORMATION,UNIT,STATE)),),(('disband_battalions',TROOPS),('disband_one_unit',(UNIT_ID,)),('disband_army',(FORMATION,)))),
    *pair('mobilisation',(('mobilise_army',(FORMATION,)),('mobilise_all_armies',()),('call_up_conscripts',(FORMATION,UNIT,STATE)),('raise_army_conscripts',(FORMATION,)),
                          ('switch_on_mobilisation_option',(FORMATION,OPTION))),
          (('demobilise_army',(FORMATION,)),('demobilise_all_armies',()),('send_conscripts_home',TROOPS),('switch_off_mobilisation_option',(FORMATION,OPTION)))),
    *pair('navy',(('queue_ship',(SHIP_TYPE,)),('queue_ship_for_fleet',(SHIP_TYPE,FORMATION)),*((name,(STATE,)) for name in NAVAL),('raise_supply_ship_share',())),
          (('cancel_queued_ship',(SHIP_TYPE,)),('cancel_queued_ship_for_fleet',(SHIP_TYPE,FORMATION)),('cancel_ship_order',(INDEX,)),('scrap_ship',(SHIP,)),
           ('disband_fleet',(FORMATION,)),('lower_supply_ship_share',()))),
    *pair('strait_restrictions',(('raise_strait_toll',(STRAIT,)),('tighten_strait_access',PASSAGE),('narrow_strait_passage',PASSAGE)),
          (('lower_strait_toll',(STRAIT,)),('loosen_strait_access',PASSAGE),('widen_strait_passage',PASSAGE))),
    Lever('change_production_method',SINGLE,(('switch_building_method',(BUILDING,METHOD)),('reset_building_methods',(BUILDING,)))),
    Lever('change_production_method_statewide',SINGLE,(('switch_methods_statewide',(STATE,KIND,METHOD,OWNERSHIP)),('reset_methods_statewide',(STATE,)))),
    Lever('nationalise_statewide',SINGLE,(('buy_out_statewide',WHOLE_STATE),('expropriate_statewide',WHOLE_STATE))),
    Lever('relocate_capital',SINGLE,(('relocate_national_capital',(STATE,)),('relocate_market_capital',(STATE,)))),
    Lever('trade_territory',SINGLE,(('exchange_states',(COUNTRY,('given','state'),('taken','state'))),('give_state_in_trade',(COUNTRY,STATE)),('ask_state_in_trade',(COUNTRY,STATE)))),
    Lever('laws',SINGLE,(('enact_new_law',(LAW,)),('negotiate_over_law',(GROUP,)),('abandon_law_enactment',(LAW,)),('impose_law_on_subject',(LAW,)),
                         ('repeal_law_amendment',(AMENDMENT,)))),
    *[Lever(f'research_{tree}',SINGLE,((f'research_{tree}_technology',(TECHNOLOGY,)),(f'queue_{tree}_technology',(TECHNOLOGY,)))) for tree in TECHNOLOGY_TREES],
    Lever('change_army_equipment',SINGLE,(('upgrade_regular_units',TROOPS),('upgrade_conscript_units',TROOPS),('set_standard_unit_type',TROOPS),('upgrade_every_unit',()))),
    Lever('change_navy_equipment',SINGLE,(('design_ship',(SHIP_TYPE,MODIFICATION)),('redesign_ship',(SHIP_TYPE,INDEX,MODIFICATION)),('set_standard_ship_design',DESIGN),
                                           ('set_fleet_ship_design',(SHIP_TYPE,INDEX,FORMATION)),('scrap_ship_design',DESIGN),('refit_fleet',(FORMATION,)),
                                           ('cancel_fleet_refit',(FORMATION,)),('refit_every_fleet',()),('cancel_every_refit',()),('refit_fleet_in_port',(FORMATION,)),
                                           ('refit_every_fleet_in_port',()),('refit_ship',(SHIP,)),('cancel_ship_refit',(SHIP,)),('rebuild_ship_to_design',(SHIP,INDEX)))),
    Lever('disposition_of_forces',SINGLE,(('form_army',(('option','int'),)),('move_battalions',(FORMATION,('target','military_formation'))),('recruit_commander',(CHARACTER,)),
                                           ('recruit_commander_for',(CHARACTER,FORMATION)),('give_command',(CHARACTER,FORMATION)),('take_away_command',(CHARACTER,)),
                                           ('promote_officer',(CHARACTER,)),('station_army',(FORMATION,STATE)),('station_army_at_headquarters',(FORMATION,REGION)),
                                           ('rehome_army',(FORMATION,REGION)),('send_to_front',(FORMATION,('front','int'))),('defend_against_invasion',(FORMATION,('front','int'))),
                                           ('set_objective',(FORMATION,STATE)),('clear_objective',(FORMATION,STATE)),('give_order',(CHARACTER,ORDER)),
                                           ('start_fleet_mission',(FORMATION,MISSION)),('end_fleet_mission',(FORMATION,)),('plan_invasion',(FORMATION,STATE)),
                                           ('plan_seaborne_invasion',(FORMATION,FLEET,STATE)),('call_off_invasion',(FORMATION,)),('embark_troops',(FORMATION,FLEET)),
                                           ('land_troops',(FORMATION,)),('set_army_supply_priority',(FORMATION,('level','choice'))),('set_army_flag',(FORMATION,('flag','int'))),
                                           ('set_army_lending',(FORMATION,INDEX)),('send_new_ships_to_fleet',(FORMATION,)),('send_new_ships_to_reserve',()),
                                           ('recall_fleet_for_repairs',(FORMATION,)),('form_fleet',(('option','int'),)),('divide_army',(FORMATION,)),('divide_fleet',(FORMATION,)),
                                           ('combine_armies',(FORMATION,SOURCE)),('combine_fleets',(FORMATION,SOURCE)),('move_ships',(FORMATION,TARGET)),('move_ship',(SHIP,TARGET)),
                                           ('change_fleet_mission',(FORMATION,MISSION)),('change_fleet_mission_area',(FORMATION,REGION)),('station_fleet_in_state',(FORMATION,STATE)),
                                           ('rebase_fleet',(FORMATION,REGION)),('defend_against_invasion_at_sea',(FORMATION,FRONT)),('appoint_flagship',(SHIP,)),
                                           ('dismiss_flagship',(SHIP,)))),
    Lever('make_peace',SINGLE,(('offer_peace',(WAR,)),('offer_white_peace',(WAR,)),('accept_peace_offer',(WAR,)),('press_war_goal',(PLAY,GOAL,COUNTRY)),
                               ('drop_war_goal',(PLAY,GOAL,COUNTRY)))),
    Lever('national_decisions',SINGLE,(('take_national_decision',(DECISION,)),('take_journal_option',(ENTRY,('button','int'))),('default_on_debt',()),
                                       ('toggle_decision_alert',(DECISION,)))),
    alone('interact_with_character',SINGLE,(CHARACTER,INTERACTION)),
    Lever('petition_overlord',SINGLE,(*dealt('petition_overlord'),*dealt('petition_overlord',ENDED),*state_deals('petition_overlord'))),
    Lever('accept_offers',ANSWER,(('agree_to_treaty',NATION),('accept_proposal',NATION),('accept_call_to_side',NATION))),
    Lever('decline_offers',ANSWER,(('refuse_treaty',NATION),('decline_proposal',NATION),('decline_call_to_side',NATION))),
    alone('concede_demand',ANSWER,NATION),
    alone('refuse_demand',ANSWER,NATION),
]
EVENTS=Lever('answer_event',ANSWER,(('answer_event',(EVENT,('option','int'))),))
PROPOSALS=(('agree_to_treaty','refuse_treaty'),('concede_demand','refuse_demand'),('accept_proposal','decline_proposal'),('accept_call_to_side','decline_call_to_side'))

NAMES=[lever.name for lever in LEVERS]
ACTIONS=[Action(name,lever.domain,params,lever.name) for lever in [*LEVERS,EVENTS] for name,params in lever.acts]
BY_NAME={action.name:action for action in ACTIONS}
LEVER={action.name:action.lever for action in ACTIONS}
PARAMS={action.name:action.params for action in ACTIONS}
KEYS=frozenset(kind for params in PARAMS.values() for _,kind in params)-frozenset(ENTITIES)-{'int','choice'}
ANSWERS=frozenset({'answer_event',*(name for names in PROPOSALS for name in names)})
LAW_ACTIONS=frozenset(name for name,params in PARAMS.items() if LAW in params)
PARTY_ACTIONS=frozenset({'raise_government','lower_government'})
CANCELLING=frozenset({'cancel_queued_construction'})
SITED={**dict.fromkeys((*SECTORS,*NAVAL),'build'),'downsize_building':'downsize',
       **dict.fromkeys(('switch_building_method','reset_building_methods','switch_methods_statewide','reset_methods_statewide'),'method')}
PLAY_ACTIONS=frozenset(name for name,params in PARAMS.items() if PLAY_TYPE in params)
