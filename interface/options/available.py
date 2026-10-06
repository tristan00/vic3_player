import re
from functools import lru_cache

from ..actions.catalogue import ACCESS_PERMISSIONS, ACCESS_STATUSES, ACTIONS, LEVELS, TOLL_LEVELS
from ..common import DEFAULT_GAME, progress, timed, timed_often
from ..script import body, fields, read
from ..recording.spec import METRIC_COLUMNS
from ..runner.memory import MONTH_STARTS

from .triggers import ENGAGED, Scope, autonomous, bloc_advantage, modifier_flag, character_scope, country_scope, evaluate, overlords, parse, subject_pairs
from .triggers import play_sides, play_enemies, indirect_overlords, stance, coastal as trigger_coastal, laws as trigger_laws, technologies as trigger_technologies
from .triggers import dlc_feature, homeland, primary_cultures

SLOT=0xFFFFFF


@timed_often
def product(**domains):
    combos=[{}]
    for name,values in domains.items():
        combos=[{**combo,name:value} for combo in combos for value in values]
    return combos


@timed_often
def building_ids(s):
    return [ident for ident,_,_ in s.buildings()]


CONSTRUCTION={'building_construction_sector'}


@timed_often
def market_owner(s):
    market=s.map('country','country,market').get(s.player)
    return s.map('market','market,owner').get(market)==s.player


TARIFF_CODES={'tariff':{'None':3,'Low':4,'High':5,'Max':6},'subvention':{'Low':2,'High':1,'Max':0}}
DEFAULT_TARIFF=3
COMPANY_LOCK_MONTHS=60
COMPANY_DISBAND_MONTHS=48
GRACE_HOURS=7*24
COOLDOWN_MONTHS=3


@timed_often
def calendar(hours):
    days=hours//24
    year,day=divmod(days,365)
    month=next(m for m in range(12,0,-1) if day>=MONTH_STARTS[m-1])
    return year,month,day-MONTH_STARTS[month-1]


@timed_often
def months_later(hours,months):
    year,month,day=calendar(hours)
    month+=months
    year,month=year+(month-1)//12,(month-1)%12+1
    return (year*365+MONTH_STARTS[month-1]+day)*24


@timed_often
def now(s):
    return s.hours


@timed_often
def tariffs(s,direction,column):
    return s.map('player_tariff','goods,'+column,direction=direction)


@timed_often
def tariff_open(s,direction,goods):
    changed=tariffs(s,direction,'last_change').get(goods)
    return changed is None or now(s)-changed<GRACE_HOURS or now(s)>months_later(changed,COOLDOWN_MONTHS)


@timed_often
def law_modifier(s,key):
    return modifier_total(s,'common/laws',active_laws(s),key)


@timed_often
def modifier_total(s,folder,names,key):
    total=0
    for name in names:
        for block in definition(s,folder,name,'modifier'):
            found=re.search(r'\b'+key+r'\s*=\s*(-?[\d.]+)',block)
            total+=float(found[1]) if found else 0
    return total


@timed_often
def institution_max(s,institution):
    acquired,_,_,_=technologies(s)
    key='country_'+institution+'_max_investment_add'
    return law_modifier(s,key)+modifier_total(s,'common/technology/technologies',acquired,key)


MIN_INSTITUTION=1


@timed_often
def institution_levels(s):
    kinds=s.map('institution','institution,institution_type',country=s.player)
    cost=metric(s,'GetInstitutionInvestmentBureaucracyCost')
    spare=metric(s,"GetPowerDelta('bureaucracy')")
    return [{'institution':ident,'level':level} for ident,current in s.rows('institution','institution,investment',country=s.player)
            for level in range(MIN_INSTITUTION,6) if level!=current and level!=changing(s).get(ident) and level<=institution_max(s,kinds[ident])
            and (level<=current or spare>=cost*(level-current))]


@timed_often
def trade_level(s,direction,goods):
    return tariffs(s,direction,'level').get(goods,DEFAULT_TARIFF)


@timed_often
def traded(s):
    return [goods for goods in s.keys('goods') if definition(s,'common/goods',goods,'local')!=['yes'] and definition(s,'common/goods',goods,'tradeable')!=['no']]


@timed_often
def trade_levels(s,direction,kind):
    if not market_owner(s):
        return []
    permitted=law_modifier(s,f'state_{kind}_{direction}_add')>0
    return [{'goods':goods,'level':level} for goods in traded(s) if tariff_open(s,direction,goods) for level,code in TARIFF_CODES[kind].items()
            if (level=='None' or permitted) and code!=trade_level(s,direction,goods)]


@lru_cache(maxsize=None)
@timed_often
def parsed(text):
    return parse(text)


@timed_often
def passes(s,folder,name,fields,scope):
    return all(evaluate(parsed(text),scope) is not False for field in fields for text in definition(s,folder,name,field))


@timed_often
def decidable(s,name):
    return passes(s,'common/decisions',name,('possible',),country_scope(s))


@timed_often
def state_regions(s):
    def compute():
        regions={state:region for region,fields in s.definitions('common/strategic_regions').items() for state in fields.get('states',())}
        return {ident:regions.get(key) for ident,key in s.rows('state','state,state_region')}
    return s.memo('state_regions',compute)




@timed_often
def interests(s):
    return {region for region, in s.rows('interest','strategic_region',country=s.player)}


@timed_often
def marker_required(s,play):
    return next(iter(definition(s,'common/diplomatic_plays',play,'requires_interest_marker')),'yes')!='no'


@timed_often
def engaged(s):
    return {region for region,involvement in s.rows('interest','strategic_region,involvement',country=s.player) if involvement>=ENGAGED}


@timed_often
def truce(s,country):
    sides={country}|{first for first,second in subject_pairs(s) if second==country}
    return bool(sides&truced(s))


@timed_often
def truced(s):
    return s.memo('truced',lambda:{country for country,own,theirs in s.rows('player_relation','country,player_truce,country_truce')
                                   if any(truce is not None and truce>now(s) for truce in (own,theirs))})


@timed_often
def reachable_state(s,state):
    owner=s.map('state','state,country').get(state)
    return (not busy(s) and not truce(s,owner) and owner not in opposed(s) and owner not in defensive_partners(s)
            and not s.map('country','country,in_civil_war').get(owner) and plays_permitted(s,owner,state_regions(s).get(state),state))


@timed_often
def reachable_country(s,country):
    capital=s.map('country','country,capital').get(country)
    return (not busy(s) and not truce(s,country) and country not in decentralized(s) and country not in guaranteed(s) and country not in defensive_partners(s)
            and not in_play(s,country) and not s.map('country','country,in_civil_war').get(country) and capital is not None and plays_permitted(s,country,state_regions(s).get(capital)))


@timed_often
def opposed(s):
    sides=play_sides(s)
    return {country for (play,side),members in sides.items() if s.player in sides.get((play,1-side),set()) for country in members}


@timed_often
def regions_in_play(s):
    return s.memo('regions_in_play',lambda:{region for region,war in s.rows('diplomatic_play','strategic_region,war') if war is None})


@timed_often
def country_regions(s,country):
    regions=state_regions(s)
    return {regions.get(state) for state, in s.rows('state','state',country=country)}


@timed_often
def plays_permitted(s,country,region,state=None):
    saved={'target_country':('country',country),'region':('strategic_region',region)}
    if state is not None:
        saved['state']=('state',state)
    return passes(s,'common/scripted_rules','can_start_diplomatic_plays_against',('body',),country_scope(s,**saved))


@timed_often
def in_force(s):
    return s.memo('in_force',lambda:{treaty:(first,second) for treaty,first,second,began,withdrawn in
                                    s.rows('treaty','treaty,first_country,second_country,entered_into_force_on,withdrawn') if began is not None and not withdrawn})


@timed_often
def proposed_treaties(s):
    return s.memo('proposed_treaties',lambda:{treaty:(first,second) for treaty,first,second,began in
                                             s.rows('treaty','treaty,first_country,second_country,entered_into_force_on') if began is None and s.player in (first,second)})


@timed_often
def guaranteed(s):
    return s.memo('guaranteed',lambda:{target for treaty,kind,target in s.rows('treaty_article','treaty,treaty_article_type,target_country',source_country=s.player)
                                      if kind=='guarantee_independence' and treaty in in_force(s)})


@timed_often
def defensive_partners(s):
    def compute():
        pairs=[in_force(s).get(treaty,()) for treaty,kind in s.rows('treaty_article','treaty,treaty_article_type') if kind=='defensive_pact']
        return {other for pair in pairs if s.player in pair for other in pair if other!=s.player}
    return s.memo('defensive_partners',compute)


@timed_often
def decentralized(s):
    return s.memo('decentralized',lambda:{country for country, in s.rows('country','country',country_type='decentralized')})


@timed_often
def rank_of(s,country):
    return s.map('country','country,country_rank').get(country)


@timed_often
def type_of(s,country):
    return s.map('country','country,country_type').get(country)


@timed_often
def rank_value(s,country):
    return float(next(iter(definition(s,'common/country_ranks',rank_of(s,country),'rank_value')),-1))


@timed_often
def subject_fits(s,subject_type,country,overlord=None):
    field=lambda name:definition(s,'common/subject_types',subject_type,name)
    above=s.player if overlord is None else overlord
    return ((not field('valid_overlord_country_types') or type_of(s,above) in field('valid_overlord_country_types'))
            and (not field('valid_subject_country_types') or type_of(s,country) in field('valid_subject_country_types'))
            and (not field('valid_overlord_ranks') or rank_of(s,above) in field('valid_overlord_ranks'))
            and (not field('valid_subject_ranks') or rank_of(s,country) in field('valid_subject_ranks'))
            and (field('overlord_must_be_higher_rank')!=['yes'] or rank_value(s,above)>rank_value(s,country)))


AUTONOMY_GOALS={'independence','increase_autonomy'}
UNIFYING_GOALS={'unification','unification_leadership'}


INDEPENDENCE_LIBERTY=90


@timed_often
def own_subject_pacts(s):
    return [(action,value) for action,value in s.rows('pact','pact_type,liberty_desire',second_country=s.player)
            if definition(s,'common/diplomatic_actions',action,'subject_pact')]


@timed_often
def liberty_desire(s):
    return next((value for _,value in own_subject_pacts(s)),0)


@timed_often
def claims(s):
    return {region for region, in s.rows('country_claim','state_region',country=s.player)}


@timed_often
def owns_here(s,country):
    mine=set(building_ids(s))
    return any(owner==country and building in mine for building,owner in s.rows('building_ownership','building,owner_country',owner_kind='country'))


@timed_often
def own_subject_type(s):
    return next((next(iter(definition(s,'common/diplomatic_actions',action,'subject_type')),None) for action,_ in own_subject_pacts(s)),None)


@timed_often
def subject_type_of(s,country):
    return next((next(iter(definition(s,'common/diplomatic_actions',action,'subject_type')),None) for action, in s.rows('pact','pact_type',second_country=country)
                 if definition(s,'common/diplomatic_actions',action,'subject_pact')),None)


@timed_often
def subject_permits(s,field):
    kind=own_subject_type(s)
    return kind is None or definition(s,'common/subject_types',kind,field)!=['no']


@timed_often
def debug_goal(s,kind):
    return 'debug' in definition(s,'common/war_goal_types',kind,'settings')


@timed_often
def play_allowed(s,play,liberating=False,**saved):
    scope=country_scope(s,**saved)
    target=saved.get('target_country',(None,None))[1]
    if any(debug_goal(s,goal) for goal in definition(s,'common/diplomatic_plays',play,'war_goal')):
        return False
    if (target,'player_owes') in obligations(s):
        return False
    kinds={next(iter(definition(s,'common/war_goal_types',goal,'kind')),'') for goal in definition(s,'common/diplomatic_plays',play,'war_goal')}
    if kinds&AUTONOMY_GOALS:
        if (target,s.player) not in subject_pairs(s):
            return False
    elif not subject_permits(s,'can_start_own_diplomatic_plays'):
        return False
    if any(kind.startswith('make_') for kind in kinds):
        if not subject_permits(s,'can_have_subjects') or target in {subject for _,subject in subject_pairs(s)}:
            return False
    if 'reduce_autonomy' in kinds and (target not in subjects(s) or not definition(s,'common/subject_types',subject_type_of(s,target),'lower_autonomy_subject_type_alternatives')):
        return False
    state=saved.get('target_state',(None,None))[1]
    if 'return_state' in kinds and s.map('state','state,state_region').get(state) not in claims(s):
        return False
    if 'force_nationalization' in kinds and not owns_here(s,target):
        return False
    if 'take_treaty_port' in kinds and not trigger_coastal(s,state):
        return False
    if 'independence' in kinds and liberty_desire(s)<INDEPENDENCE_LIBERTY:
        return False
    if kinds&UNIFYING_GOALS or ('liberate_country' in kinds)!=liberating:
        return False
    for goal in definition(s,'common/diplomatic_plays',play,'war_goal'):
        kind=next(iter(definition(s,'common/war_goal_types',goal,'kind')),'')
        if kind.startswith('make_') and not subject_fits(s,'subject_type_'+kind.removeprefix('make_'),target):
            return False
    goals=definition(s,'common/diplomatic_plays',play,'war_goal')
    return (passes(s,'common/diplomatic_plays',play,('potential','possible','selectable_in_lens'),scope)
            and all(passes(s,'common/war_goal_types',goal,('possible','valid'),scope) for goal in goals))


@timed
def recently_disbanded(s):
    def compute():
        rows=s.connection.execute('''select t.name,g.game_date from company_history h
            join snapshot g on g.run_id=h.run_id and g.seq=h.seq
            join lateral (select p.country,p.company_type from company_history p where p.run_id=h.run_id and p.company=h.company and p.seq<h.seq order by p.seq desc limit 1) last on true
            join company_type t on t.company_type=last.company_type
            where h.run_id=%s and h.seq<=%s and not h.present and last.country=%s''',(s.run_id,s.seq,s.player)).fetchall()
        return {kind for kind,disbanded in rows if now(s)<months_later(disbanded,COMPANY_DISBAND_MONTHS)}
    return s.memo('recently_disbanded',compute)


@timed_often
def held_companies(s):
    return {kind for kind, in s.rows('company','company_type',country=s.player)}


@timed_often
def companies(s):
    if metric(s,'GetNumCompanies')>=metric(s,'GetMaxNumCompanies'):
        return []
    if any(second==s.player and kind=='chartered_company' for _,second,kind in s.rows('pact','first_country,second_country,pact_type')):
        return []
    acquired,_,_,_=technologies(s)
    held=held_companies(s)
    principles=bloc_principles(s)
    potential={combo['building_type'] for combo in buildable(s)}|{kind for _,kind,_ in s.buildings()}
    scope=country_scope(s)
    return [name for name in s.keys('company_type') if name not in held and name not in recently_disbanded(s)
            and (not definition(s,'common/company_types',name,'unlocking_principles') or set(definition(s,'common/company_types',name,'unlocking_principles'))&principles)
            and any(set(definition(s,'common/buildings',kind,'unlocking_technologies'))<=acquired and kind in potential
                    for block in definition(s,'common/company_types',name,'building_types') for kind in block.split())
            and company_levels(s,{kind for block in definition(s,'common/company_types',name,'building_types') for kind in block.split()})>=COMPANY_MIN_LEVELS
            and passes(s,'common/company_types',name,('potential','attainable','possible'),scope)]


COMPANY_MIN_LEVELS=5


@timed_often
def located_buildings(s):
    return s.memo('located_buildings',lambda:{ident:(kind,state) for ident,kind,state in s.rows('building','building,building_type,state')})


@timed_often
def company_levels(s,kinds):
    def compute():
        mine=set(s.states())
        located=located_buildings(s)
        totals={}
        for building,kind,country,owner,levels in s.rows('building_ownership','building,owner_kind,owner_country,owner_building,levels'):
            name,state=located.get(building,(None,None))
            if state not in mine:
                continue
            owner_state=located.get(owner,(None,None))[1]
            if (country==s.player if kind=='country' else kind not in COMPANY_OWNERS and owner_state in mine):
                totals.setdefault(name,{})[state]=totals.get(name,{}).get(state,0)+levels
        return totals
    totals={}
    for name,states in s.memo('company_levels',compute).items():
        if name in kinds:
            for state,levels in states.items():
                totals[state]=totals.get(state,0)+levels
    return max(totals.values(),default=0)


@timed_often
def sectors(s):
    return [ident for ident,kind,_ in s.buildings() if kind in CONSTRUCTION]


