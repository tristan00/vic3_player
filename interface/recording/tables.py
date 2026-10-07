from collections import defaultdict
from operator import itemgetter
import logging
from dataclasses import dataclass

from ..common import progress, slot, timed, timed_often
from .spec import DROPPED_COUNTRY_METRICS,DROPPED_STATE_METRICS,EPOCH_DATE,METRIC_COLUMNS,METRICS_KINDS,TABLE,TABLES

SLOT=0xffffff

LOG=logging.getLogger('interface')


@dataclass
class Built:
    rows: dict
    constants: dict
    meta: dict
    colors: dict


class Tracked(dict):
    @timed_often
    def __init__(self,tables):
        super().__init__(tables)
        self.read=set()

    def get(self,name,default=None):
        self.read.add(name)
        return super().get(name,default)

    def __getitem__(self,name):
        self.read.add(name)
        return super().__getitem__(name)


class Context:
    @timed_often
    def __init__(self,capture,orders):
        self.tables=Tracked(capture.tables)
        self.name=capture.name
        self.player=capture.player
        self.goods=capture.goods
        self.orders=orders
        self.out=defaultdict(list)
        self.identities={}

    def label(self,code):
        name=self.name(code) if code else None
        return name or None

    def labels(self,codes):
        return [self.label(code) for code in codes]

    @timed_often
    def table(self,name):
        data=self.tables.get(name)
        return data if data and data.get('id') else None

    @timed_often
    def rows(self,table,*columns):
        data=self.tables.get(table)
        if not data or not data[columns[0]]:
            return []
        return list(zip(*(data[column] for column in columns)))

    @timed_often
    def children(self,table,owner,*columns,sparse=False):
        grouped=defaultdict(list)
        for row in self.rows(table,owner,'ord',*columns):
            grouped[row[0]].append(row[1:])
        result={}
        for key,items in grouped.items():
            items.sort(key=lambda item:item[0])
            ords=[item[0] for item in items]
            if len(set(ords))!=len(ords) or (not sparse and ords!=list(range(len(ords)))):
                raise RuntimeError(f'{table} ords of {key} are {"duplicated" if sparse else "not dense"}: {ords[:10]}')
            result[key]=items if sparse else [item[1:] for item in items]
        return result

    def order(self,folder):
        return self.orders[folder]

    def goods_name(self,code):
        return self.order('common/goods')[self.goods.index(code)]

    def add(self,table,**values):
        self.out[table].append(values)

    def ident(self,entity,value):
        if entity not in self.identities:
            found=self.table(entity)
            self.identities[entity]=dict(zip(found['id'],found['ident'])) if found else {}
        if value&SLOT not in self.identities[entity]:
            raise RuntimeError(f'The script names {entity} {value} but the memory capture holds no such object')
        return self.identities[entity][value&SLOT]

    @timed_often
    def player_rows(self,table,*columns,sparse=False):
        items=self.children(table,'id',*columns,sparse=sparse)
        if set(items)-{self.player}:
            raise RuntimeError(f'{table} holds rows of countries other than the player: {sorted(set(items)-{self.player})[:5]}')
        return items.get(self.player,[])


OWNER_COUNTRY=2
OWNER_BUILDING=1
OWNING_TYPES={'building_manor_house':'manor_house','building_financial_district':'financial_district'}


@timed_often
def owning_types(company_types):
    return {**OWNING_TYPES,**{f'building_{company}':'company' for company in company_types},
            **{f'building_regional_{company}':'company_regional_headquarter' for company in company_types}}


def ownership_owner(ident,building,owner_type,owner,types,headquarters,owning):
    if owner_type==OWNER_COUNTRY:
        return {'owner_kind':'country','owner_country':owner,'owner_building':None,'owner_company':None}
    if owner_type!=OWNER_BUILDING:
        raise RuntimeError(f'Ownership {ident} has owner type {owner_type}, neither a country nor a building')
    if owner==building:
        kind='self'
    elif types.get(owner) in owning:
        kind=owning[types[owner]]
    else:
        raise RuntimeError(f'Ownership {ident} is owned by building {owner} of type {types.get(owner)}, which is no ownership building')
    if kind=='company' and owner not in headquarters:
        raise RuntimeError(f'Ownership {ident} is owned by company headquarters {owner}, which no captured company names as its headquarters')
    return {'owner_kind':kind,'owner_country':None,'owner_building':owner,'owner_company':headquarters.get(owner) if kind=='company' else None}


def movement_modifiers(children,ids,label):
    ends=defaultdict(list)
    for i,items in children.items():
        for modifier,end in items:
            ends[ids[i],label(modifier)].append(end)
    return [{'political_movement':movement,'modifier':modifier,'instances':len(found),'last_end_date':EPOCH_DATE if EPOCH_DATE in found else max(found)}
            for (movement,modifier),found in ends.items()]


def flag(value):
    if value not in (0,1):
        raise RuntimeError(f'Expected a 0/1 flag, found {value}')
    return bool(value)


@timed_often
def idents(t):
    return dict(zip(t['id'],t['ident']))


@timed_often
def countries(c):
    t=c.table('country')
    if not t:
        return
    ids=idents(t)
    ranks=dict(c.rows('country_rank','country','country_rank'))
    kinds=dict(c.rows('country_type','country','country_type'))
    leaders={country for country, in c.rows('power_bloc_leader','country')}
    for index,i in enumerate(t['id']):
        c.add('country_history',country=ids[i],country_definition=c.label(t['country_definition'][index]),government=c.label(t['government'][index]),
              religion=c.label(t['religion'][index]),country_rank=ranks.get(i),country_type=kinds.get(i),ruler=t['ruler'][index],capital=t['capital'][index],
              market=t['market'][index],market_capital=t['market_capital'][index],power_bloc=t['power_bloc_as_core'][index],
              founding_company=t['founding_company'][index],map_color_override=t['map_color_override'][index],
              dynamic_name_key=c.label(t['dynamic_country_name'][index]),dynamic_adjective_key=c.label(t['dynamic_country_adjective'][index]),
              in_civil_war=flag(t['civil_war'][index]),trends_initialized=flag(t['trends_initialized'][index]),bloc_leader=i in leaders,
              power_bloc_join_date=t['power_bloc_join_date'][index],power_bloc_leave_date=t['power_bloc_leave_date'][index])
        c.add('country_population',country=ids[i],loyalists_increase=t['pop_radicals_and_loyalists_statistics_loyalists_increase'][index],
              loyalists_decrease=t['pop_radicals_and_loyalists_statistics_loyalists_decrease'][index],
              radicals_increase=t['pop_radicals_and_loyalists_statistics_radicals_increase'][index],
              radicals_decrease=t['pop_radicals_and_loyalists_statistics_radicals_decrease'][index])
        c.add('country_diplomacy',country=ids[i],infamy=t['infamy'][index])
    stray=(set(ranks)|set(kinds)|leaders)-set(ids)
    if stray:
        raise RuntimeError(f'Country captures for countries absent from the country table: {sorted(stray)[:5]}')
    for name,table,column in (('country_culture','country_cultures','culture'),('country_dividend_building','country_dividend_buildings','building')):
        for i,items in c.children(table,'id','value').items():
            for value, in items:
                c.add(name,country=ids[i],**{column:value})
    for i,items in c.children('country_claims','id','value').items():
        for value, in items:
            c.add('country_claim',country=ids[i],state_region=c.label(value))
    for i,items in c.children('country_religions_present','id','religion').items():
        for value, in items:
            c.add('country_religion',country=ids[i],religion=c.label(value))
    for i,items in c.children('country_leverage','id','power_bloc','value',sparse=True).items():
        for _,bloc,value in items:
            c.add('country_leverage',country=ids[i],power_bloc=bloc,leverage=value)
    for i,modifier_id,_,modifier,multiplier,start,end,decay in c.rows('country_timed_modifier','id','modifier_id','ord','modifier','multiplier','start_date',
                                                                        'end_date','decay'):
        c.add('country_timed_modifier',country=ids[i],modifier_id=modifier_id,modifier=c.label(modifier),multiplier=multiplier,start_date=start,end_date=end,
              decays=flag(decay))
    professions=c.order('common/pop_types')
    for i,items in c.children('country_population_by_profession','id','value').items():
        for position,(value,) in enumerate(items):
            c.add('country_profession_population',country=ids[i],pop_type=professions[position],population=value)
    religions=c.order('common/religions')
    for i,parent,_,culture,value in c.rows('country_population_by_religion_culture','id','parent_ord','ord','culture','value'):
        c.add('country_religion_culture_population',country=ids[i],religion=religions[parent],culture=culture,population=value)
    c.tables.get('country_population_by_religion')
    c.tables.get('country_population_by_culture')
    for (owner,n),(date,gdp) in samples(c,'country','gdp',ids).items():
        c.add('country_gdp_sample',country=owner,n=n,date=date,gdp=gdp)
    for (owner,n),(date,sol) in samples(c,'country','avgsoltrend',ids).items():
        c.add('country_standard_of_living_sample',country=owner,n=n,date=date,average_standard_of_living=sol)
    for (owner,n),(date,population) in samples(c,'country','trend_population',ids).items():
        c.add('country_population_sample',country=owner,n=n,date=date,population=int(population))


@timed_often
def samples(c,owner,trend,ids):
    heads={}
    for i,ord_,channel,date,n in c.rows(f'{owner}_{trend}_channel','id','ord','channel','date','index'):
        if ord_!=5 or channel!=0:
            raise RuntimeError(f'{owner}_{trend} channel ({ord_}, {channel}) is not the single channel (5, 0)')
        heads[i]=(n,date)
    result={}
    for i,items in c.children(f'{owner}_{trend}','id','channel','value').items():
        if {channel for channel,_ in items}!={0}:
            raise RuntimeError(f'{owner}_{trend} of {i} has channels other than 0')
        n,date=heads[i]
        size=len(items)
        if size>n:
            raise RuntimeError(f'{owner}_{trend} of {i} holds {size} values for {n} samples')
        for position,(_,value) in enumerate(items):
            sample=n-((n-1-position)%size)
            result[(ids[i] if ids else i),sample]=(date if sample==n else None,value)
    return result


