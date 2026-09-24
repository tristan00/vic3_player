import re
from functools import lru_cache

from ..actions.catalogue import ACCESS_PERMISSIONS, ACCESS_STATUSES, ACTIONS, LEVELS, TOLL_LEVELS
from ..common import progress, timed
from ..recording.spec import METRIC_COLUMNS
from ..runner.memory import MONTH_STARTS

from .triggers import ENGAGED, Scope, autonomous, bloc_advantage, modifier_flag, character_scope, country_scope, evaluate, overlords, parse, subject_pairs
from .triggers import play_sides, stance, coastal as trigger_coastal, laws as trigger_laws, technologies as trigger_technologies

SLOT=0xFFFFFF


def product(**domains):
    combos=[{}]
    for name,values in domains.items():
        combos=[{**combo,name:value} for combo in combos for value in values]
    return combos


def building_ids(s):
    return [ident for ident,_,_ in s.buildings()]


CONSTRUCTION={'building_construction_sector'}


def market_owner(s):
    market=s.map('country','country,market').get(s.player)
    return s.map('market','market,owner').get(market)==s.player


TARIFF_CODES={'tariff':{'None':3,'Low':4,'High':5,'Max':6},'subvention':{'Low':2,'High':1,'Max':0}}
DEFAULT_TARIFF=3
COMPANY_LOCK_MONTHS=60
GRACE_HOURS=7*24
COOLDOWN_MONTHS=3


def calendar(hours):
    days=hours//24
    year,day=divmod(days,365)
    month=next(m for m in range(12,0,-1) if day>=MONTH_STARTS[m-1])
    return year,month,day-MONTH_STARTS[month-1]


def months_later(hours,months):
    year,month,day=calendar(hours)
    month+=months
    year,month=year+(month-1)//12,(month-1)%12+1
    return (year*365+MONTH_STARTS[month-1]+day)*24


def now(s):
    return s.hours


def tariffs(s,direction,column):
    return s.map('player_tariff','goods,'+column,direction=direction)


def tariff_open(s,direction,goods):
    changed=tariffs(s,direction,'last_change').get(goods)
    return changed is None or now(s)-changed<GRACE_HOURS or now(s)>=months_later(changed,COOLDOWN_MONTHS)


def law_modifier(s,key):
    return modifier_total(s,'common/laws',active_laws(s),key)


def modifier_total(s,folder,names,key):
    total=0
    for name in names:
        for block in definition(s,folder,name,'modifier'):
            found=re.search(r'\b'+key+r'\s*=\s*(-?[\d.]+)',block)
            total+=float(found[1]) if found else 0
    return total


def institution_max(s,institution):
    acquired,_,_,_=technologies(s)
    key='country_'+institution+'_max_investment_add'
    return law_modifier(s,key)+modifier_total(s,'common/technology/technologies',acquired,key)


MIN_INSTITUTION=1


def institution_levels(s):
    kinds=s.map('institution','institution,institution_type',country=s.player)
    cost=metric(s,'GetInstitutionInvestmentBureaucracyCost')
    spare=metric(s,"GetPowerDelta('bureaucracy')")
    return [{'institution':ident,'level':level} for ident,current in s.rows('institution','institution,investment',country=s.player)
            for level in range(MIN_INSTITUTION,6) if level!=current and level!=changing(s).get(ident) and level<=institution_max(s,kinds[ident])
            and (level<=current or spare>=cost*(level-current))]


def trade_level(s,direction,goods):
    return tariffs(s,direction,'level').get(goods,DEFAULT_TARIFF)


def traded(s):
    return [goods for goods in s.keys('goods') if definition(s,'common/goods',goods,'local')!=['yes'] and definition(s,'common/goods',goods,'tradeable')!=['no']]


def trade_levels(s,direction,kind):
    if not market_owner(s):
        return []
    permitted=law_modifier(s,f'state_{kind}_{direction}_add')>0
    return [{'goods':goods,'level':level} for goods in traded(s) if tariff_open(s,direction,goods) for level,code in TARIFF_CODES[kind].items()
            if (level=='None' or permitted) and code!=trade_level(s,direction,goods)]


@lru_cache(maxsize=None)
def parsed(text):
    return parse(text)


def passes(s,folder,name,fields,scope):
    return all(evaluate(parsed(text),scope) is not False for field in fields for text in definition(s,folder,name,field))


def decidable(s,name):
    return passes(s,'common/decisions',name,('possible',),country_scope(s))


def state_regions(s):
    def compute():
        regions={state:region for region,fields in s.definitions('common/strategic_regions').items() for state in fields.get('states',())}
        return {ident:regions.get(key) for ident,key in s.rows('state','state,state_region')}
    return s.memo('state_regions',compute)


ARMY_FLAGS=15
NAME_CHARACTERS=30


def interests(s):
    return {region for region, in s.rows('interest','strategic_region',country=s.player)}


def marker_required(s,play):
    return next(iter(definition(s,'common/diplomatic_plays',play,'requires_interest_marker')),'yes')!='no'


def engaged(s):
    return {region for region,involvement in s.rows('interest','strategic_region,involvement',country=s.player) if involvement>=ENGAGED}


def truce(s,country):
    sides={country}|{first for first,second in subject_pairs(s) if second==country}
    return bool(sides&truced(s))


def truced(s):
    return s.memo('truced',lambda:{country for country,own,theirs in s.rows('player_relation','country,player_truce,country_truce')
                                   if any(truce is not None and truce>now(s) for truce in (own,theirs))})


def reachable_state(s,state):
    owner=s.map('state','state,country').get(state)
    return (not busy(s) and not truce(s,owner) and owner not in opposed(s) and owner not in defensive_partners(s)
            and plays_permitted(s,owner,state_regions(s).get(state),state))


def reachable_country(s,country):
    capital=s.map('country','country,capital').get(country)
    return (not busy(s) and not truce(s,country) and country not in decentralized(s) and country not in guaranteed(s) and country not in defensive_partners(s)
            and not in_play(s,country) and not s.map('country','country,in_civil_war').get(country) and capital is not None and plays_permitted(s,country,state_regions(s).get(capital)))


def opposed(s):
    sides=play_sides(s)
    return {country for (play,side),members in sides.items() if s.player in sides.get((play,1-side),set()) for country in members}


def regions_in_play(s):
    return s.memo('regions_in_play',lambda:{region for region,war in s.rows('diplomatic_play','strategic_region,war') if war is None})


def country_regions(s,country):
    regions=state_regions(s)
    return {regions.get(state) for state, in s.rows('state','state',country=country)}


def plays_permitted(s,country,region,state=None):
    saved={'target_country':('country',country),'region':('strategic_region',region)}
    if state is not None:
        saved['state']=('state',state)
    return passes(s,'common/scripted_rules','can_start_diplomatic_plays_against',('body',),country_scope(s,**saved))


def guaranteed(s):
    return s.memo('guaranteed',lambda:{target for kind,target in s.rows('treaty_article','treaty_article_type,target_country',source_country=s.player)
                                      if kind=='guarantee_independence'})


def defensive_partners(s):
    def compute():
        sides={treaty:(first,second) for treaty,first,second in s.rows('treaty','treaty,first_country,second_country')}
        pairs=[sides.get(treaty,()) for treaty,kind in s.rows('treaty_article','treaty,treaty_article_type') if kind=='defensive_pact']
        return {other for pair in pairs if s.player in pair for other in pair if other!=s.player}
    return s.memo('defensive_partners',compute)


def decentralized(s):
    return s.memo('decentralized',lambda:{country for country, in s.rows('country','country',country_type='decentralized')})


def rank_of(s,country):
    return s.map('country','country,country_rank').get(country)


def type_of(s,country):
    return s.map('country','country,country_type').get(country)


def rank_value(s,country):
    return float(next(iter(definition(s,'common/country_ranks',rank_of(s,country),'rank_value')),-1))


def subject_fits(s,subject_type,country):
    field=lambda name:definition(s,'common/subject_types',subject_type,name)
    return ((not field('valid_overlord_country_types') or type_of(s,s.player) in field('valid_overlord_country_types'))
            and (not field('valid_subject_country_types') or type_of(s,country) in field('valid_subject_country_types'))
            and (not field('valid_overlord_ranks') or rank_of(s,s.player) in field('valid_overlord_ranks'))
            and (not field('valid_subject_ranks') or rank_of(s,country) in field('valid_subject_ranks'))
            and (field('overlord_must_be_higher_rank')!=['yes'] or rank_value(s,s.player)>rank_value(s,country)))


AUTONOMY_GOALS={'independence','increase_autonomy'}
UNSELECTABLE_GOALS={'liberate_country','unification','unification_leadership'}


INDEPENDENCE_LIBERTY=90


