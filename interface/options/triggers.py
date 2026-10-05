import collections
import re

from ..recording.spec import DROPPED_COUNTRY_METRICS, METRIC_COLUMNS
from .stored import script_hours
from ..common import timed_often

TOKEN=re.compile(r'\?=|>=|<=|!=|[{}=<>]|[^\s{}=<>?!]+')
COMPARE={'>=':lambda a,b:a>=b,'<=':lambda a,b:a<=b,'>':lambda a,b:a>b,'<':lambda a,b:a<b,'=':lambda a,b:a==b,'!=':lambda a,b:a!=b}
UNKNOWN=collections.Counter()
MARGINAL=.05
APPROVAL_STATES={"angry":0,"unhappy":1,"neutral":2,"happy":3,"loyal":4}
ADULT_AGE=16
COMMAND_LAWS={"law_monarchy","law_autocracy"}
HOURS_PER_YEAR=24*365


@timed_often
def parse(text):
    tokens=TOKEN.findall(text)
    position=0
    def block():
        nonlocal position
        nodes=[]
        while position<len(tokens) and tokens[position]!='}':
            key=tokens[position];position+=1
            if position>=len(tokens) or tokens[position] not in COMPARE and tokens[position]!='?=':
                nodes.append((key,'=',True));continue
            operator=tokens[position];position+=1
            if tokens[position]=='{':
                position+=1
                value=block()
                position+=1
            else:
                value=tokens[position];position+=1
            nodes.append((key,operator,value))
        return nodes
    return block()


class Scope:
    def __init__(self,snapshot,kind,ident,saved=None,root=None):
        self.s=snapshot
        self.kind=kind
        self.ident=ident
        self.saved=saved or {}
        self.root=root or self

    def to(self,kind,ident):
        return Scope(self.s,kind,ident,self.saved,self.root)

    def country(self):
        s=self.s
        if self.kind=='country':
            return self.ident
        if self.kind=='state':
            return s.map('state','state,country').get(self.ident)
        if self.kind=='building':
            return self.to('state',s.map('building','building,state').get(self.ident)).country()
        if self.kind=='character':
            return s.map('character','character,country').get(self.ident)
        if self.kind=='formation':
            return s.map('formation','formation,country').get(self.ident)
        if self.kind=='interest_group':
            return s.map('interest_group','interest_group,country').get(self.ident)
        if self.kind=='diplomatic_catalyst':
            return s.map('diplomatic_catalyst_private','diplomatic_catalyst,country').get(self.ident)
        return None


@timed_often
def country_scope(s,country=None,**saved):
    scope=Scope(s,'country',s.player if country is None else country)
    scope.saved={name:(kind,ident) for name,(kind,ident) in saved.items()}
    return scope


@timed_often
def character_scope(s,character,**saved):
    scope=Scope(s,'character',character)
    scope.saved=dict(saved)
    return scope


def both(results):
    results=list(results)
    return False if False in results else None if None in results else True


@timed_often
def either(results):
    results=list(results)
    return True if True in results else None if None in results else False


@timed_often
def negate(result):
    return None if result is None else not result


@timed_often
def counted(operator,needed,results):
    certain=results.count(True)
    possible=certain+results.count(None)
    low,high=COMPARE[operator](certain,needed),COMPARE[operator](possible,needed)
    return low if low==high else None


def evaluate(nodes,scope):
    result=True
    taken=False
    for key,operator,value in nodes:
        if key in ('trigger_if','trigger_else_if'):
            if key=='trigger_else_if' and taken is True:
                continue
            branch=both(evaluate(node[2],scope) for node in value if node[0]=='limit')
            if branch is False:
                continue
            taken=branch if taken is False else None
            body=evaluate([node for node in value if node[0]!='limit'],scope)
            result=both((result,body if branch else (None if body is False else body)))
        elif key=='trigger_else':
            if taken is not True:
                body=evaluate(value,scope)
                result=both((result,body if taken is False else (None if body is False else body)))
        else:
            try:
                outcome=test(key,operator,value,scope)
            except Unknown as missing:
                UNKNOWN[str(missing)]+=1
                outcome=None
            result=both((result,outcome))
        if result is False:
            return False
    return result


@timed_often
def number(value):
    try:
        return float(value)
    except (TypeError,ValueError):
        return None


@timed_often
def amount(s,value):
    found=number(value)
    if found is not None:
        return found
    if value.startswith('define:'):
        named=s.definitions('common/defines').get(value.split(':',1)[1],{}).get('value')
    else:
        named=s.definitions('common/script_values').get(value,{}).get('value')
    if not named or number(named[0]) is None:
        raise Unknown(value)
    return number(named[0])


class Unknown(Exception):
    pass


@timed_often
def known(value,what):
    if value is None:
        raise Unknown(f'{what} is not captured')
    return value


@timed_often
def yes(value):
    return value=='yes'


@timed_often
def technologies(s,country):
    def compute():
        research={ident for ident, in s.rows('country_research','country_research',country=country)}
        return {kind for owner,kind in s.rows('country_research_acquired','country_research,technology') if owner in research}
    return s.memo(('technologies',country),compute)


@timed_often
def laws(s,country):
    def compute():
        grouped={}
        for owner,kind,active in s.rows('law','country,law_type,active'):
            if active:
                grouped.setdefault(owner,set()).add(kind)
        return grouped
    return s.memo('laws',compute).get(country,set())


DLC_FEATURES={'power_bloc_features':'ep1','lobbies':'ep1','foreign_investment':'ep1','subject_and_bloc_actions':'ep1',
              'voice_of_the_people_content':'voice_of_the_people','agitators':'voice_of_the_people',
              'voice_of_the_people_preorder':'voice_of_the_people_preorder'}


