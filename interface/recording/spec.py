import json
import re
from pathlib import Path

from .capture import GROUPS

F,I2,I4,I8,B,T,H='float8','int2','int4','int8','bool','text','game_hours'
EPOCH_DATE=43808760
NULL_DATE=43791240

VOCABULARIES={
    'acceptance_status':('common/acceptance_statuses',),'ai_region_stance':('common/ai_strategic_region_stance_types',),'ai_strategy':('common/ai_strategies',),
    'alert_type':('common/alert_types',),'amendment_type':('common/amendments',),'battle_condition':('common/battle_conditions','common/naval_battle_conditions'),
    'building_type':('common/buildings',),'character_interaction':('common/character_interactions',),'character_role':('common/character_roles',),
    'character_trait':('common/character_traits',),'combat_unit_group':('common/combat_unit_groups',),'combat_unit_type':('common/combat_unit_types',),
    'commander_order':('common/commander_orders',),'commander_rank':('common/commander_ranks',),'company_charter_type':('common/company_charter_types',),
    'company_type':('common/company_types',),'country_definition':('common/country_definitions',),'country_rank':('common/country_ranks',),
    'country_type':('common/country_types',),'culture_type':('common/cultures',),'decision':('common/decisions',),'decree_type':('common/decrees',),
    'diplomatic_action_type':('common/diplomatic_actions',),'diplomatic_catalyst_type':('common/diplomatic_catalysts',),
    'diplomatic_play_type':('common/diplomatic_plays',),'discrimination_trait':('common/discrimination_traits',),'event_type':('events',),'goods':('common/goods',),
    'government_type':('common/government_types',),'harvest_condition_type':('common/harvest_condition_types',),'ideology':('common/ideologies',),
    'institution_type':('common/institutions',),'interest_group_trait':('common/interest_group_traits',),'interest_group_type':('common/interest_groups',),
    'journal_entry_type':('common/journal_entries',),'law_type':('common/laws',),'message_group':('common/messages',),
    'mobilization_option':('common/mobilization_options',),'modifier':('common/static_modifiers','common/modifiers'),
    'naval_mission_type':('common/naval_mission_types',),'objective':('common/objectives',),'objective_subgoal':('common/objective_subgoals',),
    'party_type':('common/parties',),'political_lobby_type':('common/political_lobbies',),'political_movement_type':('common/political_movements',),
    'pop_type':('common/pop_types',),'power_bloc_identity':('common/power_bloc_identities',),'power_bloc_map_texture':('common/power_bloc_map_textures',),
    'power_bloc_principle':('common/power_bloc_principles',),'production_method':('common/production_methods',),
    'production_method_group':('common/production_method_groups',),'religion':('common/religions',),
    'scripted_button':('common/scripted_buttons',),'scripted_progress_bar':('common/scripted_progress_bars',),'ship_modification':('common/ship_modifications',),
    'ship_type':('common/ship_types',),'social_class':('common/social_classes',),'state_region':('map_data/state_regions',),'state_trait':('common/state_traits',),
    'strait_definition':('common/strait_definitions',),'strategic_region':('common/strategic_regions',),'technology':('common/technology/technologies',),
    'terrain':('common/terrain',),'treaty_article_type':('common/treaty_articles',),'veterancy_level':('common/combat_unit_experience_levels',),
    'war_goal_type':('common/war_goal_types',),'game_rule_setting':('common/game_rules',),
    'localization_key':None,'scope_name':None,'ui_window':None,'antagonize_reason':None,'advisor':None,'action':None}

ENUMS=('ai_attitude','approval_state','battle_status','battle_type','building_owner_type','civil_war_side','civil_war_type','event_status','formation_flag',
       'formation_type','hq_type','influence_type','influence_type_reason','law_checkpoint_result','law_phase','managed_status','play_side','privatization_request',
       'scope_type','shipping_lane_type','slave_basket','supply_priority','supply_ship_construction_level','tariff_level','tax_level','toll_rate','treaty_side',
       'wage_level','war_goal_demand_type','war_goal_pressed','war_goal_status')

CHECKS={'budget_direction':('income','expense'),'tariff_direction':('import','export'),'goods_consumer':('pops','buildings','government','military'),
        'migration_direction':('inbound','outbound'),'diplomatic_play_role':('initiator','target','initiator_ally','target_ally','interested'),
        'diplomatic_side':('source','target'),'battle_role':('attacker','defender'),'expulsion_direction':('by_player','of_player'),
        'obligation_direction':('owes_player','player_owes'),'strait_type':('NATURAL','ARTIFICIAL'),'proposal_kind':('treaty','demand','sway','action_proposal')}


class Col:
    def __init__(self,name,kind,optional=False,entity=None,vocabulary=None,enum=None,check=None,sentinel=None,loose=False):
        self.name,self.kind,self.optional,self.entity,self.vocabulary,self.enum,self.check=name,kind,optional,entity,vocabulary,enum,check
        self.sentinels=((-1,) if entity else ())+(() if sentinel is None else (sentinel,))
        self.loose=loose


def f(name,kind,sentinel=None):
    return Col(name,kind,sentinel=sentinel)


def o(name,kind,sentinel=None):
    return Col(name,kind,True,sentinel=sentinel)


def r(name,entity=None,optional=True,sentinel=None,loose=False):
    return Col(name,I4,optional,entity=entity or name,sentinel=sentinel,loose=loose)


def rr(name,entity=None):
    return r(name,entity,False)


def v(name,vocabulary=None,optional=False):
    return Col(name,None,optional,vocabulary=vocabulary or name)


def ov(name,vocabulary=None):
    return v(name,vocabulary,True)


def e(name,enum=None,optional=False):
    return Col(name,I2,optional,enum=enum or name)


def oe(name,enum=None):
    return e(name,enum,True)


def x(name,check):
    return Col(name,T,check=check)


def d(name,unset=EPOCH_DATE):
    return Col(name,H,True,sentinel=unset)