@timed_often
def crew_max(s,version):
    kind=s.map('ship_template_version','ship_template_version,ship_type').get(version)
    parts=[('common/ship_types',kind)]+[('common/ship_modifications',mod) for _,mod in s.rows('ship_template_version_modification','position,ship_modification',ship_template_version=version)]
    return sum(float(found) for folder,name in parts for text in definition(s,folder,name,'modifier')
               for found in re.findall(r'ship_crew_max_add\s*=\s*(-?[\d.]+)',text))


@timed_often
def uncrewed_fleets(s):
    crew=s.grouped('ship_crew','ship,crew')
    minimum=float(definition(s,'common/defines','NMilitary|MINIMUM_SHIP_CREW_PERCENTAGE_TO_DEPLOY','value')[0])
    return {fleet for ship,fleet,version in s.rows('ship','ship,fleet,version') if sum(crew.get(ship,[]))<=minimum*crew_max(s,version)}


@timed_often
def mission_types(s,fleet):
    missions=s.map('naval_mission','naval_mission,naval_mission_type')
    current=missions.get(s.map('formation_status','formation,naval_mission').get(fleet))
    return [kind for kind in s.keys('naval_mission_type') if kind!=current and passes(s,'common/naval_mission_types',kind,('potential',),country_scope(s))]


@timed_often
def ship_queues(s):
    return {ident for ident, in s.rows('ship_queue','ship_queue',country=s.player)}


@timed_often
def ship_items(s):
    queues=ship_queues(s)
    return sorted(index for index,queue in s.rows('ship_construction','list_index,queue') if queue in queues)


@timed_often
def ship_paused(s):
    return bool(metric(s,'IsShipConstructionPaused'))


@timed_often
def construction_paused(s):
    return bool(metric(s,'IsConstructionPaused'))


@timed_often
def my_ships(s):
    queues=ship_queues(s)
    return [kind for kind,queue in s.rows('ship_construction','ship_type,queue') if queue in queues]


COMPANY_OWNERS={'company','company_regional_headquarter'}


@timed_often
def private_levels(s):
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    buildable=building_kinds(s,buildable=True)
    located=s.map('building','building,state')
    countries=s.map('state','state,country')
    levels={}
    for building,kind,owner,count in s.rows('building_ownership','building,owner_kind,owner_building,levels'):
        if kinds.get(building) in buildable and kind!='country' and count and countries.get(located.get(owner))==s.player:
            levels[building]=levels.get(building,0)+int(count)
    return levels


NATIONALIZATION_PER_POINT=500
MIN_CONSTRUCTION_POINTS=100


@timed_often
def nationalization_cost(s,building):
    kind=dict((ident,kind) for ident,kind,_ in s.buildings()).get(building)
    points=[float(value) for name in definition(s,'common/buildings',kind,'required_construction')
            for value in definition(s,'common/script_values',name,'value')]
    return NATIONALIZATION_PER_POINT*max(points+[MIN_CONSTRUCTION_POINTS])


@timed_often
def government_owned(s):
    mine=set(building_ids(s))
    return {building for building,owner,count in s.rows('building_ownership','building,owner_country,levels',owner_kind='country')
            if building in mine and owner==s.player and count}


@timed_often
def switchable(s):
    return {method for method, in s.rows('player_production_method_available','production_method')}


@timed_often
def monopolies(s):
    return {kind for kind, in s.rows('player_monopoly','building_type')}


def definition(s,folder,name,field):
    return s.definitions(folder).get(name,{}).get(field,[])


@timed_often
def building_kinds(s,**required):
    return {name for name,fields in s.definitions('common/buildings').items()
            if all((fields.get(field,['yes'])[0]!='no')==wanted for field,wanted in required.items())}


def inherited(s,kind,field):
    values=definition(s,'common/buildings',kind,field)
    group=next(iter(definition(s,'common/buildings',kind,'building_group')),None)
    while not values and group:
        values=definition(s,'common/building_groups',group,field)
        group=next(iter(definition(s,'common/building_groups',group,'parent_group')),None)
    return values


@timed_often
def private_kinds(s):
    monopolized=monopolies(s)
    return {kind for kind in building_kinds(s,buildable=True) if inherited(s,kind,'is_government_funded')!=['yes'] and kind not in monopolized}


@timed_often
def monopolizable(s):
    held=monopolies(s)
    return sorted(kind for kind in building_kinds(s,buildable=True) if definition(s,'common/buildings',kind,'unique')!=['yes']
                  and inherited(s,kind,'is_government_funded')!=['yes'] and (kind in held or (authority(s)>=MONOPOLY_COST and len(held)<MAX_MONOPOLIES)))


MONOPOLY_COST=100
MAX_MONOPOLIES=5


@timed_often
def free_arable(s,state):
    table,column=METRIC_COLUMNS['state','GetNumFreeArableLand']
    return need(s.map(table,'state,'+column).get(state),f'{column} of state {state}')


@timed_often
def owned_of(s,kinds):
    return [ident for ident,kind,_ in s.buildings() if kind in kinds]


@timed_often
def ownership_classes(s):
    def compute():
        mine=set(s.states())
        located=located_buildings(s)
        classes={}
        for building,kind,country,owner in s.rows('building_ownership','building,owner_kind,owner_country,owner_building'):
            if kind=='country':
                found='owned_national' if country==s.player else 'owned_foreign'
            elif owner in located:
                owner_state=located[owner][1]
                found='owned_company' if kind in COMPANY_OWNERS else 'owned_private' if owner_state in mine else 'owned_foreign'
            else:
                continue
            classes.setdefault(building,set()).add(found)
        return {building:found for building,found in classes.items() if located.get(building,(None,None))[1] in mine}
    return s.memo('ownership_classes',compute)


@timed_often
def bulk_subset(s,building_type,state,ownership):
    classes=ownership_classes(s)
    return [ident for ident,kind,_ in s.buildings() if kind==building_type and (state is None or s.map('building','building,state').get(ident)==state)
            and (ownership=='any' or ownership in classes.get(ident,()))]


@timed_often
def subset_options(s,kinds,wanted):
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    groups={}
    for ident,kind,_ in s.buildings():
        if kind in kinds:
            for ownership in ('any',*classes.get(ident,())):
                groups.setdefault((kind,located[ident],ownership),[]).append(wanted(s,ident))
    return [{'building_type':kind,'state':state,'ownership':ownership}
            for (kind,state,ownership),members in sorted(groups.items(),key=str) if all(members)]


@timed_often
def nationalizable_subsets(s):
    levels=private_levels(s)
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    costs={}
    for ident,count in levels.items():
        for ownership in ('any',*classes.get(ident,set())-{'owned_foreign'}):
            key=(kinds[ident],located[ident],ownership)
            costs[key]=costs.get(key,0)+nationalization_cost(s,ident)*count
    cash=money(s)
    return [{'building_type':kind,'state':state,'ownership':ownership}
            for (kind,state,ownership),cost in sorted(costs.items(),key=str) if cost<=cash]


@timed_often
def law_flag(s,modifier):
    return modifier_flag(s,s.player,modifier)


@timed_often
def privatizable(s,ident):
    return bool(setting(s,ident,'privatizable')) and not privatization_requested(s,ident)


@timed_often
def revolution_brewing(s):
    return bool(s.rows('civil_war','civil_war',origin_country=s.player))


PRIVATIZATION_REQUESTED=1


@timed_often
def privatization_requested(s,ident):
    return bool((s.map('building','building,privatization_requested').get(ident) or 0)&PRIVATIZATION_REQUESTED)


@timed_often
def active_laws(s):
    return {kind for kind, in s.rows('law','law_type',country=s.player,active=True)}


NO_DATE=43791240
PRINCIPLE_SLOTS=4
BLOC_INFLUENCE=500
ENACTMENT_COOLDOWN_HOURS=730*24


@timed_often
def enacting_laws(s):
    mine=set(s.mine('law'))
    return [ident for ident,started in s.rows('law_private','law,enactment_start_date') if ident in mine and started is not None and started!=NO_DATE]


@timed_often
def enacting(s):
    return bool(enacting_laws(s))


MIN_AMENABILITY=25
MARGINALIZED=2


@timed_often
def group_ideologies(s):
    return s.grouped('interest_group_ideology','interest_group,ideology')


@timed_often
def current_law(s,law):
    group=next(iter(definition(s,'common/laws',law,'group')),None)
    return next((name for name in active_laws(s) if definition(s,'common/laws',name,'group')==[group]),None)


@timed_often
def endorses(s,ideologies,law):
    return stance(s,ideologies,law)>stance(s,ideologies,current_law(s,law))


@timed_often
def governing(s):
    return [ident for ident, in s.rows('interest_group','interest_group',country=s.player,in_government=True)]


@timed_often
def opposed_in_government(s,law):
    ideologies=group_ideologies(s)
    clouts=s.map('interest_group_stats','interest_group,clout')
    stances=[(stance(s,ideologies.get(ident,[]),law),clouts[ident]) for ident in governing(s)]
    opposing=[clout for value,clout in stances if value<0]
    return law is not None and bool(opposing) and sum(opposing)>=sum(clout for value,clout in stances if value>0)


@timed_often
def endorsed(s,law):
    ideologies=group_ideologies(s)
    backers=[ideologies.get(ident,[]) for ident in governing(s)]
    ruler=[ideology for ident,ideology in s.rows('character','character,ideology',country=s.player) if 'character_role_ruler' in s.characters_roles(ident)]
    return any(endorses(s,values,law) for values in backers+[ruler])


@timed_often
def attached_amendments(s):
    def compute():
        active=set(s.mine('law'))&{ident for ident, in s.rows('law','law',active=True)}
        return {amendment for law,amendment in s.rows('law_amendment','law,amendment') if law in active}
    return s.memo('attached_amendments',compute)


REPEAL_COOLDOWN_MONTHS=120


@timed_often
def repealable(s):
    return {ident for ident,timeout,expiry in s.rows('amendment','amendment,timeout,timeout_date') if ident in attached_amendments(s)
            and (expiry is None or now(s)>=months_later(expiry,REPEAL_COOLDOWN_MONTHS-timeout))}


@timed_often
def negotiable(s):
    laws=s.map('law','law,law_type',country=s.player)
    enacting_law=next((laws[ident] for ident in enacting_laws(s)),None)
    if enacting_law is None or metric(s,'IsNegotiating') or metric(s,'GetNumAvailableNegotiations')<1:
        return []
    ideologies=group_ideologies(s)
    current=current_law(s,enacting_law)
    willing={ident for ident,amenability,negotiated in s.rows('interest_group_private','interest_group,amenability,negotiated')
             if amenability is not None and amenability>MIN_AMENABILITY and not negotiated}
    return [ident for ident,government,influence in s.rows('interest_group','interest_group,in_government,influence_type',country=s.player)
            if ident in willing and influence!=MARGINALIZED and (stance(s,ideologies.get(ident,[]),enacting_law)<stance(s,ideologies.get(ident,[]),current)
                                     or government and not endorses(s,ideologies.get(ident,[]),enacting_law))]


ILLEGITIMATE=25


@timed_often
def enactable(s):
    if enacting(s) or metric(s,'GetGovernmentLegitimacy')<=ILLEGITIMATE:
        return []
    acquired,_,_,_=technologies(s)
    active=active_laws(s)
    laws=s.definitions('common/laws')
    chances={ident:chance for ident,chance in s.rows('law_private','law,chance') if chance is not None}
    rows=[]
    for ident,kind,flag,stopped in s.rows('law','law,law_type,active,checkpoint_or_stop_date',country=s.player):
        fields=laws.get(kind,{})
        if stopped not in (None,NO_DATE) and now(s)-stopped<ENACTMENT_COOLDOWN_HOURS:
            continue
        if flag or not set(fields.get('unlocking_technologies',()))<=acquired or set(fields.get('disallowing_laws',()))&active:
            continue
        if fields.get('unlocking_laws') and not set(fields['unlocking_laws'])&active:
            continue
        if not chances.get(ident) or not endorsed(s,kind) or not passes(s,'common/laws',kind,('is_visible','can_enact'),country_scope(s)):
            continue
        rows.append(ident)
    return rows


@timed_often
def law_possible(s,country,law):
    fields=s.definitions('common/laws').get(law,{})
    held=trigger_laws(s,country)
    return (set(fields.get('unlocking_technologies',()))<=trigger_technologies(s,country)
            and (not fields.get('unlocking_laws') or set(fields['unlocking_laws'])&held)
            and not set(fields.get('disallowing_laws',()))&held
            and passes(s,'common/laws',law,('is_visible','can_enact'),country_scope(s,country))
            and all(passes(s,'common/law_groups',group,('change_allowed_trigger',),country_scope(s,country)) for group in fields.get('group',())))


@timed_often
def imposable(s):
    pending={owner for owner,imposer in s.rows('law','country,imposer') if imposer is not None}
    cooling={owner for owner, in s.rows('country_timed_modifier','country',modifier='impose_law_cooldown')}
    targets=subjects(s)-pending-cooling
    return [ident for ident,kind,owner,active in s.rows('law','law,law_type,country,active') if owner in targets and not active
            and law_possible(s,owner,kind) and all(evaluate(parsed(text),country_scope(s,target_country=('country',owner))) is not False
                                                   for text in definition(s,'common/laws',kind,'can_impose') or ['can_impose_law_default = yes'])]


@timed_often
def issued_decrees(s):
    return set(s.rows('player_active_decree','state,decree_type'))


@timed_often
def valid_decrees(s):
    return set(s.rows('state_decree_valid','state,decree_type'))


@timed_often
def decrees(s):
    acquired,_,_,_=technologies(s)
    active=active_laws(s)
    issued=issued_decrees(s)
    allowed=[name for name in s.keys('decree') if set(definition(s,'common/decrees',name,'unlocking_technologies'))<=acquired
             and (not definition(s,'common/decrees',name,'unlocking_laws') or set(definition(s,'common/decrees',name,'unlocking_laws'))&active)
             and authority(s)>=float(next(iter(definition(s,'common/decrees',name,'cost')),0))]
    valid=valid_decrees(s)
    return [{'state':state,'decree':name} for state in s.states() for name in allowed if (state,name) not in issued
            and (not definition(s,'common/decrees',name,'state_trigger') or (state,name) in valid)
            and passes(s,'common/decrees',name,('country_trigger',),country_scope(s))]


@timed_often
def unit_types_unlocked(s):
    acquired,_,_,_=technologies(s)
    return [name for name in s.keys('combat_unit_type') if set(definition(s,'common/combat_unit_types',name,'unlocking_technologies'))<=acquired]


@timed_often
def switch_methods(s):
    methods={}
    for kind,_,method in s.methods:
        methods.setdefault(kind,[]).append(method)
    active=s.grouped('building_production_method_active','building,production_method')
    allowed=switchable(s)
    return [{'building':ident,'production_method':method} for ident,kind,levels in s.buildings() if levels
            for method in methods.get(kind,()) if method in allowed and method not in active.get(ident,())]


@timed_often
def bulk_methods(s):
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    groups={(kinds[option['building']],located[option['building']],ownership,option['production_method'])
            for option in switch_methods(s) for ownership in ('any',*classes.get(option['building'],()))}
    return [{'building_type':kind,'state':state,'production_method':method,'ownership':ownership}
            for kind,state,ownership,method in sorted(groups,key=str)]


@timed_often
def unit_goods(s,folder,kind):
    return {goods for block in definition(s,folder,kind,'upkeep_modifier') for goods in re.findall(r'goods_input_(\w+)_add',block)}


@timed_often
def state_supply(s):
    return {state:set(goods) for state,goods in s.grouped('state_goods_supply','state,goods').items()}


@timed_often
def barracks_cap(s):
    acquired,_,_,_=technologies(s)
    blocks=[text for law in active_laws(s) for text in definition(s,'common/laws',law,'modifier')]
    blocks+=[text for tech in acquired for text in definition(s,'common/technology/technologies',tech,'modifier')]
    return sum(float(value) for text in blocks for value in re.findall(r'state_building_barrack_max_level_add\s*=\s*(-?[\d.]+)',text))


@timed_often
def recruit(s):
    supplies=state_supply(s)
    located=s.map('building','building,state')
    cap=barracks_cap(s)
    queued={state for state,kind in s.rows('player_construction_queue_item','state,building_type') if kind=='building_barrack'}
    barracks=[(ident,located.get(ident)) for ident,kind,levels in s.buildings() if kind=='building_barrack' and levels<cap and located.get(ident) not in queued]
    return [{'building':ident,'military_formation':formation,'combat_unit_type':kind}
            for ident,state in barracks for kind in unit_types_unlocked(s)
            if unit_goods(s,'common/combat_unit_types',kind)<=supplies.get(state,set())
            for formation in s.formations('army')]


@timed_often
def conscription_states(s):
    located=s.map('building','building,state')
    return sorted({located[ident] for ident,kind,levels in s.buildings() if kind=='building_conscription_center' and levels})


