import bisect

from interface.actions.catalogue import BY_NAME
from interface.common import DEFAULT_GAME, timed, timed_often
from interface.options.available import DEFAULT_TARIFF
from interface.recording.spec import TABLE
from interface.script import read, scalar
from .random_smac_weighting import COSTS

TYPED={'law':('law','law_type'),'institution':('institution','institution_type'),'interest_group':('interest_group','interest_group_type'),
       'political_movement':('political_movement','political_movement_type'),'journal_entry':('journal_entry','journal_entry_type'),
       'company':('company','company_type'),'military_formation':('formation','formation_type')}
RAW={'int','choice','event'}
SYNTHETIC={'strategic_region'}
NONE='none'
NUMBERS=['treasury','debt','interest','balance','population','bureaucracy_available','standard_of_living','government_queue_items','government_queue_left',
         'private_queue_items','private_queue_left','construction_capacity','construction_used','construction_paused','balance_gdp','battalions','mobilization_ratio',
         'wars','army_spending','army_spending_gdp']
WEEKS_PER_YEAR=52
LAW_GROUP={key:scalar(value,'group') for key,value in read(DEFAULT_GAME/'game','common/laws')}
LAW_GROUPS=sorted(set(LAW_GROUP.values()))
LAWS=[f'law.{group}' for group in LAW_GROUPS]
GOODS=[key for key,_ in read(DEFAULT_GAME/'game','common/goods')]
PRICES=[f'price.{goods}' for goods in GOODS]
INSTITUTION_TYPES=[key for key,_ in read(DEFAULT_GAME/'game','common/institutions')]
INSTITUTIONS=[f'institution.{kind}' for kind in INSTITUTION_TYPES]
DIRECTIONS=('import','export')
TARIFFS=[f'tariff.{direction}.{goods}' for direction in DIRECTIONS for goods in GOODS]
TERRAIN='''select p.world_id,sr.name,t.name,sum(p.area_pixels) from world_province p join state_region sr on sr.state_region=p.state_region join terrain t on t.terrain=p.terrain
where p.world_id = any(%s) group by 1,2,3'''
INTEREST=('expense','interest')
ARMY=('military_slaves','military_goods','military_wages')
KINDS={name:[tuple(spec.split(':')) if ':' in spec else (spec,spec) for spec in action.params] for name,action in BY_NAME.items()}


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
def laws(active):
    current={LAW_GROUP[law_type]:law_type for law_type in active}
    return [current.get(group,NONE) for group in LAW_GROUPS]


@timed_often
def institutions(levels):
    return [float(levels.get(kind,0)) for kind in INSTITUTION_TYPES]


@timed_often
def tariffs(levels):
    return [float(levels.get((direction,goods),DEFAULT_TARIFF)) for direction in DIRECTIONS for goods in GOODS]


@timed_often
def prices(found):
    return [float(found[goods]) if goods in found else float('nan') for goods in GOODS]


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
def army_lines(connection):
    return {line for line, in connection.execute("select line from budget_line where direction='expense' and name = any(%s)",(list(ARMY),)).fetchall()}


@timed_often
def army(report,wars,spending,gdp):
    return [*([float('nan')]*2 if report is None else report),wars,spending,balance_gdp(spending,gdp)]