def own_subject_pacts(s):
    return [(action,value) for action,value in s.rows('pact','pact_type,liberty_desire',second_country=s.player)
            if definition(s,'common/diplomatic_actions',action,'subject_pact')]


def liberty_desire(s):
    return next((value for _,value in own_subject_pacts(s)),0)


def claims(s):
    return {region for region, in s.rows('country_claim','state_region',country=s.player)}


def owns_here(s,country):
    mine=set(building_ids(s))
    return any(owner==country and building in mine for building,owner in s.rows('building_ownership','building,owner',owner_type=COUNTRY_OWNER))


def own_subject_type(s):
    return next((next(iter(definition(s,'common/diplomatic_actions',action,'subject_type')),None) for action,_ in own_subject_pacts(s)),None)


def subject_permits(s,field):
    kind=own_subject_type(s)
    return kind is None or definition(s,'common/subject_types',kind,field)!=['no']


def play_allowed(s,play,**saved):
    scope=country_scope(s,**saved)
    target=saved.get('target_country',(None,None))[1]
    kinds={next(iter(definition(s,'common/war_goal_types',goal,'kind')),'') for goal in definition(s,'common/diplomatic_plays',play,'war_goal')}
    if kinds&AUTONOMY_GOALS:
        if (target,s.player) not in subject_pairs(s):
            return False
    elif not subject_permits(s,'can_start_own_diplomatic_plays'):
        return False
    if any(kind.startswith('make_') for kind in kinds):
        if not subject_permits(s,'can_have_subjects') or target in {subject for _,subject in subject_pairs(s)}:
            return False
    if 'reduce_autonomy' in kinds and target not in subjects(s):
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
    if 'regime_change' in kinds:
        return False
    if kinds&UNSELECTABLE_GOALS:
        return False
    for goal in definition(s,'common/diplomatic_plays',play,'war_goal'):
        kind=next(iter(definition(s,'common/war_goal_types',goal,'kind')),'')
        if kind.startswith('make_') and not subject_fits(s,'subject_type_'+kind.removeprefix('make_'),target):
            return False
    goals=definition(s,'common/diplomatic_plays',play,'war_goal')
    return (passes(s,'common/diplomatic_plays',play,('potential','possible','selectable_in_lens'),scope)
            and all(passes(s,'common/war_goal_types',goal,('possible','valid'),scope) for goal in goals))


def companies(s):
    if metric(s,'GetNumCompanies')>=metric(s,'GetMaxNumCompanies'):
        return []
    if any(second==s.player and kind=='chartered_company' for _,second,kind in s.rows('pact','first_country,second_country,pact_type')):
        return []
    acquired,_,_,_=technologies(s)
    held={kind for kind, in s.rows('company','company_type')}
    potential={combo['building_type'] for combo in buildable(s)}|{kind for _,kind,_ in s.buildings()}
    scope=country_scope(s)
    return [name for name in s.keys('company_type') if name not in held
            and any(set(definition(s,'common/buildings',kind,'unlocking_technologies'))<=acquired and kind in potential
                    for block in definition(s,'common/company_types',name,'building_types') for kind in block.split())
            and company_levels(s,{kind for block in definition(s,'common/company_types',name,'building_types') for kind in block.split()})>=COMPANY_MIN_LEVELS
            and passes(s,'common/company_types',name,('potential','possible'),scope)]


COMPANY_MIN_LEVELS=5


def located_buildings(s):
    return s.memo('located_buildings',lambda:{ident:(kind,state) for ident,kind,state in s.rows('building','building,building_type,state')})


def company_levels(s,kinds):
    def compute():
        mine=set(s.states())
        located=located_buildings(s)
        totals={}
        for building,kind,owner,levels in s.rows('building_ownership','building,owner_type,owner,levels'):
            name,state=located.get(building,(None,None))
            if state not in mine:
                continue
            owner_kind,owner_state=located.get(owner,('',None))
            if (owner==s.player if kind==COUNTRY_OWNER else not owner_kind.startswith('building_company') and owner_state in mine):
                totals.setdefault(name,{})[state]=totals.get(name,{}).get(state,0)+levels
        return totals
    totals={}
    for name,states in s.memo('company_levels',compute).items():
        if name in kinds:
            for state,levels in states.items():
                totals[state]=totals.get(state,0)+levels
    return max(totals.values(),default=0)


def sectors(s):
    return [ident for ident,kind,_ in s.buildings() if kind in CONSTRUCTION]


def mission_types(s,fleet):
    missions=s.map('naval_mission','naval_mission,naval_mission_type')
    current=missions.get(s.map('formation_status','formation,naval_mission').get(fleet))
    return [kind for kind in s.keys('naval_mission_type') if kind!=current and passes(s,'common/naval_mission_types',kind,('potential',),country_scope(s))]


def ship_queues(s):
    return {ident for ident, in s.rows('ship_queue','ship_queue',country=s.player)}


def ship_items(s):
    queues=ship_queues(s)
    return sorted(index for index,queue in s.rows('ship_construction','list_index,queue') if queue in queues)


def ship_paused(s):
    return bool(metric(s,'IsShipConstructionPaused'))


def construction_paused(s):
    return bool(metric(s,'IsConstructionPaused'))


def my_ships(s):
    queues=ship_queues(s)
    return [kind for kind,queue in s.rows('ship_construction','ship_type,queue') if queue in queues]


COUNTRY_OWNER=2


def private_levels(s):
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    buildable=building_kinds(s,buildable=True)
    located=s.map('building','building,state')
    countries=s.map('state','state,country')
    levels={}
    for building,kind,owner,count in s.rows('building_ownership','building,owner_type,owner,levels'):
        if kinds.get(building) in buildable and kind!=COUNTRY_OWNER and count and countries.get(located.get(owner))==s.player:
            levels[building]=levels.get(building,0)+int(count)
    return levels


NATIONALIZATION_PER_POINT=500
MIN_CONSTRUCTION_POINTS=100


def nationalization_cost(s,building):
    kind=dict((ident,kind) for ident,kind,_ in s.buildings()).get(building)
    points=[float(value) for name in definition(s,'common/buildings',kind,'required_construction')
            for value in definition(s,'common/script_values',name,'value')]
    return NATIONALIZATION_PER_POINT*max(points+[MIN_CONSTRUCTION_POINTS])


def government_owned(s):
    mine=set(building_ids(s))
    return {building for building,owner,count in s.rows('building_ownership','building,owner,levels',owner_type=COUNTRY_OWNER)
            if building in mine and owner==s.player and count}


def switchable(s):
    return {method for method, in s.rows('player_production_method_available','production_method')}


def monopolies(s):
    return {kind for kind, in s.rows('player_monopoly','building_type')}


def definition(s,folder,name,field):
    return s.definitions(folder).get(name,{}).get(field,[])


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


def private_kinds(s):
    monopolized=monopolies(s)
    return {kind for kind in building_kinds(s,buildable=True) if inherited(s,kind,'is_government_funded')!=['yes'] and kind not in monopolized}


def auto_expandable(s):
    return {kind for kind in building_kinds(s,buildable=True,expandable=True) if inherited(s,kind,'should_auto_expand')}


def monopolizable(s):
    held=monopolies(s)
    return sorted(kind for kind in building_kinds(s,buildable=True) if definition(s,'common/buildings',kind,'unique')!=['yes']
                  and inherited(s,kind,'is_government_funded')!=['yes'] and (kind in held or (authority(s)>=MONOPOLY_COST and len(held)<MAX_MONOPOLIES)))


MONOPOLY_COST=100
MAX_MONOPOLIES=5


def arable_kinds(s):
    return s.memo('arable_kinds',lambda:{kind for fields in s.definitions('map_data/state_regions').values() for kind in fields.get('arable_resources',())})


def free_arable(s,state):
    table,column=METRIC_COLUMNS['state','GetNumFreeArableLand']
    return need(s.map(table,'state,'+column).get(state),f'{column} of state {state}')


def has_room(s,ident):
    return s.map('building','building,building_type')[ident] not in arable_kinds(s) or free_arable(s,s.map('building','building,state')[ident])>=1


def owned_of(s,kinds):
    return [ident for ident,kind,_ in s.buildings() if kind in kinds]


def ownership_classes(s):
    def compute():
        mine=set(s.states())
        located=located_buildings(s)
        classes={}
        for building,kind,owner in s.rows('building_ownership','building,owner_type,owner'):
            if kind==COUNTRY_OWNER:
                found='owned_national' if owner==s.player else 'owned_foreign'
            elif owner in located:
                owner_kind,owner_state=located[owner]
                found='owned_company' if owner_kind.startswith('building_company') else 'owned_private' if owner_state in mine else 'owned_foreign'
            else:
                continue
            classes.setdefault(building,set()).add(found)
        return {building:found for building,found in classes.items() if located.get(building,(None,None))[1] in mine}
    return s.memo('ownership_classes',compute)


