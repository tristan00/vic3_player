import bisect
from functools import cached_property

from interface.common import DEFAULT_GAME, timed, timed_often
from interface.recording.spec import TABLE
from interface.script import read
from ..catalogue import DUTIES, INSTITUTIONS as INSTITUTION_TYPES, LAW_ACTIONS, LAW_GROUP, LAW_GROUPS, NAVAL, RECORDED_PARAMS, PARTY_ACTIONS
from .rewards import COSTS

TYPED={'law':('law','law_type'),'institution':('institution','institution_type'),'interest_group':('interest_group','interest_group_type'),
       'political_movement':('political_movement','political_movement_type'),'journal_entry':('journal_entry','journal_entry_type'),
       'company':('company','company_type'),'military_formation':('formation','formation_type')}
RAW={'int','choice','event'}
SYNTHETIC={'strategic_region'}
NONE='none'
POLICY=['tax_level','government_wage_level','military_wage_level']
INTEREST_GROUPS=sorted(name for name,_ in read(DEFAULT_GAME/'game','common/interest_groups'))
GROUP_METRICS=('clout','approval','in_government')
GROUP_FEATURES=[f'player.interest_group.{kind}.{metric}' for kind in INTEREST_GROUPS for metric in GROUP_METRICS]
NUMBERS=['treasury','debt','interest','balance','population','bureaucracy_available','standard_of_living','government_queue_items','government_queue_left',
         'private_queue_items','private_queue_left','construction_capacity','construction_used','construction_paused','balance_gdp','battalions','mobilization_ratio',
         'wars','army_spending','army_spending_gdp','infamy','government_legitimacy','radicals_percent']+GROUP_FEATURES+['government_spending','government_spending_gdp']+POLICY
WEEKS_PER_YEAR=52
LAWS=[f'law.{group}' for group in LAW_GROUPS]
CATEGORIES=LAWS+['player.country_rank']
GOODS=[key for key,_ in read(DEFAULT_GAME/'game','common/goods')]
PRICES=[f'price.{goods}' for goods in GOODS]+[f'price_above_world.{goods}' for goods in GOODS]
INSTITUTIONS=[f'institution.{kind}' for kind in INSTITUTION_TYPES]
NO_DUTY=DUTIES.index('none')
DIRECTIONS=('import','export')
TARIFFS=[f'tariff.{direction}.{goods}' for direction in DIRECTIONS for goods in GOODS]
TAXES=[f'consumption_tax.{goods}' for goods in GOODS]
SITE=['site.unemployed','site.peasants','site.standard_of_living','site.buildings_of_type','site.literacy','site.population','site.gdp_share']
PEOPLE=['lower_strata','middle_strata','upper_strata','subsisting_workforce','unemployed_workforce']
WORLD_PRICES='''select w.run_id,g.name,w.seq,w.price from world_market_price_sample w join goods g on g.goods=w.goods
where w.run_id = any(%s) and w.date is not null order by w.run_id,w.goods,w.seq'''
TERRAIN='''select p.world_id,sr.name,t.name,sum(p.area_pixels) from world_province p join state_region sr on sr.state_region=p.state_region join terrain t on t.terrain=p.terrain
where p.world_id = any(%s) group by 1,2,3'''
INTEREST=('expense','interest')
ARMY=('military_slaves','military_goods','military_wages')
GOVERNMENT=('government_slaves','government_goods','government_wages')
KINDS={name:list(params) for name,params in RECORDED_PARAMS.items()}
LEADER_ACTIONS={name for name,params in KINDS.items() if name in LAW_ACTIONS or any(kind in ('interest_group','character','political_movement') for _,kind in params)}


@timed_often
def queues(items):
    government=[left for private,left,*_ in items if not private]
    private=[left for private_item,left,*_ in items if private_item]
    return [len(government),sum(government),len(private),sum(private)]


@timed_often
def queued(items,state,kind):
    position,left=min((position,left) for private,left,position,found,building_type in items if not private and found==state and building_type==kind)
    return position+1,1-left/COSTS[kind]


@timed_often
def construction(report):
    return [float('nan')]*3 if report is None else [report[0],report[1],float(report[2])]


@timed_often
def balance_gdp(balance,gdp):
    return WEEKS_PER_YEAR*balance/gdp if gdp else float('nan')


@timed_often
def radicals_percent(radicals,population):
    return 100*radicals/population if population else float('nan')