@timed_often
def subjects(s):
    return {second for first,second in subject_pairs(s) if first==s.player}


@timed_often
def power_bloc_members(s):
    blocs={ident:bloc for ident,bloc in s.rows('country','country,power_bloc') if bloc is not None}
    return sorted(ident for ident,bloc in blocs.items() if s.player in blocs and bloc==blocs[s.player] and ident!=s.player)


@timed_often
def research(s):
    return set(s.mine('country_research'))


@timed_often
def technologies(s):
    return s.memo('player_technologies',lambda:compute_technologies(s))


@timed_often
def compute_technologies(s):
    rows=research(s)
    acquired={kind for owner,kind in s.rows('country_research_acquired','country_research,technology') if owner in rows}
    queued={kind for owner,kind in s.rows('country_research_queued','country_research,technology') if owner in rows}
    current={kind for ident,kind in s.rows('country_research','country_research,researching') if ident in rows}
    requires={name:set(fields.get('unlocking_technologies',())) for name,fields in s.definitions('common/technology/technologies').items()}
    return acquired,queued,current,requires


@timed_often
def researchable(s):
    acquired,queued,current,requires=technologies(s)
    return [name for name in s.keys('technology') if name not in acquired|queued|current and requires.get(name,set())<=acquired and researchable_kind(s,name)]


@timed_often
def researchable_kind(s,name):
    return definition(s,'common/technology/technologies',name,'can_research')!=['no']


@timed_often
def group_kinds(s,field,value):
    groups=s.definitions('common/building_groups')
    def marked(group):
        while group is not None:
            fields=groups.get(group,{})
            if fields.get(field)==[value]:
                return True
            group=next(iter(fields.get('parent_group',())),None)
        return False
    return s.memo(('group_kinds',field,value),lambda:{kind for kind,fields in s.definitions('common/buildings').items() if marked(next(iter(fields.get('building_group',())),None))})


QUEUE_WEEKS=52


@timed_often
def queue_weeks(s):
    queued=[(speed,left) for private,speed,left in s.rows('player_construction_queue_item','private,speed,construction_left') if not private]
    pace=sum(speed for speed,_ in queued)
    return sum(left for _,left in queued)/pace if pace else float('inf') if queued else 0


@timed_often
def buildable(s):
    acquired,_,_,_=technologies(s)
    capacity={(region,kind):levels for region,kind,levels in s.rows('state_region_resource','state_region,building_type,available_levels')}
    built={(state,kind):levels for kind,state,levels in s.rows('building','building_type,state,levels')}
    regions={ident:region for ident,region in s.rows('state','state,state_region',country=s.player)}
    arable={region:set(fields.get('arable_resources',())) for region,fields in s.definitions('map_data/state_regions').items()}
    queued=set(s.rows('player_construction_queue_item','state,building_type'))
    combos=[]
    for kind,fields in s.definitions('common/buildings').items():
        if fields.get('buildable')==['no'] or fields.get('recruits_combat_units')==['yes'] or not set(fields.get('unlocking_technologies',()))<=acquired:
            continue
        for state,region in regions.items():
            if kind in group_kinds(s,'land_usage','rural'):
                if kind not in arable.get(region,set()) or free_arable(s,state)<1:
                    continue
            elif kind in group_kinds(s,'capped_by_resources','yes') and capacity.get((region,kind),0)<=built.get((state,kind),0):
                continue
            if (state,kind) in queued:
                continue
            if passes(s,'common/buildings',kind,('potential','possible','can_build','can_build_government'),Scope(s,'state',state,{'investor_country':('country',s.player)})):
                combos.append({'state':state,'building_type':kind})
    return combos


@timed_often
def construction_queue(s):
    return [(state,kind) for _,state,kind in sorted(s.rows('player_construction_queue_item','position,state,building_type',private=False))]


@timed_often
def queue_items(s,skip_first,skip_last):
    pairs=construction_queue(s)
    return [{'state':state,'building_type':kind} for state,kind in pairs[skip_first:len(pairs)-skip_last] if pairs.count((state,kind))==1]


@timed_often
def queued_buildings(s):
    pending=set(construction_queue(s))
    owned=set(s.states())
    return [ident for ident,kind,state in s.rows('building','building,building_type,state') if state in owned and (state,kind) in pending]


@timed_often
def subsidized(s,flag):
    owned=set(s.states())
    return [ident for ident,state,value in s.rows('building','building,state,subsidized') if state in owned and value==flag]


@timed_often
def settled(s,formations):
    places={ident:(current,target) for ident,current,target in s.rows('formation_status','formation,current_location,target_location')}
    return [formation for formation in formations if formation in places and places[formation][0]==places[formation][1]]


@timed_often
def war_fronts(s):
    wars=set(s.wars())
    return sorted({front for front,war in s.rows('front_side','front,war') if war in wars})


@timed_often
def deployable(s):
    return {formation for formation, in s.rows('formation_report','formation',deployable=True)}


@timed_often
def idle_armies(s):
    return [f for f in settled(s,armies(s,False)) if not demobilizing(s,f)]


@timed_often
def mobilization_options(s,formation):
    acquired,_,_,_=technologies(s)
    principles=bloc_principles(s)
    active=set(s.grouped('formation_mobilization_option','formation,mobilization_option').get(formation,()))
    return [name for name in s.keys('mobilization_option')
            if set(definition(s,'common/mobilization_options',name,'unlocking_technologies'))<=acquired
            and (not definition(s,'common/mobilization_options',name,'unlocking_principles') or set(definition(s,'common/mobilization_options',name,'unlocking_principles'))&principles)
            and passes(s,'common/mobilization_options',name,('possible',),Scope(s,'formation',formation))
            and (name not in active or passes(s,'common/mobilization_options',name,('can_be_turned_off',),Scope(s,'formation',formation)))]


@timed_often
def formation_setting(s,formation,column):
    return s.map('formation_private','formation,'+column).get(formation)


@timed_often
def formation_report(s,formation,column):
    return s.map('formation_report','formation,'+column).get(formation)


@timed_often
def demobilizing(s,formation):
    return (any(owner==formation and progress for owner,progress in s.rows('combat_unit','formation,mobilization'))
            or bool(formation_report(s,formation,'demobilizing')))


@timed_often
def armies(s,mobilized):
    manned=set(s.formations('army'))
    return [ident for ident,value in s.rows('formation_status','formation,mobilized') if ident in manned and value==mobilized]


@timed_often
def selected_units(s,formation):
    return dict(s.rows('formation_selected_unit_type','combat_unit_group,combat_unit_type',formation=formation))


@timed_often
def unit_group(s,kind):
    return next(iter(definition(s,'common/combat_unit_types',kind,'group')),None)


@timed_often
def upgradable(s,military_formation,combat_unit_type):
    selected=selected_units(s,military_formation).get(unit_group(s,combat_unit_type))
    pending={kind for kind, in s.rows('formation_upgrade_unit_type','combat_unit_type',formation=military_formation)}
    if selected is None or combat_unit_type in pending or selected not in definition(s,'common/combat_unit_types',combat_unit_type,'upgrades'):
        return False
    needed=unit_goods(s,'common/combat_unit_types',selected)
    supplies=state_supply(s)
    located=s.map('building','building,state')
    return all(needed<=supplies.get(located.get(building),set())
               for building,kind in s.rows('combat_unit','building,combat_unit_type',formation=military_formation) if kind==combat_unit_type)


@timed_often
def changing(s):
    current=s.map('institution','institution,investment')
    return {ident:target for ident,target in s.rows('institution_private','institution,target_investment') if target and target!=current.get(ident)}


@timed_often
def hq_regions(s):
    mine=set(s.mine('hq'))
    return {ident:(kind,region) for ident,kind,region in s.rows('hq_private','hq,hq_type,hq_region') if ident in mine and kind is not None}


@timed_often
def home_of(s,formation):
    return formation_setting(s,formation,'home_hq')


@timed_often
def at_home(s,formation):
    return state_regions(s).get(located(s,formation))==hq_regions(s).get(home_of(s,formation),(None,None))[1]


@timed_often
def march_components(s):
    def compute():
        allowed={s.player}|subjects(s)|overlords(s,s.player)
        colors=s.province_colors()
        state_of={colors[province]:state for province,state,controller in s.rows('province','province,state,controller') if controller in allowed and state is not None}
        parent={color:color for color in state_of}
        def root(color):
            while parent[color]!=color:
                parent[color]=parent[parent[color]]
                color=parent[color]
            return color
        for first,second in s.adjacency():
            if first in parent and second in parent:
                parent[root(first)]=root(second)
        found={}
        for color,state in state_of.items():
            found.setdefault(state,set()).add(root(color))
        return found
    return s.memo('march_components',compute)


TRANSFER_MINIMUM=4


@timed_often
def reaches(s,formation,region):
    components=march_components(s)
    here=components.get(located(s,formation),set())
    return any(components[state]&here for state,strategic in state_regions(s).items() if strategic==region and state in components)


@timed_often
def located(s,formation):
    return s.map('formation_status','formation,current_location').get(formation)


@timed_often
def home_region(s,formation):
    return hq_regions(s).get(home_of(s,formation),(None,None))[1]


@timed_often
def travelling(s,formation):
    return bool(formation_setting(s,formation,'travel_distance'))


@timed_often
def rehome(s):
    regions=hq_regions(s)
    kinds=s.map('formation','formation,formation_type',country=s.player)
    return [{'military_formation':formation,'strategic_region':region} for formation in idle_armies(s) if not travelling(s,formation)
            for kind,region in sorted(set(regions.values())) if kind==kinds[formation] and region!=regions.get(home_of(s,formation),(None,None))[1]
            and (kind!=0 or reaches(s,formation,region))]


@timed_often
def conscript_types(s,formation):
    kinds={ident:kind for ident,(kind,_) in located_buildings(s).items()}
    return sorted({unit for unit,building in s.rows('combat_unit','combat_unit_type,building',formation=formation)
                   if kinds.get(building)=='building_conscription_center'})


@timed_often
def regular_types(s,formation):
    kinds={ident:kind for ident,(kind,_) in located_buildings(s).items()}
    return sorted({unit for unit,building in s.rows('combat_unit','combat_unit_type,building',formation=formation)
                   if kinds.get(building)!='building_conscription_center'})


@timed_often
def formation_units(s,formations):
    return [{'military_formation':formation,'combat_unit_type':kind} for formation in formations for kind in regular_types(s,formation)]


@timed_often
def country_metric(s,country,name):
    table,column=METRIC_COLUMNS['country',name]
    if table.startswith('player_'):
        return s.rows(table,column)[0][0] if country==s.player and s.rows(table,column) else None
    return s.map(table,'country,'+column).get(country)


@timed_often
def metric(s,name):
    return need(country_metric(s,s.player,name),f'{name} of the player')


@timed_often
def need(value,what):
    if value is None:
        raise RuntimeError(f'{what} is not captured')
    return value


@timed_often
def authority(s):
    return metric(s,"GetPowerDelta('authority')")


@timed_often
def in_default(s):
    return bool(metric(s,'InDefault'))


@timed_often
def money(s):
    return need(player_value(s,'player_treasury','money'),'player money')


STRAIT_COOLDOWN_MONTHS=6
STRAIT_SIDES=('first','second')


@timed_often
def strait_sides(s):
    mine=set(s.states())-{state for state,controller in s.rows('occupation','state,controller') if controller!=s.player}
    sides=[]
    for strait,first,second in s.rows('strait_endpoint','strait,first_state,second_state'):
        held=[(side,state) for side,state in zip(STRAIT_SIDES,(first,second)) if state in mine]
        sides+=[(strait,side,state) for side,state in held[:1 if len(held)==2 else 2]]
    return sides


@timed_often
def strait_value(s,strait,column):
    return s.map('strait',f'strait,{column}').get(strait)


@timed_often
def strait_settable(s,strait,column):
    changed=strait_value(s,strait,column)
    return changed is None or now(s)>=months_later(changed,STRAIT_COOLDOWN_MONTHS)


@timed_often
def strait_requires(s,strait,field):
    return definition(s,'common/strait_definitions',strait_value(s,strait,'strait_definition'),field)==['yes']


@timed_often
def full_strait_control(s,strait):
    mine=set(s.states())
    return all(state in mine for first,second in s.rows('strait_endpoint','first_state,second_state',strait=strait) for state in (first,second))


@timed_often
def strait_tolls(s):
    if not player_value(s,'player_policy','can_toll_straits'):
        return []
    return [{'strait':strait,'level':level} for strait,side,_ in strait_sides(s)
            if (full_strait_control(s,strait) or not strait_requires(s,strait,'tolls_require_full_control')) and strait_settable(s,strait,f'{side}_last_toll_rate_change')
            for index,level in enumerate(TOLL_LEVELS) if strait_value(s,strait,f'{side}_toll_rate')!=index]


@timed_often
def strait_accesses(s):
    closing=player_value(s,'player_policy','can_close_straits')
    blocks={'Closed':'total_block_requires_full_control','NoMilitary':'military_block_requires_full_control'}
    return [{'strait':strait,'state':state,'access':status} for strait,side,state in strait_sides(s) if strait_settable(s,strait,f'{side}_last_access_change')
            for index,status in enumerate(ACCESS_STATUSES) if strait_value(s,strait,f'{side}_access_status')!=index
            and (status=='Open' or closing and (full_strait_control(s,strait) or not strait_requires(s,strait,blocks[status])))]


@timed_often
def strait_permissions(s):
    return [{'strait':strait,'state':state,'allowed':allowed} for strait,side,state in strait_sides(s) if strait_value(s,strait,f'{side}_access_status')
            for index,allowed in enumerate(ACCESS_PERMISSIONS,1) if strait_value(s,strait,f'{side}_access_permissions')!=index]


@timed_often
def player_value(s,table,column):
    rows=s.rows(table,column)
    return rows[0][0] if rows else None


FASTEST_SPEED='4'
DEFAULT_TAX_COST=100


@timed_often
def pop_needed(s):
    def compute():
        states=set(s.states())
        market=s.map('country','country,market').get(s.player)
        bought={goods for goods,orders in s.rows('market_goods','goods,buy_orders',market=market) if orders}
        institutional={goods for goods, in s.rows('player_consumed_goods','goods')}
        return {goods for state,goods,weight in s.rows('state_pop_need','state,goods,weight') if state in states and weight} & bought - institutional
    return s.memo('pop_needed',compute)


@timed_often
def taxable(s):
    taxed={goods for goods, in s.rows('player_taxed_goods','goods')}
    return [goods for goods in s.keys('goods') if goods in taxed or (goods in pop_needed(s)
            and authority(s)>=float(next(iter(definition(s,'common/goods',goods,'consumption_tax_cost')),DEFAULT_TAX_COST)))]


@timed_often
def movements(s,status):
    return [ident for ident,managed in s.rows('political_movement','political_movement,managed_status',country=s.player)
            if managed==status or (managed is None and authority(s)>=MOVEMENT_COST)]


MOVEMENT_COST=200
SUPPRESSED,PROMOTED=1,2


@timed_often
def other_levels(s,column):
    current=player_value(s,'player_policy',column)
    return [level for index,level in enumerate(LEVELS) if index!=current]


@timed_often
def promotable(s,character):
    rank=definition(s,'common/commander_ranks',s.map('character','character,rank').get(character),'rank_value')
    return bool(rank) and float(rank[0])<float(definition(s,'common/defines','NCharacters|HIGHEST_PROMOTION_RANK','value')[0])


@timed_often
def assigned(s,character):
    return s.map('character_status','character,has_formation').get(character) is True


@timed_often
def idle_room(s,character):
    kind='Admirals' if 'character_role_admiral' in s.characters_roles(character) else 'Generals'
    return metric(s,f'GetNumUnassigned{kind}')<metric(s,f'GetMaxUnassigned{kind}')


@timed_often
def fits(s,character,formation):
    army=s.map('formation','formation,formation_type',country=s.player).get(formation)==0
    return ('character_role_general' if army else 'character_role_admiral') in s.characters_roles(character)


@timed_often
def leaders(s,formation):
    return [ident for ident, in s.rows('character','character',country=s.player,formation=formation)]


@timed_often
def commanders_where(s,test):
    pool=set(recruitable(s))
    rows={ident:(formation,ident in pool) for ident,formation in s.rows('character','character,formation',country=s.player)}
    return [ident for ident in s.commanders() if ident in rows and test(*rows[ident])]


@timed_often
def involved(s):
    sides={ident:(initiator,target) for ident,initiator,target in s.rows('diplomatic_play','diplomatic_play,initiator,target')}
    interested={ident for ident, in s.rows('diplomatic_play_country','diplomatic_play',country=s.player,role='interested')}
    return sides,interested