PRIVATE_COUNTRY=('heir','tax_level','government_wage_level','military_wage_level','supply_ship_construction_level','budget_money',
                 'budget_investment_pool','budget_weekly_investment_pool_change_from_investment','budget_weekly_investment_pool_change_from_construction',
                 'budget_credit','budget_principal','budget_money_trend_current','budget_balance_trend_current','budget_money_trend_latest_sample',
                 'budget_balance_trend_latest_sample','pop_statistics_population_lower_strata','pop_statistics_population_middle_strata',
                 'pop_statistics_population_upper_strata','pop_statistics_population_radicals','pop_statistics_population_loyalists',
                 'pop_statistics_population_eligible_voters','supply_ships','construction_paused')


@timed_often
def player(c):
    private=c.table('country_private')
    if private:
        if private['id']!=[c.player]:
            raise RuntimeError(f'country_private holds {private["id"]}, not the player {c.player}')
        p={column:private[column][0] for column in PRIVATE_COUNTRY}
        c.add('player_policy',heir=p['heir'],tax_level=p['tax_level'],government_wage_level=p['government_wage_level'],
              military_wage_level=p['military_wage_level'],supply_ship_construction_level=p['supply_ship_construction_level'],
              can_toll_straits='toll' in straits(c),can_close_straits='close' in straits(c),has_bloc_mandates=mandates(c))
        c.add('player_treasury',money=p['budget_money'],investment_pool=p['budget_investment_pool'],
              investment_pool_change_from_investment=p['budget_weekly_investment_pool_change_from_investment'],
              investment_pool_change_from_construction=p['budget_weekly_investment_pool_change_from_construction'],credit=p['budget_credit'],
              principal=p['budget_principal'],money_trend_current=p['budget_money_trend_current'],balance_trend_current=p['budget_balance_trend_current'],
              money_trend_latest_sample_date=p['budget_money_trend_latest_sample'],balance_trend_latest_sample_date=p['budget_balance_trend_latest_sample'])
        c.add('player_population',lower_strata=p['pop_statistics_population_lower_strata'],middle_strata=p['pop_statistics_population_middle_strata'],
              upper_strata=p['pop_statistics_population_upper_strata'],radicals=p['pop_statistics_population_radicals'],
              loyalists=p['pop_statistics_population_loyalists'],eligible_voters=p['pop_statistics_population_eligible_voters'])
        c.add('player_military',supply_ships=p['supply_ships'])
        c.construction_paused=p['construction_paused']
    for line,(value,) in enumerate(c.player_rows('country_budget_weekly_income','value')):
        c.add('player_budget_line',direction='income',line=line,amount=value)
    for line,(value,) in enumerate(c.player_rows('country_budget_weekly_expenses','value')):
        c.add('player_budget_line',direction='expense',line=line,amount=value)
    for value, in c.player_rows('country_taxed_goods','value'):
        c.add('player_taxed_goods',goods=c.label(value))
    for _,decision in c.player_rows('country_ignored_decisions','decision',sparse=True):
        c.add('player_ignored_decision',decision=c.label(decision))
    for _,interaction,until in c.player_rows('country_interaction_cooldown','interaction','until',sparse=True):
        c.add('player_interaction_cooldown',character_interaction=c.label(interaction),until=until)
    for direction in ('import','export'):
        for _,goods,level,previous,change in c.player_rows(f'country_{direction}_tariff','goods_type','level','previous','last_change',sparse=True):
            c.add('player_tariff',direction=direction,goods=c.label(goods),level=level,previous_level=previous,last_change=change)
    for kind in sorted({k for k, in c.rows('country_monopoly','building_type')}):
        c.add('player_monopoly',building_type=kind)
    for method in sorted({k for k, in c.rows('production_method_available','production_method')}):
        c.add('player_production_method_available',production_method=method)
    consumed=sorted(set(c.rows('market_goods_consumed_by','goods','consumer')))
    if {consumer for _,consumer in consumed}-{'government','military'}:
        raise RuntimeError(f'Unknown goods consumers {sorted({consumer for _,consumer in consumed})}')
    for goods,consumer in consumed:
        c.add('player_consumed_goods',consumer=consumer,goods=goods)
    for objective in sorted({k for k, in c.rows('objective','objective')}):
        c.add('player_objective',objective=objective)
    for subgoal in sorted({k for k, in c.rows('subgoal_completed','subgoal')}):
        c.add('player_completed_subgoal',objective_subgoal=subgoal)
    for _,culture,value in c.player_rows('country_standard_of_living_by_culture','culture','value',sparse=True):
        c.add('player_culture_standard_of_living',culture=culture,standard_of_living=value)
    for _,culture,value in c.player_rows('country_total_pol_str_by_culture','culture','value',sparse=True):
        c.add('player_culture_political_strength',culture=culture,political_strength=value)
    religions=c.order('common/religions')
    for position,(value,) in enumerate(c.player_rows('country_total_pol_str_by_religion','value')):
        c.add('player_religion_political_strength',religion=religions[position],political_strength=value)
    for private,table in ((False,'construction_queue'),(True,'private_construction_queue')):
        columns=('state','building_type','owner_building_type','speed','construction_left') if private else ('state','building_type','speed','construction_left')
        for position,values in enumerate(c.player_rows(table,*columns)):
            row=dict(zip(columns,values))
            c.add('player_construction_queue_item',private=private,position=position,state=row['state'],building_type=c.label(row['building_type']),
                  owner_building_type=c.label(row.get('owner_building_type')),speed=row['speed'],construction_left=row['construction_left'])
    for country,kind in sorted(set(c.rows('proposal_shown','country','kind'))):
        c.add('player_proposal',country=c.ident('country',country),kind=kind)
    for country, in sorted(set(c.rows('country_adjacent','country'))):
        c.add('player_adjacent_country',country=c.ident('country',country))
    for country,direction in sorted(set(c.rows('diplomats_expelled','country','direction'))):
        c.add('player_diplomat_expulsion',country=c.ident('country',country),direction={'by':'by_player','of':'of_player'}[direction])
    for country,direction in sorted(set(c.rows('obligation','country','direction'))):
        c.add('player_obligation',country=c.ident('country',country),direction=direction)
    for position,name,formable,ignored in sorted(c.rows('formable_country','ord','name','formable','ignored')):
        c.add('player_formable_country',name=name,position=position,formable=flag(formable),ignored=flag(ignored))
    for position,name,possible in sorted(c.rows('releasable_country','ord','name','possible')):
        c.add('player_releasable_country',name=name,position=position,possible=flag(possible))
    for alert,state,instances in sorted(set(c.rows('alert','alert','state','instances'))):
        if state==-1:
            c.add('player_alert',alert_type=alert,instances=instances)
        else:
            c.add('player_state_alert',alert_type=alert,state=c.ident('state',state))
    for decision,takeable in sorted(set(c.rows('decision','decision','takeable'))):
        c.add('player_decision',decision=decision,takeable=None if takeable is None else flag(takeable))
    for position,date,kind,title,description in c.rows('message_feed','ord','date','type','name','description'):
        c.add('player_message',position=position,date_text=date,message_group=kind or None,title=title,description=description)
    for entry,button in sorted(set(c.rows('journal_button_shown','journal_entry','button'))):
        c.add('player_journal_button',journal_entry_type=entry,scripted_button=button)
    for first,second in sorted(set(c.rows('treaty_enforced_on_player','first_country','second_country'))):
        c.add('player_treaty_enforced',first_country=c.ident('country',first),second_country=c.ident('country',second))
    shown=set(c.rows('diplomatic_action_shown','country','action'))
    possible=set(c.rows('diplomatic_action_possible','country','action'))
    if possible-shown:
        raise RuntimeError(f'Diplomatic actions possible but not shown: {sorted(possible-shown)[:5]}')
    for country,action in sorted(shown):
        c.add('player_diplomatic_option',target_country=c.ident('country',country),action_type=action,possible=(country,action) in possible)
    for country,action,side,state in sorted(set(c.rows('diplomatic_action_state_pick','country','action','side','state'))):
        c.add('player_diplomatic_option_state',target_country=c.ident('country',country),action_type=action,side={'first':'source','second':'target'}[side],
              state=c.ident('state',state))
    shown=set(c.rows('interaction_shown','character','interaction'))
    possible=set(c.rows('interaction_possible','character','interaction'))
    if possible-shown:
        raise RuntimeError(f'Character interactions possible but not shown: {sorted(possible-shown)[:5]}')
    for character,interaction in sorted(shown):
        c.add('player_character_interaction',character=c.ident('character',character),character_interaction=interaction,possible=(character,interaction) in possible)
    for state,paused in c.rows('state_setting','state','colonization_paused'):
        if flag(paused):
            c.add('player_colonization_paused',state=c.ident('state',state))
    for state,kind in sorted(set(c.rows('decree_active','state','decree_type'))):
        c.add('player_active_decree',state=c.ident('state',state),decree_type=kind)
    ids=idents(c.table('country')) if c.table('country') else {}
    for table,trend,column,convert in (('player_prestige_sample','prestige','prestige',int),('player_literacy_sample','literacy','literacy',float),
                                       ('player_lower_strata_sample','trend_population_lower_strata','lower_strata',int),
                                       ('player_middle_strata_sample','trend_population_middle_strata','middle_strata',int),
                                       ('player_upper_strata_sample','trend_population_upper_strata','upper_strata',int),
                                       ('player_radicals_sample','trend_radicals','radicals',int),('player_loyalists_sample','trend_loyalists','loyalists',int)):
        for (owner,n),(date,value) in samples(c,'country',trend,ids).items():
            if owner&SLOT!=c.player:
                raise RuntimeError(f'Player trend samples belong to {owner}')
            c.add(table,n=n,date=date,**{column:convert(value)})


@timed_often
def straits(c):
    return {power for power, in c.rows('strait_power','power')}


@timed_often
def mandates(c):
    values=[m for m, in c.rows('bloc_mandates','mandates')]
    if len(values)>1:
        raise RuntimeError(f'{len(values)} bloc mandate rows in one snapshot')
    return bool(values and values[0])