@timed_often
def interest_group_values(groups,stats,player):
    missing=float('nan')
    values={kind:(*stats.get(group,(missing,missing)),float(government)) for group,country,kind,government in groups if country==player}
    return [value for kind in INTEREST_GROUPS for value in values.get(kind,(missing,missing,missing))]


@timed_often
def play_values(relation,gdp,target_gdp,prestige,target_prestige):
    return [float('nan') if relation is None else relation,
            gdp/target_gdp if gdp is not None and target_gdp else float('nan'),
            prestige/target_prestige if prestige is not None and target_prestige else float('nan')]


@timed_often
def target_links(player,hours,relations,pacts,treaties,articles,states,provinces,edges):
    truces={country:tuple(max(0,(until-hours)/24) if until is not None else 0. for until in (own,theirs)) for country,own,theirs in relations}
    agreements={}
    for first,second,kind in pacts:
        if player in (first,second):
            other=second if first==player else first
            direction='outgoing' if first==player else 'incoming'
            agreements.setdefault(other,set()).add(('play.pacts',f'{direction}.{kind}'))
    partners={treaty:second if first==player else first for treaty,first,second,withdrawn,entered in treaties
              if not withdrawn and entered is not None and entered<=hours and player in (first,second)}
    for treaty,kind,source,target in articles:
        if treaty in partners:
            direction='outgoing' if source==player else 'incoming' if target==player else 'mutual'
            agreements.setdefault(partners[treaty],set()).add(('play.treaty_articles',f'{direction}.{kind}'))
    owners=dict(states)
    placed={color:state for color,state in provinces if state in owners}
    borders={}
    for first,second in edges:
        a,b=placed.get(first),placed.get(second)
        for own,other in ((a,b),(b,a)):
            target=owners.get(other)
            if owners.get(own)==player and target is not None and target!=player:
                borders.setdefault(target,set()).add(other)
    return truces,agreements,borders


@timed_often
def target_context(links,target,state):
    if target is None:
        return [float('nan')]*6,[]
    truces,agreements,borders=links
    own,theirs=truces.get(target,(0.,0.))
    adjacent=borders.get(target,set())
    return [float(own>0 or theirs>0),own,theirs,float(bool(adjacent)),len(adjacent),float(state in adjacent) if state is not None else 0.],sorted(agreements.get(target,()))


@timed_often
def laws(active):
    current={LAW_GROUP[law_type]:law_type for law_type in active}
    return [current.get(group,NONE) for group in LAW_GROUPS]


@timed_often
def categories(lookup):
    rank=lookup.country(lookup.player)
    return lookup.laws+[NONE if rank is None else rank]


@timed_often
def institutions(levels):
    return [float(levels.get(kind,0)) for kind in INSTITUTION_TYPES]


@timed_often
def tariffs(levels):
    return [float(levels.get((direction,goods),NO_DUTY)) for direction in DIRECTIONS for goods in GOODS]


@timed_often
def taxes(taxed):
    return [float(goods in taxed) for goods in GOODS]


@timed_often
def site(people,living,built,literate,share):
    lower,middle,upper,subsisting,unemployed=[float('nan')]*5 if people is None else people
    return [float(unemployed),float(subsisting),*(float('nan') if value is None else float(value) for value in (living,built,literate)),float(lower+middle+upper),
            float('nan') if share is None else float(share)]


@timed_often
def located(action,params,lookup):
    if 'building' in params:
        return lookup.home(params['building']),lookup.building(params['building'])
    return params['state'],params.get('building_type',NAVAL.get(action))


@timed_often
def prices(found,world):
    return ([float(found[goods]) if goods in found else float('nan') for goods in GOODS]
            +[float(found[goods]-world[goods]) if goods in found and goods in world else float('nan') for goods in GOODS])


@timed_often
def majority(rows):
    best={}
    for world,region,kind,area in rows:
        if (area,kind)>best.get((world,region),(0,'')):
            best[(world,region)]=(area,kind)
    return {key:kind for key,(_,kind) in best.items()}


DEFINED='''select et.name,d.option,d.name,e.effect,e.detail from event_definition_option d join event_type et on et.event_type=d.event_type
left join event_definition_option_effect e on e.ruleset_id=d.ruleset_id and e.event_type=d.event_type and e.option=d.option
where d.ruleset_id=%s and et.name = any(%s) order by 1,2,e.position'''