OPENING_PHASE_END=21


@timed_often
def at_war_plays(s):
    return {play for play,war,level in s.rows('diplomatic_play','diplomatic_play,war,escalation') if war is not None or level>=100}


@timed_often
def play_of_war(s,war):
    return next((ident for ident, in s.rows('diplomatic_play','diplomatic_play',war=war)),None)


@timed_often
def war_of_play(s,play):
    linked=s.map('diplomatic_play','diplomatic_play,war').get(play)
    return next((war for war, in s.rows('war','war') if war==linked),None)


@timed_often
def negotiable_war(s,war):
    kind=next((kind for kind, in s.rows('diplomatic_play','diplomatic_play_type',war=war)),None)
    return next(iter(definition(s,'common/diplomatic_plays',kind,'allow_negotiated_peace')),'yes')!='no'


@timed_often
def war_leader(s,war):
    return any(s.player in (initiator,target) for initiator,target in s.rows('diplomatic_play','initiator,target',war=war))


@timed_often
def war_countries(s,war):
    play=s.map('war','war,diplomatic_play').get(war)
    return {country for country, in s.rows('war_participant','country',diplomatic_play=play)}


@timed_often
def has_say(s,war):
    play=play_of_war(s,war)
    return not overlords(s,s.player) and any(owner==play and s.player in (holder,target) for owner,holder,target in live_goals(s,'holder,target_country'))


@timed_often
def escalated(s):
    return {play for play,escalation in s.rows('diplomatic_play','diplomatic_play,escalation') if escalation>=OPENING_PHASE_END}


COUNTDOWN=80


@timed_often
def escalation(s,play):
    return s.map('diplomatic_play','diplomatic_play,escalation').get(play,0)


SIDES=('initiator','target')


@timed_often
def play_members(s):
    def compute():
        members={}
        for side,role in enumerate(SIDES):
            for play,country in s.rows('diplomatic_play_country','diplomatic_play,country',role=role):
                members.setdefault((play,side),set()).add(country)
        return members
    return s.memo('play_members',compute)


@timed_often
def committed(s,play):
    return {side for side in range(2) if s.player in play_members(s).get((play,side),set())}


HOSTILE=-80


@timed_often
def side_open(s,play,side):
    leaders=involved(s)[0].get(play,())
    mine=overlords(s,s.player)
    backers=play_members(s).get((play,1-side),set())
    return (len(leaders)==2 and relations(s,leaders[side])>HOSTILE and not mine&set(leaders) and not mine&backers
            and not truce(s,leaders[1-side]) and leaders[side] not in war_enemies(s))


@timed_often
def war_enemies(s):
    def compute():
        sides={}
        for (play,side),values in play_members(s).items():
            for value in values:
                sides.setdefault(play,({},{}))[side][value]=True
        for play,initiator,target in s.rows('diplomatic_play','diplomatic_play,initiator,target'):
            sides.setdefault(play,({},{}))[0][initiator]=True
            sides.setdefault(play,({},{}))[1][target]=True
        return {country for play in at_war_plays(s) for mine,theirs in (sides.get(play,({},{})),sides.get(play,({},{}))[::-1]) if s.player in mine for country in theirs}
    return s.memo('war_enemies',compute)


@timed_often
def interested_plays(s):
    sides,interested=involved(s)
    return sorted(ident for ident in interested if s.player not in sides.get(ident,()) and ident not in at_war_plays(s))


@timed_often
def third_party(s,start=OPENING_PHASE_END):
    return [play for play in interested_plays(s) if start<=escalation(s,play)<COUNTDOWN]


@timed_often
def opening(s):
    return [play for play in interested_plays(s) if escalation(s,play)<OPENING_PHASE_END]


@timed_often
def leaning(s,side):
    return s.memo(('leaning',side),lambda:{play for play, in s.rows('diplomatic_play_country','diplomatic_play',country=s.player,role=side+'_ally')})


@timed_often
def principal(s):
    sides,_=involved(s)
    ends=s.map('diplomatic_play','diplomatic_play,end_date')
    return sorted(ident for ident,pair in sides.items() if s.player in pair and ends.get(ident) is None)


@timed_often
def backable(s):
    return [play for play in principal(s) if play in escalated(s) and play not in at_war_plays(s)]


@timed_often
def busy(s):
    return any(play not in at_war_plays(s) for play in principal(s))


@timed_often
def colonies(s):
    mine=set(s.states())
    return [ident for ident,province in s.rows('state_status','state,next_colony_province') if ident in mine and province is not None]


@timed_often
def in_play(s,country):
    return any(country in members for members in play_sides(s).values())


@timed_often
def play_opposed(s,country):
    return bool(play_enemies(s,s.player)&({country}|overlords(s,country)|indirect_overlords(s,country)))


@timed_often
def incorporation(s):
    return s.map('state_status','state,incorporation')


@timed_often
def abandonable(s):
    progress=incorporation(s)
    return [] if in_play(s,s.player) else [state for state in colonies(s) if progress.get(state)!=1]


@timed_often
def colonizable(s):
    rows=s.rows('state','state,state_region,country')
    located=s.map('state','state,state_region')
    colonized={located.get(state) for state,province in s.rows('state_status','state,next_colony_province') if province is not None}
    blocked={region for state,region,country in rows if in_play(s,country)}
    frontier='law_frontier_colonization' in active_laws(s)
    barred=barred_regions(s)
    return sorted({region:state for state,region,country in rows if country in decentralized(s) and state_regions(s).get(state) in engaged(s)
                   and region not in colonized and region not in blocked and region not in barred and not truce(s,country)
                   and (not frontier or state in capital_frontier(s))}.values())


@timed_often
def barred_regions(s):
    acquired,*_=technologies(s)
    required={trait:set(fields.get('required_techs_for_colonization',())) for trait,fields in s.definitions('common/state_traits').items()}
    return {region for region,trait in s.rows('state_region_trait','state_region,state_trait') if required.get(trait,set())-acquired}


@timed_often
def capital_frontier(s):
    def compute():
        components=march_components(s)
        home=components.get(s.map('country','country,capital').get(s.player),set())
        owned=set(s.states())
        colors=s.province_colors()
        rows=s.rows('province','province,state')
        mine={colors[province] for province,state in rows if state in owned and components.get(state,set())&home}
        state_of={colors[province]:state for province,state in rows if state is not None}
        return {state_of[other] for first,second in s.adjacency() for near,other in ((first,second),(second,first))
                if near in mine and other not in mine and other in state_of}
    return s.memo('capital_frontier',compute)



@timed_often
def charter_toggles(s):
    unlocks=s.map('charter_private','charter,unlock')
    granted={(company,kind):unlocks.get(charter) for charter,company,kind in s.rows('charter','charter,company,company_charter_type')}
    return [{'company':company,'charter':charter} for company in s.mine('company') for charter in ('investment_charter','trade_charter')
            if (company,charter) not in granted or granted[company,charter] is not None and now(s)>=granted[company,charter]]


@timed_often
def shown_buttons(s,entry):
    shown=set(s.rows('player_journal_button','journal_entry_type,scripted_button'))
    return [button for button in definition(s,'common/journal_entries',entry,'scripted_button') if (entry,button) in shown]


@timed_often
def journal_button(s,ident,index):
    entry=s.map('journal_entry','journal_entry,journal_entry_type').get(ident)
    visible=shown_buttons(s,entry)
    return (entry,visible[index]) if index<len(visible) else None


@timed_often
def journal_buttons(s):
    combos=[]
    involved={entry for entry, in s.rows('journal_entry_involved_country','journal_entry',country=s.player)}
    for ident,entry,owner,active in s.rows('journal_entry','journal_entry,journal_entry_type,country,active'):
        if owner!=s.player and ident not in involved:
            continue
        visible=shown_buttons(s,entry)
        combos+=[{'journal_entry':ident,'button':index} for index,button in enumerate(visible)
                 if active and all(evaluate(parsed(text),country_scope(s,journal_entry=('journal_entry',ident))) is True
                                   for text in definition(s,'common/scripted_buttons',button,'possible'))]
    return combos


@timed_often
def play_types(s,target):
    targets={'country':('country','treaty_article'),'state':('state',)}[target]
    return [name for name in s.keys('diplomatic_play_type') if not definition(s,'common/diplomatic_plays',name,'never_selectable')
            and any(kind in targets for goal in definition(s,'common/diplomatic_plays',name,'war_goal') for kind in definition(s,'common/war_goal_types',goal,'target_type'))]


@timed_often
def war_goals(s):
    sides,_=involved(s)
    return [{'diplomatic_play':play,'war_goal_type':kind,'country':target} for play,kind,target,holder,creator,status in live_goals(s,'war_goal_type,target_country,holder,creator,status')
            if s.player in sides.get(play,()) and holder==s.player and creator==s.player and status==1 and target is not None]


UNMODELED_GOAL_SETTINGS={'validate_conflicts_annex_country','country_creation','validate_sole_formation_candidate','validate_take_treaty_port',
                         'targets_enemy_subject','has_other_stakeholder'}


@timed_often
def goal_targets(s,play,kind):
    target_type=definition(s,'common/war_goal_types',kind,'target_type')
    settings=set(definition(s,'common/war_goal_types',kind,'settings'))
    if target_type not in (['country'],['state'],['treaty_article']):
        return True
    if settings&UNMODELED_GOAL_SETTINGS:
        return set()
    leaders=involved(s)[0].get(play,())
    opponents={leader for leader in leaders if leader!=s.player} if s.player in leaders else set()
    goals=[row[1:] for row in live_goals(s,'war_goal_type,target_country,target_state,holder') if row[0]==play and row[1]==kind]
    if target_type==['state']:
        regions=s.map('state','state,state_region')
        targets={state for state,owner in s.rows('state','state,country') if owner in opponents}
        if 'requires_interest' in settings:
            targets={state for state in targets if state_regions(s).get(state) in interests(s)}
        if next(iter(definition(s,'common/war_goal_types',kind,'kind')),'')=='return_state':
            targets={state for state in targets if regions.get(state) in claims(s)}
        if 'validate_conflicts_conquer_state' in settings:
            targets-={state for _,_,state,_ in goals}
        owners=s.map('state','state,country')
        return {state for state in targets if goal_valid(s,kind,target_state=('state',state),target_country=('country',owners.get(state)))}
    targets=set(opponents)
    if 'validate_conflicts_war_goals_all' in settings:
        targets-={target for _,target,_,_ in goals}
    if 'validate_conflicts_make_subject' in settings:
        subjecting={name for name in s.keys('war_goal_type') if next(iter(definition(s,'common/war_goal_types',name,'kind')),'').startswith('make_')}
        targets-={target for owner,other,target in live_goals(s,'war_goal_type,target_country') if owner==play and other in subjecting}
    if 'validate_conflicts_war_goals_holder' in settings:
        targets-={target for _,target,_,holder in goals if holder==s.player}
    if 'validate_independence' in settings:
        targets&=overlords(s,s.player)
    if 'validate_increase_autonomy' in settings:
        targets&=overlords(s,s.player) if definition(s,'common/subject_types',own_subject_type(s),'higher_autonomy_subject_type_alternatives') else set()
    if next(iter(definition(s,'common/war_goal_types',kind,'kind')),'')=='reduce_autonomy':
        targets&={target for target in subjects(s) if definition(s,'common/subject_types',subject_type_of(s,target),'lower_autonomy_subject_type_alternatives')}
    if 'turns_into_subject' in settings:
        subject_type='subject_type_'+next(iter(definition(s,'common/war_goal_types',kind,'kind')),'').removeprefix('make_')
        targets={target for target in targets if subject_fits(s,subject_type,target)}
    if 'validate_revoke_claims' in settings:
        regions={region for region, in s.rows('state','state_region',country=s.player)}
        targets&={country for country,region in s.rows('country_claim','country,state_region') if region in regions}
    return {target for target in targets if goal_valid(s,kind,target_country=('country',target))}


@timed_often
def goal_valid(s,kind,**saved):
    return passes(s,'common/war_goal_types',kind,('valid',),country_scope(s,**saved))


@timed_often
def live_goals(s,columns):
    plays=set(s.plays())
    return [row for row in s.rows('war_goal','diplomatic_play,'+columns) if row[0] in plays]


@timed_often
def setting(s,building,column):
    return s.map('building_private',f'building,{column}').get(building)


@timed_often
def ship_types(s):
    acquired,_,_,_=technologies(s)
    return [name for name in s.keys('ship_type') if set(definition(s,'common/ship_types',name,'unlocking_technologies'))<=acquired
            and definition(s,'common/ship_types',name,'ship_group')!=['ship_group_supply_ships']]


@timed_often
def ship_slots(s,kind):
    slots=[(slot,mods.split()) for block in definition(s,'common/ship_types',kind,'modifications') for slot,mods in re.findall(r'(\w+) = \{([^}]*)\}',block)]
    return [(slot,mods) for slot,mods in slots if definition(s,'common/ship_modification_slots',slot,'utility')!=['yes']]


@timed_often
def latest_design(s,template):
    versions=sorted(s.rows('ship_template_version_list','position,ship_template_version',ship_template=template))
    return tuple(mod for _,mod in sorted(s.rows('ship_template_version_modification','position,ship_modification',ship_template_version=versions[-1][1]))) if versions else ()


@timed_often
def designed(s,kind):
    return {latest_design(s,template) for template,owner,ship_type in s.rows('ship_template','ship_template,country,ship_type') if owner==s.player and ship_type==kind}


@timed_often
def unlocked_modifications(s,kind):
    acquired,_,_,_=technologies(s)
    return [mod for _,mods in ship_slots(s,kind) for mod in mods
            if not definition(s,'common/ship_modifications',mod,'unlocking_technologies') or set(definition(s,'common/ship_modifications',mod,'unlocking_technologies'))&acquired]


@timed_often
def ship_designs(s):
    return [{'ship_type':kind,'ship_modification':mod} for kind in ship_types(s) for mod in unlocked_modifications(s,kind)
            if not any(mod in design for design in designed(s,kind))]


@timed_often
def cancellable_types(s):
    flags=s.map('ship_template_private','ship_template,flags')
    base=s.map('ship_template_private','ship_template,base')
    templates=own_templates(s)
    flagged={kind for (kind,_),template in templates.items() if flags.get(template,0)&1}
    defaults={template:kind for (kind,_),template in templates.items() if flags.get(template,0)&1 or kind not in flagged and base.get(template)}
    versions={version:defaults[template] for template,version in s.rows('ship_template_version_list','ship_template,ship_template_version') if template in defaults}
    queues=ship_queues(s)
    return {versions[version] for version,queue in s.rows('ship_construction','version,queue') if queue in queues and version in versions}


@timed_often
def templates_in_construction(s):
    building={version for version, in s.rows('ship_construction','version')}
    return {template for template,version in s.rows('ship_template_version_list','ship_template,ship_template_version') if version in building}


TEMPLATE_DELETING=4


@timed_often
def own_templates(s):
    base=s.map('ship_template_private','ship_template,base')
    flags=s.map('ship_template_private','ship_template,flags')
    first=s.first_seen('ship_template')
    mine=sorted((kind,not base.get(template),first[template],template) for template,owner,kind in s.rows('ship_template','ship_template,country,ship_type')
                if owner==s.player and not (flags.get(template) or 0)&TEMPLATE_DELETING)
    return {(kind,index):template for kind in {item[0] for item in mine} for index,(*_,template) in enumerate(item for item in mine if item[0]==kind)}


@timed_often
def non_default_templates(s):
    flags=s.map('ship_template_private','ship_template,flags')
    return {key for key,template in own_templates(s).items() if not flags.get(template,0)&1}


@timed_often
def fleet_templates(s):
    assigned=set(s.rows('ship_template_fleet','ship_template,fleet'))
    return [{'ship_type':kind,'index':index,'military_formation':fleet} for (kind,index),template in sorted(own_templates(s).items())
            for fleet in s.formations('fleet') if (template,fleet) not in assigned]


@timed_often
def retrofit_fleets(s,retrofitting):
    return [f for f in s.formations('fleet') if formation_report(s,f,'retrofitting')==retrofitting and (retrofitting or formation_report(s,f,'retrofittable'))]


JOIN_LEVERAGE=200


@timed_often
def bloc_leaders(s):
    return {country for country, in s.rows('country','country',bloc_leader=True)}


@timed_often
def below_leader(s,bloc):
    leader=next((c for c in bloc_leaders(s) if bloc in power_bloc_of(s,c)),None)
    return leader is not None and need(country_metric(s,s.player,'GetPrestige'),'player prestige')<need(country_metric(s,leader,'GetPrestige'),f'prestige of {leader}') or (
        leader is not None and rank_value(s,s.player)<rank_value(s,leader))