@timed_often
def dlc_feature(s,feature):
    prefix=feature.split('_')[0]
    token=DLC_FEATURES.get(feature,prefix if re.fullmatch(r'(ep|ip|mp|rp|ap)\d',prefix) else None)
    if token is None:
        raise ValueError(f'No DLC is known to provide the feature {feature}')
    return token in set(s.dlc)


@timed_often
def amendments(s,country):
    mine={law for law, in s.rows('law','law',country=country)}
    return [kind for law,kind in s.rows('amendment','law,amendment_type') if law in mine]


@timed_often
def modifier_texts(s,country):
    sources=([('common/laws',law) for law in laws(s,country)]+[('common/technology/technologies',tech) for tech in technologies(s,country)]
             +[('common/amendments',kind) for kind in amendments(s,country)])
    return [text for folder,key in sources for text in s.definitions(folder).get(key,{}).get('modifier',())]


@timed_often
def active_modifiers(s,country):
    timed={kind for kind, in s.rows('country_timed_modifier','modifier',country=country)}
    return timed|{kind for entry in journal_types(s,country) for text in s.definitions('common/journal_entries').get(entry,{}).get('modifiers_while_active',()) for kind in text.split()}


@timed_often
def modifier_flag(s,country,name):
    pattern=re.compile(re.escape(name)+r'\s*=\s*yes')
    return (any(pattern.search(text) for text in modifier_texts(s,country))
            or any(s.definitions('common/static_modifiers').get(kind,{}).get(name)==['yes'] for kind in active_modifiers(s,country)))


@timed_often
def modifier_value(s,country,name):
    pattern=re.compile(re.escape(name)+r'\s*=\s*(-?[\d.]+)')
    return (sum(float(found) for text in modifier_texts(s,country) for found in pattern.findall(text))
            +sum(float(value) for kind in active_modifiers(s,country) for value in s.definitions('common/static_modifiers').get(kind,{}).get(name,()) if number(value) is not None))


def subject_pairs(s):
    return s.memo('subject_pairs',lambda:{(first,second) for first,second,action in s.rows('pact','first_country,second_country,pact_type')
                                          if s.definitions('common/diplomatic_actions').get(action,{}).get('subject_pact')})


@timed_often
def subjects(s,country):
    return {second for first,second in subject_pairs(s) if first==country}


@timed_often
def autonomous(s,country):
    actions=s.definitions('common/diplomatic_actions')
    kinds=s.definitions('common/subject_types')
    return all(kinds.get(next(iter(actions.get(action,{}).get('subject_type',[])),''),{}).get('can_start_own_diplomatic_plays')==['yes']
               for first,second,action in s.rows('pact','first_country,second_country,pact_type')
               if second==country and actions.get(action,{}).get('subject_pact'))


@timed_often
def subject_type_of(s,country):
    actions=s.definitions('common/diplomatic_actions')
    return next((next(iter(actions.get(action,{}).get('subject_type',[])),None) for first,second,action in s.rows('pact','first_country,second_country,pact_type')
                 if second==country and actions.get(action,{}).get('subject_pact')),None)


def overlords(s,country):
    return {first for first,second in subject_pairs(s) if second==country}


@timed_often
def liberty_desire(s,country):
    return next((desire for first,second,desire in s.rows('pact','first_country,second_country,liberty_desire') if second==country and first in overlords(s,country)),0)


STANCES={'strongly_approve':2,'approve':1,'neutral':0,'disapprove':-1,'strongly_disapprove':-2}
POWERFUL=0
MARGINAL_TYPE=2


@timed_often
def stance(s,ideologies,law):
    return sum(STANCES.get(value,0) for ideology in ideologies for entry in s.definitions('common/ideologies').get(ideology,{}).get('stance',())
               for key,value in [entry.split()] if key==law)


@timed_often
def scope_ideologies(scope):
    s=scope.s
    if scope.kind=='character':
        return [character_ideology(scope)]
    return [value for value, in s.rows('interest_group_ideology','ideology',interest_group=scope.ident)]


@timed_often
def enactment_stance(operator,value,scope):
    s=scope.s
    fields={k:(o,v) for k,o,v in value}
    law=fields['law'][1].split(':',1)[-1]
    group=s.definitions('common/laws').get(law,{}).get('group')
    current=next((name for name in laws(s,scope.country()) if s.definitions('common/laws').get(name,{}).get('group')==group),None)
    ideologies=scope_ideologies(scope)
    wanted=fields['value'][1]
    return COMPARE[fields['value'][0]](stance(s,ideologies,law)-stance(s,ideologies,current),STANCES[wanted] if wanted in STANCES else amount(s,wanted))


@timed_often
def top_overlord(s,country):
    above=overlords(s,country)
    return top_overlord(s,next(iter(above))) if above else country


@timed_often
def below(s,country):
    found=set()
    for subject in subjects(s,country):
        found|={subject}|below(s,subject)
    return found


@timed_often
def indirect_overlords(s,country):
    direct=overlords(s,country)
    found=set()
    for overlord in direct:
        above=overlords(s,overlord)
        found|=above|indirect_overlords(s,overlord)
    return found


@timed_often
def play_sides(s):
    def compute():
        sides={}
        for play,country,role in s.rows('diplomatic_play_country','diplomatic_play,country,role'):
            if role in ('initiator','target'):
                sides.setdefault((play,0 if role=='initiator' else 1),set()).add(country)
        for play,initiator,target in s.rows('diplomatic_play','diplomatic_play,initiator,target'):
            sides.setdefault((play,0),set()).add(initiator)
            sides.setdefault((play,1),set()).add(target)
        return sides
    return s.memo('play_sides',compute)