class Table:
    def __init__(self,name,kind,owner,keys,columns,scope):
        self.name,self.kind,self.owner,self.keys,self.columns,self.scope=name,kind,owner,keys,columns,scope


ENTITIES=[]
TABLES=[]


def entity(name,columns,scope='public'):
    ENTITIES.append(name)
    TABLES.append(Table(name+'_history','history',name,[],columns,scope))


def subject(name,owner,columns,scope='public'):
    TABLES.append(Table(name,'subject',owner,[],columns,scope))


def private(owner,columns):
    subject(owner+'_private',owner,columns,'player')


def child(name,owner,keys,columns=(),scope='public'):
    TABLES.append(Table(name,'child',owner,keys,list(columns),scope))


def sample(name,owner,columns,scope='public',keys=()):
    TABLES.append(Table(name,'sample',owner,list(keys),columns,scope))


def listing(name,keys,columns=(),scope='public'):
    TABLES.append(Table(name,'listing',None,keys,list(columns),scope))


def singleton(name,columns):
    TABLES.append(Table(name,'singleton',None,[],columns,'player'))


entity('country',[v('country_definition'),ov('government','government_type'),v('religion'),ov('country_rank'),ov('country_type'),r('ruler','character'),
                  r('capital','state'),r('market'),r('market_capital','state'),r('power_bloc'),r('founding_company','company'),o('map_color_override',I4,-1),
                  ov('dynamic_name_key','localization_key'),ov('dynamic_adjective_key','localization_key'),f('in_civil_war',B),f('trends_initialized',B),
                  f('bloc_leader',B)])
child('country_culture','country',[rr('culture')])
child('country_claim','country',[v('state_region')])
child('country_religion','country',[v('religion')])
child('country_dividend_building','country',[rr('building')])
child('country_leverage','country',[rr('power_bloc')],[f('leverage',F)])
child('country_timed_modifier','country',[f('modifier_id',I4)],[v('modifier'),f('multiplier',F),f('start_date',H),d('end_date'),f('decays',B)])
child('country_profession_population','country',[v('pop_type')],[f('population',I8)])
child('country_religion_culture_population','country',[v('religion'),rr('culture')],[f('population',I8)])
subject('country_population','country',[f('loyalists_increase',I4),f('loyalists_decrease',I4),f('radicals_increase',I4),f('radicals_decrease',I4)])
subject('country_diplomacy','country',[f('infamy',F)])
sample('country_weekly_sample','country',[f('gdp',F),f('average_standard_of_living',F)])
sample('country_population_sample','country',[f('population',I8)])

singleton('player_policy',[r('heir','character'),e('tax_level'),e('government_wage_level','wage_level'),e('military_wage_level','wage_level'),
                           e('supply_ship_construction_level'),f('can_toll_straits',B),f('can_close_straits',B),f('has_bloc_mandates',B)])
singleton('player_treasury',[f('money',F),f('investment_pool',F),f('investment_pool_change_from_investment',F),f('investment_pool_change_from_construction',F),
                             f('credit',F),f('principal',F),f('money_trend_current',F),f('balance_trend_current',F),d('money_trend_latest_sample_date',NULL_DATE),
                             d('balance_trend_latest_sample_date',NULL_DATE)])
singleton('player_population',[f('lower_strata',I8),f('middle_strata',I8),f('upper_strata',I8),f('radicals',I8),f('loyalists',I8),f('eligible_voters',I8)])
singleton('player_military',[f('supply_ships',I4)])
sample('player_weekly_sample',None,[f('prestige',I4),f('literacy',F)],'player')
sample('player_population_sample',None,[f('lower_strata',I8),f('middle_strata',I8),f('upper_strata',I8),f('radicals',I8),f('loyalists',I8)],'player')
listing('player_budget_line',[x('direction','budget_direction'),f('line',I2)],[f('amount',F)],'player')
listing('player_taxed_goods',[v('goods')],(),'player')
listing('player_ignored_decision',[v('decision')],(),'player')
listing('player_interaction_cooldown',[v('character_interaction')],[f('until',H)],'player')
listing('player_tariff',[x('direction','tariff_direction'),v('goods')],[e('level','tariff_level'),e('previous_level','tariff_level'),d('last_change')],'player')
listing('player_monopoly',[v('building_type')],(),'player')
listing('player_production_method_available',[v('production_method')],(),'player')
listing('player_consumed_goods',[x('consumer','goods_consumer'),v('goods')],(),'player')
listing('player_objective',[v('objective')],(),'player')
listing('player_completed_subgoal',[v('objective_subgoal')],(),'player')
listing('player_culture_standard_of_living',[rr('culture')],[f('standard_of_living',I8)],'player')
listing('player_culture_political_strength',[rr('culture')],[f('political_strength',I8)],'player')
listing('player_religion_political_strength',[v('religion')],[f('political_strength',I8)],'player')
listing('player_construction_queue_item',[f('private',B),f('position',I2)],[rr('state'),v('building_type'),ov('owner_building_type','building_type'),f('speed',F),
                                                                           f('construction_left',F)],'player')
listing('player_proposal',[rr('country'),x('kind','proposal_kind')],(),'player')
listing('player_adjacent_country',[rr('country')],(),'player')
listing('player_diplomat_expulsion',[rr('country'),x('direction','expulsion_direction')],(),'player')
listing('player_obligation',[rr('country'),x('direction','obligation_direction')],(),'player')
listing('player_formable_country',[f('name',T)],[f('position',I2),f('formable',B),f('ignored',B)],'player')
listing('player_releasable_country',[f('name',T)],[f('position',I2),f('possible',B)],'player')
listing('player_alert',[v('alert_type')],[f('instances',I4)],'player')
listing('player_state_alert',[v('alert_type'),rr('state')],(),'player')
listing('player_decision',[v('decision')],[o('takeable',B)],'player')
listing('player_message',[f('position',I2)],[f('date_text',T),v('message_group'),f('title',T),f('description',T)],'player')
listing('player_journal_button',[v('journal_entry_type'),v('scripted_button')],(),'player')
listing('player_treaty_enforced',[rr('first_country','country'),rr('second_country','country')],(),'player')
listing('player_diplomatic_option',[rr('target_country','country'),v('action_type','diplomatic_action_type')],[f('possible',B)],'player')
listing('player_diplomatic_option_state',[rr('target_country','country'),v('action_type','diplomatic_action_type'),x('side','diplomatic_side'),rr('state')],(),
        'player')