@timed_often
def metrics(c):
    t=c.table('country')
    ids=idents(t) if t else {}
    tags={i:c.label(code) for i,code in zip(t['id'],t['country_definition'])} if t else {}
    values=defaultdict(dict)
    for tag,name,value,country in c.rows('country_metric','tag','name','value','country'):
        if tags.get(country)!=tag:
            raise RuntimeError(f'country_metric tag {tag} does not name country {country}')
        values[country][name]=value
    kinds=METRICS_KINDS
    rows={}
    for country,named in values.items():
        for name,value in named.items():
            converted=metric_value(kinds['country'][name],value)
            if (('country',name)) in METRIC_COLUMNS:
                table,column=METRIC_COLUMNS['country',name]
                key=None if table.startswith('player_') else ids[country]
                if key is None and country!=c.player:
                    raise RuntimeError(f'Player metric {name} captured for {country}')
                rows.setdefault(table,{}).setdefault(key,{})[column]=converted
    state=c.table('state')
    sids=idents(state) if state else {}
    for state_,name,value in c.rows('state_metric','state','name','value'):
        if ('state',name) in METRIC_COLUMNS:
            table,column=METRIC_COLUMNS['state',name]
            rows.setdefault(table,{}).setdefault(sids[state_],{})[column]=metric_value(kinds['state'][name],value)
    merge(c,rows)
    check_dropped(c,values,sids,c.rows('state_metric','state','name','value'))


@timed_often
def merge(c,rows):
    for table,owners in rows.items():
        owner=TABLE[table].owner
        existing={row[owner]:row for row in c.out[table]} if owner else {None:row for row in c.out[table]}
        for key,columns in owners.items():
            if key in existing:
                existing[key].update(columns)
            else:
                c.add(table,**({owner:key} if owner else {}),**columns)


@timed_often
def check_dropped(c,values,sids,state_rows):
    found={}
    for table,rows in c.out.items():
        owner=TABLE[table].owner if table in TABLE else None
        for row in rows:
            found[table,row.get(owner) if owner else None]=row
    t=c.table('country')
    ids=idents(t) if t else {}
    for country,named in values.items():
        for name,value in named.items():
            if name not in DROPPED_COUNTRY_METRICS:
                continue
            table,expression=DROPPED_COUNTRY_METRICS[name]
            if table=='player_budget_line':
                direction,line=expression.split()
                amounts=[row['amount'] for row in c.out[table] if row['direction']==direction and row['line']==int(line)]
                if amounts!=[value]:
                    raise RuntimeError(f'Country metric {name} is {value}, not budget {expression} {amounts}')
                continue
            key=None if table.startswith('player_') else ids[country]
            row=found.get((table,key))
            if row is not None and expression in row and not same(row[expression],value):
                raise RuntimeError(f'Country metric {name} of {country} is {value}, not {table}.{expression} {row[expression]}')
    for state_,name,value in state_rows:
        if name in DROPPED_STATE_METRICS:
            table,expression=DROPPED_STATE_METRICS[name]
            row=found.get((table,sids[state_]))
            if row is not None and expression in row and not same(row[expression],value):
                raise RuntimeError(f'State metric {name} of {state_} is {value}, not {table}.{expression} {row[expression]}')


def same(stored,metric):
    return float(stored)==float(metric)


def metric_value(kind,value):
    if kind=='bool':
        return flag(value)
    if kind in ('int32','int64'):
        if value!=int(value):
            raise RuntimeError(f'Integer metric holds {value}')
        return int(value)
    return value


@timed_often
def diplomacy(c):
    relation=c.table('relation')
    if relation:
        pairs={i:(a,b,ta,tb) for i,a,b,ta,tb in zip(relation['id'],relation['first_country'],relation['second_country'],relation['first_truce'],relation['second_truce'])}
        private=c.rows('relation_private','id','relations','improve_relations','tension')
        for i,relations,improve,tension in private:
            first,second,first_truce,second_truce=pairs[i]
            if first&SLOT==c.player:
                other,own,theirs=second,first_truce,second_truce
            elif second&SLOT==c.player:
                other,own,theirs=first,second_truce,first_truce
            else:
                raise RuntimeError(f'Private relation {i} is not between the player and another country')
            c.add('player_relation',country=other,relations=relations,improve_relations=improve,tension=tension,player_truce=own,country_truce=theirs)
    t=c.table('pact')
    if t:
        for ident,first,second,kind,liberty in zip(t['ident'],t['targets_first'],t['targets_second'],t['pact_action'],t['liberty_desire']):
            c.add('pact_history',pact=ident,first_country=first,second_country=second,pact_type=c.label(kind),liberty_desire=liberty)
        ids=idents(t)
        for i,start,duration in c.rows('pact_private','id','start_date','forced_duration'):
            c.add('pact_private',pact=ids[i],start_date=start,forced_duration=duration)
    t=c.table('diplomatic_catalyst')
    if t:
        ids=idents(t)
        for ident,kind in zip(t['ident'],t['diplomatic_catalyst_type']):
            c.add('diplomatic_catalyst_history',diplomatic_catalyst=ident,diplomatic_catalyst_type=c.label(kind))
        for i,country,target,date in c.rows('diplomatic_catalyst_private','id','country','target_country','date'):
            c.add('diplomatic_catalyst_private',diplomatic_catalyst=ids[i],country=country,target_country=target,date=date)
    t=c.table('diplomatic_action')
    if t:
        for ident,first,second,kind in zip(t['ident'],t['targets_first'],t['targets_second'],t['diplomatic_action_action']):
            c.add('diplomatic_action_history',diplomatic_action=ident,first_country=first,second_country=second,action_type=c.label(kind))
    t=c.table('diplomatic_play')
    if t:
        ids=idents(t)
        for index,i in enumerate(t['id']):
            c.add('diplomatic_play_history',diplomatic_play=ids[i],initiator=t['initiator'][index],target=t['target'][index],
                  diplomatic_play_type=c.label(t['diplomatic_play_type'][index]),strategic_region=c.label(t['strategic_region'][index]),
                  initiator_maneuvers=t['initiator_maneuvers'][index],target_maneuvers=t['target_maneuvers'][index],end_date=t['end_date'][index],
                  escalation=t['escalation'][index],war=t['war'][index])
        if any(identity!=ident for identity,ident in zip(t['identity'],t['ident'])):
            raise RuntimeError('diplomatic_play.identity differs from the play identity')
        for role,table in (('initiator','initiators'),('target','targets'),('interested','involved'),('initiator_ally','lean_initiator'),('target_ally','lean_target')):
            for i,items in c.children('diplomatic_play_'+table,'id','value').items():
                for country, in items:
                    c.add('diplomatic_play_country',diplomatic_play=ids[i],country=country,role=role)
        for i,items in c.children('diplomatic_play_country_record','id','country','side').items():
            for country,side in items:
                c.add('diplomatic_play_record',diplomatic_play=ids[i],country=country,play_side=side)
    t=c.table('treaty')
    if t:
        for index,ident in enumerate(t['ident']):
            c.add('treaty_history',treaty=ident,first_country=t['first_country'][index],second_country=t['second_country'][index],
                  entered_into_force_on=t['entered_into_force_on'][index],binding_period=t['binding_period'][index],withdrawn_by=t['withdrawn_by'][index],
                  withdrawn=flag(t['withdrawn'][index]))
    t=c.table('treaty_article')
    if t:
        for ident,treaty,kind,source,target in zip(t['ident'],t['treaty'],t['treaty_article_article'],t['source_country'],t['target_country']):
            c.add('treaty_article_history',treaty_article=ident,treaty=treaty,treaty_article_type=c.label(kind),source_country=source,target_country=target)
    t=c.table('power_bloc')
    if t:
        ids=idents(t)
        for ident,identity,texture,cohesion,progress in zip(t['ident'],t['power_bloc_identity'],t['map_texture'],t['cohesion'],t['mandate_progress']):
            c.add('power_bloc_history',power_bloc=ident,power_bloc_identity=c.label(identity),power_bloc_map_texture=c.label(texture),cohesion=cohesion,
                  mandate_progress=progress)
        for i,items in c.children('power_bloc_principles','id','value').items():
            for position,(principle,) in enumerate(items):
                c.add('power_bloc_adopted_principle',power_bloc=ids[i],power_bloc_principle=c.label(principle),position=position)
    t=c.table('interest')
    if t:
        for ident,country,region,involvement in zip(t['ident'],t['country'],t['strategic_region'],t['current_involvement']):
            c.add('interest_history',interest=ident,country=country,strategic_region=c.label(region),involvement=involvement)