def bulk_subset(s,building_type,state,ownership):
    classes=ownership_classes(s)
    return [ident for ident,kind,_ in s.buildings() if kind==building_type and (state is None or s.map('building','building,state').get(ident)==state)
            and (ownership=='any' or ownership in classes.get(ident,()))]


def bulk_options(s,kinds,wanted):
    return [{'building_type':kind} for kind in sorted({kind for ident,kind,_ in s.buildings() if kind in kinds and wanted(s,ident)})]


def subset_options(s,kinds,wanted,by_state):
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    groups={}
    for ident,kind,_ in s.buildings():
        if kind in kinds:
            for ownership in ('any',*classes.get(ident,())):
                groups.setdefault((kind,located[ident] if by_state else None,ownership),[]).append(wanted(s,ident))
    return [{'building_type':kind,**({'state':state} if by_state else {}),'ownership':ownership}
            for (kind,state,ownership),members in sorted(groups.items(),key=str) if all(members)]


def nationalizable_subsets(s,by_state):
    levels=private_levels(s)
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    costs={}
    for ident,count in levels.items():
        for ownership in ('any',*classes.get(ident,set())-{'owned_foreign'}):
            key=(kinds[ident],located[ident] if by_state else None,ownership)
            costs[key]=costs.get(key,0)+nationalization_cost(s,ident)*count
    cash=money(s)
    return [{'building_type':kind,**({'state':state} if by_state else {}),'ownership':ownership}
            for (kind,state,ownership),cost in sorted(costs.items(),key=str) if cost<=cash]


def law_flag(s,modifier):
    return modifier_flag(s,s.player,modifier)


def privatizable(s,ident):
    return bool(setting(s,ident,'privatizable')) and not privatization_requested(s,ident)


def revolution_brewing(s):
    return bool(s.rows('civil_war','civil_war',origin_country=s.player))


PRIVATIZATION_REQUESTED=1


def privatization_requested(s,ident):
    return bool((s.map('building','building,privatization_requested').get(ident) or 0)&PRIVATIZATION_REQUESTED)


def active_laws(s):
    return {kind for kind, in s.rows('law','law_type',country=s.player,active=True)}


NO_DATE=43791240
PRINCIPLE_SLOTS=4
BLOC_INFLUENCE=500
ENACTMENT_COOLDOWN_HOURS=730*24


def enacting_laws(s):
    mine=set(s.mine('law'))
    return [ident for ident,started in s.rows('law_private','law,enactment_start_date') if ident in mine and started is not None and started!=NO_DATE]


def enacting(s):
    return bool(enacting_laws(s))


MIN_AMENABILITY=25
MARGINALIZED=2


def group_ideologies(s):
    return s.grouped('interest_group_ideology','interest_group,ideology')


def current_law(s,law):
    group=next(iter(definition(s,'common/laws',law,'group')),None)
    return next((name for name in active_laws(s) if definition(s,'common/laws',name,'group')==[group]),None)


def endorses(s,ideologies,law):
    return stance(s,ideologies,law)>stance(s,ideologies,current_law(s,law))


def governing(s):
    return [ident for ident, in s.rows('interest_group','interest_group',country=s.player,in_government=True)]


def opposed_in_government(s,law):
    ideologies=group_ideologies(s)
    clouts=s.map('interest_group_stats','interest_group,clout')
    stances=[(stance(s,ideologies.get(ident,[]),law),clouts[ident]) for ident in governing(s)]
    opposing=[clout for value,clout in stances if value<0]
    return law is not None and bool(opposing) and sum(opposing)>=sum(clout for value,clout in stances if value>0)


def endorsed(s,law):
    ideologies=group_ideologies(s)
    backers=[ideologies.get(ident,[]) for ident in governing(s)]
    ruler=[ideology for ident,ideology in s.rows('character','character,ideology',country=s.player) if 'character_role_ruler' in s.characters_roles(ident)]
    return any(endorses(s,values,law) for values in backers+[ruler])


def attached_amendments(s):
    def compute():
        active=set(s.mine('law'))&{ident for ident, in s.rows('law','law',active=True)}
        return {amendment for law,amendment in s.rows('law_amendment','law,amendment') if law in active}
    return s.memo('attached_amendments',compute)


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


def enactable(s):
    if enacting(s) or metric(s,'GetGovernmentLegitimacy')<ILLEGITIMATE:
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


def law_possible(s,country,law):
    fields=s.definitions('common/laws').get(law,{})
    held=trigger_laws(s,country)
    return (set(fields.get('unlocking_technologies',()))<=trigger_technologies(s,country)
            and (not fields.get('unlocking_laws') or set(fields['unlocking_laws'])&held)
            and not set(fields.get('disallowing_laws',()))&held
            and passes(s,'common/laws',law,('is_visible','can_enact'),country_scope(s,country))
            and all(passes(s,'common/law_groups',group,('change_allowed_trigger',),country_scope(s,country)) for group in fields.get('group',())))


def imposable(s):
    pending={owner for owner,imposer in s.rows('law','country,imposer') if imposer is not None}
    cooling={owner for owner, in s.rows('country_timed_modifier','country',modifier='impose_law_cooldown')}
    targets=subjects(s)-pending-cooling
    return [ident for ident,kind,owner,active in s.rows('law','law,law_type,country,active') if owner in targets and not active
            and law_possible(s,owner,kind) and all(evaluate(parsed(text),country_scope(s,target_country=('country',owner))) is not False
                                                   for text in definition(s,'common/laws',kind,'can_impose') or ['can_impose_law_default = yes'])]


def issued_decrees(s):
    return set(s.rows('player_active_decree','state,decree_type'))


def valid_decrees(s):
    return set(s.rows('state_decree_valid','state,decree_type'))


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


def unit_types_unlocked(s):
    acquired,_,_,_=technologies(s)
    return [name for name in s.keys('combat_unit_type') if set(definition(s,'common/combat_unit_types',name,'unlocking_technologies'))<=acquired]


def switch_methods(s):
    methods={}
    for kind,_,method in s.methods:
        methods.setdefault(kind,[]).append(method)
    active=s.grouped('building_production_method_active','building,production_method')
    allowed=switchable(s)
    return [{'building':ident,'production_method':method} for ident,kind,levels in s.buildings() if levels
            for method in methods.get(kind,()) if method in allowed and method not in active.get(ident,())]


def bulk_methods(s,by_state):
    classes=ownership_classes(s)
    located=s.map('building','building,state')
    kinds={ident:kind for ident,kind,_ in s.buildings()}
    groups={(kinds[option['building']],located[option['building']] if by_state else None,ownership,option['production_method'])
            for option in switch_methods(s) for ownership in ('any',*classes.get(option['building'],()))}
    return [{'building_type':kind,**({'state':state} if by_state else {}),'production_method':method,'ownership':ownership}
            for kind,state,ownership,method in sorted(groups,key=str)]


def unit_goods(s,folder,kind):
    return {goods for block in definition(s,folder,kind,'upkeep_modifier') for goods in re.findall(r'goods_input_(\w+)_add',block)}


def state_supply(s):
    return {state:set(goods) for state,goods in s.grouped('state_goods_supply','state,goods').items()}


def recruit(s):
    supplies=state_supply(s)
    located=s.map('building','building,state')
    barracks=[(ident,located.get(ident)) for ident,kind,_ in s.buildings() if kind=='building_barrack']
    return [{'building':ident,'military_formation':formation,'combat_unit_type':kind}
            for ident,state in barracks for kind in unit_types_unlocked(s)
            if unit_goods(s,'common/combat_unit_types',kind)<=supplies.get(state,set())
            for formation in s.formations('army')]


def conscription_states(s):
    located=s.map('building','building,state')
    return sorted({located[ident] for ident,kind,levels in s.buildings() if kind=='building_conscription_center' and levels})


def subjects(s):
    return {second for first,second in subject_pairs(s) if first==s.player}


def power_bloc_members(s):
    blocs={ident:bloc for ident,bloc in s.rows('country','country,power_bloc') if bloc is not None}
    return sorted(ident for ident,bloc in blocs.items() if s.player in blocs and bloc==blocs[s.player] and ident!=s.player)


def research(s):
    return set(s.mine('country_research'))


def technologies(s):
    return s.memo('player_technologies',lambda:compute_technologies(s))


def compute_technologies(s):
    rows=research(s)
    acquired={kind for owner,kind in s.rows('country_research_acquired','country_research,technology') if owner in rows}
    queued={kind for owner,kind in s.rows('country_research_queued','country_research,technology') if owner in rows}
    current={kind for ident,kind in s.rows('country_research','country_research,researching') if ident in rows}
    requires={name:set(fields.get('unlocking_technologies',())) for name,fields in s.definitions('common/technology/technologies').items()}
    return acquired,queued,current,requires


