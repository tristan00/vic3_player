import argparse
import logging
import re
import struct
from collections import Counter, defaultdict
from math import comb
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from interface.actions.execute import Executor
from interface.common import slot
from interface.runner.session import GameInterface
from interface.script import blocks, body, clean, keys, read, scalar, script_files
from interface.timing import evidence
from . import GAME, timed, timed_often
from .write import HARBOR, HUBS

PROFILE='miniworld_coherence'
WORK=('salaried','subsisting','unemployed','laborer','government','military','slave')
STRATA=('lower','middle','upper')
IGS=('ig_landowners','ig_industrialists','ig_armed_forces','ig_devout','ig_intelligentsia','ig_petty_bourgeoisie','ig_rural_folk','ig_trade_unions')
TABLES=('country','state','ai','building','interest_group','institution','combat_unit','relation','pact','country_rankings','technology','pop','formation','ship',
        'character','party','political_movement','election','hq','journal_entry','interest','political_lobby','company','market')
FORCES={'building_barrack':'barracks','building_conscription_center':'conscription','building_construction_sector':'construction_sector',
        'building_naval_administration':'admiralty'}
TRAITS={'trait_harbor':('harbor',),'trait_river':('river',),'trait_disease':('malaria',),'trait_soil':('soil','terroir','pampas','plain'),'trait_forest':('forest','rainforest')}
DOMAINS={'economy':('treasury','debt','credit','investment','balance','tax','wage','productivity','price','shortage','market','trade_value','construction','building_budget','state_budget','innovation'),
         'government':('bureaucracy','authority','administration','institution','government_workforce','government_wage'),
         'politics':('clout','ruling','top_clout','radical','loyalist','parties','party','movement','election','participant','voter','ig_','government_strength','ruler','heir','characters'),
         'society':('population','wealth','primary','strata','workforce','literacy','sol','incorporated','migration','emigration','immigration','devastation','religion','cultures','pop_'),
         'land':('arable','trait','resource'),
         'military':('battalion','manpower','artillery','cavalry','armies','fleets','ships','generals','admirals','hqs','military','barracks','conscription','admiralty'),
         'structure':('building','staffing','infrastructure','trade_capacity','trade_center','companies','company'),
         'diplomacy':('relations','pacts','prestige','infamy','interests','lobbies'),
         'content':('journal','technologies')}
SEA=3000
INTERMEDIATE=1<<28
SPREAD=8
NEAREST=3
BAND=1.25
KS=0.2
KS_SCALE=1.63
Z=1.96
REQUIRED=('city','farm','mine','wood')
HUB_NAMES={index:hub for hub,index in HUBS.items()}
CONTINENTS=('europe','americas','africa','asia')
CLASSES={'old_world':('land','is_in_geographic_region = geographic_region_old_world'),'new_world':('land','is_in_geographic_region = geographic_region_new_world'),
         'arid':('land','is_arid_region = yes'),'ring_of_fire':('land','is_in_geographic_region = geographic_region_ring_of_fire'),
         'alpide_belt':('land','is_in_geographic_region = geographic_region_alpide_belt'),'great_rift_valley':('land','is_in_geographic_region = geographic_region_great_rift_valley'),
         'polar_seas':('sea','is_in_geographic_region = geographic_region_polar_seas'),'tropical_seas':('sea','is_in_geographic_region = geographic_region_tropical_seas'),
         **{c:('land',f'is_in_geographic_region = geographic_region_{c}') for c in CONTINENTS}}
TOKEN=re.compile(r'"(?:\\.|[^"\\])*"|[{}]|[<>!?]?=|[<>]|[^\s{}=<>!?]+')
OPERATORS=('=','?=','>=','<=','>','<','!=')
BRACE=re.compile(r'[{}]')
SPLINE={0x0c:struct.Struct('<i'),0x14:struct.Struct('<I'),0x0d:struct.Struct('<f'),0x0e:struct.Struct('<B'),0x167:struct.Struct('<i'),0x29c:struct.Struct('<q')}


@timed_often
def ratio(a,b):
    return float(a)/float(b) if b else float('nan')


@timed
def costs():
    return {key:float(scalar(block,'cost')) for key,block in read(GAME,'common/goods') if scalar(block,'cost')}


@timed
def regions(mods):
    out={}
    for key,block in read(GAME,'map_data/state_regions',mods):
        traits=re.findall(r'state_trait_\w+',re.search(r'traits\s*=\s*\{([^}]*)\}',block)[1]) if re.search(r'traits\s*=\s*\{',block) else []
        capped=re.search(r'capped_resources\s*=\s*\{([^}]*)\}',block)
        resources=[inner for name,inner in blocks(body(block)) if name=='resource']
        out[key]={'traits':traits,'capped':sum(int(n) for n in re.findall(r'=\s*(\d+)',capped[1])) if capped else 0,
                  'resources':len(resources),'resource_amount':sum(int(scalar(r,'undiscovered_amount') or 0)+int(scalar(r,'discovered_amount') or 0) for r in resources)}
    return out


@timed
def build():
    return (GAME.parent/'caligula_rev.txt').read_text(encoding='utf-8').strip()


@timed
def countries(tables,tag_of,kind):
    country,_=tables['country']
    rows={}
    for index,ident in enumerate(country['id']):
        s=slot(ident)
        get=lambda f:float(country[f][index])
        pop=sum(get(f'pop_statistics_population_{x}_strata') for x in STRATA)
        if pop<=0: continue
        row={'type':kind[s],'population':pop,'treasury_per_capita':ratio(get('budget_money'),pop),'debt_per_capita':ratio(get('budget_principal'),pop),
             'credit_per_capita':ratio(get('budget_credit'),pop),'investment_pool_per_capita':ratio(get('budget_investment_pool'),pop),
             'balance_trend_per_capita':ratio(get('budget_balance_trend_current'),pop),
             'debt_to_credit':ratio(get('budget_principal'),get('budget_credit')),'tax_level':get('tax_level'),'base_wage':get('budget_base_wage'),
             'productivity':get('budget_average_productivity'),'infamy':get('infamy'),'wealth_per_capita':ratio(get('pop_statistics_total_wealth'),pop),
             'primary_share':ratio(get('pop_statistics_primary_cultures_population'),pop),
             'primary_sol':ratio(get('pop_statistics_primary_cultures_standard_of_living'),get('pop_statistics_primary_cultures_population')),
             'radical_share':ratio(get('pop_statistics_population_radicals'),pop),'loyalist_share':ratio(get('pop_statistics_population_loyalists'),pop),
             'participant_share':ratio(get('pop_statistics_population_political_participants'),pop),'voter_share':ratio(get('pop_statistics_population_eligible_voters'),pop),
             'building_budget_per_capita':ratio(get('budget_country_building_budget_income')-get('budget_country_building_budget_expense'),pop),
             'military_wage_level':get('military_wage_level'),'government_wage_level':get('government_wage_level')}
        for x in STRATA: row[f'{x}_strata_share']=ratio(get(f'pop_statistics_population_{x}_strata'),pop)
        workforce=sum(get(f'pop_statistics_population_{x}_workforce') for x in WORK)
        for x in WORK: row[f'{x}_workforce_share']=ratio(get(f'pop_statistics_population_{x}_workforce'),workforce)
        rows[tag_of[s]]=row
    ai,_=tables['ai']
    for index,c in enumerate(ai['country']):
        if tag_of.get(slot(c)) not in rows: continue
        get=lambda f:float(ai[f][index])
        r=rows[tag_of[slot(c)]]
        r.update({'bureaucracy_ratio':ratio(get('spending_bureaucracy_income'),get('spending_bureaucracy_expenses')),'bureaucracy_income':get('spending_bureaucracy_income'),
                  'authority_balance':get('spending_authority_balance'),'construction_per_m':ratio(get('spending_construction_output'),r['population']/1e6),
                  'innovation':get('spending_innovation'),'innovation_share':ratio(get('spending_innovation'),get('spending_max_innovation'))})
    return rows