@timed_often
def states(c):
    t=c.table('state')
    if not t:
        return
    ids=idents(t)
    potential={state for state, in c.rows('treaty_port_potential','state')}
    if potential-set(ids):
        raise RuntimeError('Treaty-port potential for states absent from the state table')
    names={c.label(code) for code in set(t['custom_name'])}-{None}
    if names:
        raise RuntimeError(f'state.custom_name holds {sorted(names)[:3]}')
    columns={'lower_strata':'pop_statistics_population_lower_strata','middle_strata':'pop_statistics_population_middle_strata',
             'upper_strata':'pop_statistics_population_upper_strata','radicals':'pop_statistics_population_radicals','loyalists':'pop_statistics_population_loyalists',
             'subsisting_workforce':'pop_statistics_population_subsisting_workforce','unemployed_workforce':'pop_statistics_population_unemployed_workforce',
             'last_week_emigration':'last_week_pop_migration_statistics_weekly_emigration','last_week_immigration':'last_week_pop_migration_statistics_weekly_immigration',
             'last_week_slave_emigration':'last_week_slave_trade_statistics_weekly_emigration',
             'last_week_slave_immigration':'last_week_slave_trade_statistics_weekly_immigration'}
    for index,i in enumerate(t['id']):
        c.add('state_history',state=ids[i],state_region=c.label(t['state_region'][index]),localized_name_key=c.label(t['localized_name'][index]),
              country=t['country'][index],mass_migration_culture=t['mass_migration_culture'][index],mass_migration_country=t['mass_migration_country'][index],
              slave_import_marker=t['slave_import_marker'][index],treaty_port_potential=i in potential)
        c.add('state_population',state=ids[i],**{name:t[source][index] for name,source in columns.items()})
        c.add('state_economy',state=ids[i],arable_land=t['arable_land'][index],infrastructure=t['infrastructure'][index],
              infrastructure_usage=t['infrastructure_usage'][index],trade_capacity=t['trade_capacity'][index],trade_capacity_usage=t['trade_capacity_usage'][index],
              treaty_port=flag(t['treaty_port'][index]))
        c.add('state_status',state=ids[i],incorporation=t['incorporation'][index],colony_progress=t['colony_progress'][index],devastation=t['devastation'][index],
              next_colony_province=t['next_colony_province'][index])
    for i,wage in c.rows('state_private','id','pop_statistics_wage'):
        c.add('state_private',state=ids[i],wage=wage)
    counted=defaultdict(int)
    for i,items in c.children('state_timed_modifier','id','modifier').items():
        for modifier, in items:
            counted[ids[i],c.label(modifier)]+=1
    for (state,modifier),count in counted.items():
        c.add('state_timed_modifier',state=state,modifier=modifier,instances=count)
    for i,items in c.children('state_slave_export_markers','id','value').items():
        for marker, in items:
            c.add('state_slave_export_marker',state=ids[i],marker=marker)
    for direction,table in (('outbound','state_last_week_pop_migration_statistics_emigration_states'),
                            ('inbound','state_last_week_pop_migration_statistics_immigration_states')):
        for i,items in c.children(table,'id','value').items():
            for other in sorted({other for other, in items}):
                c.add('state_migration',state=ids[i],direction=direction,other_state=other)
    goods=defaultdict(dict)
    for i,code,value in c.rows('state_local_price','id','goods','value'):
        goods[ids[i],c.goods_name(code)]['local_price']=value
    for column,table in (('production','state_building_production'),('consumption','state_building_consumption'),('trade','state_trade')):
        for i,code,value in c.rows(table,'id','goods','value'):
            key=ids[i],c.label(code)
            if key not in goods:
                raise RuntimeError(f'{table} has goods {key[1]} without a local price in state {i}')
            goods[key][column]=value
    for (state,name),values in goods.items():
        c.add('state_goods',state=state,goods=name,**values)
    for i,group,need,code,weight in c.rows('state_pop_need','id','need_group','need','goods_type','weight'):
        c.add('state_pop_need',state=ids[i],culture_type=c.label(group),need=need,goods=c.label(code),weight=weight)
    for state,name in sorted(set(c.rows('state_goods_supply','state','goods'))):
        c.add('state_goods_supply',state=c.ident('state',state),goods=name)
    for state,kind in sorted(set(c.rows('decree_state_valid','state','decree_type'))):
        c.add('state_decree_valid',state=c.ident('state',state),decree_type=kind)
    t=c.table('decree')
    if t:
        for ident,owner,state,kind in zip(t['ident'],t['owner'],t['state'],t['decree_type']):
            c.add('decree_history',decree=ident,owner=owner,state=state,decree_type=c.label(kind))
    t=c.table('harvest_condition')
    if t:
        ids=idents(t)
        for ident,kind,region in zip(t['ident'],t['harvest_type'],t['state_region']):
            c.add('harvest_condition_history',harvest_condition=ident,harvest_condition_type=c.label(kind),state_region=c.label(region))
        for i,items in c.children('harvest_condition_area','id','intensity','duration').items():
            for position,(intensity,duration) in enumerate(items):
                c.add('harvest_condition_area',harvest_condition=ids[i],position=position,intensity=intensity,duration=duration)
    t=c.table('famine')
    if t:
        for ident,state,start,births,deaths in zip(t['ident'],t['state'],t['start_date'],t['num_births'],t['num_deaths']):
            c.add('famine_history',famine=ident,state=state,start_date=start,num_births=births,num_deaths=deaths)
    regions=region_names(c)
    for region,items in c.children('state_region_resource','id','building_type','amount').items():
        for kind,amount in items:
            c.add('state_region_resource',state_region=regions[region],building_type=c.label(kind),available_levels=amount)
    for region,items in c.children('state_region_traits','id','value').items():
        for trait, in items:
            c.add('state_region_trait',state_region=regions[region],state_trait=c.label(trait))


@timed_often
def region_names(c):
    t=c.tables.get('state_region')
    if not t or not t['id']:
        raise RuntimeError('The capture holds no state regions')
    return {i:c.label(code) for i,code in zip(t['id'],t['state_region_template'])}


@timed_often
def pops(c):
    t=c.table('pop')
    if not t:
        return
    ids=idents(t)
    for index,i in enumerate(t['id']):
        c.add('pop_history',pop=ids[i],location=t['location'][index],workplace=t['workplace'][index],culture=t['culture'][index],
              religion=c.label(t['religion'][index]),pop_type=c.label(t['pop_type'][index]),social_class=c.label(t['social_class'][index]),
              acceptance_status=c.label(t['acceptance_status'][index]),assimilation_culture=t['assimilation_culture'][index],
              conversion_religion=c.label(t['conversion_religion'][index]))
        c.add('pop_status',pop=ids[i],**{name:t[name][index] for name in ('wealth_progress','num_literate','loyalists_and_radicals','wealth','food_security',
                                                                         'political_strength','workforce','dependents','job_satisfaction')})
    for i,items in c.children('pop_movement_support','id','political_movement','supporters',sparse=True).items():
        for _,movement,supporters in items:
            c.add('pop_movement_support',pop=ids[i],political_movement=movement,supporters=supporters)
    movements=c.table('political_movement')
    mids=idents(movements) if movements else {}
    listed=defaultdict(set)
    for i,items in c.children('political_movement_pops','id','value').items():
        for pop, in items:
            listed[pop&SLOT].add(mids[i]&SLOT)
    supported=defaultdict(set)
    for row in c.out['pop_movement_support']:
        supported[row['pop']&SLOT].add(row['political_movement']&SLOT)
    if dict(listed)!=dict(supported):
        raise RuntimeError('Movement pop lists differ from the inverse of pop movement support')


@timed_often
def cultures(c):
    t=c.table('culture')
    if not t:
        return
    ids=idents(t)
    regions=region_names(c)
    for ident,kind,fervor,casualties,region,started in zip(t['ident'],t['culture_type'],t['current_fervor'],t['casualties_from_wars'],
                                                           t['national_awakening_state_region'],t['has_started_national_awakening']):
        c.add('culture_history',culture=ident,culture_type=c.label(kind),fervor=fervor,casualties_from_wars=casualties,
              national_awakening_state_region=None if region==-1 else regions[region],national_awakening_started=flag(started))
    for name,table,column in (('culture_core_state','core_states','state_region'),('culture_obsession','obsessions','goods'),
                              ('culture_taboo','taboos','goods'),('culture_tradition','traditions','discrimination_trait')):
        for i,items in c.children('culture_'+table,'id','value').items():
            for value, in items:
                c.add(name,culture=ids[i],**{column:c.label(value)})
    t=c.table('cultural_community')
    if t:
        for ident,culture,state,delta in zip(t['ident'],t['culture'],t['state'],t['acceptance_delta']):
            c.add('cultural_community_history',cultural_community=ident,culture=culture,state=state,acceptance_delta=delta)


@timed_often
def provinces(c,colors):
    for province,state,controller in c.rows('province_state','province','state','controller_country'):
        c.add('province_history',province=province,state=state,controller=controller)
        if province not in colors:
            raise RuntimeError(f'Province {province} has no captured colour')


BUILDING_FLOW=('balance_subsidies','trade_revenue','input_goods_shortage','tariffs','tolls','subventions','supply_ship_construction','military_ship_construction',
               'produced_supply','income_taxes','cash_reserves','staffing','throughput','salary_rate','dividends','goods_cost','goods_sales','slave_upkeep')


@timed_often
def buildings(c):
    t=c.table('building')
    if t:
        ids=idents(t)
        for index,i in enumerate(t['id']):
            c.add('building_history',building=ids[i],building_type=c.label(t['building'][index]),state=t['state'][index],levels=t['levels'][index],
                  slave_basket=t['slave_basket'][index],active=flag(t['active'][index]),subsidized=flag(t['subsidized'][index]),
                  privatization_requested=t['privatization_requested'][index],dead=flag(t['dead'][index]))
            c.add('building_flow',building=ids[i],**{name:t[name][index] for name in BUILDING_FLOW})
        settings={building:values for building,*values in c.rows('building_setting','building','auto_expand','output_paused','monopoly','privatizable')}
        states=c.table('state')
        mine={int(i) for i,owner in zip(states['id'],states['country']) if slot(owner)==c.player}
        live={i for i,state,dead in zip(t['id'],t['state'],t['dead']) if not flag(dead) and slot(state) in mine}
        if set(settings)!=live:
            raise RuntimeError(f'Building GUI captures cover {sorted(set(settings)-live)[:5]} beyond the live player buildings and miss {sorted(live-set(settings))[:5]}')
        for building,values in settings.items():
            c.add('building_private',building=c.ident('building',building),**dict(zip(('auto_expand','output_paused','monopoly','privatizable'),map(flag,values))))
        for i,items in c.children('building_pm','id','production_method').items():
            for method, in items:
                c.add('building_production_method_active',building=ids[i],production_method=c.label(method))
        for i,items in c.children('building_enable_privatization','id','country').items():
            for country, in items:
                c.add('building_privatization_enabled',building=ids[i],country=country)
        goods=defaultdict(dict)
        for column,table in (('input','building_input_goods'),('output','building_output_goods'),('slave_input','building_slave_goods')):
            for i,code,value in c.rows(table,'id','goods','value'):
                goods[ids[i],c.label(code)][column]=value
        for (building,name),values in goods.items():
            c.add('building_goods',building=building,goods=name,**values)
        c.tables.get('building_goods_derived')
        for i,items in c.children('building_failed_hire','id','workplace').items():
            for position,(workplace,) in enumerate(items):
                c.add('building_failed_hire',building=ids[i],position=position,workplace=workplace)
    t=c.table('building_ownership')
    if t:
        owners={value&SLOT:(building,value) for building,_,value in c.rows('building_owners','id','ord','value')}
        assets={value&SLOT:(owner,value) for owner,_,value in c.rows('building_assets','id','ord','value')}
        captured=set(c.table('building')['ident']) if c.table('building') else set()
        types={ident:c.label(code) for ident,code in zip(c.table('building')['ident'],c.table('building')['building'])} if c.table('building') else {}
        headquarters={building:ident for ident,building in zip(c.table('company')['ident'],c.table('company')['building']) if building!=-1} if c.table('company') else {}
        owning=owning_types(c.order('common/company_types'))
        for i,ident,building,owner_type,owner,levels,privatization in zip(t['id'],t['ident'],t['building'],t['identity_type'],t['identity_building'],
                                                                           t['levels'],t['privatization']):
            listed=owners.pop(i,None)
            if building not in captured:
                if listed is not None:
                    raise RuntimeError(f'Ownership {ident} of vanished building {building} is still listed among the owners of building {listed[0]}')
            elif listed is None or listed[0]!=building&SLOT or listed[1]!=ident:
                raise RuntimeError(f'Ownership {ident} is not listed among the owners of building {building}')
            asset=assets.pop(i,None)
            if asset is not None and (asset[0]!=owner&SLOT or asset[1]!=ident):
                raise RuntimeError(f'Ownership {ident} is listed among the assets of {asset[0]}, not of its owner {owner}')
            c.add('building_ownership_history',building_ownership=ident,building=building,**ownership_owner(ident,building,owner_type,owner,types,headquarters,owning),
                  levels=levels,privatization=flag(privatization),in_owner_assets=asset is not None)
        if owners or assets:
            raise RuntimeError(f'Owner or asset entries without an ownership: {sorted(owners)[:3]} {sorted(assets)[:3]}')