listing('player_character_interaction',[rr('character'),v('character_interaction')],[f('possible',B)],'player')
listing('player_colonization_paused',[rr('state')],(),'player')
listing('ui_open_window',[v('ui_window')],(),'player')

listing('player_relation',[rr('country')],[f('relations',I2),f('improve_relations',F),f('tension',F),d('player_truce'),d('country_truce')],'player')
entity('pact',[rr('first_country','country'),rr('second_country','country'),v('pact_type','diplomatic_action_type'),f('liberty_desire',F)])
entity('diplomatic_catalyst',[v('diplomatic_catalyst_type')])
private('diplomatic_catalyst',[r('country'),r('target_country','country'),f('date',H)])
entity('diplomatic_action',[rr('first_country','country'),rr('second_country','country'),v('action_type','diplomatic_action_type')])
entity('diplomatic_play',[rr('initiator','country'),rr('target','country'),v('diplomatic_play_type'),v('strategic_region'),f('initiator_maneuvers',I4),
                          f('target_maneuvers',I4),d('end_date'),f('escalation',I4),r('war')])
child('diplomatic_play_country','diplomatic_play',[rr('country'),x('role','diplomatic_play_role')])
child('diplomatic_play_record','diplomatic_play',[rr('country')],[e('play_side')],'player')
entity('treaty',[rr('first_country','country'),rr('second_country','country'),d('entered_into_force_on'),f('binding_period',I4),e('withdrawn_by','treaty_side'),
                 f('withdrawn',B)])
entity('treaty_article',[rr('treaty'),v('treaty_article_type'),r('source_country','country'),r('target_country','country')])
entity('power_bloc',[v('power_bloc_identity'),v('power_bloc_map_texture'),f('cohesion',F),f('mandate_progress',F)])
child('power_bloc_adopted_principle','power_bloc',[v('power_bloc_principle')])
entity('interest',[rr('country'),v('strategic_region'),f('involvement',F)])

entity('state',[v('state_region'),ov('localized_name_key','localization_key'),r('country'),r('mass_migration_culture','culture'),
                r('mass_migration_country','country'),r('slave_import_marker','state'),f('treaty_port_potential',B)])
private('state',[f('wage',F)])
child('state_timed_modifier','state',[v('modifier')],[f('instances',I4)])
child('state_slave_export_marker','state',[rr('marker','state')])
child('state_migration','state',[x('direction','migration_direction'),rr('other_state','state')])
child('state_goods','state',[v('goods')],[f('local_price',F),o('production',F),o('consumption',F),o('trade',F)])
child('state_pop_need','state',[v('culture_type'),f('need',I2),v('goods')],[f('weight',F)])
child('state_goods_supply','state',[v('goods')],(),'player')
child('state_decree_valid','state',[v('decree_type')],(),'player')
subject('state_population','state',[f('lower_strata',I8),f('middle_strata',I8),f('upper_strata',I8),f('radicals',I8),f('loyalists',I8),f('subsisting_workforce',I8),
                                    f('unemployed_workforce',I8),f('last_week_emigration',I4),f('last_week_immigration',I4),f('last_week_slave_emigration',I4),
                                    f('last_week_slave_immigration',I4)])
subject('state_economy','state',[f('arable_land',I4),f('infrastructure',F),f('infrastructure_usage',F),f('trade_capacity',I4),f('trade_capacity_usage',I4),
                                 f('treaty_port',B)])
subject('state_status','state',[f('incorporation',F),f('colony_progress',F),f('devastation',F),r('next_colony_province','province',sentinel=65535)])
entity('decree',[rr('owner','country'),r('state'),v('decree_type')])
listing('player_active_decree',[rr('state'),v('decree_type')],(),'player')
entity('pop',[rr('location','state'),r('workplace','building'),rr('culture'),v('religion'),v('pop_type'),v('social_class'),v('acceptance_status'),
              r('assimilation_culture','culture'),ov('conversion_religion','religion')])
subject('pop_status','pop',[f('wealth_progress',F),f('num_literate',I4),f('loyalists_and_radicals',I4),f('wealth',I4),f('food_security',F),f('political_strength',I8),
                            f('workforce',I8),f('dependents',I8),f('job_satisfaction',F)])
child('pop_movement_support','pop',[rr('political_movement')],[f('supporters',I8)])
entity('culture',[v('culture_type'),f('fervor',F),f('casualties_from_wars',I4),ov('national_awakening_state_region','state_region'),f('national_awakening_started',B)])
child('culture_core_state','culture',[v('state_region')])
child('culture_obsession','culture',[v('goods')])
child('culture_taboo','culture',[v('goods')])
child('culture_tradition','culture',[v('discrimination_trait')])
entity('cultural_community',[rr('culture'),rr('state'),f('acceptance_delta',F)])
listing('state_region_resource',[v('state_region'),v('building_type')],[f('available_levels',I4)])
listing('state_region_trait',[v('state_region'),v('state_trait')])
entity('harvest_condition',[v('harvest_condition_type'),v('state_region')])
child('harvest_condition_area','harvest_condition',[f('position',I2)],[f('intensity',F),f('duration',I4)])
entity('famine',[rr('state'),f('start_date',H),f('num_births',I4),f('num_deaths',I4)])
entity('province',[r('state'),r('controller','country')])

entity('building',[v('building_type'),r('state'),f('levels',I4),e('slave_basket'),f('active',B),f('subsidized',B),e('privatization_requested','privatization_request')])
private('building',[f('auto_expand',B),f('output_paused',B),f('monopoly',B),f('privatizable',B)])
subject('building_flow','building',[f('balance_subsidies',F),f('trade_revenue',F),f('input_goods_shortage',F),f('tariffs',F),f('tolls',F),f('subventions',F),
                                    f('supply_ship_construction',F),f('military_ship_construction',F),f('produced_supply',F),f('income_taxes',F),f('cash_reserves',F),
                                    f('staffing',F),f('throughput',F),f('salary_rate',F),f('dividends',F),f('goods_cost',F),f('goods_sales',F),f('slave_upkeep',F)])