@timed_often
def defined(connection,ruleset,events):
    found={}
    for event,option,name,effect,detail in connection.execute(DEFINED,(ruleset,sorted(events))).fetchall():
        effects=found.setdefault((event,option),(name,[]))[1]
        if effect is not None:
            effects.append((effect,detail))
    return found


@timed_often
def answers(events,options,definitions):
    found={}
    for event,kind in events.items():
        shown=[row for row in options if row[0]==event and row[2] is not None and row[4]]
        for _,option,position,default,_ in shown:
            name,effects=definitions[kind,option]
            found[kind,position]=(name,default,len(shown),effects)
    return found


@timed
def interest_line(connection):
    return connection.execute('select line from budget_line where direction=%s and name=%s',INTEREST).fetchone()[0]


@timed
def expense_lines(connection,names):
    return {line for line, in connection.execute("select line from budget_line where direction='expense' and name = any(%s)",(list(names),)).fetchall()}


@timed_often
def spent(budget,lines):
    return sum(amount for direction,line,amount in budget if direction=='expense' and line in lines)


@timed_often
def army(report,wars,spending,gdp):
    return [*([float('nan')]*2 if report is None else report),wars,spending,balance_gdp(spending,gdp)]


class Leaders:
    @timed_often
    def __init__(self,player,groups,characters,traits,movements,laws):
        self.player=player
        self.groups=groups
        self.characters=characters
        self.movements=[(group,movement) for group,movement,clout in movements if clout>0]
        self.laws=laws
        self.traits={}
        for character,trait in traits:
            self.traits.setdefault(character,set()).add(trait)

    @timed_often
    def at(self,action,params):
        groups=set()
        if action in LAW_ACTIONS:
            target=self.laws.get(params['law'])
            groups={group for group,(country,_,_) in self.groups.items() if country==target}
        elif action in PARTY_ACTIONS:
            member=params['interest_group']
            if member in self.groups:
                country,party,_=self.groups[member]
                groups={member} if party is None else {group for group,(owner,other,_) in self.groups.items() if (owner,other)==(country,party)}
        else:
            for param,kind in KINDS[action]:
                if param not in params:
                    continue
                if kind=='interest_group':
                    groups.add(params[param])
                elif kind=='character':
                    groups.update(group for group,(_,_,leader) in self.groups.items() if leader==params[param])
                elif kind=='political_movement':
                    groups.update(group for group,movement in self.movements if movement==params[param] and group in self.groups and self.groups[group][0]==self.player)
        leaders={self.groups[group][2] for group in groups if group in self.groups and self.groups[group][2] is not None}
        return [(self.characters[leader],sorted(self.traits.get(leader,()))) for leader in sorted(leaders) if leader in self.characters]