BLOC_MEMBERSHIP_MONTHS=6


@timed_often
def may_leave(s):
    bloc=next(iter(power_bloc_of(s,s.player)))
    identity=s.map('power_bloc','power_bloc,power_bloc_identity').get(bloc)
    joined=s.map('country','country,power_bloc_join_date').get(s.player)
    return (joined is not None and now(s)>=months_later(joined,BLOC_MEMBERSHIP_MONTHS)
            and passes(s,'common/power_bloc_identities',identity,('can_leave',),country_scope(s)))


@timed_often
def bloc_leader(s):
    return s.player in bloc_leaders(s)


@timed_often
def may_found_bloc(s):
    return (not power_bloc_of(s,s.player) and not overlords(s,s.player) and s.player not in decentralized(s) and not revolution_brewing(s)
            and 'law_isolationism' not in active_laws(s) and metric(s,"GetPowerDelta('influence')")>=BLOC_INFLUENCE
            and rank_value(s,s.player)>=float(next(iter(definition(s,'common/country_ranks','unrecognized_major_power','rank_value')),99)))


@timed_often
def power_bloc_of(s,country):
    bloc=s.map('country','country,power_bloc').get(country)
    return set() if bloc is None else {bloc}


@timed_often
def insurrectionary(s):
    uprisings={movement for movement, in s.rows('civil_war','political_movement',origin_country=s.player)}
    return {group for group,movement in s.rows('interest_group_movement_support','interest_group,political_movement') if movement in uprisings}


@timed_often
def party_blocs(s):
    blocs={}
    for group,party,governs in s.rows('interest_group','interest_group,party,in_government',country=s.player):
        if party is not None:
            blocs.setdefault(party,[]).append((group,governs))
    return [([group for group,_ in found],any(governs for _,governs in found)) for _,found in sorted(blocs.items())]


@timed_often
def governing_count(s):
    return len(governing(s))


@timed_often
def principle_allowed(s,principle):
    return passes(s,'common/power_bloc_principles',principle,('visible','possible'),country_scope(s))


@timed_often
def bloc_principles(s):
    return {kind for bloc,kind in s.rows('power_bloc_adopted_principle','power_bloc,power_bloc_principle') if bloc in player_blocs(s)}


@timed_often
def bloc_identity(s):
    return next((kind for bloc,kind in s.rows('power_bloc','power_bloc,power_bloc_identity') if bloc in player_blocs(s)),None)


@timed_often
def mandates(s):
    return bool(player_value(s,'player_policy','has_bloc_mandates'))


@timed_often
def player_blocs(s):
    return power_bloc_of(s,s.player)


@timed_often
def pressed_in(s,war):
    play=play_of_war(s,war)
    return any(flag for owner,holder,flag in live_goals(s,'holder,pressed') if owner==play and holder==s.player)


@timed_often
def revolution_against_player(s,war):
    return any(kind=='dp_revolution' and target==s.player for kind,target in s.rows('diplomatic_play','diplomatic_play_type,target',war=war))


@timed_often
def peace_open(s,war):
    date=s.map('war','war,peace_date').get(war)
    return date is None or now(s)>=date


@timed_often
def proposer(s,war):
    return s.map('war','war,peace_proposer').get(war)


@timed_often
def proposers(s,kind):
    return sorted({country for country, in s.rows('player_proposal','country',kind=kind)})


@timed_often
def recruitable(s):
    return [ident for ident, in s.rows('character_private','character',recruitable=True)]


@timed_often
def cooling(s):
    return {kind for kind,until in s.rows('player_interaction_cooldown','character_interaction,until') if until>now(s)}


@timed_often
def action_group_allows(s,action,country):
    groups=set(definition(s,'common/diplomatic_actions',action,'groups'))
    if 'overlord' in groups and country not in subjects(s):
        return False
    if 'subject' in groups and (country,s.player) not in subject_pairs(s):
        return False
    if groups&{'power_bloc_leader','power_bloc_member'} and country not in power_bloc_members(s):
        return False
    return True


AMICABLE,CORDIAL,COLD=50,20,-50


@timed_often
def relations(s,country):
    return s.map('player_relation','country,relations').get(country,0)


@timed_often
def pact_between(s,action,country):
    pacts=s.memo('pacts',lambda:set(s.rows('pact','first_country,second_country,pact_type')))
    return (s.player,country,action) in pacts or any((country,s.player,reverse) in pacts for reverse in definition(s,'common/diplomatic_actions',action,'reverse_pact'))


@timed_often
def rank_ladder(s,country):
    recognized=lambda c:type_of(s,c)=='recognized'
    ladder=sorted((r for r in s.definitions('common/country_ranks') if r!='decentralized_power' and r.startswith('unrecognized')!=recognized(country)),
                  key=lambda r:float(next(iter(definition(s,'common/country_ranks',r,'rank_value')),0)))
    return ladder.index(rank_of(s,country)) if rank_of(s,country) in ladder else None


@timed_often
def shared_interest(s,country):
    regions={}
    for owner,region,involvement in s.rows('interest','country,strategic_region,involvement'):
        if involvement>=ENGAGED:
            regions.setdefault(owner,set()).add(region)
    return bool(regions.get(s.player,set())&regions.get(country,set()))


@timed_often
def rivalry_allowed(s,country):
    if not shared_interest(s,country) or not autonomous(s,s.player) or not autonomous(s,country):
        return False
    mine,theirs=rank_ladder(s,s.player),rank_ladder(s,country)
    return (relations(s,country)<CORDIAL and (type_of(s,s.player)=='recognized')==(type_of(s,country)=='recognized')
            and mine is not None and theirs is not None and abs(mine-theirs)<=1)


DIPLOMATIC={'da_knowledge_sharing':lambda s,c:len(technologies(s)[0])>len(tech_of(s,c)),
            'da_request_knowledge_sharing':lambda s,c:len(tech_of(s,c))>len(technologies(s)[0]),
            'increase_relations':lambda s,c:relations(s,c)<AMICABLE and not pact_between(s,'damage_relations',c),
            'damage_relations':lambda s,c:relations(s,c)>COLD and not pact_between(s,'increase_relations',c),
            'rivalry':lambda s,c:rivalry_allowed(s,c) and not pact_between(s,'rivalry',c),
            'join_power_bloc':lambda s,c:not overlords(s,s.player) and any(bloc_advantage(s,bloc,s.player)>=JOIN_LEVERAGE and below_leader(s,bloc)
                                                                            for bloc in power_bloc_of(s,c)),
            'invite_to_power_bloc':lambda s,c:not power_bloc_of(s,c),
            'fund_lobbies':lambda s,c:rank_value(s,s.player)>=rank_value(s,c) and not in_default(s),
            'da_support_regime':lambda s,c:country_metric(s,c,'GetGovernmentLegitimacy') is not None and country_metric(s,c,'GetGovernmentLegitimacy')<75}


@timed_often
def diplomatic_options(s):
    return s.rows('player_diplomatic_option','target_country,action_type,possible')


@timed_often
def diplomatic_shown(s):
    return s.memo('diplomatic_shown',lambda:{(country,action) for country,action,_ in diplomatic_options(s)})


@timed_often
def diplomatic_possible(s):
    return s.memo('diplomatic_possible',lambda:{(country,action) for country,action,possible in diplomatic_options(s) if possible})


INFAMY_PACT_COST=((100,1.0),(50,.5),(25,.25))
LOBBY_PACT_COST_MAX=.5


@timed_often
def pact_cost_multiplier(s,country,action):
    infamy=s.map('country_diplomacy','country,infamy').get(s.player) or 0
    clout=s.map('interest_group_stats','interest_group,clout')
    members=s.grouped('political_lobby_member','political_lobby,interest_group')
    hostile=definition(s,'common/diplomatic_actions',action,'pact_hostile')==['yes']
    lobbied=sum(clout.get(group,0)*(1 if kind.startswith('lobby_pro')==hostile else -1)
                for lobby,owner,target,kind in s.rows('political_lobby','political_lobby,country,target_country,political_lobby_type')
                if owner==s.player and target==country for group in members.get(lobby,[]))
    rank=float(next(iter(definition(s,'common/country_ranks',rank_of(s,country),'diplo_pact_cost')),1))-1
    return (1+next((extra for threshold,extra in INFAMY_PACT_COST if infamy>=threshold),0)+rank
            +max(-LOBBY_PACT_COST_MAX,min(LOBBY_PACT_COST_MAX,lobbied)))


@timed_often
def diplomatic_allowed(s,country,action):
    return (set(definition(s,'common/diplomatic_actions',action,'unlocking_technologies'))<=technologies(s)[0]
            and (country,action) in diplomatic_possible(s)
            and passes(s,'common/diplomatic_actions',action,('maintain',),country_scope(s,target_country=('country',country),actor=('country',s.player)))
            and action_group_allows(s,action,country) and not pact_between(s,action,country)
            and metric(s,"GetPowerDelta('influence')")>=float(next(iter(definition(s,'common/diplomatic_actions',action,'pact_cost')),0))*pact_cost_multiplier(s,country,action)
            and DIPLOMATIC.get(action,lambda s,c:True)(s,country))


@timed_often
def obligations(s):
    return set(s.rows('player_obligation','country,direction'))


@timed_often
def tech_of(s,country):
    rows={ident for ident, in s.rows('country_research','country_research',country=country)}
    return {kind for owner,kind in s.rows('country_research_acquired','country_research,technology') if owner in rows}


@timed_often
def event_options(s):
    kinds=s.map('event','event,event_type')
    return [{'event':kinds[event],'option':visible} for event,enabled,visible in s.rows('event_option','event,enabled,visible_position')
            if visible is not None and enabled]


@timed_often
def remove_companies(s):
    owning={company for company, in s.rows('company_owned_country','company')}
    return [kind for ident,kind,established in s.rows('company','company,company_type,established',country=s.player)
            if ident not in owning and established is not None and now(s)>=months_later(established,COMPANY_LOCK_MONTHS)]


@timed_often
def invasions(s):
    return s.rows('invasion','front,ended',invaded=s.player)


@timed_often
def enforced_on_player(s):
    return set(s.rows('player_treaty_enforced','first_country,second_country'))


GOODS_INPUTS=({'goods'},{'goods','quantity'})
EXCHANGED=frozenset(next(action for action in ACTIONS if action.name=='exchange_treaty_articles').choices)
C_MEMBERSHIP='join_power_bloc'


@timed_often
def treaty_partners(s):
    waiting={country for pair in proposed_treaties(s).values() for country in pair}
    return sorted({country for country,_ in diplomatic_shown(s)}-waiting)


@timed_often
def treaty_allowed(s,country):
    return s.memo(('treaty_allowed',country),lambda:passes(s,'common/scripted_rules','can_sign_treaty_with',('body',),country_scope(s,other_country=('country',country))))


@timed_often
def compatible_article(article,selected):
    return not set(stated('common/treaty_articles',article,'mutual_exclusions'))&set(selected)


@timed_often
def threatened_articles(s):
    if not dlc_feature(s,'ep2_content'):
        return []
    return [option for option in treaty_articles(s,'directed',False,False)
            if passes(s,'common/scripted_rules','can_threaten_naval_hostilities',('body',),country_scope(s,other_country=('country',option['country'])))]


@timed_often
def articles_between(s):
    def compute():
        return {(source,target,kind) for treaty,kind,source,target in s.rows('treaty_article','treaty,treaty_article_type,source_country,target_country')
                if treaty in in_force(s)}
    return s.memo('articles_between',compute)


@lru_cache(maxsize=None)
@timed
def installed(folder):
    return {name:dict(fields(body(text))) for name,text in read(DEFAULT_GAME/'game',folder)}


@timed_often
def stated(folder,name,field):
    return installed(folder).get(name,{}).get(field) or []


@lru_cache(maxsize=None)
@timed
def ratification():
    terms={}
    for name,text in read(DEFAULT_GAME/'game','common/treaty_articles'):
        found=list(fields(body(text)))
        terms[name]=' '.join([' '.join(values) for field,values in found if field=='can_ratify']
                             +[' '.join(trigger) for field,values in found if field=='requirement_to_maintain'
                               for kind,trigger in fields(' '.join(values)) if kind=='trigger'])
    return terms


@timed_often
def parties(s,source,target):
    return country_scope(s,source,other_country=('country',target),source_country=('country',source),target_country=('country',target),
                         first_country=('country',source),second_country=('country',target))


@timed_often
def ratifiable(s,article,source,target):
    return evaluate(parsed(ratification()[article]),parties(s,source,target)) is not False


@timed_often
def treaty_articles(s,kind,offered,goods,amending=False):
    acquired=technologies(s)[0]
    combos=[]
    for article,fields in s.definitions('common/treaty_articles').items():
        inputs=set(fields.get('required_inputs',()))
        fitting=inputs==goods if isinstance(goods,set) else inputs in GOODS_INPUTS if goods else not inputs
        if fields.get('kind')!=[kind] or not fitting or not set(fields.get('unlocked_by_technologies',()))<=acquired:
            continue
        for country in sorted(set(standing_treaties(s).values())) if amending else treaty_partners(s):
            if not treaty_allowed(s,country):
                continue
            source,target=(s.player,country) if offered else (country,s.player)
            if not passes(s,'common/treaty_articles',article,('visible','possible'),parties(s,source,target)):
                continue
            if not ratifiable(s,article,source,target):
                continue
            if goods is True:
                combos+=[{'country':country,'treaty_article':article,'goods':item} for item in traded(s)]
            elif goods:
                combos.append({'country':country,'treaty_article':article})
            elif (source,target,article) not in articles_between(s):
                combos.append({'country':country,'treaty_article':article})
    return combos


@lru_cache(maxsize=None)
@timed
def pact_terms():
    terms={}
    for name,text in read(DEFAULT_GAME/'game','common/diplomatic_actions'):
        found=dict(fields(body(text)))
        if 'pact' in found and found.get('can_select_to_break')!=['no']:
            inner=dict(fields(' '.join(found['pact'])))
            terms[name]=(int(inner.get('forced_duration',['0'])[0]),' '.join(inner.get('actor_can_break',())),
                         None if inner.get('is_two_sided_pact')==['no'] else ' '.join(inner.get('target_can_break',())))
    return terms


@timed_often
def snapshot_hours(s,seq):
    return s.memo(('snapshot_hours',seq),lambda:s.connection.execute('select game_date from snapshot where run_id=%s and seq=%s',(s.run_id,seq)).fetchone()[0])


@timed_often
def opening_seq(s):
    return s.memo('opening_seq',lambda:s.connection.execute('select min(seq) from snapshot where run_id=%s',(s.run_id,)).fetchone()[0])


@timed_often
def breakable_pacts(s):
    seen=s.first_seen('pact')
    found=[]
    for pact,first,second,kind in s.rows('pact','pact,first_country,second_country,pact_type'):
        if s.player not in (first,second) or kind not in pact_terms():
            continue
        months,began,joined=pact_terms()[kind]
        can_break,other=(began,second) if first==s.player else (joined,first)
        if can_break is None or seen[pact]!=opening_seq(s) and now(s)<months_later(snapshot_hours(s,seen[pact]),months):
            continue
        if evaluate(parsed(can_break),country_scope(s,target_country=('country',other),actor=('country',s.player))) is not False:
            found.append({'country':other,'diplomatic_action':kind})
    return found


@timed_often
def replaceable_principles(s):
    held=bloc_principles(s)
    if not bloc_leader(s) or not mandates(s):
        return []
    identity=bloc_identity(s)
    groups=s.definitions('common/power_bloc_principle_groups')
    return [{'slot':slot,'power_bloc_principle':levels[0]} for slot in range(len(held)) for group in groups
            for levels in [definition(s,'common/power_bloc_principle_groups',group,'levels')] if levels and not set(levels)&held and principle_allowed(s,levels[0])
            and definition(s,'common/power_bloc_principle_groups',group,'unlocking_identity') in ([],[identity])
            and definition(s,'common/power_bloc_principle_groups',group,'blocking_identity')!=[identity]]


@timed_often
def marines(s,formation):
    kinds=regular_types(s,formation)
    return bool(kinds) and all(definition(s,'common/combat_unit_types',kind,'group')==['combat_unit_group_marines'] for kind in kinds)


@timed_often
def ashore(s):
    return [f for f in settled(s,s.formations('army')) if not formation_report(s,f,'embarked') and not formation_report(s,f,'invading') and not demobilizing(s,f)]


@timed_often
def embarkable(s):
    return [{'military_formation':army,'fleet':fleet} for army in ashore(s) if marines(s,army)
            for fleet in s.formations('fleet') if not formation_report(s,fleet,'retrofitting') and not formation_report(s,fleet,'invading')]