child('building_production_method_active','building',[v('production_method')])
child('building_privatization_enabled','building',[rr('country')])
child('building_goods','building',[v('goods')],[o('input',F),o('output',F),o('slave_input',F)])
child('building_failed_hire','building',[f('position',I2)],[r('workplace','building')])
entity('building_ownership',[rr('building'),e('owner_type','building_owner_type'),f('owner',I4),f('levels',I4),f('privatization',B),f('in_owner_assets',B)])
entity('market',[rr('owner','country')])
child('market_goods','market',[v('goods')],[f('price',F),f('sell_orders',F),f('buy_orders',F)])
entity('market_area',[rr('market')])
child('market_area_state','market_area',[rr('state')],[f('port',B)])
listing('world_market_hub',[rr('state')],[f('trade_centers',I2)])
listing('world_market_price_channel',[v('goods')],[f('bucket',I2)])
sample('world_market_price_sample',None,[f('price',F)],keys=[v('goods')])
entity('company',[rr('country'),r('building'),r('ceo','character'),f('prosperity',F),v('company_type'),ov('company_name_key','localization_key'),
                  o('investment_charter',B),o('trade_charter',B),o('established',H)])
child('company_owned_country','company',[rr('country')])
entity('charter',[rr('company'),v('company_charter_type')])
private('charter',[f('unlock',H)])
entity('hq',[rr('country')])
private('hq',[e('hq_type'),ov('hq_region','strategic_region')])
entity('shipping_lane',[rr('country'),rr('begin_point','state'),rr('end_point','state'),f('convoy_cost',F),e('lane_type','shipping_lane_type')])
entity('strait',[v('strait_definition'),d('first_last_access_change'),d('second_last_access_change'),e('first_toll_rate','toll_rate'),e('second_toll_rate','toll_rate')])
child('strait_endpoint','strait',[],[rr('first_state','state'),rr('second_state','state'),x('strait_type','strait_type')],'player')
entity('country_research',[rr('country'),ov('researching','technology')],'player')
child('country_research_acquired','country_research',[v('technology')],(),'player')
child('country_research_spreading','country_research',[v('technology')],(),'player')
child('country_research_queued','country_research',[f('position',I2)],[v('technology')],'player')
child('country_research_progress','country_research',[v('technology')],[f('progress',F)],'player')

entity('interest_group',[rr('country'),v('interest_group_type'),v('name_key','localization_key'),r('party'),r('leader','character'),e('approval_state'),
                         e('influence_type'),f('in_government',B),e('influence_type_reason')])
private('interest_group',[e('civil_war_side'),r('party_to_join','party'),f('wants_to_leave_party',B),o('amenability',F),f('negotiated',B)])
subject('interest_group_stats','interest_group',[f('approval',I2),f('political_strength',I8),f('radicals_political_strength',I8),f('loyalists_political_strength',I8),
                                                 f('clout',F)])
child('interest_group_ideology','interest_group',[v('ideology')])
child('interest_group_character_ideology','interest_group',[v('ideology')])
child('interest_group_held_trait','interest_group',[v('interest_group_trait')],[f('enabled',B)])
child('interest_group_influencing_movement','interest_group',[rr('political_movement')])
child('interest_group_movement_support','interest_group',[rr('political_movement')],[f('clout',F)])
child('interest_group_pop','interest_group',[rr('pop')])
sample('interest_group_sample','interest_group',[f('clout',F),f('radicals',I8),f('loyalists',I8)])
entity('political_movement',[rr('country'),v('political_movement_type'),v('ideology'),f('radicalism',F),oe('managed_status'),r('civil_war')])
child('political_movement_character','political_movement',[rr('character')])
child('political_movement_character_ideology','political_movement',[v('ideology')])
child('political_movement_timed_modifier','political_movement',[v('modifier')],[d('end_date')])
entity('law',[rr('country'),v('law_type'),f('progress',F),e('phase','law_phase'),d('checkpoint_or_stop_date',NULL_DATE),f('active',B),r('imposer','country')])
private('law',[e('checkpoint_result','law_checkpoint_result'),ov('replacing_law_type','law_type'),d('enactment_start_date',NULL_DATE),o('chance',F)])
child('law_amendment','law',[rr('amendment')])
entity('amendment',[rr('law'),v('amendment_type'),r('sponsor','interest_group'),f('timeout',I4),d('timeout_date',NULL_DATE)])
entity('party',[rr('country'),v('party_type'),f('votes',I4)])
private('party',[f('num_voters',I4),r('leader','character',loose=True)])
child('party_member','party',[rr('interest_group')],(),'player')
entity('election',[rr('country'),d('next_election'),d('last_election'),f('electoral_confidence',F),f('campaign_period',B)],'player')
child('election_vote','election',[rr('party')],[f('momentum',F),f('raw_votes',I4),f('raw_num_voters',I4),f('last_votes',I4),f('last_num_voters',I4),
                                                d('last_vote_date')],'player')
entity('institution',[rr('country'),v('institution_type'),f('investment',I2)])
private('institution',[f('target_investment',I2),f('growth',F)])
entity('political_lobby',[rr('country'),rr('target_country','country'),v('political_lobby_type'),f('appeasement',I2)])
child('political_lobby_member','political_lobby',[rr('interest_group')])
entity('civil_war',[rr('origin_country','country'),e('civil_war_type'),f('progress',F),f('time',F),rr('political_movement'),f('conscription_rate',F)])
child('civil_war_interest_group','civil_war',[rr('interest_group')],(),'player')
child('civil_war_seceded_state','civil_war',[v('state_region')],[f('incorporated',B)])