def researchable(s):
    acquired,queued,current,requires=technologies(s)
    return [name for name in s.keys('technology') if name not in acquired|queued|current and requires.get(name,set())<=acquired and researchable_kind(s,name)]


def queueable(s):
    acquired,queued,current,_=technologies(s)
    return [name for name in s.keys('technology') if name not in acquired|queued|current and researchable_kind(s,name)]


def researchable_kind(s,name):
    return definition(s,'common/technology/technologies',name,'can_research')!=['no']


def buildable(s):
    acquired,_,_,_=technologies(s)
    capped={kind for kind, in s.rows('state_region_resource','building_type')}
    regions={ident:region for ident,region in s.rows('state','state,state_region',country=s.player)}
    arable={region:set(fields.get('arable_resources',())) for region,fields in s.definitions('map_data/state_regions').items()}
    limited={kind for fields in s.definitions('common/building_groups').values() for kind in fields.get('default_building',())}
    combos=[]
    for kind,fields in s.definitions('common/buildings').items():
        if fields.get('buildable')==['no'] or fields.get('recruits_combat_units')==['yes'] or not set(fields.get('unlocking_technologies',()))<=acquired:
            continue
        for state,region in regions.items():
            if kind in limited and kind not in arable.get(region,set()):
                continue
            if kind in arable_kinds(s) and free_arable(s,state)<1:
                continue
            if kind in capped and kind not in limited:
                continue
            if passes(s,'common/buildings',kind,('potential','possible','can_build','can_build_government'),Scope(s,'state',state)):
                combos.append({'state':state,'building_type':kind})
    return combos


def construction_queue(s):
    return [(state,kind) for _,state,kind in sorted(s.rows('player_construction_queue_item','position,state,building_type',private=False))]


def queue_items(s,skip_first,skip_last):
    pairs=construction_queue(s)
    return [{'state':state,'building_type':kind} for state,kind in pairs[skip_first:len(pairs)-skip_last] if pairs.count((state,kind))==1]


def queued_buildings(s):
    pending=set(construction_queue(s))
    owned=set(s.states())
    return [ident for ident,kind,state in s.rows('building','building,building_type,state') if state in owned and (state,kind) in pending]


def subsidized(s,flag):
    owned=set(s.states())
    return [ident for ident,state,value in s.rows('building','building,state,subsidized') if state in owned and value==flag]


def settled(s,formations):
    places={ident:(current,target) for ident,current,target in s.rows('formation_status','formation,current_location,target_location')}
    return [formation for formation in formations if formation in places and places[formation][0]==places[formation][1]]


def war_fronts(s):
    wars=set(s.wars())
    return sorted({front for front,war in s.rows('front_side','front,war') if war in wars})


def deployable(s):
    return {formation for formation, in s.rows('formation_report','formation',deployable=True)}


def idle_armies(s):
    return [f for f in settled(s,armies(s,False)) if not demobilizing(s,f)]


def mobilization_options(s,formation):
    acquired,_,_,_=technologies(s)
    principles=bloc_principles(s)
    active=set(s.grouped('formation_mobilization_option','formation,mobilization_option').get(formation,()))
    return [name for name in s.keys('mobilization_option')
            if set(definition(s,'common/mobilization_options',name,'unlocking_technologies'))<=acquired
            and (not definition(s,'common/mobilization_options',name,'unlocking_principles') or set(definition(s,'common/mobilization_options',name,'unlocking_principles'))&principles)
            and passes(s,'common/mobilization_options',name,('possible',),Scope(s,'formation',formation))
            and (name not in active or passes(s,'common/mobilization_options',name,('can_be_turned_off',),Scope(s,'formation',formation)))]


def formation_setting(s,formation,column):
    return s.map('formation_private','formation,'+column).get(formation)


def formation_report(s,formation,column):
    return s.map('formation_report','formation,'+column).get(formation)


def demobilizing(s,formation):
    return (any(owner==formation and progress for owner,progress in s.rows('combat_unit','formation,mobilization'))
            or bool(formation_report(s,formation,'demobilizing')))


def armies(s,mobilized):
    manned=set(s.formations('army'))
    return [ident for ident,value in s.rows('formation_status','formation,mobilized') if ident in manned and value==mobilized]


def unit_types(s,military_formation):
    return sorted({kind for kind, in s.rows('combat_unit','combat_unit_type',formation=military_formation)})


def selected_units(s,formation):
    return dict(s.rows('formation_selected_unit_type','combat_unit_group,combat_unit_type',formation=formation))


def unit_group(s,kind):
    return next(iter(definition(s,'common/combat_unit_types',kind,'group')),None)


def upgradable(s,military_formation,combat_unit_type):
    selected=selected_units(s,military_formation).get(unit_group(s,combat_unit_type))
    pending={kind for kind, in s.rows('formation_upgrade_unit_type','combat_unit_type',formation=military_formation)}
    return selected is not None and combat_unit_type not in pending and selected in definition(s,'common/combat_unit_types',combat_unit_type,'upgrades')


def changing(s):
    current=s.map('institution','institution,investment')
    return {ident:target for ident,target in s.rows('institution_private','institution,target_investment') if target and target!=current.get(ident)}


def hq_regions(s):
    mine=set(s.mine('hq'))
    return {ident:(kind,region) for ident,kind,region in s.rows('hq_private','hq,hq_type,hq_region') if ident in mine and kind is not None}


def home_of(s,formation):
    return formation_setting(s,formation,'home_hq')


def at_home(s,formation):
    return state_regions(s).get(located(s,formation))==hq_regions(s).get(home_of(s,formation),(None,None))[1]


def located(s,formation):
    return s.map('formation_status','formation,current_location').get(formation)


def home_region(s,formation):
    return hq_regions(s).get(home_of(s,formation),(None,None))[1]


def travelling(s,formation):
    return bool(formation_setting(s,formation,'travel_distance'))


def rehome(s):
    regions=hq_regions(s)
    kinds=s.map('formation','formation,formation_type',country=s.player)
    return [{'military_formation':formation,'strategic_region':region} for formation in idle_armies(s) if not travelling(s,formation)
            for kind,region in sorted(set(regions.values())) if kind==kinds[formation] and region!=regions.get(home_of(s,formation),(None,None))[1]]


def conscript_types(s,formation):
    kinds={ident:kind for ident,(kind,_) in located_buildings(s).items()}
    return sorted({unit for unit,building in s.rows('combat_unit','combat_unit_type,building',formation=formation)
                   if kinds.get(building)=='building_conscription_center'})


def formation_units(s,formations):
    return [{'military_formation':formation,'combat_unit_type':kind} for formation in formations for kind in unit_types(s,formation)]


def country_metric(s,country,name):
    table,column=METRIC_COLUMNS['country',name]
    if table.startswith('player_'):
        return s.rows(table,column)[0][0] if country==s.player and s.rows(table,column) else None
    return s.map(table,'country,'+column).get(country)


def metric(s,name):
    return need(country_metric(s,s.player,name),f'{name} of the player')


def need(value,what):
    if value is None:
        raise RuntimeError(f'{what} is not captured')
    return value


def authority(s):
    return metric(s,"GetPowerDelta('authority')")


def in_default(s):
    return bool(metric(s,'InDefault'))


def money(s):
    return need(player_value(s,'player_treasury','money'),'player money')


STRAIT_COOLDOWN_MONTHS=6
STRAIT_SIDES=('first','second')


def strait_sides(s):
    mine=set(s.states())-{state for state,controller in s.rows('occupation','state,controller') if controller!=s.player}
    sides=[]
    for strait,first,second in s.rows('strait_endpoint','strait,first_state,second_state'):
        held=[(side,state) for side,state in zip(STRAIT_SIDES,(first,second)) if state in mine]
        sides+=[(strait,side,state) for side,state in held[:1 if len(held)==2 else 2]]
    return sides


def strait_value(s,strait,column):
    return s.map('strait',f'strait,{column}').get(strait)


def strait_settable(s,strait,column):
    changed=strait_value(s,strait,column)
    return changed is None or now(s)>=months_later(changed,STRAIT_COOLDOWN_MONTHS)


def strait_requires(s,strait,field):
    return definition(s,'common/strait_definitions',strait_value(s,strait,'strait_definition'),field)==['yes']


def full_strait_control(s,strait):
    mine=set(s.states())
    return all(state in mine for first,second in s.rows('strait_endpoint','first_state,second_state',strait=strait) for state in (first,second))


def strait_tolls(s):
    if not player_value(s,'player_policy','can_toll_straits'):
        return []
    return [{'strait':strait,'level':level} for strait,side,_ in strait_sides(s)
            if (full_strait_control(s,strait) or not strait_requires(s,strait,'tolls_require_full_control')) and strait_settable(s,strait,f'{side}_last_toll_rate_change')
            for index,level in enumerate(TOLL_LEVELS) if strait_value(s,strait,f'{side}_toll_rate')!=index]