class LiveLookup:
    @timed_often
    def __init__(self,snapshot):
        self.player=snapshot.player
        self.snapshot=snapshot
        self.__dict__.update(snapshot.memo('feature_lookups',lambda:self.load(snapshot)))

    @staticmethod
    @timed
    def load(s):
        world=s.connection.execute('select world_id from run where run_id=%s',(s.run_id,)).fetchone()[0]
        names,rows=s.table('player_treasury')
        treasury=dict(zip(names,rows[0]))
        names,rows=s.table('player_population')
        population=dict(zip(names,rows[0]))
        total=population['lower_strata']+population['middle_strata']+population['upper_strata']
        names,rows=s.table('player_politics')
        politics=dict(zip(names,rows[0]))
        sol=s.map('country_standard_of_living_report','country,average_standard_of_living_by_population').get(s.player)
        legitimacy=s.map('country_politics_report','country,government_legitimacy').get(s.player)
        groups=interest_group_values(s.rows('interest_group','interest_group,country,interest_group_type,in_government'),
                                     {group:(clout,approval) for group,clout,approval in s.rows('interest_group_stats','interest_group,clout,approval')},s.player)
        gdp=s.map('country_economy_report','country,gdp').get(s.player)
        queue=s.rows('player_construction_queue_item','private,construction_left,position,state,building_type')
        buildings=s.rows('building','building,building_type,state,levels')
        built={}
        for _,kind,state,levels in buildings:
            built[state,kind]=built.get((state,kind),0)+levels
        report=next((tuple(found) for country,*found in s.rows('country_construction_report','country,base_construction_speed,used_construction,is_construction_paused')
                     if country==s.player),None)
        line=interest_line(s.connection)
        budget=s.rows('player_budget_line','direction,line,amount')
        government=spent(budget,expense_lines(s.connection,GOVERNMENT))
        military=next((tuple(found) for country,*found in s.rows('country_military_report','country,battalions,mobilization_ratio') if country==s.player),None)
        wars=sum(1 for _,country in s.rows('war_participant','war,country') if country==s.player)
        return {'terrain':{region:kind for (_,region),kind in majority(s.connection.execute(TERRAIN,([world],)).fetchall()).items()},
                'states':{state:(region,country) for state,region,country in s.rows('state','state,state_region,country')},
                'buildings':{building:building_type for building,building_type,_,_ in buildings},
                'homes':{building:state for building,_,state,_ in buildings},
                'built':built,
                'people':{state:found for state,*found in s.rows('state_population','state,'+','.join(PEOPLE))},
                'living':s.map('state_standard_of_living_report','state,average_standard_of_living_all'),
                'literate':s.map('state_population_report','state,literacy'),
                'shares':s.map('state_economy_report','state,gdp_contribution_percentage'),
                'queue':queue,
                'types':{kind:s.map(table,f'{table},{column}') for kind,(table,column) in TYPED.items()},
                'characters':s.map('character','character,ideology'),
                'countries':s.map('country','country,country_rank'),
                'laws':laws(law_type for law_type,country,active in s.rows('law','law_type,country,active') if country==s.player and active),
                'prices':prices({goods:price for market,goods,price in s.rows('market_goods','market,goods,price') if market==s.map('country','country,market').get(s.player)},
                                WorldPrices(s.connection,[s.run_id]).at(s.run_id,s.seq)),
                'institutions':institutions({kind:level for kind,country,level in s.rows('institution','institution_type,country,investment') if country==s.player}),
                'tariffs':tariffs({(direction,goods):level for direction,goods,level in s.rows('player_tariff','direction,goods,level')}),
                'taxes':taxes({goods for goods, in s.rows('player_taxed_goods','goods')}),
                'answers':answers(s.map('event','event,event_type'),s.rows('event_option','event,option,visible_position,default_option,enabled'),
                                  defined(s.connection,s.ruleset_id,set(s.map('event','event,event_type').values()))),
                'numbers':[treasury['money'],treasury['principal'],
                           sum(amount for direction,found,amount in budget if direction==INTEREST[0] and found==line),
                           treasury['balance_trend_current'],total,
                           politics['power_delta_bureaucracy'],float('nan') if sol is None else sol,*queues(queue),*construction(report),
                           balance_gdp(treasury['balance_trend_current'],gdp),
                           *army(military,wars,spent(budget,expense_lines(s.connection,ARMY)),gdp),
                           s.map('country_diplomacy','country,infamy')[s.player],float('nan') if legitimacy is None else legitimacy,
                           radicals_percent(population['radicals'],total),*groups,government,balance_gdp(government,gdp),
                           *s.rows('player_policy',','.join(POLICY))[0]]}

    @timed_often
    def state(self,state):
        return self.states.get(state,(None,None))

    @timed_often
    def building(self,ident):
        return self.buildings.get(ident)

    @timed_often
    def home(self,ident):
        return self.homes.get(ident)

    @timed_often
    def site(self,state,kind):
        return site(self.people.get(state),self.living.get(state),None if kind is None else self.built.get((state,kind),0),self.literate.get(state),self.shares.get(state))

    @timed_often
    def typed(self,kind,ident):
        return self.types[kind].get(ident)

    @timed_often
    def character(self,ident):
        return self.characters.get(ident)

    @property
    @timed_often
    def leadership(self):
        s=self.snapshot
        return s.memo('interest_group_leaders',lambda:Leaders(self.player,{group:(country,party,leader) for group,country,party,leader in
                                                                         s.rows('interest_group','interest_group,country,party,leader')},self.characters,
                                                            s.rows('character_assigned_trait','character,character_trait'),
                                                            s.rows('interest_group_movement_support','interest_group,political_movement,clout'),s.map('law','law,country')))

    @timed_often
    def leaders(self,action,params):
        return self.leadership.at(action,params)

    @timed_often
    def country(self,ident):
        return self.countries.get(ident)

    @timed_often
    def answer(self,event,position):
        return self.answers[event,position]

    @timed_often
    def play(self,target):
        s=self.snapshot
        values=s.memo('play_features',lambda:(s.map('player_relation','country,relations'),s.map('country_economy_report','country,gdp'),
                                             s.map('country_diplomacy_report','country,prestige')))
        relations,gdp,prestige=values
        relation=relations.get(target,0) if target in self.countries else None
        return play_values(relation,gdp.get(self.player),gdp.get(target),prestige.get(self.player),prestige.get(target))

    @timed_often
    def context(self,target,state=None):
        s=self.snapshot
        def load():
            colors=s.province_colors()
            return target_links(s.player,s.hours,s.rows('player_relation','country,player_truce,country_truce'),
                                s.rows('pact','first_country,second_country,pact_type'),s.rows('treaty','treaty,first_country,second_country,withdrawn,entered_into_force_on'),
                                s.rows('treaty_article','treaty,treaty_article_type,source_country,target_country'),s.rows('state','state,country'),
                                [(colors[province],state) for province,state in s.rows('province','province,state')],s.adjacency())
        return target_context(s.memo('play_context',load),target,state)