entity('character',[rr('culture'),v('religion'),f('birth_date',H),v('first_name_key','localization_key'),v('last_name_key','localization_key'),f('noble',B),
                    f('historical',B),f('adult',B),r('country'),r('interest_group'),v('ideology'),f('prominence',I4),ov('order_type','commander_order'),
                    ov('rank','commander_rank'),r('formation'),d('travel_arrival_date'),r('assigned_state','state')])
private('character',[f('loyalty',I2),f('recruitable',B)])
child('character_status','character',[],[f('popularity',F),f('has_formation',B)],'player')
child('character_assigned_trait','character',[v('character_trait')])
child('character_assigned_role','character',[v('character_role')])
child('character_timed_modifier','character',[v('modifier')],[f('instances',I4)])
entity('combat_unit',[r('country'),r('formation'),r('building'),r('battle'),v('combat_unit_type'),v('veterancy_level'),f('manpower',I4),f('mobilization',F),
                      f('experience',F)])
entity('casualties',[r('unit','combat_unit'),r('building')])
child('casualties_event','casualties',[f('position',I2)],[r('battle')])
entity('formation',[rr('country'),e('formation_type'),ov('name_key','localization_key'),e('flag','formation_flag'),f('color_red',I2),f('color_green',I2),
                    f('color_blue',I2),r('supply_hub','state'),e('supply_priority'),r('attached_to_fleet','formation')])
subject('formation_status','formation',[r('province',sentinel=65535),o('current_location',I4,-1),o('target_location',I4,-1),r('naval_mission'),f('x',F),f('y',F),
                                         f('organization',F),f('sea_presence',F),f('supply',F),f('delivered_supply',F),f('supply_ships',I4),f('mobilized',B),
                                         f('raised_conscripts',B)])
private('formation',[rr('home_hq','hq'),r('strategic_objective','state'),f('travel_distance',F),f('default_fleet',B),f('demobilizing',B),f('invading',B),
                     f('embarked',B),f('docked',B),f('recalled',B),f('hit_points_percent',F),f('deployable',B),f('display_name',T)])
child('formation_mobilization_option','formation',[v('mobilization_option')])
child('formation_upgrade_unit_type','formation',[v('combat_unit_type')])
child('formation_selected_unit_type','formation',[v('combat_unit_group')],[v('combat_unit_type')])
child('formation_borrow_setting','formation',[f('name',T)],[f('position',I2),f('selected',B)],'player')
entity('ship',[r('fleet','formation'),f('hit_points',F),f('experience',F)])
child('ship_crew','ship',[f('position',I2)],[r('state'),f('crew',I4)])
entity('ship_construction',[rr('queue','ship_queue'),o('list_index',I4,-1),v('ship_type'),f('construction_left',F)],'player')
entity('ship_queue',[rr('country')],'player')
entity('ship_template',[rr('country'),v('ship_type'),f('ordinal_number',I2),f('year',I2)])
private('ship_template',[f('flags',I2),f('base',B)])
child('ship_template_fleet','ship_template',[rr('fleet','formation')],(),'player')
entity('ship_template_version',[rr('ship_template'),f('position',I2),v('ship_type')])
child('ship_template_version_modification','ship_template_version',[f('position',I2)],[v('ship_modification')])
entity('naval_mission',[v('naval_mission_type')])
entity('war',[r('diplomatic_play'),f('days_since_exhaustion',I4),d('peace_date'),r('peace_proposer','country'),d('peace_proposal_date')])
child('war_participant','war',[rr('country')],[rr('diplomatic_play'),f('war_support',F)])
entity('war_goal',[rr('holder','country'),rr('creator','country'),rr('diplomatic_play'),v('war_goal_type'),r('target_state','state'),r('target_country','country'),
                   o('target_other',I4,-1),e('demand_type','war_goal_demand_type'),e('status','war_goal_status'),e('pressed','war_goal_pressed')])
entity('front',[f('x',F),f('y',F)])
subject('front_advantage','front',[f('advantage',F)],'player')
child('front_listed_side','front',[rr('front_side')])
child('invasion','front',[rr('invader','country'),rr('invaded','country'),rr('state')],[f('ended',B)])
entity('front_side',[rr('front'),rr('war'),e('play_side')])
entity('occupation',[rr('state'),rr('controller','country')])
child('occupation_country','occupation',[rr('country')],[f('fraction',F)])
entity('battle',[rr('war'),r('front'),rr('province'),e('battle_type'),e('status','battle_status'),o('invasion',I4,-1),v('name_key','localization_key'),
                 f('start_date',H),d('end_date'),f('victory_score',F),f('occupation_score',F),o('still_fighting_samples',I4),d('still_fighting_date')])
child('battle_side','battle',[x('side','battle_role')],[r('commander','character'),rr('country'),r('formation'),ov('order_type','commander_order'),
                                                          ov('condition','battle_condition'),f('start_battalions',I4),f('end_battalions',I4),f('start_manpower',I4),
                                                          f('end_manpower',I4),f('start_morale',F),f('end_morale',F)])
child('battle_occupation','battle',[rr('state')],[f('fraction',F),f('occupation_progress',F)])
sample('battle_manpower_sample','battle',[f('attacker_manpower',I4),f('defender_manpower',I4)])
entity('country_ai',[rr('country')])
child('country_ai_strategy','country_ai',[f('position',I2)],[v('ai_strategy')])
child('country_ai_region_stance','country_ai',[v('strategic_region')],[v('stance','ai_region_stance')])
child('country_ai_goal','country_ai',[rr('target_country','country')],[f('neighbour',B),f('diplomatic_relevance',B),e('attitude','ai_attitude')])
child('country_ai_antagonize_reason','country_ai',[rr('target_country','country'),f('position',I2)],[v('reason','antagonize_reason'),f('score',F)])