def strait_accesses(s):
    closing=player_value(s,'player_policy','can_close_straits')
    blocks={'Closed':'total_block_requires_full_control','NoMilitary':'military_block_requires_full_control'}
    return [{'strait':strait,'state':state,'access':status} for strait,side,state in strait_sides(s) if strait_settable(s,strait,f'{side}_last_access_change')
            for index,status in enumerate(ACCESS_STATUSES) if strait_value(s,strait,f'{side}_access_status')!=index
            and (status=='Open' or closing and (full_strait_control(s,strait) or not strait_requires(s,strait,blocks[status])))]


def strait_permissions(s):
    return [{'strait':strait,'state':state,'allowed':allowed} for strait,side,state in strait_sides(s) if strait_value(s,strait,f'{side}_access_status')
            for index,allowed in enumerate(ACCESS_PERMISSIONS,1) if strait_value(s,strait,f'{side}_access_permissions')!=index]


def player_value(s,table,column):
    rows=s.rows(table,column)
    return rows[0][0] if rows else None


FASTEST_SPEED='4'
DEFAULT_TAX_COST=100


def pop_demand(s):
    def compute():
        market=s.map('country','country,market').get(s.player)
        areas={area for area, in s.rows('market_area','market_area',market=market)}
        states={state for area,state in s.rows('market_area_state','market_area,state') if area in areas}
        mine={ident for ident,state in s.rows('building','building,state') if state in states}
        demand=dict(s.rows('market_goods','goods,buy_orders',market=market))
        for ident,goods,value in s.rows('building_goods','building,goods,input'):
            if ident in mine and value is not None:
                demand[goods]=demand.get(goods,0)-value
        return demand
    return s.memo('pop_demand',compute)


def taxable(s):
    taxed={goods for goods, in s.rows('player_taxed_goods','goods')}
    consumed={goods for fields in s.definitions('common/pop_needs').values() for goods in fields.get('goods',[])}
    return [goods for goods in s.keys('goods') if goods in taxed or (goods in consumed and pop_demand(s).get(goods,0)>0
            and authority(s)>=float(next(iter(definition(s,'common/goods',goods,'consumption_tax_cost')),DEFAULT_TAX_COST)))]


def movements(s,status):
    return [ident for ident,managed in s.rows('political_movement','political_movement,managed_status',country=s.player)
            if managed==status or (managed is None and authority(s)>=MOVEMENT_COST)]


MOVEMENT_COST=200
SUPPRESSED,PROMOTED=1,2


def other_levels(s,column):
    current=player_value(s,'player_policy',column)
    return [level for index,level in enumerate(LEVELS) if index!=current]


def promotable(s,character):
    rank=definition(s,'common/commander_ranks',s.map('character','character,rank').get(character),'rank_value')
    return bool(rank) and float(rank[0])<float(definition(s,'common/defines','NCharacters|HIGHEST_PROMOTION_RANK','value')[0])


def assigned(s,character):
    return s.map('character_status','character,has_formation').get(character) is True


def idle_room(s,character):
    kind='Admirals' if 'character_role_admiral' in s.characters_roles(character) else 'Generals'
    return metric(s,f'GetNumUnassigned{kind}')<metric(s,f'GetMaxUnassigned{kind}')


def fits(s,character,formation):
    army=s.map('formation','formation,formation_type',country=s.player).get(formation)==0
    return ('character_role_general' if army else 'character_role_admiral') in s.characters_roles(character)


def leaders(s,formation):
    return [ident for ident, in s.rows('character','character',country=s.player,formation=formation)]


def commanders_where(s,test):
    pool=set(recruitable(s))
    rows={ident:(formation,ident in pool) for ident,formation in s.rows('character','character,formation',country=s.player)}
    return [ident for ident in s.commanders() if ident in rows and test(*rows[ident])]


def involved(s):
    sides={ident:(initiator,target) for ident,initiator,target in s.rows('diplomatic_play','diplomatic_play,initiator,target')}
    interested={ident for ident, in s.rows('diplomatic_play_country','diplomatic_play',country=s.player,role='interested')}
    return sides,interested


OPENING_PHASE_END=21


def at_war_plays(s):
    return {play for play,war,level in s.rows('diplomatic_play','diplomatic_play,war,escalation') if war is not None or level>=100}


def play_of_war(s,war):
    return next((ident for ident, in s.rows('diplomatic_play','diplomatic_play',war=war)),None)


def war_of_play(s,play):
    linked=s.map('diplomatic_play','diplomatic_play,war').get(play)
    return next((war for war, in s.rows('war','war') if war==linked),None)


def negotiable_war(s,war):
    kind=next((kind for kind, in s.rows('diplomatic_play','diplomatic_play_type',war=war)),None)
    return next(iter(definition(s,'common/diplomatic_plays',kind,'allow_negotiated_peace')),'yes')!='no'


def war_leader(s,war):
    return any(s.player in (initiator,target) for initiator,target in s.rows('diplomatic_play','initiator,target',war=war))


def war_countries(s,war):
    play=s.map('war','war,diplomatic_play').get(war)
    return {country for country, in s.rows('war_participant','country',diplomatic_play=play)}


def has_say(s,war):
    play=play_of_war(s,war)
    return not overlords(s,s.player) and any(owner==play and s.player in (holder,target) for owner,holder,target in live_goals(s,'holder,target_country'))


def escalated(s):
    return {play for play,escalation in s.rows('diplomatic_play','diplomatic_play,escalation') if escalation>=OPENING_PHASE_END}


COUNTDOWN=80


def escalation(s,play):
    return s.map('diplomatic_play','diplomatic_play,escalation').get(play,0)


SIDES=('initiator','target')


def play_members(s):
    def compute():
        members={}
        for side,role in enumerate(SIDES):
            for play,country in s.rows('diplomatic_play_country','diplomatic_play,country',role=role):
                members.setdefault((play,side),set()).add(country)
        return members
    return s.memo('play_members',compute)


def committed(s,play):
    return {side for side in range(2) if s.player in play_members(s).get((play,side),set())}


HOSTILE=-80


def side_open(s,play,side):
    leaders=involved(s)[0].get(play,())
    mine=overlords(s,s.player)
    backers=play_members(s).get((play,1-side),set())
    return (len(leaders)==2 and relations(s,leaders[side])>HOSTILE and not mine&set(leaders) and not mine&backers
            and not truce(s,leaders[1-side]) and leaders[side] not in war_enemies(s))


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


def interested_plays(s):
    sides,interested=involved(s)
    return sorted(ident for ident in interested if s.player not in sides.get(ident,()) and ident not in at_war_plays(s))


def third_party(s,start=OPENING_PHASE_END):
    return [play for play in interested_plays(s) if start<=escalation(s,play)<COUNTDOWN]


def opening(s):
    return [play for play in interested_plays(s) if escalation(s,play)<OPENING_PHASE_END]


def leaning(s,side):
    return s.memo(('leaning',side),lambda:{play for play, in s.rows('diplomatic_play_country','diplomatic_play',country=s.player,role=side+'_ally')})


def principal(s):
    sides,_=involved(s)
    ends=s.map('diplomatic_play','diplomatic_play,end_date')
    return sorted(ident for ident,pair in sides.items() if s.player in pair and ends.get(ident) is None)


def backable(s):
    return [play for play in principal(s) if play in escalated(s) and play not in at_war_plays(s)]


def busy(s):
    return any(play not in at_war_plays(s) for play in principal(s))


def colonies(s):
    mine=set(s.states())
    return [ident for ident,province in s.rows('state_status','state,next_colony_province') if ident in mine and province is not None]


def in_play(s,country):
    return any(country in members for members in play_sides(s).values())


def incorporation(s):
    return s.map('state_status','state,incorporation')


def abandonable(s):
    progress=incorporation(s)
    return [] if in_play(s,s.player) else [state for state in colonies(s) if progress.get(state)!=1]


def colonizable(s):
    rows=s.rows('state','state,state_region,country')
    colonized={s.map('state','state,state_region').get(state) for state in colonies(s)}
    blocked={region for state,region,country in rows if in_play(s,country)}
    return sorted({region:state for state,region,country in rows if country in decentralized(s) and state_regions(s).get(state) in interests(s)
                   and region not in colonized and region not in blocked and not truce(s,country)}.values())


def charter_toggles(s):
    unlocks=s.map('charter_private','charter,unlock')
    granted={(company,kind):unlocks.get(charter) for charter,company,kind in s.rows('charter','charter,company,company_charter_type')}
    return [{'company':company,'charter':charter} for company in s.mine('company') for charter in ('investment_charter','trade_charter')
            if (company,charter) not in granted or granted[company,charter] is not None and now(s)>=granted[company,charter]]