class Versions:
    @timed
    def __init__(self,connection,table,keys,columns,runs):
        spec=TABLE[table]
        vocabularies={column.name:column.vocabulary for column in list(spec.keys)+list(spec.columns) if column.vocabulary}
        names={name:dict(connection.execute(f'select {name},name from {name}').fetchall()) for name in set(vocabularies.values())}
        self.index={}
        self.by_run={}
        selected=keys+columns
        for run,seq,present,*values in connection.execute(f'select run_id,seq,present,{",".join(selected)} from {table} where run_id = any(%s) order by run_id,{",".join(keys)},seq',(runs,)).fetchall():
            values=[names[vocabularies[name]][value] if name in vocabularies and value is not None else value for name,value in zip(selected,values)]
            key=tuple(values[:len(keys)])
            if (run,key) not in self.index:
                self.by_run.setdefault(run,[]).append(key)
            seqs,states=self.index.setdefault((run,key),([],[]))
            seqs.append(seq)
            states.append(tuple(values[len(keys):]) if present else None)

    def at(self,run,key,seq):
        found=self.index.get((run,key))
        if found is None:
            return None
        position=bisect.bisect_right(found[0],seq)-1
        return None if position<0 else found[1][position]

    def live(self,run,seq):
        return [found for key in self.by_run.get(run,[]) if (found:=self.at(run,key,seq)) is not None]


class Samples:
    @timed
    def __init__(self,connection,table,columns,runs,owner=None):
        self.index={}
        mine=f' join run r on r.run_id=t.run_id and r.player_country=t.{owner}' if owner else ''
        selected=','.join(f't.{column}' for column in columns)
        for run,seq,*values in connection.execute(f'select t.run_id,t.seq,{selected} from {table} t{mine} where t.run_id = any(%s) order by t.run_id,t.seq',(runs,)).fetchall():
            seqs,rows=self.index.setdefault(run,([],[]))
            seqs.append(seq)
            rows.append(values)

    def at(self,run,seq):
        seqs,rows=self.index.get(run,([],[]))
        position=bisect.bisect_right(seqs,seq)-1
        return None if position<0 else rows[position]


class Latest:
    @timed
    def __init__(self,connection,table,key,columns,runs):
        self.index={}
        for run,ident,seq,*values in connection.execute(f'select run_id,{key},seq,{",".join(columns)} from {table} where run_id = any(%s) order by run_id,{key},seq',(runs,)).fetchall():
            seqs,rows=self.index.setdefault((run,ident),([],[]))
            seqs.append(seq)
            rows.append(values)

    def at(self,run,ident,seq):
        seqs,rows=self.index.get((run,ident),([],[]))
        position=bisect.bisect_right(seqs,seq)-1
        return None if position<0 else rows[position]


class WorldPrices:
    @timed
    def __init__(self,connection,runs):
        self.index={}
        for run,goods,seq,price in connection.execute(WORLD_PRICES,(runs,)).fetchall():
            seqs,found=self.index.setdefault(run,{}).setdefault(goods,([],[]))
            seqs.append(seq)
            found.append(price)

    @timed_often
    def at(self,run,seq):
        return {goods:found[position] for goods,(seqs,found) in self.index.get(run,{}).items() if (position:=bisect.bisect_right(seqs,seq)-1)>=0}