entity('journal_entry',[r('country'),v('journal_entry_type'),f('active',B),f('goal_value',F),f('baseline_value',F),o('progress',F),o('goal',F),o('percent',F)],'player')
child('journal_entry_target','journal_entry',[v('name_key','scope_name')],[e('scope_type'),f('scope_target',I8)],'player')
child('journal_entry_progress_bar','journal_entry',[v('scripted_progress_bar')],[f('value',F)],'player')
child('journal_entry_timed_modifier','journal_entry',[v('modifier')],(),'player')
child('journal_entry_involved_country','journal_entry',[rr('country')],(),'player')
entity('event',[v('event_type'),rr('origin_country','country'),oe('status','event_status')],'player')
child('event_target','event',[v('name_key','scope_name')],[e('scope_type'),f('scope_target',I8)],'player')
child('event_option','event',[f('option',I2)],[f('enabled',B),f('default_option',B),o('visible_position',I2,-1),o('text',T),o('description',T)],'player')

TOPICS={
 'economy':['GetGDP','GetDomesticallyOwnedGDP','GetForeignOwnedGDP','GetGDPOwnedInForeignCountries','GetGDPWithOwnershipsInForeignCountries','GetTotalExportedAmount',
            'GetTotalImportedAmount','GetArableLand','GetUsedFreeCharters','GetNumIsolatedStates','GetNumLowMarketAccessStates','GetNumInsufficientTaxCapacityStates',
            'GetMerchantMarineShortage','GetNumCompanies','GetMaxNumCompanies','GetNumPreviousAutonomousInvestments','GetTotalForeignConstructions'],
 'treasury':['GetAverageStateTaxCollectionMult','GetAverageTaxWaste','GetGoldReserveRatio','GetGovernmentSelfDebt','GetInvestmentPoolChange','GetUnrealizedTaxes',
             'GetWeeklyFixedExpenses','GetWeeklyTemporaryExpenses','GetWeeklyTemporaryIncome','HasAnyTaxes','HasGovernmentWages','InDefault','GetYearlyInterestRate'],
 'spending':['GetPiracyIncome','GetPowerBlocIncomeRaw','GetArmyWagesExpenses','GetNavyWagesExpenses','GetGovernmentConstructionGoodsExpenses',
             'GetPrivateConstructionGoodsExpenses','GetShipConstructionGoodsExpenses','GetWelfarePaymentsExpenses','GetPowerBlocExpenseRaw'],
 'population':['GetDependents','GetInactivePopulation','GetIncorporatedPopulation','GetPoliticallyInvolvedPopulation','GetSalariedWorkingAdults',
               'GetSubsistingWorkingAdults','GetUnemployedWorkingAdults','GetPeopleAbroad','GetIncorporatedLiteracyRate','GetNumIncorporatedLiteratePops',
               'GetNumTotalLiteratePops','GetTotalLiteracyRate','GetLimitedMassMigrationCountryAttraction','GetRadicalizationFromBankruptcy',
               'GetLoyalistsOrRadicalsGainedFromLegitimacy','GetLoyaltiesGain'],
 'standard_of_living':['GetAverageSoLByPoliticalStrength','GetAverageSoLByPopulation','GetAverageStandardOfLivingMiddle','GetAverageStandardOfLivingPoor',
                       'GetAverageStandardOfLivingRich','GetExpectedSoLByPopulation','GetExpectedStandardOfLivingMiddle','GetExpectedStandardOfLivingPoor',
                       'GetExpectedStandardOfLivingRich'],
 'politics':['GetGovernmentLegitimacy','GetLawEnactmentProgress','GetDaysUntilElection','HasElections','GetMaxLawEnactmentSetbacks','GetNumAvailableNegotiations',
             'IsNegotiating','GetNumInterestGroupMembers','GetEmptyAgitatorSlots','HasIGApprovalFromLoyalists','HasIGApprovalFromRadicals',
             "GetPowerDelta('authority')","GetPowerDelta('bureaucracy')","GetPowerDelta('influence')","GetPowerIncome('authority')","GetPowerIncome('bureaucracy')",
             "GetPowerIncome('influence')",'GetNumTurmoilStates','GetNumStatesThatCanBeIncorporated','GetInstitutionInvestment',
             'GetInstitutionInvestmentBureaucracyCost','GetInstitutionInvestmentBureaucracyFactor'],
 'military':['CalcConscriptableBattalions','GetBattalions','GetRegularBattalions','GetMobilizationRatio','GetNumShips','GetSupplyNetworkNumSeaNodes',
             'GetSupplyNetworkStrength','GetSupplyNetworkStrengthTarget','GetSupplyNetworkStrengthWeeklyChange','GetEnemyOccupation','GetMilitaryShipCount',
             'GetCurrentSailors','GetNeededSailors','HasInsufficientMaxSailors','GetNumAssignedSupplyShips','GetNumAssignedSupplyShipsToFleets',
             'GetNumRequiredSupplyShipsToFleets','GetTotalSupplyShipCount','GetMilitaryMaintenanceDemand','GetMilitaryMaintenanceFulfillment',
             'GetSupplyMaintenanceDemand','GetSupplyMaintenanceFulfillment','GetMaxUnassignedAdmirals','GetMaxUnassignedGenerals','GetNumUnassignedAdmirals',
             'GetNumUnassignedGenerals','HasDefaultConstructionFleet'],
 'construction':['CalcBaseConstructionSpeed','CalcUsedConstruction','HasConstructionQueued','IsConstructionPaused','IsShipConstructionPaused',
                 'GetNumActiveGovernmentConstructionQueueElements','GetNumActivePrivateConstructionQueueElements','GetNumGovernmentConstructionsInQueue',
                 'GetNumInactiveAndNonShownGovernmentConstructionQueueElements','GetNumInactiveAndNonShownPrivateConstructionQueueElements',
                 'GetNumInactiveConstructionQueueElements','GetNumInactivePrivateConstructionQueueElements','GetNumPrivateConstructionsInQueue',
                 'GetFreeMilitaryConstructionCapacity','GetFreeSupplyConstructionCapacity','GetMilitaryConstructionCapacity','GetMilitaryConstructionQueueUsage',
                 'GetMilitaryConstructionUsageTotal','GetSupplyConstructionCapacity','GetSupplyConstructionQueueUsage','GetShipConstruction',
                 'GetShipConstructionUsage','GetShipConstructionWeeksLeft'],
 'diplomacy':['GetPrestige','GetRankProgress','GetCountryScorePosition','GetLibertyDesireRaw','GetWeeklyLibertyDesireChange',
              'GetWeeklyLibertyDesireChangeFromSupportIndependence','GetLeverageResistance','GetPowerBlocsTotalLeverageShare','GetTotalLeverageFactorsWithResistance',
              'GetUnclaimedLeverage','GetUnclaimedLeverageShare','GetUnclaimedLeverageShareTarget','GetUnclaimedLeverageTarget','HasHigherUnclaimedLeverage',
              'GetCurrentPowerStruggleMonth','GetMaxPowerStruggleMonth','IsPowerStruggling','HasActiveDiplomacy','IsColonizable','GetPrestigeToMaintainRank',
              'GetDaysUntilRankLoss'],
 'research':['GetWeeklyInnovation','GetWeeklyMaxInnovation','GetWeeklyResearchSpeed','HasCurrentlyResearchedTechnology']}