@timed_often
def warleaders(s,war):
    play=s.map('war','war,diplomatic_play').get(war)
    return {country for ident,initiator,target in s.rows('diplomatic_play','diplomatic_play,initiator,target') if ident==play for country in (initiator,target)}


@timed_often
def play_participants(s,first,second):
    return any(first in members and second in members for members in play_sides(s).values())


@timed_often
def play_enemies(s,country):
    sides=play_sides(s)
    return {member for (play,side),members in sides.items() if country in sides.get((play,1-side),set()) for member in members}


@timed_often
def interest_tier(s,country,region):
    involvement=next((value for owner,key,value in s.rows('interest','country,strategic_region,involvement') if owner==country and key==region),0)
    tiers=s.definitions('common/interest_tier_types').values()
    return max((int(fields['rank'][0]) for fields in tiers if float(fields['min_involvement'][0])<=involvement),default=0)


@timed_often
def region_tier(operator,value,scope):
    fields={k:(o,v) for k,o,v in value}
    region=resolve(scope,fields['strategic_region'][1])
    return region is not None and COMPARE[fields['value'][0]](interest_tier(scope.s,scope.country(),region),amount(scope.s,fields['value'][1]))


@timed_often
def journal_types(s,country):
    def compute():
        held={}
        involved=s.grouped('journal_entry_involved_country','journal_entry,country')
        for entry,kind,owner,active in s.rows('journal_entry','journal_entry,journal_entry_type,country,active'):
            if active:
                for member in {owner}|set(involved.get(entry,())):
                    held.setdefault(member,set()).add(kind)
        return held
    return s.memo('journal_types',compute).get(country,set())


@timed_often
def bloc_modifier(s,bloc,name):
    pattern=re.compile(re.escape(name)+r'\s*=\s*yes')
    principles={kind for kind, in s.rows('power_bloc_adopted_principle','power_bloc_principle',power_bloc=bloc)}
    return any(pattern.search(text) for principle in principles for text in s.definitions('common/power_bloc_principles').get(principle,{}).get('power_bloc_modifier',()))


@timed_often
def at_war(s,country):
    def compute():
        return any(owner==country for owner, in s.rows('war_participant','country'))
    return s.memo(('at_war',country),compute)


@timed_often
def roles(s,character):
    return {role for role, in s.rows('character_assigned_role','character_role',character=character)}


@timed_often
def ruler(s,country):
    return next((ident for ident, in s.rows('character','character',country=country) if 'character_role_ruler' in roles(s,ident)),None)


@timed_often
def now(s):
    return s.hours


@timed_often
def years_since(s,start):
    return (now(s)-start)/HOURS_PER_YEAR if start is not None else 0


@timed_often
def children(scope,iterator):
    s=scope.s
    country=scope.country()
    if iterator=='any_scope_state' and scope.kind=='state_region':
        return [scope.to('state',ident) for ident, in s.rows('state','state',state_region=scope.ident)]
    if iterator=='any_scope_state':
        return [scope.to('state',ident) for ident, in s.rows('state','state',country=country)]
    if iterator=='any_scope_building':
        if scope.kind=='state':
            return [scope.to('building',ident) for ident, in s.rows('building','building',state=scope.ident)]
        owned={ident for ident, in s.rows('state','state',country=country)}
        return [scope.to('building',ident) for ident,state in s.rows('building','building,state') if state in owned]
    if iterator=='any_scope_character':
        pool={ident for ident,recruitable in s.rows('character_private','character,recruitable') if recruitable}
        return [scope.to('character',ident) for ident, in s.rows('character','character',country=country) if ident not in pool]
    if iterator=='any_subject_or_below':
        return [scope.to('country',ident) for ident in subjects(s,country)]
    if iterator=='any_scope_treaty':
        return [scope.to('treaty',ident) for ident,first,second in s.rows('treaty','treaty,first_country,second_country') if country in (first,second)]
    if iterator=='any_scope_article' and scope.kind=='treaty':
        return [scope.to('article',ident) for ident, in s.rows('treaty_article','treaty_article',treaty=scope.ident)]
    if iterator=='any_diplomatic_catalyst':
        return [scope.to('diplomatic_catalyst',ident) for ident,owner,other in s.rows('diplomatic_catalyst_private','diplomatic_catalyst,country,target_country')
                if owner==country and s.player in (owner,other)]
    if iterator=='any_interest_group':
        return [scope.to('interest_group',ident) for ident, in s.rows('interest_group','interest_group',country=country)]
    if iterator=='any_primary_culture':
        return [scope.to('culture',ident) for ident, in s.rows('country_culture','culture',country=country)]
    if iterator=='any_scope_war':
        return [scope.to('war',ident) for ident in sorted({war for war, in s.rows('war_participant','war',country=country)})]
    return None