@timed_often
def markets(c):
    t=c.table('market')
    if t:
        ids=idents(t)
        for ident,owner in zip(t['ident'],t['owner']):
            c.add('market_history',market=ident,owner=owner)
        for i,code,price,sell,buy in c.rows('market_goods','id','goods','price','sell_orders','buy_orders'):
            c.add('market_goods',market=ids[i],goods=c.goods_name(code),price=price,sell_orders=sell,buy_orders=buy)
    t=c.table('market_area')
    if t:
        ids=idents(t)
        for ident,market in zip(t['ident'],t['market']):
            c.add('market_area_history',market_area=ident,market=market)
        ports={(i,state&SLOT) for i,items in c.children('market_area_port','id','state').items() for state, in items}
        for i,items in c.children('market_area_state','id','state').items():
            for state, in items:
                c.add('market_area_state',market_area=ids[i],state=state,port=(i,state&SLOT) in ports)
                ports.discard((i,state&SLOT))
        if ports:
            raise RuntimeError(f'Market area ports outside their market area: {sorted(ports)[:3]}')
    hubs=c.children('world_market_hub','id','state')
    if set(hubs)-{0}:
        raise RuntimeError(f'World market hubs of owners {sorted(hubs)}')
    centers=defaultdict(int)
    for owner,state,_ in c.rows('world_market_hub_trade_center','id','state','ord'):
        if owner!=0:
            raise RuntimeError('World market trade centers of an owner other than 0')
        centers[state&SLOT]+=1
    for state, in hubs.get(0,[]):
        c.add('world_market_hub',state=state,trade_centers=centers.pop(state&SLOT,0))
    if centers:
        raise RuntimeError(f'Trade centers of states that are not hubs: {sorted(centers)[:3]}')
    channels=c.rows('world_market_price_trend_channel','id','ord','channel','date','index')
    if {owner for owner,*_ in channels}-{0} or len({(date,n) for *_,date,n in channels})>1:
        raise RuntimeError('World market price channels do not share one clock')
    goods=c.order('common/goods')
    for _,bucket,channel,_,_ in channels:
        c.add('world_market_price_channel',goods=goods[channel],bucket=bucket)
    if channels:
        _,_,_,date,n=channels[0]
        buffers=defaultdict(dict)
        for _,channel,position,value in c.rows('world_market_price_trend','id','channel','ord','value'):
            buffers[channel][position]=value
        for channel,values in buffers.items():
            size=len(values)
            if size>n or sorted(values)!=list(range(size)):
                raise RuntimeError(f'World market price buffer of channel {channel} holds {size} values for {n} samples')
            for position,value in values.items():
                sample=n-((n-1-position)%size)
                c.add('world_market_price_sample',goods=goods[channel],n=sample,date=date if sample==n else None,price=value)


@timed_often
def companies(c):
    t=c.table('company')
    if t:
        ids=idents(t)
        charters={}
        by_type={}
        for i,country,kind in zip(t['id'],t['country'],t['company_type']):
            if country&SLOT==c.player:
                if c.label(kind) in by_type:
                    raise RuntimeError(f'The player holds two companies of type {c.label(kind)}')
                by_type[c.label(kind)]=i
        for kind,investment,trade,established in c.rows('company_charter','company_type','investment','trade','established'):
            charters[by_type[kind]]=(flag(investment),flag(trade),established)
        for index,i in enumerate(t['id']):
            investment,trade,established=charters.get(i,(None,None,None))
            c.add('company_history',company=ids[i],country=t['country'][index],building=t['building'][index],ceo=t['ceo'][index],
                  prosperity=t['prosperity'][index],company_type=c.label(t['company_type'][index]),company_name_key=c.label(t['company_name'][index]),
                  investment_charter=investment,trade_charter=trade,established=established)
        by_owner={}
        for i,country,kind in zip(t['id'],t['country'],t['company_type']):
            if (c.label(kind),country&SLOT) in by_owner:
                raise RuntimeError(f'Country {country} holds two companies of type {c.label(kind)}')
            by_owner[c.label(kind),country&SLOT]=i
        for kind,country,owned in sorted(set(c.rows('company_owns_country','company_type','country','owned_country'))):
            c.add('company_owned_country',company=ids[by_owner[kind,country]],country=c.ident('country',owned))
    t=c.table('charter')
    if t:
        ids=idents(t)
        for ident,company,kind in zip(t['ident'],t['company'],t['charter_type']):
            c.add('charter_history',charter=ident,company=company,company_charter_type=c.label(kind))
        for i,unlock in c.rows('charter_private','id','unlock'):
            c.add('charter_private',charter=ids[i],unlock=unlock)
    t=c.table('hq')
    if t:
        ids=idents(t)
        for ident,country in zip(t['ident'],t['country']):
            c.add('hq_history',hq=ident,country=country)
        for i,kind,region in c.rows('hq_private','id','type','hq_region'):
            c.add('hq_private',hq=ids[i],hq_type=kind,hq_region=c.label(region))
    t=c.table('shipping_lane')
    if t:
        for ident,country,begin,end,cost,kind in zip(t['ident'],t['country'],t['begin_point'],t['end_point'],t['convoy_cost'],t['shipping_lane_type']):
            c.add('shipping_lane_history',shipping_lane=ident,country=country,begin_point=begin,end_point=end,convoy_cost=cost,lane_type=kind)
    t=c.table('strait')
    if t:
        ids=idents(t)
        columns=('first_access_status','first_access_permissions','second_access_status','second_access_permissions','first_last_access_change',
                 'second_last_access_change','first_last_toll_rate_change','second_last_toll_rate_change','first_toll_rate','second_toll_rate')
        for ident,kind,*values in zip(t['ident'],t['strait_definition'],*(t[column] for column in columns)):
            c.add('strait_history',strait=ident,strait_definition=c.label(kind),**dict(zip(columns,values)))
        for strait,first,second,kind in c.rows('strait_endpoint','strait','first_state','second_state','strait_type'):
            c.add('strait_endpoint',strait=ids[strait],first_state=c.ident('state',first),second_state=c.ident('state',second),strait_type=kind)
    t=c.table('technology')
    if t:
        ids=idents(t)
        for ident,country,research in zip(t['ident'],t['country'],t['research_technology']):
            c.add('country_research_history',country_research=ident,country=country,researching=c.label(research))
        for name,table in (('country_research_acquired','acquired'),('country_research_spreading','spreading')):
            for i,items in c.children('technology_'+table,'id','technology').items():
                for technology, in items:
                    c.add(name,country_research=ids[i],technology=c.label(technology))
        for i,items in c.children('technology_research_queue','id','technology').items():
            for position,(technology,) in enumerate(items):
                c.add('country_research_queued',country_research=ids[i],position=position,technology=c.label(technology))
        for i,items in c.children('technology_progress','id','technology','progress').items():
            for technology,progress in items:
                c.add('country_research_progress',country_research=ids[i],technology=c.label(technology),progress=progress)