@timed
def society(tables,rows,tag_of):
    country,vectors=tables['country']
    owner={slot(i):tag_of.get(slot(i)) for i in country['id']}
    professions=keys(GAME,'common/pop_types')
    found=defaultdict(lambda:defaultdict(list))
    for vector,column in (('country_population_by_religion','total'),('country_population_by_culture','value'),('country_population_by_profession','value')):
        for i,v in zip(vectors[vector]['id'],vectors[vector][column]): found[owner.get(slot(i))][vector].append(float(v))
    for t,r in rows.items():
        religions=np.array(found[t]['country_population_by_religion']);cultures=np.array(found[t]['country_population_by_culture'])
        jobs=found[t]['country_population_by_profession']
        r.update({'top_religion_share':ratio(religions.max(initial=0),religions.sum()),'religions':int((religions>.01*religions.sum()).sum()) if religions.sum() else 0,
                  'cultures':int((cultures>.01*cultures.sum()).sum()) if cultures.sum() else 0})
        for name,value in zip(professions,jobs): r[f'pop_{name}']=ratio(value,sum(jobs))


@timed
def states(tables,rows,tag_of,name,land,prices):
    state,children=tables['state']
    owner={slot(i):tag_of.get(slot(c)) for i,c in zip(state['id'],state['country'])}
    traded=Counter()
    for i,g,v in zip(children['state_trade']['id'],children['state_trade']['goods'],children['state_trade']['value']): traded[slot(i)]+=abs(float(v))*prices.get(name(g),0.)
    pops,_=tables['pop']
    literate=Counter()
    for location,count in zip(pops['location'],pops['num_literate']): literate[slot(location)]+=float(count)
    out={}
    for index,ident in enumerate(state['id']):
        t=owner[slot(ident)]
        if t not in rows: continue
        get=lambda f:float(state[f][index])
        pop=sum(get(f'pop_statistics_population_{x}_strata') for x in STRATA)
        if pop<=0: continue
        workforce=sum(get(f'pop_statistics_population_{x}_workforce') for x in WORK)
        region=land[name(state['state_region'][index])]
        row={'type':rows[t]['type'],'country':t,'state_region':name(state['state_region'][index]),'population':pop,'arable_land':get('arable_land'),'incorporated':get('incorporation'),
             'infrastructure_use':ratio(get('infrastructure_usage'),get('infrastructure')),'trade_capacity_use':ratio(get('trade_capacity_usage'),get('trade_capacity')),
             'wage':get('pop_statistics_wage'),'wealth_per_capita':ratio(get('pop_statistics_total_wealth'),pop),'primary_share':ratio(get('pop_statistics_primary_cultures_population'),pop),
             'primary_sol':ratio(get('pop_statistics_primary_cultures_standard_of_living'),get('pop_statistics_primary_cultures_population')),
             'bureaucracy_cost_per_k':ratio(get('base_pop_bureaucracy_cost'),pop/1e3),'devastation':get('devastation'),
             'state_budget_per_capita':ratio(get('state_building_budget_income')-get('state_building_budget_expense'),pop),'literacy':ratio(literate[slot(ident)],pop),
             'emigration_per_k':ratio(get('pop_migration_statistics_weekly_emigration'),pop/1e3),'immigration_per_k':ratio(get('pop_migration_statistics_weekly_immigration'),pop/1e3),
             'building_levels_per_k':0.,'traits':len(region['traits']),'capped_resources':region['capped'],'discoverable_resources':region['resources'],
             'discoverable_amount':region['resource_amount'],'literate':literate[slot(ident)],'trade_capacity_per_k':ratio(get('trade_capacity'),pop/1e3),
             'trade_value_per_capita':ratio(traded[slot(ident)],pop)}
        for key,words in TRAITS.items(): row[key]=int(any(w in trait for trait in region['traits'] for w in words))
        for x in STRATA: row[f'{x}_strata_share']=ratio(get(f'pop_statistics_population_{x}_strata'),pop)
        for x in WORK: row[f'{x}_workforce_share']=ratio(get(f'pop_statistics_population_{x}_workforce'),workforce)
        out[slot(ident)]=row
    for t,r in rows.items():
        mine=[row for row in out.values() if row['country']==t]
        r.update({'literacy':ratio(sum(row['literate'] for row in mine),r['population']),'traits_per_state':float(np.mean([row['traits'] for row in mine])) if mine else float('nan'),
                  'arable_per_m':ratio(sum(row['arable_land'] for row in mine),r['population']/1e6),
                  'trade_value_per_capita':ratio(sum(row['trade_value_per_capita']*row['population'] for row in mine),r['population']),
                  'trade_capacity_per_m':ratio(sum(row['trade_capacity_per_k']*row['population']/1e3 for row in mine),r['population']/1e6)})
    return out


@timed
def structure(tables,rows,states_,tag_of,name):
    building,_=tables['building']
    levels=Counter();staffed=defaultdict(list);kinds=defaultdict(set);profit=Counter();admin=Counter()
    trade=defaultdict(Counter);forces=defaultdict(Counter)
    for index,where in enumerate(building['state']):
        row=states_.get(slot(where))
        if row is None: continue
        t=row['country']
        n=float(building['levels'][index])
        kind=name(building['building'][index])
        workers=float(building['staffing'][index])
        levels[t]+=n;staffed[t].append(ratio(workers,n));kinds[t].add(kind);profit[t]+=float(building['profit_after_reserves'][index])
        row['building_levels_per_k']+=n/(row['population']/1e3)
        if kind=='building_government_administration': admin[t]+=n
        if kind in FORCES: forces[t][FORCES[kind]]+=n
        if kind=='building_trade_center':
            trade[t]['levels']+=n
            trade[t]['staffed']+=workers
            trade[t]['shortage']+=n*float(building['input_goods_shortage'][index])
            trade[t]['centers']+=1
            trade[t]['inactive']+=int(workers>0 and row['trade_capacity_per_k']==0)
    for t,r in rows.items():
        r.update({'building_levels_per_m':ratio(levels[t],r['population']/1e6),'building_types':len(kinds[t]),'mean_staffing':float(np.mean(staffed[t])) if staffed[t] else float('nan'),
                  'building_profit_per_capita':ratio(profit[t],r['population']),'administration_levels_per_m':ratio(admin[t],r['population']/1e6),
                  'trade_center_levels_per_m':ratio(trade[t]['levels'],r['population']/1e6),'trade_center_staffing':ratio(trade[t]['staffed'],trade[t]['levels']),
                  'trade_center_shortage':ratio(trade[t]['shortage'],trade[t]['levels']),'inactive_trade_center_share':ratio(trade[t]['inactive'],trade[t]['centers']),
                  **{f'{force}_levels_per_m':ratio(forces[t][force],r['population']/1e6) for force in FORCES.values()}})
    company,_=tables['company']
    prosperity=defaultdict(list)
    for c,p in zip(company['country'],company['prosperity']): prosperity[tag_of.get(slot(c))].append(float(p))
    institution,_=tables['institution']
    invested=Counter()
    for c,v in zip(institution['country'],institution['investment']): invested[tag_of.get(slot(c))]+=float(v)
    technology,acquired=tables['technology']
    holder={slot(i):tag_of.get(slot(c)) for i,c in zip(technology['id'],technology['country'])}
    techs=Counter(holder.get(slot(i)) for i in acquired['technology_acquired']['id'])
    journal=Counter(tag_of.get(slot(c)) for c,a in zip(tables['journal_entry'][0]['country'],tables['journal_entry'][0]['active']) if int(a))
    for t,r in rows.items():
        r.update({'companies':len(prosperity[t]),'company_prosperity':float(np.mean(prosperity[t])) if prosperity[t] else float('nan'),
                  'institution_investment':invested[t],'technologies':techs[t],'journal_entries':journal[t]})