def step(scope,name):
    s=scope.s
    if name in ('root','ROOT'):
        return scope.root
    if name=='owner':
        return scope.to('country',scope.country())
    if name.startswith('scope:'):
        found=scope.saved.get(name.split(':',1)[1])
        return scope.to(*found) if found else None
    if name=='ruler':
        found=ruler(s,scope.country())
        return scope.to('character',found) if found is not None else None
    if name=='heir':
        found=next((ident for ident, in s.rows('character','character',country=scope.country()) if 'character_role_heir' in roles(s,ident)),None)
        return scope.to('character',found) if found is not None else None
    if name=='interest_group' and scope.kind=='character':
        group=s.map('character','character,interest_group').get(scope.ident)
        return scope.to('interest_group',group) if group is not None else None
    if name=='leader' and scope.kind=='interest_group':
        found=s.map('interest_group','interest_group,leader').get(scope.ident)
        return scope.to('character',found) if found is not None else None
    if name=='state_region' and scope.kind=='state':
        return scope.to('state_region',s.map('state','state,state_region').get(scope.ident))
    if name=='this':
        return scope
    if name.startswith('c:'):
        found=tagged(s).get(name[2:])
        return scope.to('country',found) if found is not None else None
    if name.startswith('ig:'):
        found=next((ident for ident,kind in s.rows('interest_group','interest_group,interest_group_type',country=scope.country()) if kind==name[3:]),None)
        return scope.to('interest_group',found) if found is not None else None
    if name.startswith('s:'):
        return scope.to('state_region',name[2:]) if name[2:] in s.order('map_data/state_regions') else None
    if name=='market':
        found=s.map('country','country,market').get(scope.country())
        return scope.to('market',found) if found is not None else None
    if name.startswith('mg:') and scope.kind=='market':
        return scope.to('market_goods',(scope.ident,name[3:]))
    if name=='capital':
        found=s.map('country','country,capital').get(scope.country())
        return scope.to('state',found) if found is not None else None
    if name=='top_overlord':
        country=scope.country()
        return scope.to('country',top_overlord(s,country)) if country is not None else None
    if name=='power_bloc':
        found=s.map('country','country,power_bloc').get(scope.country())
        return scope.to('power_bloc',found) if found is not None else None
    if name=='commander_military_formation' and scope.kind=='character':
        formation=s.map('character','character,formation').get(scope.ident)
        owned=formation is not None and s.map('formation','formation,country').get(formation)==s.map('character','character,country').get(scope.ident)
        return scope.to('formation',formation) if owned else None
    return None


@timed_often
def tagged(s):
    return s.memo('tagged',lambda:{definition:ident for ident,definition in s.rows('country','country,country_definition')})


@timed_often
def strategic_region(s,state):
    def compute():
        regions={member:region for region,fields in s.definitions('common/strategic_regions').items() for member in fields.get('states',())}
        return {ident:regions.get(key) for ident,key in s.rows('state','state,state_region')}
    return s.memo('strategic_regions',compute).get(state)


@timed_often
def culture_names(s,cultures):
    kinds=s.map('culture','culture,culture_type')
    return {kinds.get(culture) for culture in cultures}


@timed_often
def primary_cultures(s,country):
    return culture_names(s,[value for value, in s.rows('country_culture','culture',country=country)])


@timed_often
def homeland(s,state,culture):
    region=s.map('state','state,state_region').get(state)
    return any(value==region and culture in culture_names(s,[owner]) for owner,value in s.rows('culture_core_state','culture,state_region'))


@timed_often
def geographic(s,state,name):
    fields=s.definitions('common/geographic_regions').get(name,{})
    region=s.map('state','state,state_region').get(state)
    return region in fields.get('state_regions',()) or 'sr:'+str(strategic_region(s,state)) in fields.get('strategic_regions',())


def target(scope,name):
    for part in name.split('.'):
        scope=step(scope,part) if scope else None
    return scope


SCOPES={'root','ROOT','owner','ruler','heir','interest_group','commander_military_formation','state_region','power_bloc','market','top_overlord','leader','capital'}


@timed_often
def unsupplied(scope,key):
    head=key.split('.')[0]
    return head.startswith('scope:') and head.split(':',1)[1] not in scope.saved


@timed_often
def is_scope(key):
    return all(part in SCOPES or part.startswith(('scope:','c:','s:','mg:','ig:')) for part in key.split('.'))


@timed_often
def resolve(scope,value):
    found=target(scope,value)
    return found.ident if found else None


def scripted(key,scope):
    body=scope.s.definitions('common/scripted_triggers').get(key,{}).get('body')
    return parse(body[0]) if body else None


def test(key,operator,value,scope):
    if key=='AND':
        return evaluate(value,scope)
    if key=='OR':
        return either(evaluate([node],scope) for node in value)
    if key in ('NOT','NOR'):
        return negate(either(evaluate([node],scope) for node in value))
    if key=='NAND':
        return negate(evaluate(value,scope))
    if key=='calc_true_if':
        needed=next(node for node in value if node[0]=='amount')
        results=[evaluate([node],scope) for node in value if node[0]!='amount']
        return counted(needed[1],amount(scope.s,needed[2]),results)
    if key in ('custom_tooltip','hidden_trigger','custom_description'):
        return evaluate([node for node in value if node[0] not in ('text','subject','object')],scope) if isinstance(value,list) else True
    if key=='has_dlc_feature':
        return dlc_feature(scope.s,value)
    if key=='always':
        return yes(value)
    if key=='has_variable':
        UNKNOWN[key]+=1
        return None
    if key.startswith('any_'):
        members=children(scope,key)
        if members is None:
            UNKNOWN[key]+=1
            return None
        wanted=[node for node in value if node[0]!='count']
        count=next((node for node in value if node[0]=='count'),None)
        results=[evaluate(wanted,member) for member in members]
        if count is None:
            return either(results)
        if count[2]=='all':
            return both(results)
        return counted(count[1],amount(scope.s,count[2]),results)
    if isinstance(value,list) and is_scope(key):
        if unsupplied(scope,key):
            return None
        found=target(scope,key)
        return bool(found) and evaluate(value,found)
    if key.startswith(('c:','s:')) and isinstance(value,str):
        left,right=target(scope,key),target(scope,value)
        return bool(left) and bool(right) and (left.kind,left.ident)==(right.kind,right.ident)
    body=scripted(key,scope)
    if body is not None:
        result=evaluate(body,scope)
        return None if result is None else result==yes(value)
    handled=HANDLERS.get(scope.kind,{}).get(key)
    if handled is not None:
        return handled(operator,value,scope)
    return country_test(key,operator,value,scope)