@timed_often
def politics(c):
    t=c.table('interest_group')
    if t:
        ids=idents(t)
        for index,i in enumerate(t['id']):
            c.add('interest_group_history',interest_group=ids[i],country=t['country'][index],interest_group_type=c.label(t['interest_group_definition'][index]),
                  name_key=c.label(t['name'][index]),party=t['party'][index],leader=t['leader'][index],approval_state=t['approval_state'][index],
                  influence_type=t['influence_type'][index],in_government=flag(t['in_government'][index]),influence_type_reason=t['influence_type_reason'][index])
            c.add('interest_group_stats',interest_group=ids[i],approval=t['approval'][index],political_strength=t['political_strength'][index],
                  radicals_political_strength=t['radicals_political_strength'][index],loyalists_political_strength=t['loyalists_political_strength'][index],
                  clout=t['clout'][index])
        negotiation={group:(amenability,flag(negotiated)) for group,amenability,negotiated in
                     c.rows('interest_group_negotiation','interest_group','amenability','negotiated')}
        private=c.rows('interest_group_private','id','party_to_join','wants_to_leave_party','civil_war')
        if {i for i,*_ in private}!=set(negotiation):
            raise RuntimeError('Interest group private data and negotiation captures cover different groups')
        for i,joining,leaving,side in private:
            amenability,negotiated=negotiation[i]
            c.add('interest_group_private',interest_group=ids[i],civil_war_side=side,party_to_join=joining,wants_to_leave_party=flag(leaving),
                  amenability=amenability,negotiated=negotiated)
        for name,table in (('interest_group_ideology','ideologies'),('interest_group_character_ideology','character_ideologies')):
            for i,items in c.children('interest_group_'+table,'id','value').items():
                for ideology, in items:
                    c.add(name,interest_group=ids[i],ideology=c.label(ideology))
        enabled={(i,trait) for i,items in c.children('interest_group_enabled_traits','id','value').items() for trait, in items}
        for i,items in c.children('interest_group_traits','id','value').items():
            for trait, in items:
                c.add('interest_group_held_trait',interest_group=ids[i],interest_group_trait=c.label(trait),enabled=(i,trait) in enabled)
                enabled.discard((i,trait))
        if enabled:
            raise RuntimeError(f'Enabled interest group traits the groups do not hold: {sorted(enabled)[:3]}')
        for i,items in c.children('interest_group_influencing_movements','id','value').items():
            for movement, in items:
                c.add('interest_group_influencing_movement',interest_group=ids[i],political_movement=movement)
        for i,items in c.children('interest_group_movement_support','id','political_movement','clout',sparse=True).items():
            for _,movement,clout in items:
                c.add('interest_group_movement_support',interest_group=ids[i],political_movement=movement,clout=clout)
        for i,items in c.children('interest_group_pops','id','value').items():
            for pop, in items:
                c.add('interest_group_pop',interest_group=ids[i],pop=pop)
        for (group,n),(date,clout) in samples(c,'interest_group','clout_trend',ids).items():
            c.add('interest_group_clout_sample',interest_group=group,n=n,date=date,clout=clout)
        for (group,n),(date,radicals) in samples(c,'interest_group','radical_trend',ids).items():
            c.add('interest_group_radicals_sample',interest_group=group,n=n,date=date,radicals=int(radicals))
        for (group,n),(date,loyalists) in samples(c,'interest_group','loyalist_trend',ids).items():
            c.add('interest_group_loyalists_sample',interest_group=group,n=n,date=date,loyalists=int(loyalists))
    t=c.table('political_movement')
    if t:
        ids=idents(t)
        for ident,country,kind,ideology,radicalism,managed,war in zip(t['ident'],t['country'],t['movement_type'],t['ideology'],t['radicalism'],
                                                                      t['managed_status'],t['civil_war']):
            c.add('political_movement_history',political_movement=ident,country=country,political_movement_type=c.label(kind),ideology=c.label(ideology),
                  radicalism=radicalism,managed_status=None if managed==0 else managed,civil_war=war)
        for i,items in c.children('political_movement_characters','id','value').items():
            for character, in items:
                c.add('political_movement_character',political_movement=ids[i],character=character)
        for i,items in c.children('political_movement_character_ideologies','id','value').items():
            for ideology, in items:
                c.add('political_movement_character_ideology',political_movement=ids[i],ideology=c.label(ideology))
        for row in movement_modifiers(c.children('political_movement_timed_modifier','id','modifier','end_date'),ids,c.label):
            c.add('political_movement_timed_modifier',**row)
    t=c.table('law')
    if t:
        ids=idents(t)
        chances=dict(c.rows('law_chance','law','chance'))
        held={}
        for index,i in enumerate(t['id']):
            c.add('law_history',law=ids[i],country=t['country'][index],law_type=c.label(t['law'][index]),progress=t['progress'][index],phase=t['phase'][index],
                  checkpoint_or_stop_date=t['enactment_last_checkpoint_or_stop_date'][index],active=flag(t['active'][index]),imposer=t['imposer'][index])
            if t['country'][index]&SLOT==c.player and c.label(t['law'][index]) in chances:
                held[i]=chances[c.label(t['law'][index])]
        if len(held)!=len(chances):
            raise RuntimeError('Law chances do not each match one player law')
        private=c.rows('law_private','id','enactment_last_checkpoint_result','replace','enactment_start_date')
        if set(held)-{i for i,*_ in private}:
            raise RuntimeError('Law chances for laws without private data')
        for i,result,replacing,start in private:
            c.add('law_private',law=ids[i],checkpoint_result=result,replacing_law_type=c.label(replacing),enactment_start_date=start,chance=held.get(i))
        for i,items in c.children('law_amendments','id','value').items():
            for amendment, in items:
                c.add('law_amendment',law=ids[i],amendment=amendment)
    t=c.table('amendment')
    if t:
        for ident,law,kind,sponsor,timeout,date in zip(t['ident'],t['law'],t['amendment_type'],t['sponsor'],t['timeout'],t['timeout_date']):
            c.add('amendment_history',amendment=ident,law=law,amendment_type=c.label(kind),sponsor=sponsor,timeout=timeout,timeout_date=date)
    t=c.table('party')
    if t:
        ids=idents(t)
        for ident,country,kind,votes in zip(t['ident'],t['country'],t['party_definition'],t['votes']):
            c.add('party_history',party=ident,country=country,party_type=c.label(kind),votes=votes)
        for i,voters,leader in c.rows('party_private','id','num_voters','leader'):
            c.add('party_private',party=ids[i],num_voters=voters,leader=leader)
        for i,items in c.children('party_members','id','value').items():
            for group, in items:
                c.add('party_member',party=ids[i],interest_group=group)
    t=c.table('election')
    if t:
        ids=idents(t)
        for ident,country,upcoming,last,confidence,campaign in zip(t['ident'],t['country'],t['next_election'],t['last_election'],t['electoral_confidence'],
                                                                   t['campaign_period']):
            c.add('election_history',election=ident,country=country,next_election=upcoming,last_election=last,electoral_confidence=confidence,
                  campaign_period=flag(campaign))
        for i,items in c.children('election_vote','id','party','momentum','raw_votes','raw_num_voters','last_votes','last_num_voters','last_vote_date').items():
            for party,*values in items:
                c.add('election_vote',election=ids[i],party=party,**dict(zip(('momentum','raw_votes','raw_num_voters','last_votes','last_num_voters',
                                                                              'last_vote_date'),values)))
    t=c.table('institution')
    if t:
        ids=idents(t)
        for ident,country,kind,investment in zip(t['ident'],t['country'],t['institution'],t['investment']):
            c.add('institution_history',institution=ident,country=country,institution_type=c.label(kind),investment=investment)
        for i,target,growth in c.rows('institution_private','id','target','growth'):
            c.add('institution_private',institution=ids[i],target_investment=target,growth=growth)
    t=c.table('political_lobby')
    if t:
        ids=idents(t)
        for ident,country,target,kind,appeasement in zip(t['ident'],t['country'],t['target_country'],t['political_lobby_type'],t['appeasement']):
            c.add('political_lobby_history',political_lobby=ident,country=country,target_country=target,political_lobby_type=c.label(kind),
                  appeasement=appeasement)
        for i,items in c.children('political_lobby_members','id','value').items():
            for group, in items:
                c.add('political_lobby_member',political_lobby=ids[i],interest_group=group)
    t=c.table('civil_war')
    if t:
        ids=idents(t)
        for ident,origin,kind,progress,time,movement,rate in zip(t['ident'],t['origin_country'],t['type'],t['progress'],t['time'],t['political_movement'],
                                                                 t['conscription_rate']):
            c.add('civil_war_history',civil_war=ident,origin_country=origin,civil_war_type=kind,progress=progress,time=time,political_movement=movement,
                  conscription_rate=rate)
        for i,items in c.children('civil_war_interest_group','id','value').items():
            for group, in items:
                c.add('civil_war_interest_group',civil_war=ids[i],interest_group=group)
        for i,items in c.children('civil_war_seceded_state','id','state_region','incorporated').items():
            empty=[incorporated for region,incorporated in items if not region]
            if empty:
                LOG.warning('Civil war %s lists %d seceded entries without a state region',ids[i],len(empty))
            for region,incorporated in items:
                if region:
                    c.add('civil_war_seceded_state',civil_war=ids[i],state_region=c.label(region),incorporated=flag(incorporated))


CHARACTER_KEYS=('religion','first_name','last_name','ideology','order_type','rank')


@timed_often
def characters(c):
    t=c.table('character')
    if not t:
        return
    ids=idents(t)
    names={'first_name':'first_name_key','last_name':'last_name_key'}
    for index,i in enumerate(t['id']):
        row={names.get(name,name):c.label(t[name][index]) for name in CHARACTER_KEYS}
        c.add('character_history',character=ids[i],culture=t['culture'][index],birth_date=t['birth_date'][index],noble=flag(t['noble'][index]),
              historical=flag(t['historical'][index]),adult=flag(t['adult'][index]),country=t['country'][index],interest_group=t['interest_group'][index],
              prominence=t['prominence'][index],formation=t['formation'][index],travel_arrival_date=t['travel_arrival_date'][index],
              assigned_state=t['assigned_state'][index],**row)
    popularity=dict(c.rows('character_popularity','character','popularity'))
    has_formation=dict(c.rows('character_formation','character','has_formation'))
    private=c.rows('character_private','id','loyalty','recruitable')
    if set(popularity)!=set(has_formation):
        raise RuntimeError(f'Character popularity covers {sorted(popularity)[:8]} ({len(popularity)}), formation {sorted(has_formation)[:8]} ({len(has_formation)})')
    for i,loyalty,recruitable in private:
        c.add('character_private',character=ids[i],loyalty=loyalty,recruitable=flag(recruitable))
    for i,value in popularity.items():
        c.add('character_status',character=ids[i],popularity=value,has_formation=flag(has_formation[i]))
    for name,table,column in (('character_assigned_trait','traits','character_trait'),('character_assigned_role','character_roles','character_role')):
        for i,items in c.children('character_'+table,'id','value').items():
            for value, in items:
                c.add(name,character=ids[i],**{column:c.label(value)})
    counted=defaultdict(int)
    for i,items in c.children('character_timed_modifier','id','modifier').items():
        for modifier, in items:
            counted[ids[i],c.label(modifier)]+=1
    for (character,modifier),count in counted.items():
        c.add('character_timed_modifier',character=character,modifier=modifier,instances=count)


FORMATION_PRIVATE=('default_fleet','demobilizing','invading','embarked','docked','recalled')