class History:
    @timed
    def __init__(self,connection,runs):
        self.player=dict(connection.execute('select run_id,player_country from run where run_id = any(%s)',(runs,)).fetchall())
        worlds=dict(connection.execute('select run_id,world_id from run where run_id = any(%s)',(runs,)).fetchall())
        terrain=majority(connection.execute(TERRAIN,(list(set(worlds.values())),)).fetchall())
        self.terrain={run:{region:kind for (world,region),kind in terrain.items() if world==worlds[run]} for run in runs}
        load=lambda table,keys,columns:Versions(connection,table,keys,columns,runs)
        self.states=load('state_history',['state'],['state_region','country'])
        self.buildings=load('building_history',['building'],['building_type','state','levels'])
        self.people=Latest(connection,'state_population','state',PEOPLE,runs)
        self.living=load('state_standard_of_living_report',['state'],['average_standard_of_living_all'])
        self.literate=load('state_population_report',['state'],['literacy'])
        self.shares=load('state_economy_report',['state'],['gdp_contribution_percentage'])
        self.types={kind:load(table+'_history',[table],[column]) for kind,(table,column) in TYPED.items()}
        self.characters=load('character_history',['character'],['ideology'])
        self.groups=load('interest_group_history',['interest_group'],['country','party','leader','interest_group_type','in_government'])
        self.group_stats=Latest(connection,'interest_group_stats','interest_group',['clout','approval'],runs)
        self.traits=load('character_assigned_trait',['character','character_trait'],[])
        self.movements=load('interest_group_movement_support',['interest_group','political_movement'],['clout'])
        self.countries=load('country_history',['country'],['country_rank'])
        self.law_rows=load('law_history',['law'],['law_type','country','active'])
        self.markets=load('country_history',['country'],['market'])
        self.goods=load('market_goods',['market','goods'],['price'])
        self.world=WorldPrices(connection,runs)
        self.budget=load('player_budget_line',['direction','line'],['amount'])
        self.interest=interest_line(connection)
        self.army=expense_lines(connection,ARMY)
        self.government=expense_lines(connection,GOVERNMENT)
        self.policy=Samples(connection,'player_policy',POLICY,runs)
        self.taxed=load('player_taxed_goods',['goods'],[])
        self.military=load('country_military_report',['country'],['battalions','mobilization_ratio'])
        self.wars=load('war_participant',['war','country'],['country'])
        self.treasury=Samples(connection,'player_treasury',['money','principal','balance_trend_current'],runs)
        self.population=Samples(connection,'player_population',['lower_strata','middle_strata','upper_strata','radicals'],runs)
        self.politics=Samples(connection,'player_politics',['power_delta_bureaucracy'],runs)
        self.legitimacy=load('country_politics_report',['country'],['government_legitimacy'])
        self.infamy=Samples(connection,'country_diplomacy',['infamy'],runs,'country')
        self.sol=load('country_standard_of_living_report',['country'],['average_standard_of_living_by_population'])
        self.gdp=load('country_economy_report',['country'],['gdp'])
        self.relations=load('player_relation',['country'],['relations','player_truce','country_truce'])
        self.prestige=load('country_diplomacy_report',['country'],['prestige'])
        self.pacts=load('pact_history',['pact'],['first_country','second_country','pact_type'])
        self.treaties=load('treaty_history',['treaty'],['first_country','second_country','withdrawn','entered_into_force_on'])
        self.articles=load('treaty_article_history',['treaty_article'],['treaty','treaty_article_type','source_country','target_country'])
        self.provinces=load('province_history',['province'],['state'])
        self.hours=Samples(connection,'snapshot',['game_date'],runs)
        self.colors={}
        for run,province,color in connection.execute('select run_id,province,color from province where run_id=any(%s)',(runs,)).fetchall():
            self.colors.setdefault(run,{})[province]=color
        edges={}
        for world,first,second in connection.execute('select world_id,first_color,second_color from world_adjacency where world_id=any(%s)',(list(set(worlds.values())),)).fetchall():
            edges.setdefault(world,[]).append((first,second))
        self.edges={run:edges.get(world,[]) for run,world in worlds.items()}
        self.queue=load('player_construction_queue_item',['private','position'],['private','construction_left','position','state','building_type'])
        self.construction=load('country_construction_report',['country'],['base_construction_speed','used_construction','is_construction_paused'])
        self.institution_rows=load('institution_history',['institution'],['institution_type','country','investment'])
        self.tariff_rows=load('player_tariff',['direction','goods'],['level'])
        self.events=load('event_history',['event'],['event_type'])
        self.options=load('event_option',['event','option'],['visible_position','default_option','enabled'])
        self.rulesets=dict(connection.execute('select run_id,ruleset_id from run where run_id = any(%s)',(runs,)).fetchall())
        seen={}
        for (run,_),(_,states) in self.events.index.items():
            seen.setdefault(self.rulesets[run],set()).update(state[0] for state in states if state is not None)
        self.defined={ruleset:defined(connection,ruleset,events) for ruleset,events in seen.items()}

    @timed_often
    def at(self,run,seq):
        return HistoryLookup(self,run,seq)