class LiveLookup:
    @timed_often
    def __init__(self,snapshot):
        self.player=snapshot.player
        self.__dict__.update(snapshot.memo('feature_lookups',lambda:self.load(snapshot)))

    @staticmethod
    @timed
    def load(s):
        world=s.connection.execute('select world_id from run where run_id=%s',(s.run_id,)).fetchone()[0]
        names,rows=s.table('player_treasury')
        treasury=dict(zip(names,rows[0]))
        names,rows=s.table('player_population')
        population=dict(zip(names,rows[0]))
        names,rows=s.table('player_politics')
        politics=dict(zip(names,rows[0]))
        sol=s.map('country_standard_of_living_report','country,average_standard_of_living_by_population').get(s.player)
        gdp=s.map('country_economy_report','country,gdp').get(s.player)
        queue=s.rows('player_construction_queue_item','private,construction_left,position,state,building_type')
        buildings=s.rows('building','building,building_type,state')
        report=next((tuple(found) for country,*found in s.rows('country_construction_report','country,base_construction_speed,used_construction,is_construction_paused')
                     if country==s.player),None)
        line=interest_line(s.connection)
        lines=army_lines(s.connection)
        budget=s.rows('player_budget_line','direction,line,amount')
        military=next((tuple(found) for country,*found in s.rows('country_military_report','country,battalions,mobilization_ratio') if country==s.player),None)
        wars=sum(1 for _,country in s.rows('war_participant','war,country') if country==s.player)
        return {'terrain':{region:kind for (_,region),kind in majority(s.connection.execute(TERRAIN,([world],)).fetchall()).items()},
                'states':{state:(region,country) for state,region,country in s.rows('state','state,state_region,country')},
                'buildings':{building:building_type for building,building_type,_ in buildings},
                'places':{building:(state,building_type) for building,building_type,state in buildings},
                'queue':queue,
                'types':{kind:s.map(table,f'{table},{column}') for kind,(table,column) in TYPED.items()},
                'characters':s.map('character','character,ideology'),
                'countries':s.map('country','country,country_rank'),
                'laws':laws(law_type for law_type,country,active in s.rows('law','law_type,country,active') if country==s.player and active),
                'prices':prices({goods:price for market,goods,price in s.rows('market_goods','market,goods,price') if market==s.map('country','country,market').get(s.player)}),
                'institutions':institutions({kind:level for kind,country,level in s.rows('institution','institution_type,country,investment') if country==s.player}),
                'tariffs':tariffs({(direction,goods):level for direction,goods,level in s.rows('player_tariff','direction,goods,level')}),
                'answers':answers(s.map('event','event,event_type'),s.rows('event_option','event,option,visible_position,default_option,enabled'),
                                  defined(s.connection,s.ruleset_id,set(s.map('event','event,event_type').values()))),
                'numbers':[treasury['money'],treasury['principal'],
                           sum(amount for direction,found,amount in budget if direction==INTEREST[0] and found==line),
                           treasury['balance_trend_current'],population['lower_strata']+population['middle_strata']+population['upper_strata'],
                           politics['power_delta_bureaucracy'],float('nan') if sol is None else sol,*queues(queue),*construction(report),
                           balance_gdp(treasury['balance_trend_current'],gdp),
                           *army(military,wars,sum(amount for direction,found,amount in budget if direction=='expense' and found in lines),gdp)]}

    @timed_often
    def state(self,state):
        return self.states.get(state,(None,None))

    @timed_often
    def building(self,ident):
        return self.buildings.get(ident)

    @timed_often
    def place(self,ident):
        return self.places[ident]

    @timed_often
    def typed(self,kind,ident):
        return self.types[kind].get(ident)

    @timed_often
    def character(self,ident):
        return self.characters.get(ident)

    @timed_often
    def country(self,ident):
        return self.countries.get(ident)

    @timed_often
    def answer(self,event,position):
        return self.answers[event,position]


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
    def __init__(self,connection,table,columns,runs):
        self.index={}
        for run,seq,*values in connection.execute(f'select run_id,seq,{",".join(columns)} from {table} where run_id = any(%s) order by run_id,seq',(runs,)).fetchall():
            seqs,rows=self.index.setdefault(run,([],[]))
            seqs.append(seq)
            rows.append(values)

    def at(self,run,seq):
        seqs,rows=self.index.get(run,([],[]))
        position=bisect.bisect_right(seqs,seq)-1
        return None if position<0 else rows[position]