@timed_often
def military(c):
    t=c.table('combat_unit')
    if t:
        for index,ident in enumerate(t['ident']):
            c.add('combat_unit_history',combat_unit=ident,country=t['country'][index],formation=t['formation'][index],building=t['building'][index],
                  battle=t['battle'][index],combat_unit_type=c.label(t['combat_unit_type'][index]),veterancy_level=c.label(t['current_veterancy_level'][index]),
                  manpower=t['current_manpower'][index],mobilization=t['mobilization'][index],experience=t['xp_towards_next_level'][index])
    t=c.table('casualties')
    if t:
        ids=idents(t)
        for ident,unit,building in zip(t['ident'],t['unit'],t['building']):
            c.add('casualties_history',casualties=ident,unit=unit,building=building)
        for i,items in c.children('casualties_event','id','battle').items():
            for position,(battle,) in enumerate(items):
                c.add('casualties_event',casualties=ids[i],position=position,battle=battle)
    t=c.table('formation')
    if t:
        ids=idents(t)
        names={c.label(code) for code in set(t['name'])}-{None}
        if names:
            raise RuntimeError(f'formation.name holds {sorted(names)[:3]}')
        position=c.children('formation_position','id','value')
        for index,i in enumerate(t['id']):
            xy=[value for value, in position.get(i,[])]
            if len(xy)!=2:
                raise RuntimeError(f'Formation {i} has {len(xy)} position values')
            c.add('formation_history',formation=ids[i],country=t['country'][index],formation_type=t['type'][index],name_key=c.label(t['localizable_name'][index]),
                  flag=t['flag'][index],color_red=t['color_red'][index],color_green=t['color_green'][index],color_blue=t['color_blue'][index],
                  supply_hub=t['supply_hub'][index],supply_priority=t['supply_priority'][index],attached_to_fleet=t['attached_to_fleet'][index],
                  dead=flag(t['dead'][index]))
            c.add('formation_status',formation=ids[i],province=t['province'][index],current_location=t['current_location_identity'][index],
                  target_location=t['target_location_identity'][index],naval_mission=t['naval_mission'][index],x=xy[0],y=xy[1],
                  organization=t['organization'][index],sea_presence=t['sea_presence'][index],supply=t['supply'][index],
                  delivered_supply=t['delivered_supply'][index],supply_ships=t['supply_ships'][index],mobilized=flag(t['is_mobilized'][index]),
                  raised_conscripts=flag(t['has_raised_conscripts'][index]))
        settings={f:values for f,*values in c.rows('formation_setting','formation',*FORMATION_PRIVATE,'hit_points_percent','retrofittable','retrofitting')}
        deployable={f for f, in c.rows('formation_deployable','formation')}
        display=dict(c.rows('formation_name','formation','name'))
        private={i:values for i,*values in c.rows('formation_private','id','home_hq','strategic_objective','travel_progress_path_distance')}
        dead=dict(zip(t['id'],t['dead']))
        live={i for i in private if not flag(dead[i])}
        if set(settings)!=set(display) or deployable-set(settings):
            raise RuntimeError(f'Formation GUI captures cover different formations: settings {sorted(settings)[:5]}, names {sorted(display)[:5]}, '
                               f'deployable {sorted(deployable)[:5]}')
        if set(settings)!=live:
            raise RuntimeError(f'Formation GUI captures cover {sorted(set(settings)-live)[:5]} beyond the live player formations and miss {sorted(live-set(settings))[:5]}')
        for i,(home,objective,distance) in private.items():
            c.add('formation_private',formation=ids[i],home_hq=home,strategic_objective=objective,travel_distance=distance)
        for i,values in settings.items():
            c.add('formation_report',formation=ids[i],**{name:flag(value) for name,value in zip(FORMATION_PRIVATE,values[:6])},hit_points_percent=values[6],
                  deployable=i in deployable,display_name=display[i],retrofittable=int(values[7]),retrofitting=flag(values[8]))
        for name,table,column in (('formation_mobilization_option','active_mobilization_options','mobilization_option'),
                                  ('formation_upgrade_unit_type','regular_unit_types_to_upgrade','combat_unit_type')):
            for i,items in c.children('formation_'+table,'id','value').items():
                for value, in items:
                    c.add(name,formation=ids[i],**{column:c.label(value)})
        for i,items in c.children('formation_unit_type_selected','id','combat_unit_group','combat_unit_type',sparse=True).items():
            for _,group,kind in items:
                c.add('formation_selected_unit_type',formation=ids[i],combat_unit_group=c.label(group),combat_unit_type=c.label(kind))
        for formation,position,name,selected in c.rows('formation_borrow_setting','formation','ord','name','selected'):
            c.add('formation_borrow_setting',formation=c.ident('formation',formation),name=name,position=position,selected=flag(selected))
    t=c.table('ship')
    if t:
        ids=idents(t)
        for ident,fleet,version,hp,xp in zip(t['ident'],t['fleet'],t['version'],t['hit_points'],t['veterancy_experience']):
            c.add('ship_history',ship=ident,fleet=fleet,version=version,hit_points=hp,experience=xp)
        for i,items in c.children('ship_crew','id','state','crew').items():
            for position,(state,crew) in enumerate(items):
                c.add('ship_crew',ship=ids[i],position=position,state=state,crew=crew)
    t=c.table('ship_construction')
    if t:
        for ident,queue,position,kind,version,left in zip(t['ident'],t['queue'],t['index'],t['ship_construction_type'],t['version'],t['construction_left']):
            c.add('ship_construction_history',ship_construction=ident,queue=queue,list_index=position,ship_type=c.label(kind),version=version,construction_left=left)
    t=c.table('ship_queue')
    if t:
        c.ship_queue_paused={country&SLOT:flag(paused) for country,paused in zip(t['country'],t['paused'])}
        for ident,country in zip(t['ident'],t['country']):
            c.add('ship_queue_history',ship_queue=ident,country=country)
    t=c.table('ship_templates')
    templates=idents(t) if t else {}
    if t:
        ids=templates
        for ident,country,kind,number,year in zip(t['ident'],t['country'],t['ship_templates_type'],t['ordinal_number'],t['year']):
            c.add('ship_template_history',ship_template=ident,country=country,ship_type=c.label(kind),ordinal_number=number,year=year)
        for i,flags,base in c.rows('ship_templates_private','id','flags','base'):
            c.add('ship_template_private',ship_template=ids[i],flags=flags,base=flag(base))
        for i,items in c.children('ship_templates_fleets','id','value').items():
            for fleet, in items:
                c.add('ship_template_fleet',ship_template=ids[i],fleet=fleet)
    t=c.table('ship_template_version')
    if t:
        vids=idents(t)
        for ident,kind in zip(t['ident'],t['type']):
            c.add('ship_template_version_history',ship_template_version=ident,ship_type=c.label(kind))
        for version,items in c.children('ship_template_modification','id','type').items():
            for position,(kind,) in enumerate(items):
                c.add('ship_template_version_modification',ship_template_version=vids[version],position=position,ship_modification=c.label(kind))
    for template,items in c.children('ship_template_version_ids','id','value').items():
        for position,(version,) in enumerate(items):
            c.add('ship_template_version_list',ship_template=templates[template],position=position,ship_template_version=version)
    t=c.table('naval_mission')
    if t:
        for ident,kind in zip(t['ident'],t['naval_mission_type']):
            c.add('naval_mission_history',naval_mission=ident,naval_mission_type=c.label(kind))


BATTLE_SIDES=(('attacker',{'commander':'battle_data_attacker_commander','country':'battle_data_attacker_country','formation':'battle_data_attacker_formation',
                           'order_type':'attacker_order_type','condition':'attacker_battle_condition','start_battalions':'attacker_start_battalions',
                           'end_battalions':'attacker_ending_battalions','start_manpower':'attacker_starting_manpower','end_manpower':'attacker_ending_manpower',
                           'start_morale':'attacker_starting_morale','end_morale':'attacker_ending_morale'}),
              ('defender',{'commander':'battle_data_defender_commander','country':'battle_data_defender_country','formation':'battle_data_defender_formation',
                           'order_type':'defender_order_type','condition':'defender_battle_condition','start_battalions':'defender_start_battalions',
                           'end_battalions':'defender_ending_battalions','start_manpower':'defender_starting_manpower','end_manpower':'defender_ending_manpower',
                           'start_morale':'defender_starting_morale','end_morale':'defender_ending_morale'}))


@timed_often
def wars(c):
    t=c.table('war')
    if t:
        ids=idents(t)
        for ident,play,days,peace,proposer,proposal,dead in zip(t['ident'],t['diplomatic_play'],t['days_since_exhaustion'],t['peace_date'],t['peace_proposer'],
                                                                t['peace_proposal_date'],t['dead']):
            c.add('war_history',war=ident,diplomatic_play=play,days_since_exhaustion=days,peace_date=peace,peace_proposer=proposer,peace_proposal_date=proposal,
                  dead=flag(dead))
        for i,items in c.children('war_participant','id','diplomatic_play','country','war_support').items():
            for play,country,support in items:
                c.add('war_participant',war=ids[i],country=country,diplomatic_play=play,war_support=support)
    t=c.table('war_goal')
    if t:
        for index,ident in enumerate(t['ident']):
            c.add('war_goal_history',war_goal=ident,holder=t['holder'][index],creator=t['creator'][index],diplomatic_play=t['diplomatic_play'][index],
                  war_goal_type=c.label(t['war_goal_type'][index]),target_state=t['target_state'][index],target_country=t['target_country'][index],
                  target_other=t['target_other'][index],demand_type=t['demand_type'][index],status=t['status'][index],pressed=t['pressed'][index])
    t=c.table('front')
    if t:
        ids=idents(t)
        for ident,x,y in zip(t['ident'],t['x'],t['y']):
            c.add('front_history',front=ident,x=x,y=y)
        for front,advantage in c.rows('front_advantage','front','advantage'):
            c.add('front_advantage',front=c.ident('front',front),advantage=advantage)
        for i,items in c.children('front_sides','id','value').items():
            for side, in items:
                c.add('front_listed_side',front=ids[i],front_side=side)
    for front,invader,invaded,state,ended in sorted(set(c.rows('invasion','front','invader','invaded','state','ended'))):
        c.add('invasion',front=c.ident('front',front),invader=c.ident('country',invader),invaded=c.ident('country',invaded),state=c.ident('state',state),ended=flag(ended))
    t=c.table('front_side')
    if t:
        for ident,front,war,side in zip(t['ident'],t['front'],t['war'],t['play_side']):
            c.add('front_side_history',front_side=ident,front=front,war=war,play_side=side)
    t=c.table('occupation')
    if t:
        ids=idents(t)
        for ident,state,controller in zip(t['ident'],t['state'],t['controller']):
            c.add('occupation_history',occupation=ident,state=state,controller=controller)
        for i,items in c.children('occupation_country','id','country','fraction').items():
            for country,fraction in items:
                c.add('occupation_country',occupation=ids[i],country=country,fraction=fraction)
    t=c.table('battle')
    if t:
        ids=idents(t)
        fighting={i:(n,date) for i,_,_,date,n in c.rows('battle_attacker_still_fighting_trend_channel','id','ord','channel','date','index')}
        counts=defaultdict(int)
        for i,_ in c.rows('battle_attacker_still_fighting_trend','id','channel'):
            counts[i]+=1
        if any(counts.get(i,0)!=n for i,(n,_) in fighting.items()) or set(counts)-set(fighting):
            raise RuntimeError('Still-fighting sample counts differ from their channel index')
        for index,i in enumerate(t['id']):
            n,date=fighting.get(i,(None,None))
            c.add('battle_history',battle=ids[i],war=t['war'][index],front=t['front'][index],province=t['province'][index],battle_type=t['type'][index],
                  status=t['status'][index],invasion=t['invasion'][index],name_key=c.label(t['name_key'][index]),start_date=t['start_date'][index],
                  end_date=t['end_date'][index],victory_score=t['victory_script_value_data_result'][index],
                  occupation_score=t['occupation_script_value_data_result'][index],still_fighting_samples=n,still_fighting_date=date)
            for side,columns in BATTLE_SIDES:
                row={name:t[column][index] for name,column in columns.items()}
                row['order_type']=c.label(row['order_type'])
                row['condition']=c.label(row['condition'])
                c.add('battle_side',battle=ids[i],side=side,**row)
        for i,items in c.children('battle_occupation','id','state','fraction','occupation').items():
            for state,fraction,occupation in items:
                c.add('battle_occupation',battle=ids[i],state=state,fraction=fraction,occupation_progress=occupation)
        for (battle,n),(date,attacker) in samples(c,'battle','attacker_manpower_trend',ids).items():
            c.add('battle_attacker_manpower_sample',battle=battle,n=n,date=date,attacker_manpower=int(attacker))
        for (battle,n),(date,defender) in samples(c,'battle','defender_manpower_trend',ids).items():
            c.add('battle_defender_manpower_sample',battle=battle,n=n,date=date,defender_manpower=int(defender))