@timed_often
def coastal(s,state):
    region=s.map('state','state,state_region').get(state)
    return bool(s.definitions('map_data/state_regions').get(region,{}).get('naval_exit_id'))


@timed_often
def state_metric(scope,name):
    table,column=METRIC_COLUMNS['state',name]
    value=scope.s.map(table,'state,'+column).get(scope.ident)
    if value is None:
        raise Unknown(f'{name} of state {scope.ident} is not captured')
    return value


@timed_often
def devastation_level(scope):
    value=scope.s.map('state_status','state,devastation').get(scope.ident)
    if value is None:
        raise Unknown(f'devastation of state {scope.ident} is not captured')
    return int(value*1000)/100000


@timed_often
def character_ideology(scope):
    s=scope.s
    return s.map('character','character,ideology').get(scope.ident)


@timed_often
def group_row(scope):
    s=scope.s
    government=s.map('interest_group','interest_group,in_government').get(scope.ident)
    clout=s.map('interest_group_stats','interest_group,clout').get(scope.ident)
    if government is None or clout is None:
        raise Unknown(f'interest group {scope.ident} is not captured')
    return government,clout


@timed_often
def leverage_advantage(operator,value,scope):
    s=scope.s
    fields={k:(o,v) for k,o,v in value}
    found=target(scope,fields['target'][1])
    if not found:
        return False
    return COMPARE[fields['value'][0]](bloc_advantage(s,scope.ident,found.country()),amount(s,fields['value'][1]))


@timed_often
def bloc_advantage(s,bloc,country):
    held=dict(s.rows('country_leverage','power_bloc,leverage',country=country))
    if bloc not in held:
        return 0
    return held[bloc]-max([metric(s,country,'GetUnclaimedLeverage')]+[amount for other,amount in held.items() if other!=bloc])


@timed_often
def supplied(s,market,goods):
    def compute():
        areas={area for area,owner in s.rows('market_area','market_area,market') if owner==market}
        states={state for area,state in s.rows('market_area_state','market_area,state') if area in areas}
        return {kind for state,kind in s.rows('state_goods_supply','state,goods') if state in states}
    return goods in s.memo(('market_supply',market),compute)


@timed_often
def formation_fraction(operator,value,scope):
    s=scope.s
    fields={k:(o,v) for k,o,v in value}
    kind=fields['target'][1].split(':',1)[1]
    units=[unit for unit, in s.rows('combat_unit','combat_unit_type',formation=scope.ident)]
    share=units.count(kind)/len(units) if units else 0
    return COMPARE[fields['value'][0]](share,amount(s,fields['value'][1]))


@timed_often
def discrimination_traits(scope):
    fields=scope.s.definitions('common/cultures').get(scope.s.map('culture','culture,culture_type').get(scope.ident),{})
    return {trait for field in ('heritage','language','traditions') for trait in fields.get(field,())}