STATE_TOPICS={
 'population':['GetNumberOfPopsPoor','GetNumberOfPopsMiddle','GetNumberOfPopsRich','GetPopBirthrate','GetPopMortality','GetPopNetGrowth','GetPopTotalChange',
               'GetWeeklyPopNetMigration','GetMigrationPull','GetNumJobseekers','GetTotalLabor','GetLiteracy','GetUrbanization','GetUrbanizationNeededPerLevelRaw',
               'HasInsufficientQualificationsForAvailablePositions','GetConscriptionLimit'],
 'standard_of_living':['GetAverageStandardOfLivingAll','GetAverageStandardOfLivingMiddle','GetAverageStandardOfLivingPoor','GetAverageStandardOfLivingRich',
                       'GetExpectedStandardOfLivingAll','GetExpectedStandardOfLivingMiddle','GetExpectedStandardOfLivingPoor','GetExpectedStandardOfLivingRich',
                       'GetPopulationRatioBelowExpectedStandardOfLiving','GetObstinance','GetNumObstinanceSupporters','CalcTurmoil','HasTurmoilEffects'],
 'economy':['GetGDPContribution','GetGDPContributionPercentage','GetYearlyGDP','GetAverageAnnualWage','GetTaxationRevenue','CalcTaxCapacity','CalcTaxCapacityUsage',
            'GetGovernmentExpenses','GetBureaucracyCost','GetBaseBureaucracyCostRaw','GetBasePopBureaucracyCostRaw','CalcPopInstitutionBureaucracyCost',
            'GetMarketAccess','GetWorldMarketAccess','GetTradePotential','GetInfrastructure','GetInfrastructureUsage','GetNumBuildingsAffectedByGoodsShortage',
            'GetNumFreeArableLand','GetNumBaseFreeArableLand','GetNumArableLandReservedForSubsistence','GetPollutionGeneration','IsMarketCapital','IsSlaveState'],
 'status':['GetColonyProgressAsDays','GetDailyColonyProgress','GetNumColonizers','IsColonyProgressBlockedByInactiveInterest','IsCompanyColony','IsIncorporated',
           'IsIncorporating','GetYearsToIncorporate','GetBlockadeLevel','GetCurrentBlockadeStrength','GetRequiredBlockadeStrength','GetDevastationDailyChange',
           'GetDailyDevastationIncreaseFromBombardment','HasFamine','IsSplitState']}
METRIC_NAMES={'GetInfrastructure':'infrastructure_recomputed','GetInfrastructureUsage':'infrastructure_usage_recomputed','GetArableLand':'arable_land_total',
              'IsMarketCapital':'is_market_capital_reported','HasFamine':'has_famine_reported','GetNumCompanies':'num_companies_reported',
              'GetShipConstruction':'ship_construction_capacity'}

DROPPED_COUNTRY_METRICS={
 'GetInfamy':('country_diplomacy','infamy'),'GetGoldReserves':('player_treasury','money'),'GetInvestmentPool':('player_treasury','investment_pool'),
 'GetMaxCredit':('player_treasury','credit'),'GetPrincipal':('player_treasury','principal'),'GetNumLoyalists':('player_population','loyalists'),
 'GetNumRadicals':('player_population','radicals'),'GetTotalNumLoyalistsIncrease':('country_population','loyalists_increase'),
 'GetTotalNumLoyalistsDecrease':('country_population','loyalists_decrease'),'GetTotalNumRadicalsIncrease':('country_population','radicals_increase'),
 'GetTotalNumRadicalsDecrease':('country_population','radicals_decrease'),'GetNumSupplyShips':('player_military','supply_ships'),
 'GetNumAvailableSupplyShips':('player_military','supply_ships'),'GetTotalPopulation':('country_profession_population','sum(population)'),
 'GetElectoralConfidence':('election_history','electoral_confidence'),'GetTotalNumLoyalistsChange':('country_population','loyalists_increase - loyalists_decrease'),
 'IsInPowerBloc':('country_history','power_bloc is not null'),'GetWeeklyExpenses':('player_treasury','weekly_fixed_expenses + weekly_temporary_expenses'),
 'GetGovernmentSelfDebtFraction':('player_treasury','government_self_debt / principal'),'GetRemainingCredit':('player_treasury','credit - principal'),
 'GetNumNeutrals':('player_population','total population - loyalists - radicals'),
 'GetTotalNumRadicalsChange':('country_population','radicals_increase - radicals_decrease'),'GetNumCombatUnitsAndShips':('country_military_report','battalions + num_ships'),
 'GetTotalMaintenanceDemand':('player_military','military_maintenance_demand + supply_maintenance_demand'),
 'GetNumActiveConstructionQueueElements':('player_construction','num_active_government_construction_queue_elements + num_active_private_construction_queue_elements'),
 'CalcNumStatesInTurmoil':('player_politics','num_turmoil_states'),'GetGDPPerCapita':('country_economy_report','trunc(gdp / total population, 5)'),
 'GetDomesticallyOwnedGDPFraction':('country_economy_report','trunc(domestically_owned_gdp / gdp, 5)'),
 'GetForeignOwnedGDPFraction':('country_economy_report','trunc(foreign_owned_gdp / gdp, 5)'),'GetCreditRatio':('player_treasury','trunc(principal / credit, 5)'),
 'GetIncomeTaxIncome':('player_budget_line','income 1'),'GetPollTaxIncome':('player_budget_line','income 2'),'GetInvestmentIncome':('player_budget_line','income 7'),
 'GetMarketFeesIncome':('player_budget_line','income 15'),'GetGovernmentSlavesExpenses':('player_budget_line','expense 1'),
 'GetGovernmentGoodsExpenses':('player_budget_line','expense 2'),'GetGovernmentWagesExpenses':('player_budget_line','expense 3'),
 'GetMilitarySlavesExpenses':('player_budget_line','expense 4'),'GetMilitaryGoodsExpenses':('player_budget_line','expense 5'),
 'GetMilitaryWagesExpenses':('player_budget_line','expense 6'),'GetConstructionGoodsExpenses':('player_budget_line','expense 7'),
 'GetSubsidiesExpenses':('player_budget_line','expense 8'),'GetSubventionsExpenses':('player_budget_line','expense 9'),
 'GetInterestPayment':('player_budget_line','expense 10'),'GetSupplyShipConstructionGoodsExpenses':('player_budget_line','expense 17'),
 'GetMilitaryShipConstructionGoodsExpenses':('player_budget_line','expense 18'),'GetSupplyShipMaintenanceExpenses':('player_budget_line','expense 19'),
 'GetMilitaryShipMaintenanceExpenses':('player_budget_line','expense 20'),'GetPortConnectionExpenses':('player_budget_line','expense 21')}