class HistoryLookup:
    @timed_often
    def __init__(self,history,run,seq):
        self.h=history
        self.run=run
        self.seq=seq
        self.player=history.player[run]
        self.terrain=history.terrain[run]

    @property
    @timed_often
    def numbers(self):
        treasury=self.h.treasury.at(self.run,self.seq)
        population=self.h.population.at(self.run,self.seq)
        politics=self.h.politics.at(self.run,self.seq)
        if treasury is None or population is None or politics is None:
            return None
        total=sum(population[:3])
        legitimacy=self.h.legitimacy.at(self.run,(self.player,),self.seq)
        interest=self.h.budget.at(self.run,(INTEREST[0],self.h.interest),self.seq)
        sol=self.h.sol.at(self.run,(self.player,),self.seq)
        report=self.h.construction.at(self.run,(self.player,),self.seq)
        gdp=self.h.gdp.at(self.run,(self.player,),self.seq)
        gdp=None if gdp is None else gdp[0]
        government=self.spent(self.h.government)
        return [treasury[0],treasury[1],interest[0] if interest else 0,treasury[2],total,politics[0],float('nan') if sol is None else sol[0],
                *queues(self.queue),*construction(report),balance_gdp(treasury[2],gdp),
                *army(self.h.military.at(self.run,(self.player,),self.seq),sum(1 for country, in self.h.wars.live(self.run,self.seq) if country==self.player),
                      self.spent(self.h.army),gdp),
                self.h.infamy.at(self.run,self.seq)[0],float('nan') if legitimacy is None else legitimacy[0],radicals_percent(population[3],total),*self.interest_groups,
                government,balance_gdp(government,gdp),*self.h.policy.at(self.run,self.seq)]

    @cached_property
    @timed_often
    def interest_groups(self):
        groups=[]
        stats={}
        for group, in self.h.groups.by_run.get(self.run,[]):
            found=self.h.groups.at(self.run,(group,),self.seq)
            if found is not None and found[0]==self.player:
                groups.append((group,found[0],found[3],found[4]))
                rating=self.h.group_stats.at(self.run,group,self.seq)
                if rating is not None:
                    stats[group]=rating
        return interest_group_values(groups,stats,self.player)

    @timed_often
    def spent(self,lines):
        return sum(found[0] for line in lines if (found:=self.h.budget.at(self.run,('expense',line),self.seq)) is not None)

    @property
    @timed_often
    def queue(self):
        return self.h.queue.live(self.run,self.seq)

    @property
    @timed_often
    def institutions(self):
        return institutions({kind:level for kind,country,level in self.h.institution_rows.live(self.run,self.seq) if country==self.player})

    @property
    @timed_often
    def tariffs(self):
        return tariffs({key:found[0] for key in self.h.tariff_rows.by_run.get(self.run,[]) if (found:=self.h.tariff_rows.at(self.run,key,self.seq)) is not None})

    @property
    @timed_often
    def taxes(self):
        return taxes({goods for goods, in self.h.taxed.by_run.get(self.run,[]) if self.h.taxed.at(self.run,(goods,),self.seq) is not None})

    @property
    @timed_often
    def laws(self):
        return laws(law_type for law_type,country,active in self.h.law_rows.live(self.run,self.seq) if country==self.player and active)

    @property
    @timed_often
    def prices(self):
        market=self.h.markets.at(self.run,(self.player,),self.seq)
        return prices({goods:found[0] for market_id,goods in self.h.goods.by_run.get(self.run,[]) if market and market_id==market[0]
                       and (found:=self.h.goods.at(self.run,(market_id,goods),self.seq)) is not None},self.h.world.at(self.run,self.seq))

    @timed_often
    def state(self,state):
        return self.h.states.at(self.run,(state,),self.seq) or (None,None)

    @timed_often
    def building(self,ident):
        found=self.h.buildings.at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def home(self,ident):
        found=self.h.buildings.at(self.run,(ident,),self.seq)
        return found[1] if found else None

    @cached_property
    @timed_often
    def built(self):
        found={}
        for key in self.h.buildings.by_run.get(self.run,[]):
            now=self.h.buildings.at(self.run,key,self.seq)
            if now is not None:
                found[now[1],now[0]]=found.get((now[1],now[0]),0)+now[2]
        return found

    @timed_often
    def site(self,state,kind):
        living,literate,share=(None if found is None else found[0] for found in (table.at(self.run,(state,),self.seq) for table in (self.h.living,self.h.literate,self.h.shares)))
        return site(self.h.people.at(self.run,state,self.seq),living,None if kind is None else self.built.get((state,kind),0),literate,share)

    @timed_often
    def typed(self,kind,ident):
        found=self.h.types[kind].at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def character(self,ident):
        found=self.h.characters.at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @cached_property
    @timed_often
    def leadership(self):
        h=self.h
        groups={group:found[:3] for group, in h.groups.by_run.get(self.run,[]) if (found:=h.groups.at(self.run,(group,),self.seq)) is not None}
        characters={character:found[0] for character, in h.characters.by_run.get(self.run,[]) if (found:=h.characters.at(self.run,(character,),self.seq)) is not None}
        traits=[key for key in h.traits.by_run.get(self.run,[]) if h.traits.at(self.run,key,self.seq) is not None]
        movements=[(*key,found[0]) for key in h.movements.by_run.get(self.run,[]) if (found:=h.movements.at(self.run,key,self.seq)) is not None]
        laws={law:found[1] for law, in h.law_rows.by_run.get(self.run,[]) if (found:=h.law_rows.at(self.run,(law,),self.seq)) is not None}
        return Leaders(self.player,groups,characters,traits,movements,laws)

    @timed_often
    def leaders(self,action,params):
        return self.leadership.at(action,params)

    @timed_often
    def country(self,ident):
        found=self.h.countries.at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def answer(self,event,position):
        events={key[0]:now[0] for key in self.h.events.by_run.get(self.run,[]) if (now:=self.h.events.at(self.run,key,self.seq)) is not None}
        options=[(*key,*now) for key in self.h.options.by_run.get(self.run,[]) if key[0] in events and (now:=self.h.options.at(self.run,key,self.seq)) is not None]
        return answers(events,options,self.h.defined[self.h.rulesets[self.run]])[event,position]

    @timed_often
    def play(self,target):
        values=[table.at(self.run,(country,),self.seq) for table,country in
                ((self.h.relations,target),(self.h.gdp,self.player),(self.h.gdp,target),(self.h.prestige,self.player),(self.h.prestige,target))]
        if values[0] is None and self.h.countries.at(self.run,(target,),self.seq) is not None:
            values[0]=(0,)
        return play_values(*(None if value is None else value[0] for value in values))

    @cached_property
    @timed_often
    def links(self):
        h=self.h
        relations=[(country,*found[1:]) for country, in h.relations.by_run.get(self.run,[]) if (found:=h.relations.at(self.run,(country,),self.seq)) is not None]
        treaties=[(treaty,*found) for treaty, in h.treaties.by_run.get(self.run,[]) if (found:=h.treaties.at(self.run,(treaty,),self.seq)) is not None]
        states=[(state,found[1]) for state, in h.states.by_run.get(self.run,[]) if (found:=h.states.at(self.run,(state,),self.seq)) is not None]
        provinces=[(h.colors[self.run][province],found[0]) for province, in h.provinces.by_run.get(self.run,[]) if (found:=h.provinces.at(self.run,(province,),self.seq)) is not None]
        return target_links(self.player,h.hours.at(self.run,self.seq)[0],relations,h.pacts.live(self.run,self.seq),treaties,h.articles.live(self.run,self.seq),states,provinces,h.edges[self.run])

    @timed_often
    def context(self,target,state=None):
        return target_context(self.links,target,state)


def resolve(param,kind,value,lookup):
    if kind in SYNTHETIC:
        return param
    if kind=='state':
        region,owner=lookup.state(value)
        return ('player' if owner==lookup.player else 'none' if owner is None else 'foreign')+'/'+str(lookup.terrain.get(region))
    if kind=='building':
        return str(lookup.building(value))
    if kind in TYPED:
        found=lookup.typed(kind,value)
        return f'{TYPED[kind][1]}={found}' if isinstance(found,int) else str(found)
    if kind=='character':
        return str(lookup.character(value))
    if kind=='country':
        return str(lookup.country(value))
    if kind in RAW:
        return f'{param}={value}'
    return value if isinstance(value,str) else param