@timed
def markets(tables,rows,tag_of,name,prices):
    market,goods=tables['market']
    owner={slot(i):tag_of.get(slot(o)) for i,o in zip(market['id'],market['owner'])}
    trade=goods['market_goods']
    deviation=defaultdict(list);short=defaultdict(list)
    for m,g,sell,buy,price in zip(trade['id'],trade['goods'],trade['sell_orders'],trade['buy_orders'],trade['price']):
        key=name(g)
        t=owner.get(slot(m))
        if t not in rows or key not in prices or (sell<=0 and buy<=0): continue
        deviation[t].append(abs(np.log(max(float(price),1e-6)/prices[key])))
        short[t].append(float(buy)>float(sell))
    country,_=tables['country']
    member={tag_of[slot(i)]:slot(m) for i,m in zip(country['id'],country['market'])}
    sharing=Counter(m for t,m in member.items() if t in rows)
    for t,r in rows.items():
        r.update({'price_deviation':float(np.mean(deviation[t])) if deviation[t] else float('nan'),'shortage_share':float(np.mean(short[t])) if short[t] else float('nan'),
                  'own_market':int(owner.get(member[t])==t),'market_countries':sharing[member[t]]})


@timed
def politics(tables,rows,tag_of,name):
    ig,_=tables['interest_group']
    groups=defaultdict(list)
    for c,d,cl,g,p,rad,loy,a in zip(ig['country'],ig['interest_group_definition'],ig['clout'],ig['in_government'],ig['political_strength'],
                                    ig['radicals_political_strength'],ig['loyalists_political_strength'],ig['approval']):
        if tag_of.get(slot(c)) in rows: groups[tag_of[slot(c)]].append((name(d),float(cl),int(g),float(p),float(rad),float(loy),float(a)))
    party,_=tables['party']
    parties=defaultdict(list)
    for c,v in zip(party['country'],party['votes']):
        if tag_of.get(slot(c)) in rows: parties[tag_of[slot(c)]].append(float(v))
    movement,_=tables['political_movement']
    movements=defaultdict(list)
    for c,x in zip(movement['country'],movement['radicalism']):
        if tag_of.get(slot(c)) in rows: movements[tag_of[slot(c)]].append(float(x))
    elections={tag_of.get(slot(c)) for c in tables['election'][0]['country']}
    people=Counter(tag_of.get(slot(c)) for c in tables['character'][0]['country'])
    country,_=tables['country']
    ruler={tag_of[slot(i)]:(int(a)>0,int(b)>0) for i,a,b in zip(country['id'],country['ruler'],country['heir'])}
    for t,r in rows.items():
        found=groups[t]
        clout=sum(x[1] for x in found)
        strength=sum(x[3] for x in found)
        for key in IGS: r[f'clout_{key[3:]}']=ratio(sum(x[1] for x in found if x[0]==key),clout)
        r.update({'ruling_clout_share':ratio(sum(x[1] for x in found if x[2]),clout),'top_clout_share':ratio(max((x[1] for x in found),default=0),clout),
                  'ruling_groups':sum(x[2] for x in found),'government_strength_share':ratio(sum(x[3] for x in found if x[2]),strength),
                  'radical_strength_share':ratio(sum(x[4] for x in found),strength),'loyalist_strength_share':ratio(sum(x[5] for x in found),strength),
                  'ig_approval_mean':float(np.mean([x[6] for x in found])) if found else float('nan'),'ig_approval_min':min((x[6] for x in found),default=float('nan')),
                  'parties':sum(v>0 for v in parties[t]),'top_party_share':ratio(max(parties[t],default=0),sum(parties[t])),'movements':len(movements[t]),
                  'movement_radicalism_max':max(movements[t],default=0.),'has_election':int(t in elections),'characters':people[t],
                  'has_ruler':int(ruler[t][0]),'has_heir':int(ruler[t][1])})


@timed
def military(tables,rows,tag_of,name):
    unit,_=tables['combat_unit']
    manpower=Counter();kinds=defaultdict(Counter);armies=defaultdict(set)
    for c,m,k,f in zip(unit['country'],unit['current_manpower'],unit['combat_unit_type'],unit['formation']):
        t=tag_of.get(slot(c))
        if t not in rows: continue
        manpower[t]+=float(m)
        armies[t].add(slot(f))
        kind=name(k) or ''
        kinds[t]['artillery' if 'artillery' in kind or 'cannon' in kind else 'cavalry' if any(w in kind for w in ('hussar','dragoon','cuirassier','lancer','cavalry')) else 'infantry']+=1
    formation,_=tables['formation']
    owner={slot(i):tag_of.get(slot(c)) for i,c in zip(formation['id'],formation['country'])}
    ships=Counter();fleets=defaultdict(set)
    for f in tables['ship'][0]['fleet']:
        ships[owner.get(slot(f))]+=1
        fleets[owner.get(slot(f))].add(slot(f))
    hq=Counter(tag_of.get(slot(c)) for c in tables['hq'][0]['country'])
    character,roles=tables['character']
    holder={slot(i):tag_of.get(slot(c)) for i,c in zip(character['id'],character['country'])}
    commanders=defaultdict(Counter)
    for i,v in zip(roles['character_character_roles']['id'],roles['character_character_roles']['value']):
        text=name(v) or ''
        if 'general' in text or 'admiral' in text: commanders[holder.get(slot(i))]['admiral' if 'admiral' in text else 'general']+=1
    for t,r in rows.items():
        m=r['population']/1e6
        units=sum(kinds[t].values())
        r.update({'battalions_per_m':ratio(units,m),'manpower_per_m':ratio(manpower[t],m),'artillery_share':ratio(kinds[t]['artillery'],units),
                  'cavalry_share':ratio(kinds[t]['cavalry'],units),'armies':len(armies[t]),'fleets':len(fleets[t]),'ships_per_m':ratio(ships[t],m),
                  'generals':commanders[t]['general'],'admirals':commanders[t]['admiral'],'hqs':hq[t]})