def journal_buttons(s):
    shown=set(s.rows('player_journal_button','journal_entry_type,scripted_button'))
    combos=[]
    involved={entry for entry, in s.rows('journal_entry_involved_country','journal_entry',country=s.player)}
    for ident,entry,owner,active in s.rows('journal_entry','journal_entry,journal_entry_type,country,active'):
        if owner!=s.player and ident not in involved:
            continue
        visible=[button for button in definition(s,'common/journal_entries',entry,'scripted_button') if (entry,button) in shown]
        combos+=[{'journal_entry':ident,'button':index} for index,button in enumerate(visible)
                 if active and passes(s,'common/scripted_buttons',button,('possible',),country_scope(s,journal_entry=('journal_entry',ident)))]
    return combos


def play_types(s,target):
    return [name for name in s.keys('diplomatic_play_type') if not definition(s,'common/diplomatic_plays',name,'never_selectable')
            and any(definition(s,'common/war_goal_types',goal,'target_type')==[target] for goal in definition(s,'common/diplomatic_plays',name,'war_goal'))]


def war_goals(s):
    sides,_=involved(s)
    return [{'diplomatic_play':play,'war_goal_type':kind,'country':target} for play,kind,target,holder,creator,status in live_goals(s,'war_goal_type,target_country,holder,creator,status')
            if s.player in sides.get(play,()) and holder==s.player and creator==s.player and status==1 and target is not None]


def goal_targets(s,play,kind):
    if definition(s,'common/war_goal_types',kind,'target_type')!=['country']:
        return True
    leaders=involved(s)[0].get(play,())
    targets={leader for leader in leaders if leader!=s.player} if s.player in leaders else set()
    settings=set(definition(s,'common/war_goal_types',kind,'settings'))
    goals=[(target,holder) for other,goal_kind,target,holder in live_goals(s,'war_goal_type,target_country,holder') if other==play and goal_kind==kind]
    if 'validate_conflicts_war_goals_all' in settings:
        targets-={target for target,_ in goals}
    if 'validate_conflicts_war_goals_holder' in settings:
        targets-={target for target,holder in goals if holder==s.player}
    if 'validate_revoke_claims' in settings:
        regions={region for region, in s.rows('state','state_region',country=s.player)}
        targets&={country for country,region in s.rows('country_claim','country,state_region') if region in regions}
    return targets


def live_goals(s,columns):
    plays=set(s.plays())
    return [row for row in s.rows('war_goal','diplomatic_play,'+columns) if row[0] in plays]


def setting(s,building,column):
    return s.map('building_private',f'building,{column}').get(building)


def ship_types(s):
    acquired,_,_,_=technologies(s)
    return [name for name in s.keys('ship_type') if set(definition(s,'common/ship_types',name,'unlocking_technologies'))<=acquired
            and definition(s,'common/ship_types',name,'ship_group')!=['ship_group_supply_ships']]


def ship_slots(s,kind):
    slots=[(slot,mods.split()) for block in definition(s,'common/ship_types',kind,'modifications') for slot,mods in re.findall(r'(\w+) = \{([^}]*)\}',block)]
    return [(slot,mods) for slot,mods in slots if definition(s,'common/ship_modification_slots',slot,'utility')!=['yes']]


def latest_design(s,template):
    versions=sorted(s.rows('ship_template_version_list','position,ship_template_version',ship_template=template))
    return tuple(mod for _,mod in sorted(s.rows('ship_template_version_modification','position,ship_modification',ship_template_version=versions[-1][1]))) if versions else ()


def designed(s,kind):
    return {latest_design(s,template) for template,owner,ship_type in s.rows('ship_template','ship_template,country,ship_type') if owner==s.player and ship_type==kind}


def unlocked_modifications(s,kind):
    acquired,_,_,_=technologies(s)
    return [mod for _,mods in ship_slots(s,kind) for mod in mods
            if not definition(s,'common/ship_modifications',mod,'unlocking_technologies') or set(definition(s,'common/ship_modifications',mod,'unlocking_technologies'))&acquired]


def ship_designs(s):
    return [{'ship_type':kind,'ship_modification':mod} for kind in ship_types(s) for mod in unlocked_modifications(s,kind)
            if not any(mod in design for design in designed(s,kind))]


def templates_in_construction(s):
    building={version for version, in s.rows('ship_construction','version')}
    return {template for template,version in s.rows('ship_template_version_list','ship_template,ship_template_version') if version in building}


TEMPLATE_DELETING=4


def own_templates(s):
    base=s.map('ship_template_private','ship_template,base')
    flags=s.map('ship_template_private','ship_template,flags')
    first=s.first_seen('ship_template')
    mine=sorted((kind,not base.get(template),first[template],template) for template,owner,kind in s.rows('ship_template','ship_template,country,ship_type')
                if owner==s.player and not (flags.get(template) or 0)&TEMPLATE_DELETING)
    return {(kind,index):template for kind in {item[0] for item in mine} for index,(*_,template) in enumerate(item for item in mine if item[0]==kind)}


def non_default_templates(s):
    flags=s.map('ship_template_private','ship_template,flags')
    return {key for key,template in own_templates(s).items() if not flags.get(template,0)&1}


def fleet_templates(s):
    assigned=set(s.rows('ship_template_fleet','ship_template,fleet'))
    return [{'ship_type':kind,'index':index,'military_formation':fleet} for (kind,index),template in sorted(own_templates(s).items())
            for fleet in s.formations('fleet') if (template,fleet) not in assigned]


def retrofit_fleets(s,retrofitting):
    return [f for f in s.formations('fleet') if formation_report(s,f,'retrofitting')==retrofitting and (retrofitting or formation_report(s,f,'retrofittable'))]


JOIN_LEVERAGE=200


def bloc_leaders(s):
    return {country for country, in s.rows('country','country',bloc_leader=True)}


def below_leader(s,bloc):
    leader=next((c for c in bloc_leaders(s) if bloc in power_bloc_of(s,c)),None)
    return leader is not None and need(country_metric(s,s.player,'GetPrestige'),'player prestige')<need(country_metric(s,leader,'GetPrestige'),f'prestige of {leader}') or (
        leader is not None and rank_value(s,s.player)<rank_value(s,leader))


BLOC_MEMBERSHIP_MONTHS=6


def may_leave(s):
    bloc=next(iter(power_bloc_of(s,s.player)))
    identity=s.map('power_bloc','power_bloc,power_bloc_identity').get(bloc)
    joined=s.map('country','country,power_bloc_join_date').get(s.player)
    return (joined is not None and now(s)>=months_later(joined,BLOC_MEMBERSHIP_MONTHS)
            and passes(s,'common/power_bloc_identities',identity,('can_leave',),country_scope(s)))


def bloc_leader(s):
    return s.player in bloc_leaders(s)


def may_found_bloc(s):
    return (not power_bloc_of(s,s.player) and not overlords(s,s.player) and s.player not in decentralized(s) and not revolution_brewing(s)
            and 'law_isolationism' not in active_laws(s) and metric(s,"GetPowerDelta('influence')")>=BLOC_INFLUENCE
            and rank_value(s,s.player)>=float(next(iter(definition(s,'common/country_ranks','unrecognized_major_power','rank_value')),99)))


def power_bloc_of(s,country):
    bloc=s.map('country','country,power_bloc').get(country)
    return set() if bloc is None else {bloc}


def insurrectionary(s):
    uprisings={movement for movement, in s.rows('civil_war','political_movement',origin_country=s.player)}
    return {group for group,movement in s.rows('interest_group_movement_support','interest_group,political_movement') if movement in uprisings}


def governing_count(s):
    return len(governing(s))


def principle_allowed(s,principle):
    return passes(s,'common/power_bloc_principles',principle,('visible','possible'),country_scope(s))


def bloc_principles(s):
    return {kind for bloc,kind in s.rows('power_bloc_adopted_principle','power_bloc,power_bloc_principle') if bloc in player_blocs(s)}


def bloc_identity(s):
    return next((kind for bloc,kind in s.rows('power_bloc','power_bloc,power_bloc_identity') if bloc in player_blocs(s)),None)


def mandates(s):
    return bool(player_value(s,'player_policy','has_bloc_mandates'))


def player_blocs(s):
    return power_bloc_of(s,s.player)


def pressed_in(s,war):
    play=play_of_war(s,war)
    return any(flag for owner,holder,flag in live_goals(s,'holder,pressed') if owner==play and holder==s.player)


def peace_open(s,war):
    date=s.map('war','war,peace_date').get(war)
    return date is None or now(s)>=date


def proposer(s,war):
    return s.map('war','war,peace_proposer').get(war)


