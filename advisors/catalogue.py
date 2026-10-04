from collections import namedtuple

from interface.common import DEFAULT_GAME
from interface.script import body, fields, read

Action=namedtuple('Action','name domain params lever')
Lever=namedtuple('Lever','name domain acts')

GAME=DEFAULT_GAME/'game'
LAW_GROUP={name:dict(fields(body(text)))['group'][0] for name,text in read(GAME,'common/laws')}
LAW_CATEGORY={name:dict(fields(body(text)))['law_group_category'][0] for name,text in read(GAME,'common/law_groups')}
LAW_GROUPS=list(LAW_CATEGORY)
LAW_CATEGORIES=('power_structure','economy','human_rights')
INSTITUTIONS=[name for name,_ in read(GAME,'common/institutions')]
TECHNOLOGY_TREE={name:dict(fields(body(text)))['category'][0] for name,text in read(GAME,'common/technology/technologies')}
TECHNOLOGY_TREES=('production','military','society')
DUTIES=('max_subvention','high_subvention','low_subvention','none','low_tariff','high_tariff','max_tariff')
ENTITIES=('building','character','company','country','diplomatic_play','institution','interest_group','journal_entry','law','military_formation','political_movement',
          'power_bloc','ship','state','treaty','war')
CONSTRUCT,QUEUE,RAISE,LOWER,SINGLE,ANSWER='construct','queue','raise','lower','single','answer'

STATE=('state','state')
BUILDING=('building','building')
KIND=('building_type','building_type')
GOODS=('goods','goods')
COUNTRY=('country','country')
TREATY=('treaty','treaty')
LAW=('law','law')
GROUP=('interest_group','interest_group')
MOVEMENT=('political_movement','political_movement')
CHARACTER=('character','character')
FORMATION=('military_formation','military_formation')
UNIT=('combat_unit_type','combat_unit_type')
PLAY=('diplomatic_play','diplomatic_play')
PLAY_TYPE=('diplomatic_play_type','diplomatic_play_type')
GOAL=('war_goal_type','war_goal_type')
WAR=('war','war')
ARTICLE=('treaty_article','treaty_article')
GIVER=('giver','choice')
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
OPTION=('mobilization_option','mobilization_option')
ORDER=('commander_order_type','commander_order_type')
MISSION=('naval_mission_type','naval_mission_type')
REGION=('strategic_region','strategic_region')
DECISION=('decision','decision')
ENTRY=('journal_entry','journal_entry')
EVENT=('event','event')
BUILD=(STATE,KIND)
NATION=(COUNTRY,)
TROOPS=(FORMATION,UNIT)

SECTORS={'construct_construction_capacity':('building_construction_sector',),
         'construct_infrastructure':('building_railway','building_port'),
         'construct_food_production':('building_rye_farm','building_wheat_farm','building_rice_farm','building_maize_farm','building_millet_farm','building_vineyard',
                                      'building_livestock_ranch'),
         'construct_plantations':('building_coffee_plantation','building_cotton_plantation','building_dye_plantation','building_opium_plantation','building_tea_plantation',
                                  'building_tobacco_plantation','building_sugar_plantation','building_banana_plantation','building_silk_plantation'),
         'construct_raw_materials':('building_coal_mine','building_iron_mine','building_lead_mine','building_sulfur_mine','building_gold_mine','building_logging_camp',
                                    'building_fishing_wharf','building_whaling_station','building_oil_rig','building_rubber_plantation'),
         'construct_consumer_goods':('building_food_industry','building_textile_mill','building_furniture_manufactory'),
         'construct_industrial_goods':('building_tooling_workshop','building_paper_mill','building_glassworks','building_steel_mill','building_motor_industry',
                                       'building_chemical_plant','building_explosives_factory','building_synthetics_plant','building_electrics_industry',
                                       'building_automotive_industry','building_shipyard','building_power_plant'),
         'construct_military_goods':('building_arms_industry','building_artillery_foundry','building_munition_plant'),
         'construct_trade_capacity':('building_trade_center',),
         'construct_bureaucracy':('building_government_administration',),
         'construct_innovation':('building_university',)}