@timed
def diplomacy(tables,rows,tag_of,name):
    related=defaultdict(list)
    relation,_=tables['relation']
    for a,b,v in zip(relation['first_country'],relation['second_country'],relation['relations']):
        if tag_of.get(slot(a)) in rows and tag_of.get(slot(b)) in rows:
            related[tag_of[slot(a)]].append(float(v));related[tag_of[slot(b)]].append(float(v))
    pacts=Counter()
    pact,_=tables['pact']
    for f,s in zip(pact['targets_first'],pact['targets_second']):
        for x in (f,s):
            if tag_of.get(slot(x)) in rows: pacts[tag_of[slot(x)]]+=1
    values={key:int(scalar(block,'rank_value')) for key,block in read(GAME,'common/country_ranks')}
    prestige,rank=ranking(tables['country_rankings'],tag_of,name,values)
    interests=Counter(tag_of.get(slot(c)) for c in tables['interest'][0]['country'])
    lobbies=Counter(tag_of.get(slot(c)) for c in tables['political_lobby'][0]['country'])
    for t,r in rows.items():
        r.update({'relations_mean':float(np.mean(related[t])) if related[t] else float('nan'),'pacts':pacts[t],'interests':interests[t],'lobbies':lobbies[t],
                  'prestige':prestige.get(t,float('nan')),'prestige_rank':rank.get(t,float('nan'))})


@timed_often
def ranking(table,tag_of,name,values):
    _,children=table
    found=children['country_ranking']
    return ({tag_of[slot(c)]:float(p) for c,p in zip(found['country'],found['prestige']) if slot(c) in tag_of},
            {tag_of[slot(c)]:values[name(k)] for c,k in zip(found['country'],found['rank']) if slot(c) in tag_of})


@timed
def measure(reader,mods):
    names=reader.names
    name=lambda code:names[int(code)-1][1] if int(code)>0 else None
    tables={t:reader.table(t) for t in TABLES}
    country,_=tables['country']
    tag_of={slot(i):name(c) for i,c in zip(country['id'],country['country_definition'])}
    kind={slot(i):name(c) for i,c in zip(country['id'],country['country_type'])}
    rows=countries(tables,tag_of,kind)
    prices=costs()
    found=states(tables,rows,tag_of,name,regions(mods),prices)
    society(tables,rows,tag_of)
    structure(tables,rows,found,tag_of,name)
    markets(tables,rows,tag_of,name,prices)
    politics(tables,rows,tag_of,name)
    military(tables,rows,tag_of,name)
    diplomacy(tables,rows,tag_of,name)
    for row in found.values(): row.pop('literate')
    return rows,list(found.values())


@timed_often
def domain(feature):
    return next((d for d,words in DOMAINS.items() if any(w in feature for w in words)),'other')


@timed
def located(mod,name):
    return mod/name if mod and (mod/name).exists() else GAME/name


@timed_often
def optional(block,key):
    found=re.search(r'\b'+key+r'\s*=\s*\{([^}]*)\}',block)
    return [token.strip('"') for token in found[1].split()] if found else []


@timed_often
def listed(block,key):
    if not re.search(r'\b'+key+r'\s*=\s*\{',block): raise RuntimeError(evidence(key=key,block=block[:300]))
    return optional(block,key)


@timed_often
def field(block,key):
    found=scalar(block,key)
    if found is None: raise RuntimeError(evidence(key=key,block=block[:300]))
    return found


@timed_often
def fraction(a,b):
    return a/b if b else None