@timed_often
def war_enemies(s):
    plays={s.map('war','war,diplomatic_play').get(war) for war in s.wars()}
    sides=play_sides(s)
    return {member for (play,side),members in sides.items() if play in plays and s.player in sides.get((play,1-side),set()) for member in members}


@timed_often
def invadable(s):
    enemies=war_enemies(s)
    return [state for state,country in s.rows('state','state,country') if country in enemies]


@timed_often
def land_invasions(s):
    return [{'military_formation':army,'state':state} for army in ashore(s) for state in invadable(s)]


@timed_often
def naval_invasions(s):
    fleets=[fleet for fleet in s.formations('fleet') if not formation_report(s,fleet,'retrofitting') and not formation_report(s,fleet,'invading')]
    return [{'military_formation':army,'fleet':fleet,'state':state} for army in ashore(s) for fleet in fleets for state in invadable(s) if trigger_coastal(s,state)]


@timed_often
def seizable_subsets(s):
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    return [{'building_type':kind,'state':state,'ownership':ownership}
            for kind,state,ownership in sorted({(kinds[ident],located[ident],ownership) for ident in private_levels(s)
                                                for ownership in ('any',*classes.get(ident,set())-{'owned_foreign'})},key=str)]


@timed_often
def standard_methods(s):
    def compute():
        group_of={(kind,method):group for kind,group,method in s.methods}
        active=s.grouped('building_production_method_active','building,production_method')
        counts={}
        for ident,kind,levels in s.buildings():
            for method in active.get(ident,()) if levels else ():
                tally=counts.setdefault((kind,group_of.get((kind,method))),{})
                tally[method]=tally.get(method,0)+levels
        return {key:max(tally,key=tally.get) for key,tally in counts.items() if sorted(tally.values())[-2:].count(max(tally.values()))==1}
    return s.memo('standard_methods',compute)


@timed_often
def resettable(s):
    group_of={(kind,method):group for kind,group,method in s.methods}
    active=s.grouped('building_production_method_active','building,production_method')
    standard=standard_methods(s)
    return [ident for ident,kind,levels in s.buildings() if levels
            and any(standard.get((kind,group_of.get((kind,method))),method)!=method for method in active.get(ident,()))]


@timed_often
def moved_recently(s,modifier):
    return bool(s.rows('country_timed_modifier','country',country=s.player,modifier=modifier))


@timed_often
def settled_country(s):
    return not in_play(s,s.player) and not s.wars()


@timed_often
def capital_sites(s):
    if not settled_country(s) or moved_recently(s,'moved_capital_recently'):
        return []
    capital=s.map('country','country,capital').get(s.player)
    cultures=primary_cultures(s,s.player)
    return [state for state in s.states() if state!=capital and incorporation(s).get(state)==1 and any(homeland(s,state,culture) for culture in cultures)]


@timed_often
def market_capital_sites(s):
    if not settled_country(s) or not market_owner(s) or moved_recently(s,'moved_market_capital_recently'):
        return []
    capital=s.map('country','country,market_capital').get(s.player)
    return [state for state in s.states() if state!=capital and incorporation(s).get(state)==1]


BUILDING_CHARTERS={'monopoly_charter':'building_types','industry_charter':'extension_building_types'}
REGION_CHARTER='colonization_charter'


@timed_often
def building_charters(s):
    kinds=s.map('company','company,company_type',country=s.player)
    return [{'company':company,'charter':charter,'building_type':kind} for company in s.mine('company') for charter,field in BUILDING_CHARTERS.items()
            for kind in stated('common/company_types',kinds[company],field)]


@timed_often
def region_charters(s):
    return [{'company':company,'charter':REGION_CHARTER,'state':state} for company in s.mine('company') for state in colonizable(s)]


@timed_often
def fleet_ships(s):
    fleets=set(s.formations('fleet'))
    return [(ship,fleet) for ship,fleet in s.rows('ship','ship,fleet') if fleet in fleets]


@timed_often
def free_fleets(s):
    return [fleet for fleet in s.formations('fleet') if not formation_report(s,fleet,'invading') and not formation_report(s,fleet,'retrofitting')]


@timed_often
def divisible(s,fleets):
    counts={}
    for _,fleet in fleet_ships(s):
        counts[fleet]=counts.get(fleet,0)+1
    return [fleet for fleet in fleets if counts.get(fleet,0)>=2]


@timed_often
def mergeable(s,kind):
    return [{'military_formation':target,'source':source} for target in s.formations(kind) if not formation_report(s,target,'invading')
            for source in s.formations(kind) if source!=target and not formation_report(s,source,'invading')
            and not (demobilizing(s,source) and target in armies(s,True))]


@timed_often
def naval_regions(s):
    return sorted({region for kind,region in hq_regions(s).values() if kind==1})


@timed_often
def sea_regions(s):
    return [name for name,fields in s.definitions('common/strategic_regions').items() if not fields.get('capital_province') and name.startswith('region_interface_sea')]


@timed_often
def on_mission(s,wanted):
    fleets=set(s.formations('fleet'))
    return [fleet for fleet,mission in s.rows('formation_status','formation,naval_mission') if fleet in fleets and (mission is not None)==wanted
            and not formation_report(s,fleet,'retrofitting') and fleet not in uncrewed_fleets(s)]


@timed_often
def ship_kinds(s):
    kinds=s.map('ship_template_version','ship_template_version,ship_type')
    return {ship:kinds.get(version) for ship,version in s.rows('ship','ship,version')}


@timed_often
def ship_template_choices(s):
    kinds=ship_kinds(s)
    held=s.grouped('ship_template_version_list','ship_template,ship_template_version')
    versions=s.map('ship','ship,version')
    return [{'ship':ship,'index':index} for ship,_ in fleet_ships(s) for (kind,index),template in sorted(own_templates(s).items())
            if kind==kinds[ship] and versions[ship] not in held.get(template,())]


@timed_often
def state_picks(s,side):
    found={}
    for country,action,flank,state in s.rows('player_diplomatic_option_state','target_country,action_type,side,state'):
        if flank==side:
            found.setdefault((country,action),[]).append(state)
    return found


@timed_often
def owing(s,country,action):
    usable=definition(s,'common/diplomatic_actions',action,'can_use_obligations')==['yes']
    return ['None',*(name for name,direction,wanted in (('CallInObligation','owes_player',True),('OweObligation','player_owes',False))
                     if usable and ((country,direction) in obligations(s))==wanted)]


@timed_often
def state_actions(s,side):
    other=state_picks(s,'target' if side=='source' else 'source')
    return [{'country':country,'diplomatic_action':action,'state':state,'obligation':obligation}
            for (country,action),states in sorted(state_picks(s,side).items()) if (country,action) not in other and diplomatic_allowed(s,country,action)
            for state in states for obligation in owing(s,country,action)]


@timed_often
def state_trades(s):
    taken=state_picks(s,'target')
    return [{'country':country,'diplomatic_action':action,'given':given,'taken':wanted,'obligation':obligation}
            for (country,action),states in sorted(state_picks(s,'source').items()) if (country,action) in taken and diplomatic_allowed(s,country,action)
            for given in states for wanted in taken[country,action] for obligation in owing(s,country,action)]


@timed_often
def liberations(s):
    owners={}
    for state,region,country in s.rows('state','state,state_region,country'):
        owners.setdefault(country,set()).add(region)
    homelands={}
    for culture,region in s.rows('culture_core_state','culture,state_region'):
        homelands.setdefault(s.map('culture','culture,culture_type').get(culture),set()).add(region)
    found=[]
    for option in RULES['start_play_country'](s,liberating=True):
        held=owners.get(option['country'],set())
        for name in creatable(s):
            fields=installed('common/country_creation')[name]
            wanted=set(fields.get('states') or ())|{region for culture in stated('common/country_definitions',name,'cultures') for region in homelands.get(culture,())
                                                    if fields.get('use_culture_states')==['yes']}
            if wanted&held:
                found.append({**option,'country_definition':name})
    return found


@timed_often
def creatable(s):
    alive={kind for kind, in s.rows('country','country_definition')}
    return [name for name in s.keys('country_definition') if name in installed('common/country_creation') and name not in alive]


TREATY_SHARES=('0','1','2','3','4')
TREATY_DAYS=('1825','3650','5475','9125','18250','36135')
INPUT_KINDS={'state':{'state'},'region':{'strategic_region'},'law':{'law_type'},'subject':{'country'},'ship':{'ship'},'monopoly':{'company','building_type'},
             'money':{'quantity'},'goods_amount':{'quantity','goods'}}


@timed_often
def land_regions(s):
    return sorted({region for region in state_regions(s).values() if region})


@timed_often
def country_ships(s,country):
    fleets={formation for formation, in s.rows('formation','formation',country=country)}
    return [ship for ship,fleet in s.rows('ship','ship,fleet') if fleet in fleets]


@timed_often
def article_states(s,article,giver,taker):
    ports=s.map('state','state,treaty_port_potential')
    return [state for state, in s.rows('state','state',country=giver) if article!='treaty_port' or taker!=s.player or ports.get(state)]


@timed_often
def article_regions(s,article):
    unclaimed={state_regions(s).get(state) for state,country in s.rows('state','state,country') if country in decentralized(s)}
    return [region for region in land_regions(s) if article!='non_colonization_agreement' or region in unclaimed]


@timed_often
def article_inputs(s,kind,giver,taker,article):
    if kind=='state':
        return [{'state':state} for state in article_states(s,article,giver,taker)]
    if kind=='region':
        return [{'strategic_region':region} for region in article_regions(s,article)]
    if kind=='law':
        return [{'commitment':law} for law,active in s.rows('law','law,active',country=giver) if not active]
    if kind=='subject':
        return [{'subject':subject} for overlord,subject in sorted(subject_pairs(s)) if overlord==giver]
    if kind=='ship':
        return [{'ship':ship} for ship in country_ships(s,giver)]
    if kind=='monopoly':
        return [{'company':company,'building_type':building} for company,name in s.rows('company','company,company_type',country=taker)
                for block in definition(s,'common/company_types',name,'building_types') for building in block.split()]
    if kind=='money':
        return [{'share':share} for share in TREATY_SHARES]
    return [{'goods':goods,'share':share} for goods in traded(s) for share in TREATY_SHARES]


@timed_often
def input_articles(s,offered,kind):
    return [{**option,**extra} for option in treaty_articles(s,'directed',offered,INPUT_KINDS[kind])
            for giver,taker in [(s.player,option['country']) if offered else (option['country'],s.player)] for extra in article_inputs(s,kind,giver,taker,option['treaty_article'])]


@timed_often
def promises(s,country):
    owed=obligations(s)
    return [name for name,usable in (('OweObligation',(country,'player_owes') not in owed),('CallInObligation',(country,'owes_player') in owed),
                                     ('AskForObligation',(country,'owes_player') not in owed)) if usable]


@timed_often
def exchanges(s):
    wanted={}
    for option in treaty_articles(s,'directed',False,False):
        wanted.setdefault(option['country'],[]).append(option['treaty_article'])
    return [{**option,'demand':demand} for option in treaty_articles(s,'directed',True,False) for demand in wanted.get(option['country'],())
            if demand in EXCHANGED and demand!=C_MEMBERSHIP and option['treaty_article']!=demand]


@timed_often
def standing_treaties(s):
    return {treaty:(first if second==s.player else second) for treaty,(first,second) in {**in_force(s),**proposed_treaties(s)}.items()
            if s.player in (first,second) and (treaty in in_force(s) or second==s.player)}


@timed_often
def amendments(s,kind,offered):
    held={}
    for treaty,article in s.rows('treaty_article','treaty,treaty_article_type'):
        held.setdefault(treaty,set()).add(article)
    return [{'treaty':treaty,'treaty_article':option['treaty_article']} for treaty,country in sorted(standing_treaties(s).items())
            for option in treaty_articles(s,kind,offered,False,amending=True) if option['country']==country and option['treaty_article'] not in held.get(treaty,())
            and compatible_article(option['treaty_article'],held.get(treaty,()))]


@timed_often
def droppable(s,kind,offered):
    treaties=standing_treaties(s)
    found=[]
    for treaty,article,source,target in s.rows('treaty_article','treaty,treaty_article_type,source_country,target_country'):
        fields=s.definitions('common/treaty_articles').get(article,{})
        if treaty in treaties and fields.get('kind')==[kind] and 'can_be_renegotiated' in stated('common/treaty_articles',article,'flags') \
                and (kind=='mutual' or (source==s.player)==offered):
            found.append({'treaty':treaty,'treaty_article':article})
    return found


@timed_often
def play_opponents(s,play):
    leaders=involved(s)[0].get(play,())
    side=leaders.index(s.player)
    return play_members(s).get((play,1-side),set())|{leaders[1-side]}


@timed_often
def sway_goals(s,target_type):
    found=[]
    for option in swayable(s):
        for kind in listed_goals(s,target_type):
            targets=goal_targets(s,option['diplomatic_play'],kind)
            found+=[{**option,'war_goal_type':kind,('target' if target_type=='country' else 'state'):target} for target in sorted(targets if targets is not True else ())]
    return found


@timed_often
def listed_goals(s,target_type):
    return [kind for kind in s.keys('war_goal_type') if kind not in UNIFYING_GOALS and not debug_goal(s,kind) and definition(s,'common/war_goal_types',kind,'target_type')==[target_type]
            and 'skip_build_list' not in definition(s,'common/war_goal_types',kind,'settings')
            and 'country_creation' not in definition(s,'common/war_goal_types',kind,'settings')]


@timed_often
def open_plays(s):
    return [play for play in principal(s) if play not in at_war_plays(s) and escalation(s,play)<COUNTDOWN]


@timed_often
def goal_drafts(s,target_type):
    key='country' if target_type=='country' else 'state'
    found=[]
    for play in open_plays(s):
        for kind in listed_goals(s,target_type):
            targets=goal_targets(s,play,kind)
            seizing='validate_force_nationalization' in definition(s,'common/war_goal_types',kind,'settings')
            found+=[{'diplomatic_play':play,'war_goal_type':kind,'holder':s.player,key:target} for target in sorted(targets if targets is not True else ())
                    if not seizing or owns_here(s,target)]
    return found


@timed_often
def enforceable(s,inputs):
    return [article for article,fields in s.definitions('common/treaty_articles').items()
            if 'can_be_enforced' in stated('common/treaty_articles',article,'flags') and set(fields.get('required_inputs',()))==inputs]


ENFORCED='enforce_treaty_article'


@timed_often
def article_goals(s,inputs,extra):
    return [{'diplomatic_play':play,'war_goal_type':ENFORCED,'country':country,'treaty_article':article,**added}
            for play in open_plays(s) for country in sorted(play_opponents(s,play)) for article in enforceable(s,inputs) for added in extra(country,article)]


@timed_often
def liberation_goals(s):
    owners={}
    for state,region,country in s.rows('state','state,state_region,country'):
        owners.setdefault(country,set()).add(region)
    kinds=[kind for kind in s.keys('war_goal_type') if 'country_creation' in definition(s,'common/war_goal_types',kind,'settings')
           and 'skip_build_list' not in definition(s,'common/war_goal_types',kind,'settings')]
    return [{'diplomatic_play':play,'war_goal_type':kind,'country':country,'country_definition':name}
            for play in open_plays(s) for kind in kinds for country in sorted(play_opponents(s,play))
            for name in creatable(s) if set(installed('common/country_creation')[name].get('states') or ())&owners.get(country,set())]


@timed_often
def swayable(s):
    found=[]
    for play in principal(s):
        if play in at_war_plays(s) or not OPENING_PHASE_END<=escalation(s,play)<COUNTDOWN:
            continue
        taken={country for side in range(2) for country in play_members(s).get((play,side),set())}|set(involved(s)[0][play])
        found+=[{'diplomatic_play':play,'country':country} for country in s.countries() if country not in taken]
    return found


@timed_often
def allies(s):
    pairs=[in_force(s).get(treaty,()) for treaty,kind in s.rows('treaty_article','treaty,treaty_article_type') if kind in ('alliance','defensive_pact')]
    return {other for pair in pairs if s.player in pair for other in pair if other!=s.player}


@lru_cache(maxsize=None)
@timed
def sway_pacts():
    pacts,subjections=[],{}
    for name,found in installed('common/diplomatic_actions').items():
        inner=dict(fields(' '.join(found.get('pact',()))))
        kind=inner.get('subject_type')
        if kind and stated('common/subject_types',kind[0],'can_offer_to_become_in_sway_offers')==['yes']:
            subjections[name]=kind[0]
        elif inner.get('can_be_used_in_sway_offers')==['yes']:
            pacts.append(name)
    return pacts,subjections


@timed_often
def transferable_subjects(s):
    return sorted(subject for subject in subjects(s) if stated('common/subject_types',subject_type_of(s,subject),'can_be_used_in_sway_offers')!=['no'])