def enemy_states(s):
    wars=set(s.wars())
    plays={play for ident,play in s.rows('war','war,diplomatic_play') if ident in wars}
    enemies={country for country,play in s.rows('war_participant','country,diplomatic_play') if play in plays}-{s.player}
    return [ident for ident,country in s.rows('state','state,country') if country in enemies]


def proposers(s,kind):
    return sorted({country for country, in s.rows('player_proposal','country',kind=kind)})


def recruitable(s):
    return [ident for ident, in s.rows('character_private','character',recruitable=True)]


def cooling(s):
    return {kind for kind,until in s.rows('player_interaction_cooldown','character_interaction,until') if until>now(s)}


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


def relations(s,country):
    return s.map('player_relation','country,relations').get(country,0)


def pact_between(s,action,country):
    pacts=s.memo('pacts',lambda:set(s.rows('pact','first_country,second_country,pact_type')))
    return (s.player,country,action) in pacts or any((country,s.player,reverse) in pacts for reverse in definition(s,'common/diplomatic_actions',action,'reverse_pact'))


def rank_ladder(s,country):
    recognized=lambda c:type_of(s,c)=='recognized'
    ladder=sorted((r for r in s.definitions('common/country_ranks') if r!='decentralized_power' and r.startswith('unrecognized')!=recognized(country)),
                  key=lambda r:float(next(iter(definition(s,'common/country_ranks',r,'rank_value')),0)))
    return ladder.index(rank_of(s,country)) if rank_of(s,country) in ladder else None


def shared_interest(s,country):
    regions={}
    for owner,region,involvement in s.rows('interest','country,strategic_region,involvement'):
        if involvement>=ENGAGED:
            regions.setdefault(owner,set()).add(region)
    return bool(regions.get(s.player,set())&regions.get(country,set()))


def rivalry_allowed(s,country):
    if not shared_interest(s,country) or not autonomous(s,s.player) or not autonomous(s,country):
        return False
    mine,theirs=rank_ladder(s,s.player),rank_ladder(s,country)
    return (relations(s,country)<CORDIAL and (type_of(s,s.player)=='recognized')==(type_of(s,country)=='recognized')
            and mine is not None and theirs is not None and abs(mine-theirs)<=1)


DIPLOMATIC={'da_knowledge_sharing':lambda s,c:len(technologies(s)[0])>len(tech_of(s,c)),
            'increase_relations':lambda s,c:relations(s,c)<AMICABLE and not pact_between(s,'damage_relations',c),
            'damage_relations':lambda s,c:relations(s,c)>COLD and not pact_between(s,'increase_relations',c),
            'rivalry':lambda s,c:rivalry_allowed(s,c) and not pact_between(s,'rivalry',c),
            'join_power_bloc':lambda s,c:not overlords(s,s.player) and any(bloc_advantage(s,bloc,s.player)>=JOIN_LEVERAGE and below_leader(s,bloc)
                                                                            for bloc in power_bloc_of(s,c)),
            'invite_to_power_bloc':lambda s,c:not power_bloc_of(s,c),
            'da_support_regime':lambda s,c:country_metric(s,c,'GetGovernmentLegitimacy') is not None and country_metric(s,c,'GetGovernmentLegitimacy')<75}


def diplomatic_options(s):
    return s.rows('player_diplomatic_option','target_country,action_type,possible')


def diplomatic_shown(s):
    return s.memo('diplomatic_shown',lambda:{(country,action) for country,action,_ in diplomatic_options(s)})


def diplomatic_possible(s):
    return s.memo('diplomatic_possible',lambda:{(country,action) for country,action,possible in diplomatic_options(s) if possible})


def diplomatic_allowed(s,country,action):
    return (set(definition(s,'common/diplomatic_actions',action,'unlocking_technologies'))<=technologies(s)[0]
            and (country,action) in diplomatic_possible(s)
            and passes(s,'common/diplomatic_actions',action,('maintain',),country_scope(s,target_country=('country',country),actor=('country',s.player)))
            and action_group_allows(s,action,country) and not pact_between(s,action,country)
            and metric(s,"GetPowerDelta('influence')")>=float(next(iter(definition(s,'common/diplomatic_actions',action,'pact_cost')),0))
            and DIPLOMATIC.get(action,lambda s,c:True)(s,country))


def obligations(s):
    return set(s.rows('player_obligation','country,direction'))


def tech_of(s,country):
    rows={ident for ident, in s.rows('country_research','country_research',country=country)}
    return {kind for owner,kind in s.rows('country_research_acquired','country_research,technology') if owner in rows}


def event_options(s):
    kinds=s.map('event','event,event_type')
    return [{'event':kinds[event],'option':visible} for event,enabled,visible in s.rows('event_option','event,enabled,visible_position')
            if visible is not None and enabled]


def listed(s,table,column):
    return [value for _,value in sorted(s.rows(table,'position,'+column))]


def remove_companies(s):
    owning={company for company, in s.rows('company_owned_country','company')}
    return [kind for ident,kind,established in s.rows('company','company,company_type,established',country=s.player)
            if ident not in owning and established is not None and now(s)>=months_later(established,COMPANY_LOCK_MONTHS)]


def invasions(s):
    return s.rows('invasion','front,ended',invaded=s.player)


def enforced_on_player(s):
    return set(s.rows('player_treaty_enforced','first_country,second_country'))