class History:
    @timed
    def __init__(self,connection,runs):
        self.player=dict(connection.execute('select run_id,player_country from run where run_id = any(%s)',(runs,)).fetchall())
        worlds=dict(connection.execute('select run_id,world_id from run where run_id = any(%s)',(runs,)).fetchall())
        terrain=majority(connection.execute(TERRAIN,(list(set(worlds.values())),)).fetchall())
        self.terrain={run:{region:kind for (world,region),kind in terrain.items() if world==worlds[run]} for run in runs}
        load=lambda table,keys,columns:Versions(connection,table,keys,columns,runs)
        self.states=load('state_history',['state'],['state_region','country'])
        self.buildings=load('building_history',['building'],['building_type','state'])
        self.types={kind:load(table+'_history',[table],[column]) for kind,(table,column) in TYPED.items()}
        self.characters=load('character_history',['character'],['ideology'])
        self.countries=load('country_history',['country'],['country_rank'])
        self.law_rows=load('law_history',['law'],['law_type','country','active'])
        self.markets=load('country_history',['country'],['market'])
        self.goods=load('market_goods',['market','goods'],['price'])
        self.budget=load('player_budget_line',['direction','line'],['amount'])
        self.interest=interest_line(connection)
        self.army=army_lines(connection)
        self.military=load('country_military_report',['country'],['battalions','mobilization_ratio'])
        self.wars=load('war_participant',['war','country'],['country'])
        self.treasury=Samples(connection,'player_treasury',['money','principal','balance_trend_current'],runs)
        self.population=Samples(connection,'player_population',['lower_strata','middle_strata','upper_strata'],runs)
        self.politics=Samples(connection,'player_politics',['power_delta_bureaucracy'],runs)
        self.sol=load('country_standard_of_living_report',['country'],['average_standard_of_living_by_population'])
        self.gdp=load('country_economy_report',['country'],['gdp'])
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
        interest=self.h.budget.at(self.run,(INTEREST[0],self.h.interest),self.seq)
        sol=self.h.sol.at(self.run,(self.player,),self.seq)
        report=self.h.construction.at(self.run,(self.player,),self.seq)
        gdp=self.h.gdp.at(self.run,(self.player,),self.seq)
        return [treasury[0],treasury[1],interest[0] if interest else 0,treasury[2],sum(population),politics[0],float('nan') if sol is None else sol[0],
                *queues(self.queue),*construction(report),balance_gdp(treasury[2],None if gdp is None else gdp[0]),
                *army(self.h.military.at(self.run,(self.player,),self.seq),sum(1 for country, in self.h.wars.live(self.run,self.seq) if country==self.player),
                      sum(found[0] for line in self.h.army if (found:=self.h.budget.at(self.run,('expense',line),self.seq)) is not None),None if gdp is None else gdp[0])]

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
    def laws(self):
        return laws(law_type for law_type,country,active in self.h.law_rows.live(self.run,self.seq) if country==self.player and active)

    @property
    @timed_often
    def prices(self):
        market=self.h.markets.at(self.run,(self.player,),self.seq)
        return prices({goods:found[0] for market_id,goods in self.h.goods.by_run.get(self.run,[]) if market and market_id==market[0]
                       and (found:=self.h.goods.at(self.run,(market_id,goods),self.seq)) is not None})

    @timed_often
    def state(self,state):
        return self.h.states.at(self.run,(state,),self.seq) or (None,None)

    @timed_often
    def building(self,ident):
        found=self.h.buildings.at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def place(self,ident):
        kind,state=self.h.buildings.at(self.run,(ident,),self.seq)
        return state,kind

    @timed_often
    def typed(self,kind,ident):
        found=self.h.types[kind].at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def character(self,ident):
        found=self.h.characters.at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def country(self,ident):
        found=self.h.countries.at(self.run,(ident,),self.seq)
        return found[0] if found else None

    @timed_often
    def answer(self,event,position):
        events={key[0]:now[0] for key in self.h.events.by_run.get(self.run,[]) if (now:=self.h.events.at(self.run,key,self.seq)) is not None}
        options=[(*key,*now) for key in self.h.options.by_run.get(self.run,[]) if key[0] in events and (now:=self.h.options.at(self.run,key,self.seq)) is not None]
        return answers(events,options,self.h.defined[self.h.rulesets[self.run]])[event,position]


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