RULES={
    'build':lambda s:[] if in_default(s) or queue_weeks(s)>=QUEUE_WEEKS else buildable(s),
    'offer_treaty_article':lambda s:treaty_articles(s,'directed',True,False),
    'demand_treaty_article':lambda s:treaty_articles(s,'directed',False,False),
    'agree_treaty_article':lambda s:treaty_articles(s,'mutual',True,False),
    'offer_goods_treaty_article':lambda s:treaty_articles(s,'directed',True,True),
    'demand_goods_treaty_article':lambda s:treaty_articles(s,'directed',False,True),
    'cancel_construction':lambda s:product(building=queued_buildings(s)),
    'downsize':lambda s:[] if revolution_brewing(s) else product(building=sorted(set(owned_of(s,building_kinds(s,downsizeable=True)))&government_owned(s)-set(queued_buildings(s)))),
    'pause_construction':lambda s:[{}] if not construction_paused(s) else [],
    'resume_construction':lambda s:[{}] if construction_paused(s) and not in_default(s) else [],
    'pause_construction_output':lambda s:product(building=[i for i,k,_ in s.buildings() if k=='building_construction_sector' and not setting(s,i,'output_paused')]),
    'resume_construction_output':lambda s:product(building=[i for i,k,_ in s.buildings() if k=='building_construction_sector' and setting(s,i,'output_paused')]),
    'nationalize':lambda s:[] if law_flag(s,'country_disable_nationalization_bool') else
                           [{'building':ident,'levels':n} for ident,levels in private_levels(s).items() for n in range(1,levels+1)
                            if money(s)>=nationalization_cost(s,ident)*n],
    'toggle_privatization':lambda s:[] if law_flag(s,'country_force_privatization_bool') else product(building=[i for i in owned_of(s,private_kinds(s)) if privatizable(s,i) or privatization_requested(s,i)]),
    'toggle_monopoly':lambda s:product(building_type=monopolizable(s)),
    'subsidies_on':lambda s:product(building=[i for i in subsidized(s,0) if i in owned_of(s,private_kinds(s))]),
    'subsidies_off':lambda s:product(building=subsidized(s,1)),
    'switch_production_method':switch_methods,
    'subset_subsidies_on_state':lambda s:subset_options(s,private_kinds(s),lambda s,i:not s.map('building','building,subsidized').get(i)),
    'subset_subsidies_off_state':lambda s:subset_options(s,private_kinds(s),lambda s,i:bool(s.map('building','building,subsidized').get(i))),
    'bulk_nationalize_state':lambda s:[] if law_flag(s,'country_disable_nationalization_bool') else nationalizable_subsets(s),
    'bulk_expropriate_state':lambda s:[] if law_flag(s,'country_disable_nationalization_bool') or law_flag(s,'country_disable_nationalization_without_compensation_bool')
                                      else seizable_subsets(s),
    'reset_building_production_methods':lambda s:product(building=resettable(s)),
    'reset_production_methods':lambda s:product(state=sorted({s.map('building','building,state')[ident] for ident in resettable(s)})),
    'move_capital':lambda s:product(state=capital_sites(s)),
    'move_market_capital':lambda s:product(state=market_capital_sites(s)),
    'grant_building_charter':building_charters,
    'revoke_building_charter':building_charters,
    'grant_region_charter':region_charters,
    'revoke_region_charter':region_charters,
    'bulk_switch_production_method_state':bulk_methods,
    'cancel_queue_item':lambda s:queue_items(s,0,0),
    'raise_queue_item':lambda s:queue_items(s,1,0),
    'first_queue_item':lambda s:queue_items(s,1,0),
    'lower_queue_item':lambda s:queue_items(s,0,1),
    'last_queue_item':lambda s:queue_items(s,0,1),
    'set_tax_level':lambda s:product(level=other_levels(s,'tax_level')),
    'set_government_wages':lambda s:product(level=other_levels(s,'government_wage_level')),
    'set_military_wages':lambda s:product(level=other_levels(s,'military_wage_level')),
    'toggle_consumption_tax':lambda s:product(goods=taxable(s)),
    'set_import_tariff':lambda s:trade_levels(s,'import','tariff'),
    'set_export_tariff':lambda s:trade_levels(s,'export','tariff'),
    'set_import_subvention':lambda s:trade_levels(s,'import','subvention'),
    'set_export_subvention':lambda s:trade_levels(s,'export','subvention'),
    'declare_bankruptcy':lambda s:[{}] if in_default(s) else [],
    'set_strait_toll':strait_tolls,
    'set_strait_access':strait_accesses,
    'set_strait_allowed':strait_permissions,
    'enact_law':lambda s:product(law=enactable(s)),
    'cancel_enactment':lambda s:[{}] if enacting(s) else [],
    'impose_law':lambda s:product(law=imposable(s)),
    'repeal_amendment':lambda s:product(amendment=[ident for ident,law,kind in s.rows('amendment','amendment,law,amendment_type')
                                                   if ident in repealable(s)
                                                   and opposed_in_government(s,next(iter(definition(s,'common/amendments',kind,'parent')),None))
                                                   and passes(s,'common/amendments',kind,('can_repeal',),country_scope(s))]),
    'toggle_bolster_movement':lambda s:product(political_movement=movements(s,PROMOTED)),
    'toggle_suppress_movement':lambda s:product(political_movement=movements(s,SUPPRESSED)),
    'negotiate':lambda s:product(interest_group=negotiable(s)),
    'set_institution_level':institution_levels,
    'stop_institution_change':lambda s:product(institution=[ident for ident in s.mine('institution') if ident in changing(s)]),
    'issue_decree':decrees,
    'remove_decree':lambda s:[{'state':state,'decree':kind} for state,kind in sorted(issued_decrees(s))
                             if passes(s,'common/decrees',kind,('state_trigger',),Scope(s,'state',state))],
    'research':lambda s:product(technology=researchable(s)),
    'queue_research':lambda s:product(technology=researchable(s)),
    'dequeue_research':lambda s:product(technology=[kind for owner,kind in s.rows('country_research_queued','country_research,technology') if owner in research(s)]),
    'recruit':recruit,
    **{f'{name}_selected':(lambda s,name=name:RULES[name](s)) for name in ('mobilize','demobilize','raise_conscripts')},
    'deploy_selected_to_front':lambda s:RULES['deploy_to_front'](s),
    'defend_invasion':lambda s:[{'military_formation':f,'front':front} for front,ended in invasions(s) if not ended for f in armies(s,True)],
    'recall_fleet':lambda s:product(military_formation=[f for fleets in [set(s.formations('fleet'))] for f,docked,recalled,health in
                                                        s.rows('formation_report','formation,docked,recalled,hit_points_percent')
                                                        if f in fleets and not docked and not recalled and health<1]),
    **{f'{verb}_ship_item':(lambda s,skip=skip:product(index=ship_items(s)[skip[0]:len(ship_items(s))-skip[1]]))
       for verb,skip in (('raise',(1,0)),('first',(1,0)),('lower',(0,1)),('last',(0,1)),('cancel',(0,0)))},
    'station_selected':lambda s:[{'military_formation':f,'strategic_region':region} for f in settled(s,s.formations('army')) if not demobilizing(s,f)
                                 for region in sorted({region for kind,region in hq_regions(s).values() if kind==0})
                                 if region not in (home_region(s,f),state_regions(s).get(s.map('formation_status','formation,target_location').get(f))) and reaches(s,f,region)],
    'transfer_battalions':lambda s:[{'military_formation':source,'target':target} for source in s.formations('army') for target in s.formations('army')
                                    if source!=target and located(s,source)==located(s,target) and len(s.rows('combat_unit','combat_unit',formation=source))>=TRANSFER_MINIMUM
                                    and not formation_report(s,target,'invading')],
    'transfer_ships':lambda s:[{'military_formation':source,'target':target} for source in divisible(s,free_fleets(s)) for target in free_fleets(s) if source!=target],
    'split_army':lambda s:product(military_formation=[f for f in s.formations('army') if len(s.rows('combat_unit','combat_unit',formation=f))>=TRANSFER_MINIMUM
                                                      and not formation_report(s,f,'invading')]),
    'split_fleet':lambda s:product(military_formation=divisible(s,free_fleets(s))),
    'transfer_ship':lambda s:[{'ship':ship,'target':target} for ship,fleet in fleet_ships(s) if fleet in divisible(s,free_fleets(s)) for target in free_fleets(s) if target!=fleet],
    'merge_armies':lambda s:mergeable(s,'army'),
    'merge_fleets':lambda s:mergeable(s,'fleet'),
    'create_fleet':lambda s:product(option=range(len(naval_regions(s)))),
    'toggle_naval_mission_region':lambda s:[{'military_formation':fleet,'strategic_region':region} for fleet in on_mission(s,True) for region in sea_regions(s)],
    'change_naval_mission_type':lambda s:[{'military_formation':fleet,'naval_mission_type':kind} for fleet in on_mission(s,True) for kind in mission_types(s,fleet)],
    'station_fleet':lambda s:[{'military_formation':fleet,'state':state} for fleet in free_fleets(s) for state in s.states() if trigger_coastal(s,state)],
    'rehome_fleet':lambda s:[{'military_formation':fleet,'strategic_region':region} for fleet in free_fleets(s) for region in naval_regions(s)
                             if region!=hq_regions(s)[home_of(s,fleet)][1]],
    'defend_invasion_fleet':lambda s:[{'military_formation':fleet,'front':front} for front,ended in invasions(s) if not ended for fleet in free_fleets(s)],
    'assign_flagship':lambda s:product(ship=[ship for ship,_ in fleet_ships(s) if stated('common/ship_types',ship_kinds(s)[ship],'can_be_flagship')==['yes']]),
    'unassign_flagship':lambda s:product(ship=[ship for ship,_ in fleet_ships(s)]),
    'retrofit_ship':lambda s:product(ship=[ship for ship,_ in fleet_ships(s)]),
    'cancel_retrofit_ship':lambda s:product(ship=[ship for ship,_ in fleet_ships(s)]),
    'change_ship_template':ship_template_choices,
    'retrofit_fleet_and_station':lambda s:product(military_formation=retrofit_fleets(s,False)),
    'retrofit_all_and_station':lambda s:[{}] if retrofit_fleets(s,False) else [],
    'disband_unit':lambda s:[] if revolution_brewing(s) else product(combat_unit=[unit for mine in [set(s.formations())] for unit,formation in s.rows('combat_unit','combat_unit,formation')
                                                                                 if formation in mine]),
    'cancel_ship_for':lambda s:product(ship_type=sorted(cancellable_types(s)),military_formation=s.formations('fleet')),
    'upgrade_all_units':lambda s:[{}] if RULES['upgrade_regulars'](s) else [],
    'create_army':lambda s:product(option=range(len({region for kind,region in hq_regions(s).values() if kind==0}))),
    'recruit_from_formation':lambda s:[{'military_formation':combo['military_formation'],'combat_unit_type':combo['combat_unit_type'],'state':s.map('building','building,state')[combo['building']]}
                                       for combo in recruit(s)],
    'activate_conscription_center':lambda s:[{'military_formation':formation,'combat_unit_type':kind,'state':state} for state in conscription_states(s)
                                             for kind in unit_types_unlocked(s) for formation in s.formations('army')] if 'law_peasant_levies' not in active_laws(s) else [],
    'disembark':lambda s:product(military_formation=[f for armies_ in [set(s.formations('army'))] for f, in s.rows('formation_report','formation',embarked=True) if f in armies_]),
    'cancel_invasion':lambda s:product(military_formation=[f for manned in [set(s.formations())] for f, in s.rows('formation_report','formation',invading=True) if f in manned]),
    'mobilize':lambda s:product(military_formation=[f for f in armies(s,False) if not demobilizing(s,f)] if principal(s) else []),
    'demobilize':lambda s:product(military_formation=armies(s,True)),
    'raise_conscripts':lambda s:product(military_formation=[i for i,r in s.rows('formation_status','formation,raised_conscripts') if i in armies(s,True) and not r and at_home(s,i)]),
    'disband_formation':lambda s:product(military_formation=[f for f in s.formations() if all(idle_room(s,c) for c in leaders(s,f))]),
    'mobilize_all':lambda s:[{}] if principal(s) and [f for f in armies(s,False) if not demobilizing(s,f)] else [],
    'demobilize_all':lambda s:[{}] if armies(s,True) else [],
    'toggle_mobilization_option':lambda s:[{'military_formation':formation,'mobilization_option':option} for formation in settled(s,s.formations('army'))
                                           for option in mobilization_options(s,formation)],
    'set_supply_priority':lambda s:[{'military_formation':f,'level':level} for f in s.formations('army') for index,level in enumerate(('low','medium','high'))
                            if s.map('formation','formation,supply_priority').get(f)!=index],
    'disband_regulars':lambda s:[] if revolution_brewing(s) else formation_units(s,s.formations()),
    'disband_conscripts':lambda s:[{'military_formation':f,'combat_unit_type':k} for f in armies(s,True) for k in conscript_types(s,f)],
    'upgrade_regulars':lambda s:[combo for combo in formation_units(s,s.formations('army')) if upgradable(s,**combo)],
    'upgrade_conscripts':lambda s:[{'military_formation':f,'combat_unit_type':kind} for f in armies(s,True) for kind in conscript_types(s,f)
                                   if upgradable(s,f,kind)],
    'set_default_unit_type':lambda s:[{'military_formation':formation,'combat_unit_type':kind} for formation in s.formations('army')
                                      for kind in unit_types_unlocked(s) if kind not in selected_units(s,formation).values()],
    'commander_order':lambda s:[{'character':character,'commander_order_type':order} for character,current in s.rows('character','character,order_type',country=s.player)
                                if character in set(s.characters('character_role_general')) and character in {c for f in s.mine('formation') for c in leaders(s,f)}
                                for order in s.keys('commander_order_type') if definition(s,'common/commander_orders',order,'military_type')==['army'] and current!=order
                                and evaluate(parse(next(iter(definition(s,'common/commander_orders',order,'possible')),'')),character_scope(s,character)) is not False],
    'hire_commander':lambda s:product(character=[c for c in recruitable(s) if idle_room(s,c)]),
    'hire_commander_for':lambda s:[{'character':c,'military_formation':f} for c in recruitable(s) if idle_room(s,c) for f in s.formations() if fits(s,c,f)],
    'promote_commander':lambda s:product(character=[c for c in s.commanders() if promotable(s,c)]),
    'assign_commander':lambda s:[{'character':character,'military_formation':formation} for character in commanders_where(s,lambda formation,recruitable:not recruitable)
                                 for formation in s.formations() if s.map('character','character,formation',country=s.player).get(character)!=formation
                                 and fits(s,character,formation)],
    'unassign_commander':lambda s:product(character=[c for c in commanders_where(s,lambda formation,recruitable:formation in set(s.mine('formation'))) if assigned(s,c) and idle_room(s,c)]),
    'start_naval_mission':lambda s:[{'military_formation':fleet,'naval_mission_type':kind} for fleet in on_mission(s,False) for kind in mission_types(s,fleet)],
    'start_naval_mission_selected':lambda s:RULES['start_naval_mission'](s),
    'end_naval_mission_selected':lambda s:RULES['end_naval_mission'](s),
    'end_naval_mission':lambda s:product(military_formation=[i for fleets in [set(s.formations('fleet'))] for i,m in s.rows('formation_status','formation,naval_mission') if i in fleets and m is not None]),
    'pause_ship_construction':lambda s:[{}] if not ship_paused(s) and not construction_paused(s) and metric(s,'GetShipConstruction')>0 else [],
    'resume_ship_construction':lambda s:[{}] if ship_paused(s) and not construction_paused(s) and not in_default(s) else [],
    'set_supply_ship_construction':lambda s:product(level=other_levels(s,'supply_ship_construction_level')),
    'design_ship_template':ship_designs,
    'edit_ship_template':lambda s:[{'ship_type':kind,'ship_modification':mod,'index':index} for (kind,index),template in sorted(own_templates(s).items())
                                   for mod in unlocked_modifications(s,kind) if mod not in latest_design(s,template)],
    'set_default_ship_template':lambda s:[{'ship_type':kind,'index':index} for kind,index in sorted(non_default_templates(s))],
    'set_fleet_ship_template':fleet_templates,
    'delete_ship_template':lambda s:[{'ship_type':kind,'index':index} for (kind,index),template in sorted(own_templates(s).items())
                                     if sum(1 for other,_ in own_templates(s) if other==kind)>1 and template not in templates_in_construction(s)],
    'retrofit_fleet':lambda s:product(military_formation=retrofit_fleets(s,False)),
    'cancel_retrofit_fleet':lambda s:product(military_formation=retrofit_fleets(s,True)),
    'retrofit_all':lambda s:[{}] if retrofit_fleets(s,False) else [],
    'cancel_retrofit_all':lambda s:[{}] if retrofit_fleets(s,True) else [],
    'character_interaction':lambda s:[{'character':character,'interaction':interaction}
                                      for character,interaction,possible in s.rows('player_character_interaction','character,character_interaction,possible')
                                      if interaction not in cooling(s) and possible],
    'diplomatic_action':lambda s:[{'country':country,'diplomatic_action':action} for country,action in sorted(diplomatic_shown(s))
                                  if not definition(s,'common/diplomatic_actions',action,'picks_states') and diplomatic_allowed(s,country,action)],
    'diplomatic_action_obligation':lambda s:[{**option,'obligation':obligation} for option in RULES['diplomatic_action'](s)
                                             if definition(s,'common/diplomatic_actions',option['diplomatic_action'],'can_use_obligations')==['yes']
                                             for obligation,direction,wanted in (('CallInObligation','owes_player',True),('OweObligation','player_owes',False))
                                             if ((option['country'],direction) in obligations(s))==wanted],
    'start_play_confirmed':lambda s:[{**option,'mode':mode} for option in RULES['start_play_country'](s) for mode in ('AsDemand','ForcePlay')],
    'start_play_liberation':liberations,
    'diplomatic_action_first_state':lambda s:state_actions(s,'source'),
    'diplomatic_action_second_state':lambda s:state_actions(s,'target'),
    'diplomatic_action_states':state_trades,
    'start_play_country':lambda s,liberating=False:[{'country':country,'diplomatic_play_type':play} for country in s.countries() if reachable_country(s,country) and not play_opposed(s,country)
                                   for play in play_types(s,'country') if play_allowed(s,play,liberating,target_country=('country',country))
                                   and not country_regions(s,country)&regions_in_play(s)
                                   and (not marker_required(s,play) or state_regions(s).get(s.map('country','country,capital').get(country)) in engaged(s))],
    'start_play_state':lambda s:[{'state':state,'diplomatic_play_type':play} for state,country in s.rows('state','state,country') if country!=s.player and reachable_state(s,state) and not play_opposed(s,country)
                                 for play in play_types(s,'state') if play_allowed(s,play,target_country=('country',country),target_state=('state',state))
                                 and state_regions(s).get(state) not in regions_in_play(s)
                                 and (not marker_required(s,play) or state_regions(s).get(state) in engaged(s))],
    'support_initiator':lambda s:product(diplomatic_play=[p for p in third_party(s) if 0 not in committed(s,p) and side_open(s,p,0)]),
    'support_target':lambda s:product(diplomatic_play=[p for p in third_party(s) if 1 not in committed(s,p) and side_open(s,p,1)]),
    'lean_initiator':lambda s:product(diplomatic_play=[p for p in opening(s) if not committed(s,p) and p not in leaning(s,'initiator') and side_open(s,p,0)]),
    'lean_target':lambda s:product(diplomatic_play=[p for p in opening(s) if not committed(s,p) and p not in leaning(s,'target') and side_open(s,p,1)]),
    'stay_on_fence':lambda s:product(diplomatic_play=[p for p in third_party(s,0) if not committed(s,p) and p in leaning(s,'initiator')|leaning(s,'target')
                                                      and not overlords(s,s.player)&set(involved(s)[0].get(p,()))]),
    'declare_neutrality':lambda s:product(diplomatic_play=[p for p in third_party(s) if not committed(s,p)]),
    'back_down':lambda s:product(diplomatic_play=backable(s)),
    'propose_peace':lambda s:product(war=[w for w in s.wars() if war_leader(s,w) and negotiable_war(s,w) and proposer(s,w) is None and peace_open(s,w)]),
    'white_peace':lambda s:product(war=[w for w in s.wars() if war_leader(s,w) and negotiable_war(s,w) and proposer(s,w) is None and pressed_in(s,w) and peace_open(s,w)]),
    'toggle_accept_peace':lambda s:product(war=[w for w in s.wars() if proposer(s,w) not in (None,s.player) and has_say(s,w) and negotiable_war(s,w)]),
    'capitulate':lambda s:product(war=[w for w in s.wars() if not overlords(s,s.player)&war_countries(s,w) and not revolution_against_player(s,w)]),
    'toggle_press_war_goal':lambda s:[goal for goal in war_goals(s) if goal['diplomatic_play'] in at_war_plays(s)
                                      and (war:=war_of_play(s,goal['diplomatic_play'])) is not None
                                      and war_leader(s,war) and negotiable_war(s,war) and proposer(s,war) is None and peace_open(s,war)],
    'make_primary_demand':lambda s:[goal for goal in war_goals(s) if goal['diplomatic_play'] not in at_war_plays(s) and goal['diplomatic_play'] in principal(s)
                                    and sum(other['diplomatic_play']==goal['diplomatic_play'] for other in war_goals(s))>1],
    'withdraw_treaty':lambda s:product(treaty=[ident for ident,(first,second) in sorted(in_force(s).items())
                                              if s.player in (first,second) and (first,second) not in enforced_on_player(s)]),
    'request_join_power_bloc':lambda s:product(power_bloc=[] if player_blocs(s) or overlords(s,s.player) else
                                               [bloc for bloc, in s.rows('country_leverage','power_bloc',country=s.player)
                                                if bloc_advantage(s,bloc,s.player)>=JOIN_LEVERAGE and below_leader(s,bloc)]),
    'kick_from_power_bloc':lambda s:product(country=[c for c in power_bloc_members(s) if not overlords(s,c)]) if bloc_leader(s) else [],
    'reform_government':lambda s:[{'interest_group':group,'mode':'Staged' if governs else 'Potential'}
                                  for group,governs,influence,party in s.rows('interest_group','interest_group,in_government,influence_type,party',country=s.player)
                                  if party is None and not law_flag(s,'country_block_government_reform_bool')
                                  and group not in insurrectionary(s) and ((governs and governing_count(s)>1) or (not governs and influence!=MARGINALIZED))],
    'reform_government_party':lambda s:[{'member':min(members),'mode':'Staged' if governs else 'Potential'}
                                        for members,governs in party_blocs(s) if not law_flag(s,'country_block_government_reform_bool')
                                        and not set(members)&insurrectionary(s) and (not governs or governing_count(s)>len(members))],
    'form_power_bloc':lambda s:[{'power_bloc_identity':identity,'power_bloc_principle':levels[0]} for identity in s.keys('power_bloc_identity') if may_found_bloc(s)
                                and passes(s,'common/power_bloc_identities',identity,('visible','possible'),country_scope(s))
                                for group in s.definitions('common/power_bloc_principle_groups')
                                if definition(s,'common/power_bloc_principle_groups',group,'primary_for_identity')==[identity]
                                for levels in [definition(s,'common/power_bloc_principle_groups',group,'levels')] if levels and principle_allowed(s,levels[0])],
    'leave_power_bloc':lambda s:[{}] if power_bloc_of(s,s.player) and not overlords(s,s.player) and may_leave(s) else [],
    'create_company':lambda s:product(company_type=companies(s)),
    'remove_company':lambda s:product(company_type=remove_companies(s)),
    'colonize':lambda s:[] if 'law_no_colonial_affairs' in active_laws(s) or revolution_brewing(s) else
                        product(state=colonizable(s)),
    'toggle_pause_colonization':lambda s:product(state=colonies(s)),
    'abandon_colony':lambda s:product(state=abandonable(s)),
    'incorporate':lambda s:product(state=[i for i in s.states() if incorporation(s).get(i)==0 and i not in colonies(s) and not s.map('state_economy','state,treaty_port').get(i)]),
    'unincorporate':lambda s:product(state=[i for i in s.states() if 0<need(incorporation(s).get(i),f'incorporation of state {i}')<1]),
    'press_journal_button':journal_buttons,
    'choose_event_option':event_options,
    'quick_decline_proposal':lambda s:product(country=sorted({country for country, in s.rows('player_proposal','country')})),
    'break_pact':breakable_pacts,
    'replace_principle':replaceable_principles,
    'embark_formation':embarkable,
    'plan_land_invasion':land_invasions,
    'plan_naval_invasion':naval_invasions,
    **{f'{verb}_{kind}_treaty_article':(lambda s,offered=offered,kind=kind:input_articles(s,offered,kind)) for verb,offered in (('offer',True),('demand',False)) for kind in INPUT_KINDS},
    **{f'{verb}_timed_treaty_article':(lambda s,kind=kind,offered=offered:[{**option,'days':days} for option in treaty_articles(s,kind,offered,False) for days in TREATY_DAYS])
       for verb,kind,offered in (('offer','directed',True),('demand','directed',False),('agree','mutual',True))},
    **{f'{verb}_obliged_treaty_article':(lambda s,kind=kind,offered=offered:[{**option,'obligation':promise} for option in treaty_articles(s,kind,offered,False)
                                                                           for promise in promises(s,option['country'])])
       for verb,kind,offered in (('offer','directed',True),('demand','directed',False),('agree','mutual',True))},
    'threaten_treaty_article':threatened_articles,
    'work_out_treaty_article':lambda s:treaty_articles(s,'directed',False,False),
    'exchange_treaty_articles':exchanges,
    **{f'amend_{verb}_treaty_article':(lambda s,kind=kind,offered=offered:amendments(s,kind,offered)) for verb,kind,offered in (('offer','directed',True),('demand','directed',False),('agree','mutual',True))},
    **{f'amend_drop_{verb}_treaty_article':(lambda s,kind=kind,offered=offered:droppable(s,kind,offered)) for verb,kind,offered in (('offer','directed',True),('demand','directed',False),('agree','mutual',True))},
    'offer_sway_state':lambda s:[{**option,'state':state} for option in swayable(s) for state in s.states()],
    'offer_sway_subject':lambda s:[{**option,'subject':subject} for option in swayable(s) for subject in transferable_subjects(s)],
    'offer_sway_pact':lambda s:[{**option,'diplomatic_action':action} for option in swayable(s) for action in sway_pacts()[0]],
    'offer_sway_subjection':lambda s:[{**option,'diplomatic_action':action} for option in swayable(s) for action,kind in sway_pacts()[1].items()
                                      if subject_fits(s,kind,s.player,option['country'])],
    'offer_sway_ally':lambda s:[option for option in swayable(s) if option['country'] in allies(s)],
    'offer_sway_goal_country':lambda s:sway_goals(s,'country'),
    'offer_sway_goal_state':lambda s:sway_goals(s,'state'),
    'offer_sway_goods_article':lambda s:[{**option,'war_goal_type':ENFORCED,'treaty_article':article,'goods':goods} for option in swayable(s) for article in enforceable(s,{'goods'}) for goods in traded(s)],
    'offer_sway_state_article':lambda s:[{**option,'war_goal_type':ENFORCED,'treaty_article':article,'state':state} for option in swayable(s) for article in enforceable(s,{'state'})
                                         for opponent in sorted(play_opponents(s,option['diplomatic_play'])) for state, in s.rows('state','state',country=opponent)],
    'offer_sway_region_article':lambda s:[{**option,'war_goal_type':ENFORCED,'treaty_article':article,'strategic_region':region} for option in swayable(s)
                                          for article in enforceable(s,{'strategic_region'}) for region in article_regions(s,article)],
    'offer_sway_law_article':lambda s:[{**option,'war_goal_type':ENFORCED,'treaty_article':article,'commitment':law} for option in swayable(s) for article in enforceable(s,{'law_type'})
                                       for opponent in sorted(play_opponents(s,option['diplomatic_play'])) for law,active in s.rows('law','law,active',country=opponent) if not active],
    'add_war_goal_country':lambda s:goal_drafts(s,'country'),
    'add_war_goal_state':lambda s:goal_drafts(s,'state'),
    'add_war_goal_liberation':liberation_goals,
    'add_war_goal_article':lambda s:article_goals(s,set(),lambda country,article:[{}]),
    'add_goods_war_goal':lambda s:article_goals(s,{'goods'},lambda country,article:[{'goods':goods} for goods in traded(s)]),
    'add_state_war_goal':lambda s:article_goals(s,{'state'},lambda country,article:[{'state':state} for state in article_states(s,article,country,s.player)]),
    'add_region_war_goal':lambda s:article_goals(s,{'strategic_region'},lambda country,article:[{'strategic_region':region} for region in article_regions(s,article)]),
    'add_law_war_goal':lambda s:article_goals(s,{'law_type'},lambda country,article:[{'commitment':law} for law,active in s.rows('law','law,active',country=country) if not active]),
    'offer_sway':swayable,
    **{name:(lambda s,kind=name.split('_',1)[1]:product(country=proposers(s,kind))) for name in ('accept_treaty','decline_treaty','accept_demand','reject_demand',
                                                                    'accept_action_proposal','decline_action_proposal','accept_sway','reject_sway')},
    'pause_all_construction':lambda s:[{}] if not construction_paused(s) else [],
    'resume_all_construction':lambda s:[{}] if construction_paused(s) and not in_default(s) else [],
    'set_default_construction_fleet':lambda s:product(military_formation=[f for f in s.formations('fleet') if not formation_report(s,f,'default_fleet')]),
    'clear_default_construction_fleet':lambda s:[{}] if s.rows('formation_report','formation',default_fleet=True) else [],
    'decommission_ship':lambda s:[] if revolution_brewing(s) else product(ship=[ident for fleets in [set(s.formations('fleet'))] for ident,fleet in s.rows('ship','ship,fleet') if fleet in fleets]),
    'build_ship':lambda s:product(ship_type=ship_types(s) if metric(s,'GetShipConstruction')>0 else []),
    'build_ship_for':lambda s:product(ship_type=ship_types(s) if metric(s,'GetShipConstruction')>0 else [],military_formation=s.formations('fleet')),
    'cancel_ship':lambda s:product(ship_type=sorted(cancellable_types(s))),
    'station_formation':lambda s:[{'military_formation':f,'state':st} for f in settled(s,s.formations('army')) if not demobilizing(s,f)
                                  for st in s.states() if st not in (located(s,f),s.map('formation_status','formation,target_location').get(f))
                                  and march_components(s).get(st,set())&march_components(s).get(located(s,f),set())],
    'rehome_formation':rehome,
    'deploy_to_front':lambda s:[{'military_formation':f,'front':front} for f in armies(s,True) if f in deployable(s) for front in war_fronts(s)
                                if s.map('formation_status','formation,target_location').get(f)!=front],
    'set_borrow_setting':lambda s:[{'military_formation':f,'index':index} for mine in [set(s.mine('formation'))]
                                   for f,index,chosen in s.rows('formation_borrow_setting','formation,position,selected') if f in mine and not chosen],
    'cancel_strategic_objective_selected':lambda s:[{'military_formation':f,'state':objective&SLOT} for idle in [set(settled(s,s.formations('army')))]
                                                    for f,objective in s.rows('formation_private','formation,strategic_objective')
                                                    if f in idle and objective is not None],
    'set_strategic_objective':lambda s:[{'military_formation':f,'state':st} for f in settled(s,s.formations('army')) for st in s.states()
                                        if st!=formation_setting(s,f,'strategic_objective')],
    'pick_principle':lambda s:[{'slot':len(held),'power_bloc_principle':levels[0]} for held in [bloc_principles(s)] if bloc_leader(s) and mandates(s) and len(held)<PRINCIPLE_SLOTS
                               for identity in [bloc_identity(s)]
                               for group in s.definitions('common/power_bloc_principle_groups')
                               for levels in [definition(s,'common/power_bloc_principle_groups',group,'levels')] if levels and not set(levels)&held and principle_allowed(s,levels[0])
                               and definition(s,'common/power_bloc_principle_groups',group,'unlocking_identity') in ([],[identity])
                               and definition(s,'common/power_bloc_principle_groups',group,'blocking_identity')!=[identity]],
    'upgrade_principle':lambda s:product(power_bloc_principle=[kind for kind in sorted(bloc_principles(s)) if not kind.endswith('_3')]) if bloc_leader(s) and mandates(s) else [],
    'toggle_charter':charter_toggles,
    'pause':lambda s:[{}],
    'unpause':lambda s:[{}],
    'set_speed':lambda s:product(speed=(FASTEST_SPEED,)),
    'take_decision':lambda s:product(decision=[name for name, in s.rows('player_decision','decision') if decidable(s,name)]),
    'toggle_ignore_decision':lambda s:product(decision=[name for name, in s.rows('player_decision','decision')]),
}


@timed
def available(snapshot):
    snapshot.load()
    offered={}
    for action in ACTIONS:
        progress(f'available {action.name}')
        offered[action.name]=RULES[action.name](snapshot)
    return offered
