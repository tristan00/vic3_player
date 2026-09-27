from ..actions.catalogue import action_folders
from ..common import timed, timed_often
from ..recording.spec import VOCABULARIES
from ..runner.memory import MONTH_STARTS

HOURS_PER_DAY=24
DAYS_PER_YEAR=365
YEAR_OFFSET=5000


def script_hours(text):
    year,month,day,*hour=(int(part) for part in text.split('.'))
    return ((year+YEAR_OFFSET)*DAYS_PER_YEAR+MONTH_STARTS[month-1]+day-1)*HOURS_PER_DAY+(hour[0] if hour else 0)


def date_text(hours):
    days,hour=divmod(hours,HOURS_PER_DAY)
    year,day=divmod(days,DAYS_PER_YEAR)
    month=max(index for index,start in enumerate(MONTH_STARTS) if start<=day)
    return f'{year-YEAR_OFFSET}.{month+1}.{day-MONTH_STARTS[month]+1}.{hour}'


ADJACENCY={}


@timed
def world_adjacency(connection,world_id):
    if world_id not in ADJACENCY:
        ADJACENCY[world_id]=connection.execute('select first_color,second_color from world_adjacency where world_id=%s',(world_id,)).fetchall()
    return ADJACENCY[world_id]


class Stored:
    @timed
    def __init__(self,connection,run_id,seq):
        self.connection=connection
        self.run_id=run_id
        self.seq=seq
        self.player,self.ruleset_id=connection.execute('select player_country,ruleset_id from run where run_id=%s',(run_id,)).fetchone()
        row=connection.execute('select game_date,paused,speed,ui_panel_open,ui_interaction_open,ui_map_list_open from snapshot where run_id=%s and seq=%s',
                               (run_id,seq)).fetchone()
        self.hours=row[0]
        self.meta={'paused':row[1],'speed':row[2],'ui_panel_open':row[3],'ui_interaction_open':row[4],'ui_map_list_open':row[5]}
        self.date=date_text(self.hours)
        self.tables={name for name, in connection.execute("select relname from pg_class where relnamespace='public'::regnamespace and relkind='r'")}
        self.name_columns={}
        for table,column,vocabulary in connection.execute(
                "select c.conrelid::regclass::text,a.attname,c.confrelid::regclass::text from pg_constraint c "
                "join pg_attribute a on a.attrelid=c.conrelid and a.attnum=c.conkey[1] "
                "where c.connamespace='public'::regnamespace and c.contype='f' and array_length(c.conkey,1)=1 and c.confrelid::regclass::text = any(%s)",
                (list(VOCABULARIES),)):
            self.name_columns.setdefault(table,{})[column]=vocabulary
        self.names={}
        self.cache={}

    @timed_often
    def vocabulary(self,name):
        if name not in self.names:
            self.names[name]=dict(self.connection.execute(f'select {name},name from {name}').fetchall())
        return self.names[name]

    @timed_often
    def table(self,table):
        stored=table+'_history' if table+'_history' in self.tables else table
        def compute():
            function=(stored[:-len('_history')] if stored.endswith('_history') else stored)+'_at'
            cursor=self.connection.execute(f'select * from {function}(%s,%s)',(self.run_id,self.seq))
            names=[column.name for column in cursor.description]
            rows=cursor.fetchall()
            for index,column in enumerate(names):
                vocabulary=self.name_columns.get(stored,{}).get(column)
                if vocabulary:
                    lookup=self.vocabulary(vocabulary)
                    rows=[(*row[:index],None if row[index] is None else lookup[row[index]],*row[index+1:]) for row in rows]
            return names,rows
        return self.memo(('table',stored),compute)

    def rows(self,table,columns,**equal):
        signature=(table,columns,tuple(sorted(equal.items())))
        if signature not in self.cache:
            names,rows=self.table(table)
            picks=[names.index(column) for column in columns.split(',')]
            tests=[(names.index(column),wanted) for column,wanted in equal.items()]
            self.cache[signature]=[tuple(row[i] for i in picks) for row in rows if all(row[i]==wanted for i,wanted in tests)]
        return self.cache[signature]

    def map(self,table,columns,**equal):
        signature=('map',table,columns,tuple(sorted(equal.items())))
        if signature not in self.cache:
            self.cache[signature]=dict(self.rows(table,columns,**equal))
        return self.cache[signature]

    def grouped(self,table,columns,**equal):
        signature=('grouped',table,columns,tuple(sorted(equal.items())))
        if signature not in self.cache:
            result={}
            for key,*values in self.rows(table,columns,**equal):
                result.setdefault(key,[]).append(values[0] if len(values)==1 else tuple(values))
            self.cache[signature]=result
        return self.cache[signature]

    @timed_often
    def adjacency(self):
        def compute():
            world_id,=self.connection.execute('select world_id from run where run_id=%s',(self.run_id,)).fetchone()
            return world_adjacency(self.connection,world_id)
        return self.memo('adjacency',compute)

    @timed_often
    def province_colors(self):
        return self.memo('province_colors',lambda:dict(self.connection.execute('select province,color from province where run_id=%s',(self.run_id,)).fetchall()))

    @timed_often
    def first_seen(self,table):
        return self.memo(('first_seen',table),lambda:dict(self.connection.execute(f'select {table},first_seq from {table} where run_id=%s',(self.run_id,)).fetchall()))

    def memo(self,key,compute):
        if key not in self.cache:
            self.cache[key]=compute()
        return self.cache[key]

    @timed_often
    def definitions(self,folder):
        def compute():
            table={}
            for name,field,value in self.connection.execute('select name,field,value from game_definition where ruleset_id=%s and folder=%s order by name,field,position',
                                                            (self.ruleset_id,folder)):
                table.setdefault(name,{}).setdefault(field,[]).append(value)
            return table
        return self.memo(('definitions',folder),compute)

    @timed_often
    def order(self,folder):
        return self.memo(('order',folder),lambda:[name for name, in self.connection.execute(
            'select name from ruleset_definition where ruleset_id=%s and folder=%s order by position',(self.ruleset_id,folder))])

    def keys(self,kind):
        return self.order(action_folders()[kind])

    @property
    @timed_often
    def methods(self):
        return self.memo('methods',lambda:self.connection.execute(
            'select b.name,g.name,m.name from building_production_method p join building_type b using (building_type) '
            'join production_method_group g using (production_method_group) join production_method m using (production_method) where p.ruleset_id=%s',
            (self.ruleset_id,)).fetchall())

    @property
    @timed_often
    def dlc(self):
        return self.memo('dlc',lambda:[name for name, in self.connection.execute('select name from dlc where ruleset_id=%s',(self.ruleset_id,))])

    def mine(self,table):
        return [ident for ident, in self.rows(table,table,country=self.player)]

    def states(self):
        return self.mine('state')

    def buildings(self):
        def compute():
            owned=set(self.states())
            return [(ident,kind,levels) for ident,kind,state,levels in self.rows('building','building,building_type,state,levels') if state in owned]
        return self.memo('buildings',compute)

    def formations(self,kind=None):
        code={'army':0,'fleet':1}.get(kind)
        manned={formation for formation, in self.rows('combat_unit','formation')}|{fleet for fleet, in self.rows('ship','fleet')}
        return [ident for ident,value in self.rows('formation','formation,formation_type',country=self.player) if (code is None or value==code) and ident in manned]

    def characters(self,*roles):
        mine={ident for ident, in self.rows('character','character',country=self.player)}
        return sorted({ident for ident,role in self.rows('character_assigned_role','character,character_role') if ident in mine and role in roles})

    def characters_roles(self,character):
        return set(self.grouped('character_assigned_role','character,character_role').get(character,()))

    def commanders(self):
        return self.characters('character_role_general','character_role_admiral')

    def countries(self):
        owners={country for country, in self.rows('state','country')}
        return sorted(owners-{self.player,None})

    def plays(self):
        return [ident for ident, in self.rows('diplomatic_play','diplomatic_play')]

    def wars(self):
        return sorted({war for war, in self.rows('war_participant','war',country=self.player)})