HANDLERS={
    'culture':{
        'has_discrimination_trait':lambda o,v,sc:v in discrimination_traits(sc),
    },
    'character':{
        'has_role':lambda o,v,sc:'character_role_'+v in roles(sc.s,sc.ident),
        'has_role_of_type':lambda o,v,sc:'character_role_'+v in roles(sc.s,sc.ident),
        'has_trait':lambda o,v,sc:v in {t for t, in sc.s.rows('character_assigned_trait','character_trait',character=sc.ident)},
        'is_ruler_of_own_country':lambda o,v,sc:('character_role_ruler' in roles(sc.s,sc.ident))==yes(v),
        'is_heir_of_own_country':lambda o,v,sc:('character_role_heir' in roles(sc.s,sc.ident))==yes(v),
        'has_ideology':lambda o,v,sc:character_ideology(sc)==v.split(':',1)[-1],
        'age':lambda o,v,sc:COMPARE[o](years_since(sc.s,sc.s.map('character','character,birth_date').get(sc.ident)),amount(sc.s,v)),
        'years_of_service':lambda o,v,sc:COMPARE[o](0,amount(sc.s,v)),
        'is_busy':lambda o,v,sc:not yes(v),
        'is_in_exile_pool':lambda o,v,sc:not yes(v),
        'is_in_void':lambda o,v,sc:not yes(v),
        'is_adult':lambda o,v,sc:(years_since(sc.s,sc.s.map('character','character,birth_date').get(sc.ident))>=ADULT_AGE)==yes(v),
        'popularity':lambda o,v,sc:COMPARE[o](known(sc.s.map('character_status','character,popularity').get(sc.ident),f'popularity of {sc.ident}'),amount(sc.s,v)),
        'has_modifier':lambda o,v,sc:v in modifiers(sc.s,'character',sc.ident),
        'law_enactment_stance':enactment_stance,
    },
    'treaty':{
        'binds':lambda o,v,sc:(target(sc,v).country() if target(sc,v) else None) in {c for a,b in sc.s.rows('treaty','first_country,second_country',treaty=sc.ident) for c in (a,b)},
    },
    'article':{
        'has_type':lambda o,v,sc:v in (sc.s.map('treaty_article','treaty_article,treaty_article_type').get(sc.ident) or ''),
    },
    'interest_group':{
        'ig_clout':lambda o,v,sc:COMPARE[o](group_row(sc)[1],number(v) if number(v) is not None else 0.05),
        'ig_approval':lambda o,v,sc:COMPARE[o](sc.s.map('interest_group','interest_group,approval_state').get(sc.ident,2),APPROVAL_STATES[v]) if v in APPROVAL_STATES
                                     else COMPARE[o](sc.s.map('interest_group_stats','interest_group,approval').get(sc.ident,0),number(v)),
        'ig_counts_as_marginal':lambda o,v,sc:(not group_row(sc)[0] and group_row(sc)[1]<MARGINAL)==yes(v),
        'is_in_government':lambda o,v,sc:bool(group_row(sc)[0])==yes(v),
        'is_marginal':lambda o,v,sc:(sc.s.map('interest_group','interest_group,influence_type').get(sc.ident)==MARGINAL_TYPE)==yes(v),
        'is_powerful':lambda o,v,sc:(sc.s.map('interest_group','interest_group,influence_type').get(sc.ident)==POWERFUL)==yes(v),
        'law_enactment_stance':enactment_stance,
        'has_ideology':lambda o,v,sc:v.split(':',1)[-1] in {i for i, in sc.s.rows('interest_group_ideology','ideology',interest_group=sc.ident)},
    },
    'formation':{
        'formation_army_unit_type_fraction':formation_fraction,
        'is_mobilized':lambda o,v,sc:bool(sc.s.map('formation_status','formation,mobilized').get(sc.ident))==yes(v),
    },
    'building':{
        'is_building_type':lambda o,v,sc:sc.s.map('building','building,building_type').get(sc.ident)==v,
        'level':lambda o,v,sc:COMPARE[o](known(sc.s.map('building','building,levels').get(sc.ident),f'levels of building {sc.ident}'),amount(sc.s,v)),
    },
    'state':{
        'is_incorporated':lambda o,v,sc:(sc.s.map('state_status','state,incorporation').get(sc.ident)==1)==yes(v),
        'has_modifier':lambda o,v,sc:v in modifiers(sc.s,'state',sc.ident),
        'has_famine':lambda o,v,sc:bool(state_metric(sc,'HasFamine'))==yes(v),
        'is_isolated_from_market':lambda o,v,sc:(state_metric(sc,'GetMarketAccess')<=0)==yes(v),
        'devastation':lambda o,v,sc:COMPARE[o](devastation_level(sc),amount(sc.s,v)),
        'turmoil':lambda o,v,sc:COMPARE[o](state_metric(sc,'CalcTurmoil'),amount(sc.s,v)),
        'has_decree':lambda o,v,sc:v in {kind for kind, in sc.s.rows('player_active_decree','decree_type',state=sc.ident)},
        'is_coastal':lambda o,v,sc:coastal(sc.s,sc.ident)==yes(v),
        'has_claim_by':lambda o,v,sc:(sc.s.map('state','state,state_region').get(sc.ident),) in sc.s.rows('country_claim','state_region',country=resolve(sc,v)),
        'is_potential_treaty_port':lambda o,v,sc:bool(sc.s.map('state','state,treaty_port_potential').get(sc.ident)) if resolve(sc,v)==sc.s.player else None,
        'state_region':lambda o,v,sc:sc.s.map('state','state,state_region').get(sc.ident)==v.split(':',1)[-1],
        'is_homeland':lambda o,v,sc:homeland(sc.s,sc.ident,v.split(':',1)[-1]),
        'is_in_geographic_region':lambda o,v,sc:geographic(sc.s,sc.ident,v),
        'region':lambda o,v,sc:strategic_region(sc.s,sc.ident)==v.split(':',1)[-1],
    },
    'war':{
        'is_warleader':lambda o,v,sc:resolve(sc,v) in warleaders(sc.s,sc.ident),
    },
    'power_bloc':{
        'leverage_advantage':leverage_advantage,
    },
    'country':{
        'aggressive_diplomatic_plays_permitted':lambda o,v,sc:(not modifier_flag(sc.s,sc.ident,'country_disallow_aggressive_plays_bool'))==yes(v),
        'is_diplomatic_play_participant_with':lambda o,v,sc:resolve(sc,v) is not None and play_participants(sc.s,sc.ident,resolve(sc,v)),
        'is_indirect_subject_of':lambda o,v,sc:resolve(sc,v) in indirect_overlords(sc.s,sc.ident),
        'has_strategic_region_interest_tier':region_tier,
    },
    'market_goods':{
        'has_potential_supply':lambda o,v,sc:supplied(sc.s,*sc.ident)==yes(v),
    },
    'state_region':{
        'has_harvest_condition':lambda o,v,sc:v in {kind for kind,region in sc.s.rows('harvest_condition','harvest_condition_type,state_region') if region==sc.ident},
    },
}


@timed_often
def metric(s,country,name):
    table,column=METRIC_COLUMNS.get(('country',name)) or DROPPED_COUNTRY_METRICS[name]
    if not column.isidentifier():
        raise RuntimeError(f'{name} is derived as {column} in {table}, not stored')
    if table.startswith('player_'):
        found=s.rows(table,column)
        value=found[0][0] if country==s.player and found else None
    else:
        value=s.map(table,'country,'+column).get(country)
    if value is None:
        raise Unknown(f'{name} of {country} is not captured')
    return value


@timed_often
def relation_between(s,first,second):
    other=second if first==s.player else first if second==s.player else None
    value=s.map('player_relation','country,relations').get(other)
    if value is None:
        raise Unknown(f'relations between {first} and {second} are not captured')
    return value


@timed_often
def expelled(s,expeller,expelled_country):
    expulsions=set(s.rows('player_diplomat_expulsion','country,direction'))
    if expelled_country==s.player:
        return (expeller,'by_player') in expulsions
    if expeller==s.player:
        return (expelled_country,'of_player') in expulsions
    return False