RULES={
    'build':lambda s:[] if in_default(s) else buildable(s),
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
    'auto_expand_on':lambda s:product(building=[i for i in owned_of(s,auto_expandable(s)) if not setting(s,i,'auto_expand') and has_room(s,i)]),
    'auto_expand_off':lambda s:product(building=[i for i in owned_of(s,auto_expandable(s)) if setting(s,i,'auto_expand')]),
    'switch_production_method':switch_methods,
    **{f'subset_{name}{suffix}':(lambda kinds,wanted,by_state:lambda s:subset_options(s,kinds(s),wanted,by_state))(kinds,wanted,suffix=='_state')
       for name,kinds,wanted in (('subsidies_on',private_kinds,lambda s,i:not s.map('building','building,subsidized').get(i)),
                                 ('subsidies_off',private_kinds,lambda s,i:bool(s.map('building','building,subsidized').get(i))),
                                 ('auto_expand_on',auto_expandable,lambda s,i:not setting(s,i,'auto_expand') and has_room(s,i)),
                                 ('auto_expand_off',auto_expandable,lambda s,i:bool(setting(s,i,'auto_expand'))))
       for suffix in ('','_state')},
    'bulk_nationalize':lambda s:[] if law_flag(s,'country_disable_nationalization_bool') else nationalizable_subsets(s,False),
    'bulk_nationalize_state':lambda s:[] if law_flag(s,'country_disable_nationalization_bool') else nationalizable_subsets(s,True),
    'bulk_switch_production_method':lambda s:bulk_methods(s,False),
    'bulk_switch_production_method_state':lambda s:bulk_methods(s,True),
    **{f'bulk_{name}':(lambda kinds,wanted:lambda s:bulk_options(s,kinds(s),wanted))(kinds,wanted)
       for name,kinds,wanted in (('subsidies',private_kinds,lambda s,i:True),('auto_expand',auto_expandable,has_room),
                                 ('privatization',private_kinds,privatizable),('remove_privatization',private_kinds,lambda s,i:privatization_requested(s,i) and not law_flag(s,'country_force_privatization_bool')))},
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
                                                   if ident in attached_amendments(s)
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
    'queue_research':lambda s:product(technology=queueable(s)),
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
    'set_formation_flag':lambda s:[{'military_formation':f,'flag':flag} for f in s.formations('army')
                                   if (name:=formation_report(s,f,'display_name')) is not None and len(name)<=NAME_CHARACTERS
                                   for flag in range(ARMY_FLAGS) if flag!=s.map('formation','formation,flag').get(f)],
    'station_selected':lambda s:[{'military_formation':f,'strategic_region':region} for f in settled(s,s.formations('army')) if not demobilizing(s,f)
                                 for region in sorted({region for kind,region in hq_regions(s).values() if kind==0})
                                 if region not in (home_region(s,f),state_regions(s).get(s.map('formation_status','formation,target_location').get(f)))],
    'transfer_battalions':lambda s:[{'military_formation':source,'target':target} for source in s.formations('army') for target in s.formations('army')
                                    if source!=target and located(s,source)==located(s,target) and len(s.rows('combat_unit','combat_unit',formation=source))>=2],
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
    'disband_regulars':lambda s:formation_units(s,s.formations()),
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
    'start_naval_mission':lambda s:[{'military_formation':fleet,'naval_mission_type':kind} for fleet in s.formations('fleet') for kind in mission_types(s,fleet)],
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
                                      for chosen in [set(s.characters('character_role_ruler','character_role_heir','character_role_general','character_role_admiral',
                                                                      'character_role_ig_leader'))]
                                      for character,interaction,possible in s.rows('player_character_interaction','character,character_interaction,possible')
                                      if character in chosen and interaction not in cooling(s) and possible],
    'diplomatic_action':lambda s:[{'country':country,'diplomatic_action':action} for country,action in sorted(diplomatic_shown(s))
                                  if not definition(s,'common/diplomatic_actions',action,'picks_states') and diplomatic_allowed(s,country,action)],
    'diplomatic_action_state':lambda s:[{'country':country,'diplomatic_action':action,'state':state,'side':{'source':'First','target':'Second'}[side]}
                                        for country,action,side,state in s.rows('player_diplomatic_option_state','target_country,action_type,side,state')
                                        if (country,action) in diplomatic_shown(s) and diplomatic_allowed(s,country,action)],
    'diplomatic_action_obligation':lambda s:[{**option,'obligation':obligation} for option in RULES['diplomatic_action'](s)
                                             if definition(s,'common/diplomatic_actions',option['diplomatic_action'],'can_use_obligations')==['yes']
                                             for obligation,direction,wanted in (('CallInObligation','owes_player',True),('OweObligation','player_owes',False))
                                             if ((option['country'],direction) in obligations(s))==wanted],
    'start_play_confirmed':lambda s:[{**option,'mode':mode} for option in RULES['start_play_country'](s) for mode in ('AsDemand','ForcePlay')],
    'start_play_country':lambda s:[{'country':country,'diplomatic_play_type':play} for country in s.countries() if reachable_country(s,country)
                                   for play in play_types(s,'country') if play_allowed(s,play,target_country=('country',country))
                                   and not country_regions(s,country)&regions_in_play(s)
                                   and (not marker_required(s,play) or state_regions(s).get(s.map('country','country,capital').get(country)) in engaged(s))],
    'start_play_state':lambda s:[{'state':state,'diplomatic_play_type':play} for state,country in s.rows('state','state,country') if country!=s.player and reachable_state(s,state)
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
    'capitulate':lambda s:product(war=[w for w in s.wars() if not overlords(s,s.player)&war_countries(s,w)]),
    'toggle_press_war_goal':lambda s:[goal for goal in war_goals(s) if goal['diplomatic_play'] in at_war_plays(s)
                                      and (war:=war_of_play(s,goal['diplomatic_play'])) is not None
                                      and war_leader(s,war) and negotiable_war(s,war) and proposer(s,war) is None and peace_open(s,war)],
    'add_war_goal':lambda s:[{'diplomatic_play':play,'war_goal_type':kind,'index':0} for play in principal(s) if play not in at_war_plays(s) and escalation(s,play)<COUNTDOWN
                             for kind in sorted({kind for kind, in s.rows('war_goal','war_goal_type')}) if goal_targets(s,play,kind)],
    'make_primary_demand':lambda s:[goal for goal in war_goals(s) if goal['diplomatic_play'] not in at_war_plays(s) and goal['diplomatic_play'] in principal(s)
                                    and sum(other['diplomatic_play']==goal['diplomatic_play'] for other in war_goals(s))>1],
    'withdraw_treaty':lambda s:product(treaty=[ident for ident,first,second,withdrawn in s.rows('treaty','treaty,first_country,second_country,withdrawn')
                                              if s.player in (first,second) and not withdrawn and (first,second) not in enforced_on_player(s)]),
    'request_join_power_bloc':lambda s:product(power_bloc=[] if player_blocs(s) or overlords(s,s.player) else
                                               [bloc for bloc, in s.rows('country_leverage','power_bloc',country=s.player)
                                                if bloc_advantage(s,bloc,s.player)>=JOIN_LEVERAGE and below_leader(s,bloc)]),
    'kick_from_power_bloc':lambda s:product(country=[c for c in power_bloc_members(s) if not overlords(s,c)]) if bloc_leader(s) else [],
    'reform_government':lambda s:[{'interest_group':group,'mode':'Staged' if governs else 'Potential'}
                                  for group,governs,influence in s.rows('interest_group','interest_group,in_government,influence_type',country=s.player)
                                  if not law_flag(s,'country_block_government_reform_bool')
                                  and group not in insurrectionary(s) and ((governs and governing_count(s)>1) or (not governs and influence!=MARGINALIZED))],
    'form_power_bloc':lambda s:[{'power_bloc_identity':identity,'power_bloc_principle':levels[0]} for identity in s.keys('power_bloc_identity') if may_found_bloc(s)
                                and passes(s,'common/power_bloc_identities',identity,('visible','possible'),country_scope(s))
                                for group in s.definitions('common/power_bloc_principle_groups')
                                if definition(s,'common/power_bloc_principle_groups',group,'primary_for_identity')==[identity]
                                for levels in [definition(s,'common/power_bloc_principle_groups',group,'levels')] if levels and principle_allowed(s,levels[0])],
    'leave_power_bloc':lambda s:[{}] if power_bloc_of(s,s.player) and not overlords(s,s.player) and may_leave(s) else [],
    'create_company':lambda s:product(company_type=companies(s)),
    'remove_company':lambda s:product(company_type=remove_companies(s)),
    'colonize':lambda s:[] if 'law_no_colonial_affairs' in active_laws(s) else
                        product(state=colonizable(s)),
    'toggle_pause_colonization':lambda s:product(state=colonies(s)),
    'abandon_colony':lambda s:product(state=abandonable(s)),
    'incorporate':lambda s:product(state=[i for i in s.states() if incorporation(s).get(i)==0 and i not in colonies(s)]),
    'unincorporate':lambda s:product(state=[i for i in s.states() if 0<need(incorporation(s).get(i),f'incorporation of state {i}')<1]),
    'press_journal_button':journal_buttons,
    'choose_event_option':event_options,
    'quick_decline_proposal':lambda s:product(country=sorted({country for country, in s.rows('player_proposal','country')})),
    **{name:(lambda s,kind=name.split('_',1)[1]:product(country=proposers(s,kind))) for name in ('accept_treaty','decline_treaty','accept_demand','reject_demand',
                                                                    'accept_action_proposal','decline_action_proposal','accept_sway','reject_sway')},
    'pause_all_construction':lambda s:[{}] if not construction_paused(s) else [],
    'resume_all_construction':lambda s:[{}] if construction_paused(s) and not in_default(s) else [],
    'set_default_construction_fleet':lambda s:product(military_formation=[f for f in s.formations('fleet') if not formation_report(s,f,'default_fleet')]),
    'clear_default_construction_fleet':lambda s:[{}] if s.rows('formation_report','formation',default_fleet=True) else [],
    'decommission_ship':lambda s:[] if revolution_brewing(s) else product(ship=[ident for fleets in [set(s.formations('fleet'))] for ident,fleet in s.rows('ship','ship,fleet') if fleet in fleets]),
    'build_ship':lambda s:product(ship_type=ship_types(s) if metric(s,'GetShipConstruction')>0 else []),
    'build_ship_for':lambda s:product(ship_type=ship_types(s) if metric(s,'GetShipConstruction')>0 else [],military_formation=s.formations('fleet')),
    'cancel_ship':lambda s:product(ship_type=sorted(set(my_ships(s)))),
    'station_formation':lambda s:[{'military_formation':f,'state':st} for f in settled(s,s.formations('army')) if not demobilizing(s,f)
                                  for st in s.states() if st!=located(s,f)],
    'rehome_formation':rehome,
    'deploy_to_front':lambda s:[{'military_formation':f,'front':front} for f in armies(s,True) if f in deployable(s) for front in war_fronts(s)
                                if s.map('formation_status','formation,target_location').get(f)!=front],
    'set_borrow_setting':lambda s:[{'military_formation':f,'index':index} for mine in [set(s.mine('formation'))]
                                   for f,index,chosen in s.rows('formation_borrow_setting','formation,position,selected') if f in mine and not chosen],
    'cancel_strategic_objective_selected':lambda s:[{'military_formation':f,'state':objective&SLOT} for idle in [set(settled(s,s.formations('army')))]
                                                    for f,objective in s.rows('formation_private','formation,strategic_objective')
                                                    if f in idle and objective is not None],
    'set_strategic_objective':lambda s:[{'military_formation':f,'state':st} for f in settled(s,s.formations('army')) for st in enemy_states(s)
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
    'release_country':lambda s:product(index=[index for index,possible in enumerate(listed(s,'player_releasable_country','possible')) if possible]),
    'toggle_ignore_formable':lambda s:product(index=list(range(len(listed(s,'player_formable_country','name'))))),
    'form_country':lambda s:product(index=[index for index,formable in enumerate(listed(s,'player_formable_country','formable')) if formable]),
}


@timed
def available(snapshot):
    offered={}
    for action in ACTIONS:
        progress(f'available {action.name}')
        offered[action.name]=RULES[action.name](snapshot)
    return offered