NAVAL_ADMINISTRATION='building_naval_administration'
COMMERCIAL=('trade_privilege','transit_rights','foreign_investment_rights','acquire_monopoly_for_company')
COMMERCIAL_GOODS=('goods_transfer','no_tariffs','no_subventions','prohibit_trade_with_global_market')
SECURITY=('alliance','defensive_pact','guarantee_independence','military_access','military_assistance')
GIVERS=('us','them','both')


def pair(name,more,less):
    return [Lever(f'raise_{name}',RAISE,more),Lever(f'lower_{name}',LOWER,less)]


def alone(name,domain,params=()):
    return Lever(name,domain,((name,params),))


def both(name,params=()):
    return pair(name,((f'raise_{name}',params),),((f'lower_{name}',params),))


LEVERS=[
    *[alone(name,CONSTRUCT,BUILD) for name in SECTORS],
    alone('cancel_queued_construction',QUEUE,BUILD),
    alone('raise_construction_priority',QUEUE,BUILD),
    alone('lower_construction_priority',QUEUE,BUILD),
    alone('downsize_building',QUEUE,(BUILDING,)),
    *both('subsidies',(BUILDING,)),
    *pair('state_ownership',(('nationalise_building',(BUILDING,('levels','int'))),('reserve_building_type_for_state',(KIND,)),('withdraw_building_from_sale',(BUILDING,))),
          (('offer_building_for_sale',(BUILDING,)),('end_state_monopoly',(KIND,)))),
    *pair('companies_and_charters',(('establish_company',(COMPANY_TYPE,)),('grant_charter',(COMPANY,CHARTER))),
          (('disband_company',(COMPANY_TYPE,)),('revoke_charter',(COMPANY,CHARTER)))),
    *both('import_tariff',(GOODS,)),
    *both('export_tariff',(GOODS,)),
    *pair('commercial_treaties',(('propose_commercial_article',(COUNTRY,ARTICLE,GIVER)),('propose_goods_article',(COUNTRY,ARTICLE,GOODS,GIVER))),
          (('lower_commercial_treaties',(TREATY,)),)),
    *both('embargoes',NATION),
    *both('tax_level'),
    *both('consumption_taxes',(GOODS,)),
    *both('government_wages'),
    *both('military_wages'),
    *both('institutions',(INSTITUTION,)),
    *both('state_decrees',(STATE,DECREE)),
    *both('government',(GROUP,)),
    *pair('political_movements',(('bolster_movement',(MOVEMENT,)),('stop_suppressing_movement',(MOVEMENT,))),
          (('suppress_movement',(MOVEMENT,)),('stop_bolstering_movement',(MOVEMENT,)))),
    *pair('relations',(('improve_relations',NATION),('stop_damaging_relations',NATION),('end_rivalry',NATION)),
          (('damage_relations',NATION),('declare_rivalry',NATION),('expel_diplomats',NATION),('stop_improving_relations',NATION))),
    *pair('security_treaties',(('raise_security_treaties',(COUNTRY,ARTICLE,GIVER)),),(('lower_security_treaties',(TREATY,)),)),
    *pair('power_bloc',(('found_power_bloc',(IDENTITY,PRINCIPLE)),('ask_to_join_power_bloc',(BLOC,)),('invite_to_power_bloc',NATION),('adopt_bloc_principle',(PRINCIPLE,))),
          (('leave_bloc',()),('remove_bloc_member',NATION),('refund_bloc_principle',(PRINCIPLE,)))),
    *pair('hold_over_subjects',(('lower_subject_autonomy',NATION),('raise_subject_payments',NATION),('end_service_exemption',NATION),('take_back_subject_market',NATION)),
          (('raise_subject_autonomy',NATION),('lower_subject_payments',NATION),('exempt_subject_from_service',NATION),('grant_subject_own_market',NATION),
           ('grant_independence',NATION))),
    *pair('confrontations',(('demand_of_country',(COUNTRY,PLAY_TYPE)),('demand_for_state',(STATE,PLAY_TYPE)),('add_demand',(PLAY,GOAL)),
                            ('make_demand_primary',(PLAY,GOAL,COUNTRY)),('sway_country',(PLAY,COUNTRY))),
          (('withdraw_from_confrontation',(PLAY,)),('surrender_war',(WAR,)))),
    *pair('colonies',(('establish_colony',(STATE,)),('resume_colony',(STATE,))),(('pause_colony',(STATE,)),('give_up_colony',(STATE,)))),
    *pair('regular_army',(('raise_regular_army',(FORMATION,UNIT,STATE)),),(('disband_battalions',TROOPS),('disband_army',(FORMATION,)))),
    *pair('mobilisation',(('mobilise_army',(FORMATION,)),('mobilise_all_armies',()),('call_up_conscripts',(FORMATION,UNIT,STATE)),('raise_army_conscripts',(FORMATION,)),
                          ('switch_on_mobilisation_option',(FORMATION,OPTION))),
          (('demobilise_army',(FORMATION,)),('demobilise_all_armies',()),('send_conscripts_home',TROOPS),('switch_off_mobilisation_option',(FORMATION,OPTION)))),
    *pair('navy',(('queue_ship',(SHIP_TYPE,)),('queue_ship_for_fleet',(SHIP_TYPE,FORMATION)),('construct_naval_administration',(STATE,))),
          (('cancel_queued_ship',(SHIP_TYPE,)),('scrap_ship',(SHIP,)),('disband_fleet',(FORMATION,)))),
    alone('change_production_method',SINGLE,(BUILDING,METHOD)),
    alone('incorporate_state',SINGLE,(STATE,)),
    *[Lever(f'laws_{category}',SINGLE,((f'enact_{category}_law',(LAW,)),(f'negotiate_{category}_law',(GROUP,)))) for category in LAW_CATEGORIES],
    *[Lever(f'research_{tree}',SINGLE,((f'research_{tree}_technology',(TECHNOLOGY,)),(f'queue_{tree}_technology',(TECHNOLOGY,)))) for tree in TECHNOLOGY_TREES],
    Lever('change_army_equipment',SINGLE,(('upgrade_regular_units',TROOPS),('upgrade_conscript_units',TROOPS),('set_standard_unit_type',TROOPS),('upgrade_every_unit',()))),
    Lever('disposition_of_forces',SINGLE,(('form_army',(('option','int'),)),('move_battalions',(FORMATION,('target','military_formation'))),('recruit_commander',(CHARACTER,)),
                                           ('recruit_commander_for',(CHARACTER,FORMATION)),('give_command',(CHARACTER,FORMATION)),('take_away_command',(CHARACTER,)),
                                           ('station_army',(FORMATION,STATE)),('station_army_at_headquarters',(FORMATION,REGION)),('rehome_army',(FORMATION,REGION)),('send_to_front',(FORMATION,('front','int'))),
                                           ('defend_against_invasion',(FORMATION,('front','int'))),('set_objective',(FORMATION,STATE)),('clear_objective',(FORMATION,STATE)),
                                           ('give_order',(CHARACTER,ORDER)),('start_fleet_mission',(FORMATION,MISSION)),('end_fleet_mission',(FORMATION,)),
                                           ('call_off_invasion',(FORMATION,)),('land_troops',(FORMATION,)),('set_army_supply_priority',(FORMATION,('level','choice'))),
                                           ('plan_invasion',(FORMATION,STATE)),('embark_troops',(FORMATION,)))),
    Lever('make_peace',SINGLE,(('offer_peace',(WAR,)),('offer_white_peace',(WAR,)),('accept_peace_offer',(WAR,)),('press_war_goal',(PLAY,GOAL,COUNTRY)),
                               ('drop_war_goal',(PLAY,GOAL,COUNTRY)))),
    Lever('national_decisions',SINGLE,(('take_national_decision',(DECISION,)),('take_journal_option',(ENTRY,('button','int'))))),
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
PLAY_ACTIONS=frozenset(name for name,params in PARAMS.items() if PLAY_TYPE in params)