@timed
def raster(path,wrap):
    rgb=np.asarray(Image.open(path).convert('RGB'))
    code=(rgb[:,:,0].astype(np.int32)<<16)|(rgb[:,:,1].astype(np.int32)<<8)|rgb[:,:,2]
    present=np.zeros(1<<24,bool)
    present[code]=True
    colours=np.flatnonzero(present)
    table=np.zeros(1<<24,np.int32)
    table[colours]=np.arange(len(colours))
    index=table[code]
    n=len(colours)
    height,width=index.shape
    flat=index.ravel()
    area=np.bincount(flat,minlength=n)
    rows=np.bincount(flat,np.repeat(np.arange(height,dtype=float),width),n)/area
    if wrap:
        angle=2*np.pi*np.arange(width)/width
        cols=np.arctan2(np.bincount(flat,np.tile(np.sin(angle),height),n),np.bincount(flat,np.tile(np.cos(angle),height),n))*width/(2*np.pi)%width
    else:
        cols=np.bincount(flat,np.tile(np.arange(width,dtype=float),height),n)/area
    sides=[(index[:,:-1],index[:,1:]),(index[:-1],index[1:])]+([(index[:,-1],index[:,0])] if wrap else [])
    edges=np.unique(np.concatenate([np.minimum(a,b)[a!=b].astype(np.int64)*n+np.maximum(a,b)[a!=b] for a,b in sides]))
    neighbours=[set() for _ in range(n)]
    for a,b in zip((edges//n).tolist(),(edges%n).tolist()):
        neighbours[a].add(b)
        neighbours[b].add(a)
    return dict(zip(colours.tolist(),range(n))),area,np.stack([rows,cols],1),neighbours,width


@timed_often
def offsets(m,points,origin):
    found=np.asarray(points,float)-origin
    if m.wrap: found[...,1]=(found[...,1]+m.width/2)%m.width-m.width/2
    return found


@timed
def splines(path):
    data=path.read_bytes()
    at=0;depth=0;section=None;entry=[];found=defaultdict(list)
    while at<len(data):
        token=struct.unpack_from('<H',data,at)[0];at+=2
        if token==0x03:
            depth+=1
            if depth==2: entry=[]
        elif token==0x04:
            if depth==2: found[section].append(entry)
            depth-=1
        elif token in SPLINE:
            if depth>=2: entry.append(SPLINE[token].unpack_from(data,at)[0])
            at+=SPLINE[token].size
        elif token in (0x0f,0x17):
            at+=2+struct.unpack_from('<H',data,at)[0]
        elif depth==0 and token!=0x01:
            section=token
    return [e[1:] for e in found[0x5f5]]


@timed
def atlas(directory):
    mod=None if directory=='vanilla' else Path(directory)/'mod'
    mods=[mod] if mod else []
    m=SimpleNamespace(world='vanilla' if mod is None else Path(directory).name)
    text=clean(located(mod,'map_data/default.map'))
    m.wrap=re.search(r'\bwrap_x\s*=\s*(\w+)',text)[1]=='yes'
    position,m.area,m.centre,m.nb,m.width=raster(located(mod,'map_data/provinces.png'),m.wrap)
    at=lambda token:position[int(token.strip('"')[1:],16)]
    m.lakes=[at(t) for t in listed(text,'lakes')]
    m.land={};m.seas={}
    for key,block in read(GAME,'map_data/state_regions',mods):
        inner=body(block)
        ident=int(field(inner,'id'))
        provinces=[at(t) for t in listed(inner,'provinces')]
        if ident>=SEA:
            m.seas[key]={'id':ident,'provinces':provinces,'province':provinces[0],'impassable':bool(optional(inner,'impassable'))}
            continue
        hubs={hub:at(field(inner,hub)) for hub in REQUIRED}
        if scalar(inner,'port'): hubs['port']=at(scalar(inner,'port'))
        exit_=scalar(inner,'naval_exit_id')
        m.land[key]={'id':ident,'provinces':provinces,'impassable':{at(t) for t in optional(inner,'impassable')},'prime':len(optional(inner,'prime_land')),
                     'traits':set(optional(inner,'traits')),'hubs':hubs,'exit':int(exit_) if exit_ else None}
    m.terrain={position[int(c,16)]:kind for c,kind in re.findall(r'x([0-9A-Fa-f]{6})\s*=\s*"?(\w+)',located(mod,'map_data/province_terrains.txt').read_text(encoding='utf-8-sig'))}
    m.harsh={key for key,block in read(GAME,'common/terrain',mods) if re.search(r'\blabel\s*=\s*label_travel_harsh_environment\b',block)}
    m.strategic={key:listed(body(block),'states') for key,block in read(GAME,'common/strategic_regions',mods)}
    m.geographic={key:(optional(body(block),'state_regions'),[t.split(':')[-1] for t in optional(body(block),'strategic_regions')]) for key,block in read(GAME,'common/geographic_regions',mods)}
    m.triggers={key:body(block) for key,block in read(GAME,'common/scripted_triggers',mods)}
    m.harvest={key:(scalar(body(block),'area_type') or 'land',body(dict(blocks(body(block)))['trigger']),body(dict(blocks(body(block)))['chance']))
               for key,block in read(GAME,'common/harvest_condition_types',mods)}
    m.canal_buildings=[scalar(body(block),'strait') for _,block in read(GAME,'common/buildings',mods) if scalar(body(block),'strait')]
    rows=[line.split(';') for line in located(mod,'map_data/adjacencies.csv').read_text(encoding='utf-8-sig').splitlines()[1:] if line.strip() and not line.startswith('#')]
    m.crossings=[(at(r[0]),at(r[1])) for r in rows if r[2] in ('sea','special')]
    m.canals=[frozenset((at(r[0]),at(r[1]))) for r in rows if r[2].startswith('canal_')]
    if len(m.crossings)+len(m.canals)!=len(rows): raise RuntimeError(evidence(types=sorted({r[2] for r in rows})))
    m.straits=[];m.strait_keys=set()
    for key,block in read(GAME,'common/strait_definitions',mods):
        inner=body(block)
        m.strait_keys.add(key)
        m.straits.append((field(inner,'type'),*(at(field(inner,f'{side}_{kind}_endpoint')) for kind in ('land','sea') for side in ('first','second'))))
    m.owned=[];m.claims=defaultdict(set)
    for _,block in read(GAME,'common/history/states',mods):
        for key,inner in blocks(body(block)):
            region=key.split(':')[-1].strip('"')
            m.claims[region]|=set(re.findall(r'\badd_claim\s*=\s*c:(\w+)',inner))
            m.owned+=[(region,re.search(r'\bcountry\s*=\s*c:(\w+)',state)[1],[at(t) for t in listed(state,'owned_provinces')],
                       int(bool(re.search(r'\bstate_type\s*=\s*unincorporated\b',state)))) for kind,state in blocks(body(inner)) if kind=='create_state']
    m.ports={(key.split(':')[-1].strip('"'),owner.split(':')[-1]) for _,block in read(GAME,'common/history/buildings',mods) for key,inner in blocks(body(block))
             for owner,building in blocks(body(inner)) if owner.startswith('region_state:') and re.search(r'\bbuilding\s*=\s*"?building_port\b',building)}
    m.treaty_ports=[target for _,block in read(GAME,'common/history/treaties',mods) for target in re.findall(r'\barticle\s*=\s*"?treaty_port\b.*?\btarget_country\s*=\s*c:(\w+)',block,re.S)]
    definitions=dict(read(GAME,'common/country_definitions',mods))
    m.types={tag:scalar(body(block),'country_type') for tag,block in definitions.items()}
    m.capitals={tag:scalar(body(block),'capital') for tag,block in definitions.items()}
    for _,block in read(GAME,'common/history/countries',mods):
        for key,inner in blocks(body(block)):
            moved=re.search(r'\bset_capital\s*=\s*(STATE_\w+)',inner)
            if moved: m.capitals[key.split(':')[-1]]=moved[1]
    m.market=at(re.findall(r'\bWORLD_MARKET_LOCATION\s*=\s*"?(x[0-9A-Fa-f]{6})',' '.join(clean(p) for p in script_files(GAME,'common/defines',mods)))[-1])
    m.splines=splines(located(mod,'gfx/map/spline_network/spline_network.splnet'))
    with Image.open(located(mod,'map_data/rivers.png')) as rivers: m.rivers=int((np.asarray(rivers)<254).sum())
    return m


@timed
def components(nodes,neighbours,extra=()):
    links=defaultdict(list)
    for a,b in extra:
        links[a].append(b)
        links[b].append(a)
    found={}
    for start in nodes:
        if start in found: continue
        found[start]=start
        stack=[start]
        while stack:
            x=stack.pop()
            for o in (*neighbours[x],*links.get(x,())):
                if o in nodes and o not in found:
                    found[o]=start
                    stack.append(o)
    return found


@timed
def layout(m):
    m.land_of={p:key for key,s in m.land.items() for p in s['provinces']}
    m.sea_of={s['province']:key for key,s in m.seas.items()}
    m.by_id={s['id']:key for key,s in m.land.items()}
    m.sea_by_id={s['id']:key for key,s in m.seas.items()}
    m.blocked=set().union(*(s['impassable'] for s in m.land.values()))
    m.passable=m.land_of.keys()-m.blocked
    m.mass=components(set(m.land_of),m.nb,m.crossings)
    m.piece=components(m.passable,m.nb,m.crossings)
    m.main={key:Counter(m.mass[p] for p in s['provinces']).most_common(1)[0][0] for key,s in m.land.items()}
    m.shore={p for p in m.land_of if any(o in m.sea_of for o in m.nb[p])}
    m.coast={key:{m.sea_of[o] for p in s['provinces'] for o in m.nb[p] if o in m.sea_of} for key,s in m.land.items()}
    m.sea_nb={key:{m.sea_of[o] for o in m.nb[s['province']] if o in m.sea_of} for key,s in m.seas.items()}
    m.bordering=defaultdict(set);m.pairs=set();open_=set()
    for p,key in m.land_of.items():
        for o in m.nb[p]:
            other=m.land_of.get(o)
            if other is None or other==key: continue
            m.bordering[key].add(other)
            m.pairs.add(frozenset((key,other)))
            if p in m.passable and o in m.passable: open_.add(frozenset((key,other)))
    m.closed=m.pairs-open_
    m.region_of={x:r for r,members in m.strategic.items() for x in members}
    m.members={key:{x for x in states if x in m.land or x in m.seas}|{x for r in srs if r in m.strategic for x in m.strategic[r]} for key,(states,srs) in m.geographic.items()}
    m.recognized={tag for tag,kind in m.types.items() if kind=='recognized'}
    m.held=[row for row in m.owned if row[1] in m.recognized]
    m.owners=defaultdict(set)
    for region,tag,_,_ in m.held: m.owners[region].add(tag)
    m.created={region for region,*_ in m.owned}
    m.owner={p:tag for _,tag,provinces,_ in m.held for p in provinces}
    m.sea_owners=defaultdict(set)
    for p,tag in m.owner.items():
        for o in m.nb[p]:
            if o in m.sea_of: m.sea_owners[m.sea_of[o]].add(tag)


@timed
def ground(m):
    land=sorted(m.land_of)
    area=m.area[land]
    borders=[(p,o) for p in land for o in m.nb[p] if o>p and o in m.land_of]
    homes=Counter(m.main.values())
    largest=max(homes,key=lambda k:(homes[k],k))
    sizes=Counter(m.mass.values())
    objects={'provinces':{'area':area.tolist()},
             'lakes':{'area':m.area[m.lakes].tolist(),'land_states':[len({m.land_of[o] for o in m.nb[p] if o in m.land_of}) for p in m.lakes]},
             'landmasses':{'states':list(homes.values()),'provinces':[sizes[k] for k in homes]}}
    ratios={'terrain_change_share':[sum(m.terrain[p]!=m.terrain[o] for p,o in borders),len(borders)],'harsh_share':[sum(m.terrain[p] in m.harsh for p in land),len(land)],
            'impassable_share':[len(m.blocked),len(land)],'impassable_mass_share':[len(set(components(m.blocked,m.nb).values())),len(m.blocked)],
            'impassable_exposed_share':[sum(any(o in m.passable for o in m.nb[p]) for p in m.blocked),len(m.blocked)],'river_share':[m.rivers,int(area.sum())],
            'off_largest_share':[sum(k!=largest for k in m.main.values()),len(m.main)]}
    return objects,ratios,{}


@timed_often
def anchor(m,x):
    if not x&HARBOR: return 'hub',m.by_id[x//100],HUB_NAMES[x%100]
    ident=(x-HARBOR)//100
    return ('sea',m.sea_by_id[ident]) if ident>=SEA else ('port',m.by_id[ident])


@timed
def routes(m):
    joined=defaultdict(set);ends=[]
    for anchors in m.splines:
        inner=[x for x in (anchors[0],anchors[-1]) if x>=INTERMEDIATE]
        if len(inner)==2: raise RuntimeError(evidence(anchors=anchors[:3]))
        if inner: joined[inner[0]].add(anchors[-1] if anchors[0]==inner[0] else anchors[0])
        else: ends.append((anchors[0],anchors[-1]))
    ends+=[(a,b) for found in joined.values() for a in found for b in found if a<b]
    m.links=set();m.inner=defaultdict(set);m.used=Counter();m.docks=defaultdict(list);m.sea_links=Counter();harsh=[];crossing=[]
    for a,b in ends:
        first,second=sorted((anchor(m,a),anchor(m,b)))
        if first[0]=='hub' and second[0]=='hub':
            harsh.append(sum(m.terrain[m.land[s]['hubs'][hub]] in m.harsh for _,s,hub in (first,second)))
            m.used[first[1]]+=1
            if first[1]==second[1]: m.inner[first[1]].add(frozenset((first[2],second[2])))
            else:
                m.used[second[1]]+=1
                m.links.add(frozenset((first[1],second[1])))
                crossing.append(frozenset((first[1],second[1])))
        elif (first[0],second[0])==('port','sea'): m.docks[first[1]].append(second[1])
        elif (first[0],second[0])==('sea','sea'): m.sea_links[frozenset((first[1],second[1]))]+=1
        else: raise RuntimeError(evidence(first=first,second=second))
    ratios={'harsh_end_share':[sum(harsh),2*len(harsh)],'neighbour_link_share':[len(m.pairs&m.links),len(m.pairs)],'impassable_link_share':[len(m.closed&m.links),len(m.closed)]}
    checks={'nonneighbour_links':[sum(pair not in m.pairs for pair in crossing),len(crossing)]}
    return {'splines':{'points':[len(anchors) for anchors in m.splines]},'links':{'harsh_ends':harsh}},ratios,checks


@timed_often
def hub_shape(m,s):
    provinces=s['provinces']
    if len(provinces)<SPREAD: return None,None
    weight=m.area[provinces].astype(float)
    size=np.sqrt(weight.sum())
    city=m.centre[s['hubs']['city']]
    hubs=offsets(m,m.centre[[s['hubs'][h] for h in ('farm','mine','wood')]],city)
    middle=(offsets(m,m.centre[provinces],city)*weight[:,None]).sum(0)/weight.sum()
    return float(np.hypot(*hubs.T).mean()/size),float(np.hypot(*middle)/size)


@timed
def columns(rows):
    return {f:[r[f] for r in rows] for f in rows[0]}


@timed
def holdings(m):
    rows=[]
    for key,s in m.land.items():
        hubs=list(s['hubs'].values())
        spread,offset=hub_shape(m,s)
        rows.append({'area':int(m.area[s['provinces']].sum()),'provinces':len(s['provinces']),'neighbours':len(m.bordering[key]),'seas':len(m.coast[key]),
                     'landmasses':len({m.mass[p] for p in s['provinces']}),'passable_pieces':len({m.piece[p] for p in s['provinces'] if p in m.piece}),
                     'hub_pieces':len({m.piece[p] for p in hubs if p in m.piece}),'hub_spread':spread,'city_offset':offset,'distinct_hubs':len(set(hubs)),
                     'harsh_hubs':sum(m.terrain[p] in m.harsh for p in hubs)/len(hubs),'impassable_hubs':sum(p in s['impassable'] for p in hubs),
                     'owners':len(m.owners[key]) if m.owners[key] else None,'geographic_regions':sum(key in found for found in m.members.values()),'splines':m.used[key],
                     'hub_pair_links':fraction(len(m.inner[key]),comb(len(hubs),2)),'city_links':fraction(sum('city' in pair for pair in m.inner[key]),len(m.inner[key])),
                     'linked_neighbours':fraction(len({frozenset((key,o)) for o in m.bordering[key]}&m.links),len(m.bordering[key]))})
    coastal=[key for key in m.land if m.coast[key]]
    crossed={m.land_of[p] for pair in m.crossings for p in pair}
    owned=[key for key in m.land if m.owners[key]]
    ratios={'cut_state_share':[sum(r['passable_pieces']>1 for r in rows),len(rows)],'split_hub_share':[sum(r['hub_pieces']>1 for r in rows),len(rows)],
            'impassable_pair_share':[len(m.closed),len(m.pairs)],'spanning_state_share':[sum(r['landmasses']>1 for r in rows),len(rows)],
            'harsh_hub_share':[sum(m.terrain[p] in m.harsh for s in m.land.values() for p in s['hubs'].values()),sum(len(s['hubs']) for s in m.land.values())],
            'portless_coast_share':[sum('port' not in m.land[key]['hubs'] for key in coastal),len(coastal)],'crossing_state_share':[len(crossed),len(rows)],
            'split_region_share':[sum(len(m.owners[key])>1 for key in owned),len(owned)],'unincorporated_share':[sum(row[3] for row in m.held),len(m.held)],
            'claimed_state_share':[sum(bool(m.claims[key]&m.recognized) for key in m.land),len(rows)],
            'treaty_port_share':[sum(tag in m.recognized for tag in m.treaty_ports),len(rows)],'prime_state_share':[sum(s['prime']>0 for s in m.land.values()),len(rows)],
            'geographic_resolved_share':[sum(x in m.land or x in m.seas for states,_ in m.geographic.values() for x in states)
                                         +sum(r in m.strategic for _,srs in m.geographic.values() for r in srs),sum(len(states)+len(srs) for states,srs in m.geographic.values())]}
    return {'states':columns(rows)},ratios,{}


@timed
def waters(m):
    touching=Counter(sea for key in m.land for sea in m.coast[key])
    exits=Counter(s['exit'] for s in m.land.values() if s['exit'] is not None)
    middle=float(np.median([m.area[s['province']] for s in m.seas.values()]))
    rows=[{'area':int(m.area[s['province']]),'relative_area':float(m.area[s['province']])/middle,'land_states':touching[key],'countries':len(m.sea_owners[key]),
           'exits':exits[s['id']],'sea_neighbours':len(m.sea_nb[key])} for key,s in m.seas.items()]
    open_={key for key,s in m.seas.items() if not s['impassable']}
    touching_pairs={frozenset((key,o)) for key in open_ for o in m.sea_nb[key] if o in open_}
    market=touching[m.sea_of[m.market]]
    ratios={'impassable_sea_share':[len(m.seas)-len(open_),len(m.seas)],'market_rank_share':[sum(touching[key]>market for key in m.seas),len(m.seas)],
            'sea_link_share':[len(touching_pairs&m.sea_links.keys()),len(touching_pairs)],'strait_sea_share':[len({m.sea_of[p] for *_,a,b in m.straits for p in (a,b)}),len(m.seas)]}
    return {'seas':columns(rows)},ratios,{}


@timed
def extent(m):
    ports=np.array([m.centre[s['hubs']['port']] for s in m.land.values() if 'port' in s['hubs']]).reshape(-1,2)
    nearest=[np.sort(np.hypot(*offsets(m,np.delete(ports,i,0),p).T)) for i,p in enumerate(ports)]
    return {'ports':{f'nearest_{k+1}':[float(d[k]) if len(d)>k else None for d in nearest] for k in range(NEAREST)}},{'wrap':[int(m.wrap),1]},{}


@timed
def strategic(m):
    land=[r for r,members in m.strategic.items() if members and all(x in m.land for x in members)]
    sea_regions=defaultdict(set)
    for key in m.land:
        for sea in m.coast[key]: sea_regions[sea].add(m.region_of[key])
    capitals=Counter(m.region_of[m.capitals[tag]] for tag in {row[1] for row in m.held})
    rows=[]
    for r in land:
        states=m.strategic[r]
        border={x for x in states if any(m.region_of[o]!=r for o in m.bordering[x])}
        contact={x for x in states if x in border or any(sea_regions[sea]-{r} for sea in m.coast[x])}
        owners=set().union(*(m.owners[x] for x in states))
        rows.append({'states':len(states),'border_share':len(border)/len(states),'contact_share':len(contact)/len(states),
                     'landmasses':len({m.mass[p] for x in states for p in m.land[x]['provinces']}),'owners':len(owners) if owners else None,'capitals':capitals[r]})
    return {'regions':columns(rows)},{'spanning_region_share':[sum(r['landmasses']>1 for r in rows),len(rows)]},{}


@timed
def realms(m):
    held=defaultdict(list)
    for region,tag,provinces,_ in m.held: held[tag].append((region,provinces))
    rows=[];considered=away_total=inland=unlinked=never=unowned=0
    for tag,items in held.items():
        masses=[{m.mass[p] for p in provinces} for _,provinces in items]
        seas=[{m.sea_of[o] for p in provinces for o in m.nb[p] if o in m.sea_of} for _,provinces in items]
        border=[any(o in m.owner and m.owner[o]!=tag for p in provinces for o in m.nb[p]) for _,provinces in items]
        contact=[near or any(m.sea_owners[sea]-{tag} for sea in found) for near,found in zip(border,seas)]
        home=[mine for (region,_),mine in zip(items,masses) if region==m.capitals[tag]]
        off=None
        if home:
            started={x for (region,_),mine in zip(items,masses) if (region,tag) in m.ports for x in mine}
            capable={m.mass[p] for region,provinces in items if 'port' in m.land[region]['hubs'] for p in provinces if p in m.shore}
            away=[(mine,provinces) for (_,provinces),mine in zip(items,masses) if not mine&home[0]]
            considered+=len(items)
            away_total+=len(away)
            inland+=sum(not any(p in m.shore for p in provinces) for _,provinces in away)
            unlinked+=sum(not (mine&started and home[0]&started) for mine,_ in away)
            never+=sum(not (mine&capable and home[0]&capable) for mine,_ in away)
            off=len(away)/len(items)
        else: unowned+=1
        touched=set().union(*seas)
        rows.append({'states':len(items),'landmasses':len(set().union(*masses)),'off_capital':off,'border_share':sum(border)/len(items),
                     'contact_share':sum(contact)/len(items),'seas':len(touched) if touched else None})
    ratios={'off_capital_share':[away_total,considered],'off_capital_inland_share':[inland,away_total],'off_capital_unlinked_share':[unlinked,away_total],
            'never_linkable_share':[never,considered]}
    return {'countries':columns(rows)},ratios,{'capital_unowned':[unowned,len(held)]}


@timed_often
def token(text,at):
    found=TOKEN.search(text,at)
    if found is None or text[at:found.start()].strip(): raise RuntimeError(evidence(text=text[at:at+80]))
    return found


@timed
def statements(text):
    found=[];at=0
    while text[at:].strip():
        key=token(text,at)
        op=token(text,key.end())
        value=token(text,op.end())
        if key[0] in ('{','}') or key[0] in OPERATORS or op[0] not in OPERATORS or value[0]=='}' or value[0] in OPERATORS:
            raise RuntimeError(evidence(text=text[key.start():key.start()+80]))
        at=value.end()
        if value[0]!='{':
            found.append((key[0],op[0],value[0]))
            continue
        depth=1
        while depth:
            close=BRACE.search(text,at)
            if close is None: raise RuntimeError(evidence(text=text[value.start():value.start()+80]))
            at=close.end()
            depth+=1 if close[0]=='{' else -1
        found.append((key[0],op[0],text[value.end():at-1]))
    return found


@timed
def eligible(m,trigger,keys,chance=None):
    parsed={}

    def parts(text):
        if text not in parsed: parsed[text]=statements(text)
        return parsed[text]

    def holds(text,key,month):
        return all(test(*found,key,month) for found in parts(text))

    def test(name,op,value,key,month):
        if name=='month':
            if month is None: raise RuntimeError(evidence(name=name,op=op,value=value))
            return {'=':month==int(value),'>=':month>=int(value),'<=':month<=int(value),'>':month>int(value),'<':month<int(value)}[op]
        if op!='=': raise RuntimeError(evidence(name=name,op=op,value=value))
        if name in ('OR','NOR'): return any(test(*found,key,month) for found in parts(value))==(name=='OR')
        if name=='AND': return holds(value,key,month)
        if name=='NOT':
            if len(parts(value))!=1: raise RuntimeError(evidence(name=name,value=value))
            return not test(*parts(value)[0],key,month)
        if name=='always': return value=='yes'
        if name=='is_in_geographic_region': return key in m.members[value]
        if name in ('state_region','this'): return key==value.split(':')[-1]
        if name=='has_state_trait': return value in m.land[key]['traits']
        if name=='any_scope_state': return key in m.created and holds(value,key,month)
        if name in m.triggers and value in ('yes','no'): return holds(m.triggers[name],key,month)==(value=='yes')
        raise RuntimeError(evidence(name=name,op=op,value=value))

    def run(items,key,month,total):
        for name,op,value in items:
            if op!='=': raise RuntimeError(evidence(name=name,op=op,value=value))
            if name=='value': total=float(value)
            elif name=='add': total+=float(value)
            elif name=='multiply': total*=float(value)
            elif name=='if':
                limits=[found for found in parts(value) if found[0]=='limit']
                if len(limits)!=1: raise RuntimeError(evidence(value=value[:80]))
                if holds(limits[0][2],key,month): total=run([found for found in parts(value) if found[0]!='limit'],key,month,total)
            else: raise RuntimeError(evidence(name=name,value=value[:80]))
        return total

    def possible(key):
        base=float(next(value for name,_,value in parts(chance) if name=='value'))
        steps=re.findall(r'\b(add|multiply)\s*=\s*(-?[\d.]+)',chance)
        if base>0 and all(float(x)>0 if kind=='multiply' else float(x)>=0 for kind,x in steps): return True
        return any(run(parts(chance),key,month,0.)>0 for month in range(1,13))
    return {key for key in keys if holds(trigger,key,None) and (chance is None or possible(key))}


@timed
def climate(m):
    kinds={'land':list(m.land),'sea':list(m.seas)}
    graph={'land':m.bordering,'sea':m.sea_nb}
    ratios={};found={}
    for name,(kind,trigger) in CLASSES.items():
        found[name]=eligible(m,trigger,kinds[kind])
        pieces=Counter(components(found[name],graph[kind]).values())
        ratios[f'class_{name}_share']=[len(found[name]),len(kinds[kind])]
        ratios[f'class_{name}_scattered']=[len(found[name])-max(pieces.values(),default=0),len(found[name])]
    for name,(kind,trigger,chance) in m.harvest.items():
        ratios[f'harvest_{name}']=[len(eligible(m,trigger,kinds[kind],chance)),len(kinds[kind])]
    checks={'world_partition':[sum((key in found['old_world'])==(key in found['new_world']) for key in m.land),len(m.land)],
            'continent_partition':[sum(sum(key in found[c] for c in CONTINENTS)!=1 for key in m.land),len(m.land)]}
    return {},ratios,checks


@timed
def integrity(m):
    lakes=set(m.lakes)
    member=Counter(p for s in (*m.land.values(),*m.seas.values()) for p in s['provinces'])
    membership=Counter(x for members in m.strategic.values() for x in members)
    seas_only=[r for r,members in m.strategic.items() if members and all(x in m.seas for x in members)]
    land_only=[r for r,members in m.strategic.items() if members and all(x in m.land for x in members)]
    ports=[(key,s) for key,s in m.land.items() if 'port' in s['hubs'] and s['exit'] is not None]
    pixel=components(set(m.land_of),m.nb)
    pairs=Counter(m.canals)
    natural=[kind=='natural' for kind,*_ in m.straits]
    checks={'province_membership':[sum(member[p]!=(0 if p in lakes else 1) for p in range(len(m.area))),len(m.area)],
            'sea_state_size':[sum(len(s['provinces'])!=1 for s in m.seas.values()),len(m.seas)],
            'region_membership':[sum(membership[x]!=1 for x in (*m.land,*m.seas)),len(m.land)+len(m.seas)],
            'mixed_regions':[len(m.strategic)-len(seas_only)-len(land_only),len(m.strategic)],
            'sea_region_size':[sum(len(m.strategic[r])!=1 for r in seas_only),len(seas_only)],
            'hub_outside':[sum(p not in s['provinces'] for s in m.land.values() for p in s['hubs'].values()),sum(len(s['hubs']) for s in m.land.values())],
            'port_exit_mismatch':[sum(('port' in s['hubs'])!=(s['exit'] is not None) for s in m.land.values()),len(m.land)],
            'port_apart':[sum(m.seas[m.sea_by_id[s['exit']]]['province'] not in m.nb[s['hubs']['port']] for _,s in ports),len(ports)],
            'docking':[sum(m.docks[key]!=[m.sea_by_id[s['exit']]] for key,s in ports),len(ports)],
            'idle_crossings':[sum(pixel[a]==pixel[b] for a,b in m.crossings),len(m.crossings)],
            'strait_rows':[sum(pairs[frozenset((a,b))]!=1 for *_,a,b in m.straits),len(m.straits)],
            'strait_links':[sum(m.sea_links[frozenset((m.sea_of[a],m.sea_of[b]))]!=1 for *_,a,b in m.straits),len(m.straits)],
            'strait_touch':[sum((b in m.nb[a])!=wild for (*_,a,b),wild in zip(m.straits,natural)),len(m.straits)],
            'strait_land':[sum(len({m.land_of[first],m.land_of[second]})!=(2 if wild else 1) for (_,first,second,*_),wild in zip(m.straits,natural)),len(m.straits)],
            'orphan_canals':[sum(pair not in {frozenset((a,b)) for *_,a,b in m.straits} for pair in m.canals),len(m.canals)],
            'canal_buildings':[sum(strait not in m.strait_keys for strait in m.canal_buildings),len(m.canal_buildings)]}
    return {},{},checks


@timed
def geography(directory):
    m=atlas(directory)
    layout(m)
    result={'world':m.world,'objects':{},'ratios':{},'checks':{}}
    for part in (ground,routes,holdings,waters,extent,strategic,realms,climate,integrity):
        for kind,found in zip(('objects','ratios','checks'),part(m)): result[kind].update(found)
    return result


@timed_often
def defined(values):
    found=np.array([x for x in values if x is not None],float)
    if not np.isfinite(found).all(): raise RuntimeError(evidence(values=found[~np.isfinite(found)][:5]))
    return found


@timed_often
def ks(a,b):
    grid=np.union1d(a,b)
    return float(np.abs(np.searchsorted(np.sort(a),grid,'right')/len(a)-np.searchsorted(np.sort(b),grid,'right')/len(b)).max())


@timed_often
def bounds(num,den,one_sided):
    flip=not one_sided and num/den>.5
    k=den-num if flip else num
    p=k/den
    centre=(p+Z*Z/(2*den))/(1+Z*Z/den)
    half=Z*np.sqrt(p*(1-p)/den+Z*Z/(4*den*den))/(1+Z*Z/den)
    low,high=(0.,0.) if k==0 else (min(p/BAND,centre-half),max(p*BAND,centre+half))
    low=0. if one_sided else low
    return (1-high,1-low) if flip else (low,high)


@timed
def reference():
    from interface.recording.store import Store
    game=GameInterface(profile=PROFILE,quarterly_pause=False)
    try:
        game.campaign('GBR',None)
        Executor(game).run('pause')
        rows,found=measure(game.reader(),[])
    finally:
        game.close()
    store=Store()
    try:
        return store.record_reference(build(),rows,found,geography('vanilla'))
    finally:
        store.connection.close()


@timed
def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('command',choices=('reference',))
    parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    print(reference())


if __name__=='__main__':
    main()