@timed_often
def pact_exists(s,first,second,kind):
    pacts=s.memo('pacts',lambda:set(s.rows('pact','first_country,second_country,pact_type')))
    return (first,second,kind) in pacts or (second,first,kind) in pacts


@timed_often
def war_between(s,first,second):
    sides={}
    for war,country in s.rows('war_participant','war,country'):
        sides.setdefault(war,set()).add(country)
    return any({first,second}<=members for members in sides.values())


@timed_often
def rank_of(s,country):
    rank=s.map('country','country,country_rank').get(country)
    return float(next(iter(s.definitions('common/country_ranks').get(rank,{}).get('rank_value',[])),-1))


RELATION_THRESHOLDS={'friendly':80,'amicable':50,'cordial':20,'neutral':-19,'poor':-20,'cold':-50,'hostile':-80}
METRIC_KEYS={'gdp':'GetGDP','prestige':'GetPrestige','infamy':'GetInfamy','government_legitimacy':'GetGovernmentLegitimacy',
             **{f'produced_{power}':f"GetPowerIncome('{power}')" for power in ('authority','influence','bureaucracy')}}


def country_test(key,operator,value,scope):
    s=scope.s
    country=scope.country()
    if '.' in key and not is_scope(key):
        head,_,tail=key.rpartition('.')
        found=target(scope,head)
        return bool(found) and test(tail,operator,value,found)
    if key.startswith('relations:'):
        other=target(scope,key.split(':',1)[1])
        threshold=number(value) if number(value) is not None else RELATION_THRESHOLDS.get(str(value).split(':',1)[-1])
        if threshold is None:
            UNKNOWN[key]+=1
            return None
        return bool(other) and COMPARE[operator](relation_between(s,country,other.country()),threshold)
    if key in METRIC_KEYS and isinstance(value,str):
        other=number(value)
        if other is None:
            found=target(scope,value)
            other=metric(s,found.country(),METRIC_KEYS[key]) if found else 0
        return COMPARE[operator](metric(s,country,METRIC_KEYS[key]),other)
    if key=='country_rank':
        return COMPARE[operator](rank_of(s,country),float(next(iter(s.definitions('common/country_ranks').get(value.split(':',1)[-1],{}).get('rank_value',[])),-1)))
    if key in ('is_revolutionary','is_insurrectionary'):
        return not yes(value)
    if key=='has_war_with':
        found=target(scope,value)
        return bool(found) and war_between(s,country,found.country())
    if key=='has_diplomatic_pact':
        fields={k:v for k,_,v in value}
        found=target(scope,fields.get('who',''))
        return bool(found) and pact_exists(s,country,found.country(),fields.get('type'))
    if key=='aggressive_diplomatic_plays_permitted':
        return (autonomous(s,country) and not modifier_flag(s,country,'country_disallow_aggressive_plays_bool'))==yes(value)
    if key=='can_increase_autonomy':
        kind=subject_type_of(s,country)
        return (kind is not None and bool(s.definitions('common/subject_types').get(kind,{}).get('higher_autonomy_subject_type_alternatives')))==yes(value)
    if key=='country_has_state_religion':
        return s.map('country','country,religion').get(country)==value.split(':',1)[-1]
    if key=='country_has_primary_culture':
        return value.split(':',1)[-1] in primary_cultures(s,country)
    if key=='has_interest_marker_in_region':
        return interest_tier(s,country,value.split(':',1)[-1])>=RELEVANT_TIER
    if key=='has_diplomats_expelled':
        found=target(scope,value)
        return bool(found) and expelled(s,country,found.country())
    if key in ('has_diplomatic_relevance','is_adjacent_to_country'):
        found=target(scope,value)
        if not found:
            return False
        pair={country,found.country()}
        other=next(iter(pair-{s.player}),None)
        adjacent=s.player in pair and (other,) in s.rows('player_adjacent_country','country')
        return adjacent or key=='has_diplomatic_relevance' and bool(engaged_regions(s,country)&engaged_regions(s,found.country()))
    if key in ('owns_entire_state_region','country_or_subject_owns_entire_state_region'):
        allowed={country}|(below(s,country) if key.startswith('country_or_subject') else set())
        owners=[owner for region,owner in s.rows('state','state_region,country') if region==value.split(':',1)[-1]]
        return bool(owners) and set(owners)<=allowed
    if key=='is_in_power_bloc':
        return (s.map('country','country,power_bloc').get(country) is not None)==yes(value)
    if key=='is_power_bloc_leader':
        return bool(s.map('country','country,bloc_leader').get(country))==yes(value)
    if key in ('has_any_strait_province','has_any_strait_control'):
        listed=s.rows('strait_endpoint','strait,first_state,second_state')
        owners=s.map('state','state,country')
        country=resolve(scope,value)
        held=country in {owners.get(state) for _,first,second in listed for state in (first,second)}
        ours=country==s.player and not any(controller==s.player for _,controller in s.rows('occupation','state,controller'))
        if not held and not ours and {ident for ident, in s.rows('strait','strait')}-{strait for strait,_,_ in listed}:
            raise Unknown(f'{key}: a strait has no recorded endpoints')
        if held and key=='has_any_strait_control':
            raise Unknown(f'{key} of a country that borders a strait')
        return held
    if key=='is_in_same_power_bloc':
        other=target(scope,value)
        blocs=s.map('country','country,power_bloc')
        return bool(other) and blocs.get(country) is not None and blocs.get(country)==blocs.get(other.country())
    if key=='can_form_nation':
        return False
    if key=='exists' and isinstance(value,str) and value.startswith('c:'):
        return value[2:] in {tag for tag, in s.rows('country','country_definition')}
    if key=='ruler_can_have_command':
        return bool(laws(s,country)&COMMAND_LAWS)==yes(value)
    if key=='is_direct_subject_of':
        return resolve(scope,value) in overlords(s,country)
    if key=='has_technology_researched':
        return value in technologies(s,country)
    if key in ('has_law','has_law_or_variant'):
        return value.split(':',1)[1] in laws(s,country)
    if key=='is_subject':
        return bool(overlords(s,country))==yes(value)
    if key=='is_junior_in_customs_union':
        owners=s.map('market','market,owner')
        market=s.map('country','country,market').get(country)
        return (market is not None and owners.get(market,country)!=country)==yes(value)
    if key=='is_subject_type':
        return value.removeprefix('subject_type_') in {action for first,second,action in s.rows('pact','first_country,second_country,pact_type')
                                                         if second==country and first in overlords(s,country)}
    if key.startswith('modifier:') and value in ('yes','no') and scope.kind=='power_bloc':
        return bloc_modifier(s,scope.ident,key.split(':',1)[1])==yes(value)
    if key.startswith('modifier:') and value in ('yes','no'):
        return modifier_flag(s,country,key.split(':',1)[1])==yes(value)
    if key.startswith('modifier:') and isinstance(value,str):
        return COMPARE[operator](modifier_value(s,country,key.split(':',1)[1]),amount(s,value))
    if key=='is_subject_of':
        return resolve(scope,value) in overlords(s,country)
    if scope.kind=='diplomatic_catalyst' and key=='is_diplomatic_catalyst_type':
        return s.map('diplomatic_catalyst','diplomatic_catalyst,diplomatic_catalyst_type').get(scope.ident)==value
    if scope.kind=='diplomatic_catalyst' and key=='target':
        return resolve(scope,value)==s.map('diplomatic_catalyst_private','diplomatic_catalyst,target_country').get(scope.ident)
    if key=='is_at_war':
        return at_war(s,country)==yes(value)
    if key=='has_journal_entry':
        return value in journal_types(s,country)
    if key=='is_diplomatic_play_enemy_of':
        return resolve(scope,value) in play_enemies(s,country)
    if key=='this':
        return resolve(scope,value)==scope.ident
    if key=='has_modifier':
        return value in modifiers(s,'country',country)
    if key=='is_country_type':
        return s.map('country','country,country_type').get(country)==value
    if key=='has_government_type':
        return s.map('country','country,government').get(country)==value
    if key=='game_date':
        return COMPARE[operator](now(s),script_hours(value))
    if key=='liberty_desire':
        return COMPARE[operator](liberty_desire(s,country),amount(s,value))
    if key=='exists' and isinstance(value,str) and value.endswith(('land_hq','naval_hq')):
        wanted=0 if value.endswith('land_hq') else 1
        region=strategic_region(s,s.map('country','country,capital').get(country))
        own={hq for hq, in s.rows('hq','hq',country=country)}
        return any(hq in own and kind==wanted and where==region for hq,kind,where in s.rows('hq_private','hq,hq_type,hq_region'))
    UNKNOWN[key]+=1
    return None