DROPPED_STATE_METRICS={
 'GetNumRadicals':('state_population','radicals'),'GetNumLoyalists':('state_population','loyalists'),'GetTradeCapacity':('state_economy','trade_capacity'),
 'GetTradeCapacityUsage':('state_economy','trade_capacity_usage'),'GetColonyProgress':('state_status','colony_progress'),
 'GetIncorporationProgress':('state_status','incorporation'),'GetNumSubsistenceWorkingAdults':('state_population','subsisting_workforce'),
 'GetNumUnemployedWorkingAdults':('state_population','unemployed_workforce'),'GetArableLandCapacity':('state_economy','arable_land'),
 'IsTreatyPort':('state_economy','treaty_port'),'GetPopulationSize':('state_population','lower_strata + middle_strata + upper_strata'),
 'GetInfrastructureBalance':('state_economy','infrastructure - infrastructure_usage'),'GetTradeCapacityBalance':('state_economy','trade_capacity - trade_capacity_usage'),
 'CalcTaxCapacityBalance':('state_economy_report','tax_capacity - tax_capacity_usage'),'GetDevastationLevel':('state_status','trunc(devastation / 100, 5)'),
 'GetColonyProgressAsFloat':('state_status','trunc(colony_progress, 2)'),'IsCapitalState':('country_history','capital = state'),
 'HasOccupation':('occupation_history','an occupation row for the state')}
DROPPED_FIELDS={'country.construction_paused':'country_construction_report.is_construction_paused','ship_queue.paused':'country_construction_report.is_ship_construction_paused'}


TYPES={'CFixedPoint':F,'float':F,'int32':I4,'int64':I8,'bool':B}
PLAYER=set(GROUPS['player'])


def metric_name(name):
    if name in METRIC_NAMES:
        return METRIC_NAMES[name]
    match=re.fullmatch(r"(\w+)\('(\w+)'\)",name)
    if match:
        name=match.group(1)+match.group(2).title()
    name=re.sub(r'^(Get|Calc)','',name)
    name=name.replace('SoL','StandardOfLiving').replace('GDP','Gdp').replace('IG','InterestGroup')
    return re.sub(r'(?<!^)(?=[A-Z])','_',name).lower()


def target(name,owner):
    name=name if owner is None else name+'_report'
    for table in TABLES:
        if table.name==name:
            return table
    table=Table(name,'singleton',None,[],[],'player') if owner is None else Table(name,'child',owner,[],[],'public')
    TABLES.append(table)
    return table


def attach_metrics():
    kinds=METRICS_KINDS
    for topics,dropped,captured,kind in ((TOPICS,DROPPED_COUNTRY_METRICS,set(GROUPS['public'])|PLAYER,'country'),
                                         (STATE_TOPICS,DROPPED_STATE_METRICS,set(GROUPS['state']),'state')):
        kept=[name for names in topics.values() for name in names]
        if len(kept)!=len(set(kept)) or set(kept)&set(dropped) or set(kept)|set(dropped)!=captured:
            raise SystemExit(f'{kind} metrics: missing {sorted(captured-set(kept)-set(dropped))} extra {sorted((set(kept)|set(dropped))-captured)} '
                             f'both {sorted(set(kept)&set(dropped))}')
        for topic,names in topics.items():
            for name in names:
                table=target(f'player_{topic}',None) if name in PLAYER else target(f'{kind}_{topic}',kind)
                table.columns.append(f(metric_name(name),TYPES[kinds[kind][name]]))
                METRIC_COLUMNS[kind,name]=(table.name,metric_name(name))
    scopes={t.name:t.scope for t in TABLES}
    for dropped in (DROPPED_COUNTRY_METRICS,DROPPED_STATE_METRICS):
        for name,(table,_) in dropped.items():
            if table not in scopes:
                raise SystemExit(f'{name} is replaced from unknown table {table}')
            if name not in PLAYER and scopes[table]!='public':
                raise SystemExit(f'{name} is captured for every owner but its replacement {table} is player-only')




METRIC_COLUMNS={}
METRICS_KINDS=json.loads((Path(__file__).parent/'metrics.json').read_text(encoding='utf-8'))
attach_metrics()
CLOSED={name for name,folders in VOCABULARIES.items() if folders}
TABLE={table.name:table for table in TABLES}