@timed_often
def ai(c):
    t=c.table('ai')
    if not t:
        return
    ids=idents(t)
    if any(a!=b for a,b in zip(t['country'],t['spending_country'])):
        raise RuntimeError('ai.spending_country differs from ai.country')
    countries=dict(zip(t['id'],t['country']))
    for index,i in enumerate(t['id']):
        c.add('country_ai_history',country_ai=ids[i],country=t['country'][index])
        for position,column in enumerate(('strategy_0','strategy_1','strategy_2')):
            if t[column][index]:
                c.add('country_ai_strategy',country_ai=ids[i],position=position,ai_strategy=c.label(t[column][index]))
    for i,items in c.children('ai_strategic_region_stance','id','strategic_region','stance',sparse=True).items():
        for _,region,stance in items:
            c.add('country_ai_region_stance',country_ai=ids[i],strategic_region=c.label(region),stance=c.label(stance))
    for i,_,country,target,neighbour,relevance,attitude in c.rows('ai_country_goal','id','ord','country','target_country','neighbour','diplomatic_relevance',
                                                                  'attitude'):
        if country!=countries[i]:
            raise RuntimeError('ai_country_goal.country differs from its AI country')
        c.add('country_ai_goal',country_ai=ids[i],target_country=target,neighbour=flag(neighbour),diplomatic_relevance=flag(relevance),attitude=attitude)
    reasons=defaultdict(list)
    for i,target,position,reason,attitude,country,score in c.rows('ai_country_goal_antagonize_reason','id','target','ord','reason','attitude','country','score'):
        if attitude!=1 or country!=-1:
            raise RuntimeError(f'Antagonize reason with attitude {attitude} and country {country}')
        reasons[i,target].append((position,reason,score))
    for (i,target),items in reasons.items():
        items.sort()
        if [p for p,_,_ in items]!=list(range(len(items))):
            raise RuntimeError(f'Antagonize reasons of ({i}, {target}) are not dense')
        for position,reason,score in items:
            c.add('country_ai_antagonize_reason',country_ai=ids[i],target_country=target,position=position,reason=c.label(reason),score=score)


@timed_often
def journal(c):
    t=c.table('journal_entry')
    if t:
        ids=idents(t)
        if set(t['scope_root_definition'])-{0}:
            raise RuntimeError('journal_entry.scope_root_definition is not always 0')
        progress={entry:(p,g,pc) for entry,p,g,pc in c.rows('journal_progress','journal','progress','goal','percent')}
        if set(progress)-set(t['id']):
            raise RuntimeError(f'Journal progress names entries memory does not hold: {sorted(set(progress)-set(t["id"]))[:5]}')
        for index,i in enumerate(t['id']):
            p,g,pc=progress.get(i,(None,None,None))
            c.add('journal_entry_history',journal_entry=ids[i],country=t['country'][index],journal_entry_type=c.label(t['journal_entry_type'][index]),
                  active=flag(t['active'][index]),goal_value=t['goal_value'][index],baseline_value=t['baseline_value'][index],progress=p,goal=g,percent=pc)
        for i,items in c.children('journal_entry_target','id','name','scope_type','identity','definition').items():
            for name,scope,target,definition in items:
                if definition!=0:
                    raise RuntimeError('journal_entry_target.definition is not always 0')
                c.add('journal_entry_target',journal_entry=ids[i],name_key=c.label(name),scope_type=scope,scope_target=target)
        for i,items in c.children('journal_entry_progress_bar','id','progress_bar','value').items():
            for bar,value in items:
                c.add('journal_entry_progress_bar',journal_entry=ids[i],scripted_progress_bar=c.label(bar),value=value)
        for i,items in c.children('journal_entry_timed_modifier','id','modifier').items():
            for modifier, in items:
                c.add('journal_entry_timed_modifier',journal_entry=ids[i],modifier=c.label(modifier))
        for i,items in c.children('journal_entry_involved_countries','id','value').items():
            for country, in items:
                c.add('journal_entry_involved_country',journal_entry=ids[i],country=country)
    t=c.table('event')
    if t:
        ids=idents(t)
        if set(t['scope_root_definition'])-{0}:
            raise RuntimeError('event.scope_root_definition is not always 0')
        labels=dict(zip(t['id'],t['event_event']))
        for ident,kind,origin,status in zip(t['ident'],t['event_event'],t['origin_country'],t['status']):
            c.add('event_history',event=ident,event_type=c.label(kind),origin_country=origin,status=status)
        for i,items in c.children('event_target','id','name','scope_type','identity','definition').items():
            for name,scope,target,definition in items:
                if definition!=0:
                    raise RuntimeError('event_target.definition is not always 0')
                c.add('event_target',event=ids[i],name_key=c.label(name),scope_type=scope,scope_target=target)
        options=defaultdict(list)
        for i,position,enabled,visible,default,visible_position,text,description,name in c.rows(
                'event_option_state','id','ord','enabled','visible','default_option','visible_ord','text','description','event'):
            if visible!=int(visible_position>=0):
                raise RuntimeError(f'event_option_state.visible disagrees with visible_ord for event {i}')
            if name!=c.label(labels[i]):
                raise RuntimeError(f'Event options of {i} name another event')
            options[i].append((position,enabled,default,visible_position,text,description))
        for i,items in options.items():
            items.sort()
            if [p for p,*_ in items]!=list(range(len(items))):
                raise RuntimeError(f'Event options of {i} are not dense')
            for position,enabled,default,visible_position,text,description in items:
                c.add('event_option',event=ids[i],option=position,enabled=flag(enabled),default_option=flag(default),visible_position=visible_position,
                      text=text,description=description)


BUILDERS=(countries,player,diplomacy,states,pops,cultures,buildings,markets,companies,politics,characters,military,wars,ai,journal,metrics)


@timed_often
def ordered(table,rows):
    names=[*(([table.owner] if table.owner else [])+[column.name for column in table.keys]),*(['n','date'] if table.kind=='sample' else []),
           *[column.name for column in table.columns]]
    known=set(names)
    picks={}
    out=[]
    for row in rows:
        shape=tuple(row)
        pick=picks.get(shape)
        if pick is None:
            unknown=set(shape)-known
            if unknown:
                raise RuntimeError(f'{table.name} rows carry unknown columns {sorted(unknown)}')
            pick=picks[shape]=picker(names,shape)
        out.append(pick(row))
    return out


@timed_often
def picker(names,shape):
    if len(names)>1 and len(shape)==len(names):
        return itemgetter(*names)
    return lambda row:tuple(row.get(name) for name in names)


@timed
def build(capture,orders,colors):
    context=Context(capture,orders)
    context.construction_paused=None
    context.ship_queue_paused={}
    for builder in BUILDERS:
        progress(f'build {builder.__name__}')
        builder(context)
    provinces(context,colors)
    windows=capture.windows
    for name in sorted(set(windows)):
        context.add('ui_open_window',ui_window=name)
    fields_match(context)
    unread=sorted(name for name,columns in capture.tables.items() if name not in context.tables.read and any(columns.values()))
    if unread:
        raise RuntimeError(f'Captured tables with rows that no table stores: {unread}')
    unknown=set(context.out)-set(TABLE)
    if unknown:
        raise RuntimeError(f'Builders produced rows for unknown tables {sorted(unknown)}')
    return {table.name:ordered(table,context.out.get(table.name,[])) for table in TABLES}


@timed_often
def fields_match(c):
    construction=[row for row in c.out['country_construction_report'] if row['country']&SLOT==c.player]
    if c.construction_paused is not None and construction and flag(c.construction_paused)!=construction[0]['is_construction_paused']:
        raise RuntimeError('country.construction_paused differs from IsConstructionPaused for the player')
    if c.player in c.ship_queue_paused and construction and c.ship_queue_paused[c.player]!=construction[0]['is_ship_construction_paused']:
        raise RuntimeError('ship_queue.paused differs from IsShipConstructionPaused for the player')