ENGAGED=1000
RELEVANT_TIER=2


@timed_often
def engaged_regions(s,country):
    def compute():
        grouped={}
        for owner,region,involvement in s.rows('interest','country,strategic_region,involvement'):
            if involvement>=ENGAGED:
                grouped.setdefault(owner,set()).add(region)
        return grouped
    return s.memo('engaged_regions',compute).get(country,set())


@timed_often
def modifiers(s,kind,ident):
    if kind=='country':
        return {modifier for modifier, in s.rows('country_timed_modifier','modifier',country=ident)}
    if kind in ('state','character'):
        return {modifier for modifier, in s.rows(kind+'_timed_modifier','modifier',**{kind:ident})}
    raise Unknown(f'{kind} timed modifiers are not captured')


HANDLED={'AND','OR','NOT','NOR','NAND','any_scope_war','calc_true_if','amount','custom_tooltip','hidden_trigger','custom_description','has_dlc_feature','always','has_variable',
         'any_scope_state','any_scope_building','any_scope_character','any_primary_culture','any_subject_or_below','any_interest_group','count','limit',
         'trigger_if','trigger_else_if','trigger_else','text','target','value','has_technology_researched','has_law','has_law_or_variant',
         'is_subject','is_subject_of','is_at_war','has_journal_entry','is_diplomatic_play_enemy_of','this','has_modifier','is_country_type','has_government_type','game_date','liberty_desire',
         'any_scope_treaty','any_scope_article','country_rank','is_revolutionary','is_insurrectionary','has_war_with','has_diplomatic_pact',
         'is_in_power_bloc','is_direct_subject_of','ruler_can_have_command','can_form_nation','exists','is_power_bloc_leader','is_in_same_power_bloc',
         'has_any_strait_province','has_any_strait_control',
         'has_diplomatic_relevance','is_adjacent_to_country','has_diplomats_expelled',
         'aggressive_diplomatic_plays_permitted','has_interest_marker_in_region',
         'country_has_primary_culture','country_has_state_religion','can_increase_autonomy','strategic_region','law','owns_entire_state_region','country_or_subject_owns_entire_state_region'}|set(METRIC_KEYS)|SCOPES|{key for table in HANDLERS.values() for key in table}


@timed_often
def unsupported(nodes):
    found=set()
    for key,_,value in nodes:
        if key not in HANDLED and not is_scope(key) and not key.startswith('modifier:'):
            found.add(key)
        if isinstance(value,list):
            found|=unsupported(value)
    return found
