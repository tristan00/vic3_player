import hashlib
import logging
from pathlib import Path
import threading

import psycopg

from ..common import timed
from .spec import CLOSED,ENTITIES,TABLES,VOCABULARIES

DSN='host=127.0.0.1 port=55433 dbname=vic3 user=postgres'
SCHEMA=Path(__file__).parent/'schema.sql'
LOG=logging.getLogger('interface')
SLOT=0xffffff
FIXED={'pact_history':('first_country','second_country'),'treaty_history':('first_country','second_country'),
       'diplomatic_action_history':('first_country','second_country')}
HEARTBEAT=.25


def digest():
    return hashlib.sha256(SCHEMA.read_bytes()).digest()


def install(connection):
    connection.execute('drop schema public cascade')
    connection.execute('create schema public')
    connection.execute(SCHEMA.read_text(encoding='utf-8'))
    connection.execute('insert into schema_digest (digest) values (%s)',(digest(),))


class Layout:
    def __init__(self,table):
        self.table=table
        self.name=table.name
        self.kind=table.kind
        self.owner=table.owner
        self.key_columns=([] if table.owner is None else [None])+table.keys
        self.width=len(self.key_columns)+(1 if self.kind=='sample' else 0)
        self.fields=self.key_columns+table.columns
        self.keys=([] if table.owner is None else [table.owner])+[column.name for column in table.keys]
        self.data=[column.name for column in table.columns]
        self.versioned=self.kind in ('history','child','listing')
        self.columns=self.keys+(['n','date'] if self.kind=='sample' else [])+self.data
        head=['run_id',*self.keys]+(['n'] if self.kind=='sample' else [])+['seq']
        self.names=head+(['date'] if self.kind=='sample' else [])+(['present'] if self.versioned else [])+self.data


class Store:
    def __init__(self,dsn=DSN):
        self.dsn=dsn
        self.connection=psycopg.connect(dsn,autocommit=True)
        self.connection.execute('set synchronous_commit = off')
        stored=self.connection.execute('select digest from schema_digest').fetchone()
        if stored is None or bytes(stored[0])!=digest():
            raise RuntimeError('The database schema differs from schema.sql; reinstall it before writing')
        self.layouts={table.name:Layout(table) for table in TABLES}
        self.vocabulary={name:dict(self.connection.execute(f'select name,{name} from {name}')) for name in VOCABULARIES}
        self.enums={name:{v for v, in self.connection.execute(f'select {name} from {name}')} for name in self.enum_names()}
        self.actions={}
        self.lines=set(self.connection.execute('select direction,line from budget_line').fetchall())
        self.orders=None
        self.definitions=None
        self.methods=None
        self.dlc=None
        self.checks=self.validation()
        self.run_id=None
        self.ruleset_id=None
        self.world_id=None
        self.session=None

    def enum_names(self):
        return sorted({column.enum for table in TABLES for column in table.keys+table.columns if column.enum})

    def validation(self):
        rows=self.connection.execute("""
            select c.conrelid::regclass::text, c.confrelid::regclass::text,
                   array(select a.attname from unnest(c.conkey) with ordinality k(n,i) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n order by k.i),
                   array(select a.attname from unnest(c.confkey) with ordinality k(n,i) join pg_attribute a on a.attrelid=c.confrelid and a.attnum=k.n order by k.i)
            from pg_constraint c where c.connamespace='public'::regnamespace and c.contype='f'""").fetchall()
        checks=[]
        for table,target,columns,keys in rows:
            if table in self.layouts:
                scope='t.run_id = %(run)s and t.seq = %(seq)s'
            elif table in ENTITIES:
                scope='t.run_id = %(run)s and t.first_seq = %(seq)s'
            else:
                continue
            present=' and '.join(f't.{column} is not null' for column in columns)
            match=' and '.join(f'r.{key} = t.{column}' for column,key in zip(columns,keys))
            checks.append((f'{table}({",".join(columns)}) -> {target}',
                           f'select exists (select 1 from {table} t where {scope} and {present} and not exists (select 1 from {target} r where {match}))'))
        return checks

    def copy(self,cursor,name,columns,rows):
        if rows:
            with cursor.copy(f'copy {name} ({",".join(columns)}) from stdin') as copy:
                for row in rows:
                    copy.write_row(row)

    def names(self,vocabulary,names):
        fresh=sorted({name for name in names if name is not None and name not in self.vocabulary[vocabulary]})
        if fresh:
            if vocabulary in CLOSED:
                raise RuntimeError(f'{vocabulary} has no entries {fresh[:5]}')
            self.vocabulary[vocabulary].update(self.connection.execute(
                f'insert into {vocabulary} (name) select unnest(%s::text[]) on conflict (name) do update set name=excluded.name returning name,{vocabulary}',
                (fresh,)).fetchall())
        return [None if name is None else self.vocabulary[vocabulary][name] for name in names]

    def codes(self,enum,values):
        fresh=sorted({value for value in values if value is not None}-self.enums[enum])
        if fresh:
            self.connection.execute(f'insert into {enum} ({enum}) select unnest(%s::int2[]) on conflict do nothing',(fresh,))
            self.enums[enum].update(fresh)

    @timed
    def ruleset(self,identity,members,definitions,event_options,building_methods,dlc,gaps,enums,lines):
        found=self.connection.execute('select ruleset_id from ruleset where digest=%s',(identity,)).fetchone()
        self.members={}
        for vocabulary,folders in VOCABULARIES.items():
            if folders:
                names=[name for folder in folders for name in members[folder]]
                if len(names)!=len(set(names)):
                    raise RuntimeError(f'{vocabulary} repeats names across {folders}')
                self.members[vocabulary]=set(names)
                fresh=sorted(set(names)-set(self.vocabulary[vocabulary]))
                if fresh:
                    self.vocabulary[vocabulary].update(self.connection.execute(
                        f'insert into {vocabulary} (name) select unnest(%s::text[]) on conflict (name) do update set name=excluded.name returning name,{vocabulary}',
                        (fresh,)).fetchall())
        for enum,labels in enums.items():
            known=dict(self.connection.execute(f'select {enum},name from {enum}'))
            clash={value:(known[value],name) for value,name in labels.items() if known.get(value) not in (None,name)}
            if clash:
                raise RuntimeError(f'{enum} codes renamed: {clash}')
            self.connection.execute(f'insert into {enum} ({enum},name) select * from unnest(%s::int2[],%s::text[]) on conflict ({enum}) do update set name=excluded.name',
                                    (list(labels),list(labels.values())))
            self.enums[enum].update(labels)
        self.connection.execute('insert into budget_line (direction,line,name) select * from unnest(%s::text[],%s::int2[],%s::text[]) '
                                'on conflict (direction,line) do update set name=excluded.name',
                                ([d for d,_,_ in lines],[n for _,n,_ in lines],[name for _,_,name in lines]))
        self.lines.update((d,n) for d,n,_ in lines)
        if found:
            self.ruleset_id=found[0]
            return self.ruleset_id
        with self.connection.transaction(),self.connection.cursor() as cursor:
            ruleset_id=cursor.execute('insert into ruleset (digest) values (%s) returning ruleset_id',(identity,)).fetchone()[0]
            self.copy(cursor,'ruleset_definition',('ruleset_id','folder','position','name'),
                      [(ruleset_id,folder,position,name) for folder,names in members.items() for position,name in enumerate(names)])
            self.copy(cursor,'game_definition',('ruleset_id','folder','name','field','position','value'),[(ruleset_id,*row) for row in definitions])
            self.copy(cursor,'event_definition_option',('ruleset_id','event_type','option','name','has_trigger','default_option'),
                      [(ruleset_id,self.vocabulary['event_type'][event],option,name,bool(trigger),bool(default)) for event,option,name,trigger,default in event_options])
            self.copy(cursor,'building_production_method',('ruleset_id','building_type','production_method_group','production_method'),
                      [(ruleset_id,self.vocabulary['building_type'][b],self.vocabulary['production_method_group'][g],self.vocabulary['production_method'][m])
                       for b,g,m in building_methods])
            self.copy(cursor,'dlc',('ruleset_id','name'),[(ruleset_id,name) for name in dlc])
            self.copy(cursor,'capture_gap',('ruleset_id','kind','subject','detail'),[(ruleset_id,*row) for row in gaps])
        self.ruleset_id=ruleset_id
        return ruleset_id

    @timed
    def world(self,identity,provinces,adjacencies,assets):
        digest_bytes=bytes.fromhex(identity)
        found=self.connection.execute('select world_id from world where digest=%s',(digest_bytes,)).fetchone()
        if found:
            self.world_id=found[0]
            return self.world_id
        regions=self.names('state_region',[p['region'] for p in provinces])
        terrains=self.names('terrain',[p['terrain'] for p in provinces])
        with self.connection.transaction(),self.connection.cursor() as cursor:
            world_id=cursor.execute('insert into world (digest) values (%s) returning world_id',(digest_bytes,)).fetchone()[0]
            self.copy(cursor,'world_asset',('world_id','name','data'),[(world_id,name,content) for name,content in assets.items()])
            self.copy(cursor,'world_province',('world_id','color','state_region','terrain','area_pixels','x','y'),
                      [(world_id,int(p['color'][1:],16),region,terrain,p['area_pixels'],p['x'],p['y']) for p,region,terrain in zip(provinces,regions,terrains)])
            self.copy(cursor,'world_adjacency',('world_id','first_color','second_color','shared_border_pixels'),
                      [(world_id,*sorted((int(e['first'][1:],16),int(e['second'][1:],16))),e['shared_border_pixels']) for e in adjacencies])
        self.world_id=world_id
        return world_id

    def begin_run(self,started_at,kind,advisors=(),**generated):
        lost=self.connection.execute("update run set ended_at=heartbeat_at,end_reason='loop_lost' where ended_at is null returning run_id,heartbeat_at").fetchall()
        for run_id,heartbeat_at in lost:
            LOG.error('RUN %s WAS LOST: its loop last beat at %s UTC',run_id,heartbeat_at)
        self.pending={'started_at':started_at,'kind':kind,'advisors':list(advisors),**generated}
        self.run_id=None
        self.constants=None
        self.seq=0
        self.beater=None
        self.anchored={entity:set() for entity in ENTITIES}
        self.previous={}
        self.samples={}
        self.fixed={}

    def open_run(self,cursor,constants):
        pending=self.pending
        tag=self.names('country_definition',[pending.get('tag')])[0]
        run_id=cursor.execute('insert into run (kind,source_session,started_at,heartbeat_at,world_id,ruleset_id,player_country,game_speed,first_start,'
                              'custom_rng_seed,tag,world_file,cli_seed) values (%s,%s,%s,now(),%s,%s,%s,%s,%s,%s,%s,%s,%s) returning run_id',
                              (pending['kind'],self.session,pending['started_at'],self.world_id,self.ruleset_id,constants['player_country'],
                               constants['game_speed'],constants['first_start'],constants['custom_rng_seed'],tag,pending.get('world'),pending.get('cli_seed'))).fetchone()[0]
        if pending['kind']!='attached':
            cursor.execute('insert into run_generated (run_id,kind,run_seed,years,minutes,profile,pool,journal) values (%s,%s,%s,%s,%s,%s,%s,%s)',
                           (run_id,pending['kind'],pending['run_seed'],pending['years'],pending['minutes'],pending['profile'],pending['pool'],pending['journal']))
        self.copy(cursor,'run_advisor',('run_id','position','advisor'),enumerate_rows(run_id,self.names('advisor',pending['advisors'])))
        self.copy(cursor,'run_game_rule',('run_id','game_rule_setting'),[(run_id,rule) for rule in self.names('game_rule_setting',constants['game_rules'])])
        self.run_id=run_id
        self.constants=constants

    def live(self,rows):
        live={}
        for entity in ENTITIES:
            idents=[row[0] for row in rows.get(entity+'_history',())]
            slots={ident&SLOT:ident for ident in idents}
            if len(slots)!=len(idents):
                raise RuntimeError(f'{entity} lists a slot twice')
            live[entity]=slots
        return live

    def resolve(self,layout,rows,live):
        offset=len(layout.key_columns)+(2 if layout.kind=='sample' else 0)
        fields=list(enumerate(layout.key_columns))+[(offset+i,c) for i,c in enumerate(layout.table.columns)]
        out=[]
        for row in rows:
            if len(row)!=offset+len(layout.table.columns):
                raise RuntimeError(f'{layout.name} row has {len(row)} values, not {offset+len(layout.table.columns)}')
            values=list(row)
            for index,column in fields:
                if column is None:
                    values[index]=identity(live,layout.owner,values[index],layout.name,layout.owner)
                    continue
                value=values[index]
                if value is not None and value in column.sentinels:
                    value=None
                if column.entity and value is not None:
                    value=loose_identity(live,column.entity,value) if column.loose else identity(live,column.entity,value,layout.name,column.name)
                if column.vocabulary and value is not None and column.vocabulary in CLOSED and value not in self.members[column.vocabulary]:
                    raise RuntimeError(f'{layout.name}.{column.name}: {value} is not a {column.vocabulary} of this ruleset')
                values[index]=value
            out.append(tuple(values))
        return out

    def stored(self,layout,rows):
        converted=[list(row) for row in rows]
        if layout.name=='player_budget_line':
            fresh=sorted({(row[0],row[1]) for row in converted}-self.lines)
            if fresh:
                self.connection.execute('insert into budget_line (direction,line) select * from unnest(%s::text[],%s::int2[]) on conflict do nothing',
                                        ([d for d,_ in fresh],[l for _,l in fresh]))
                self.lines.update(fresh)
        offset=len(layout.key_columns)+(3 if layout.kind=='sample' else 1 if layout.versioned else 0)
        positions=[(i,c) for i,c in enumerate(layout.key_columns) if c is not None]+[(offset+i,c) for i,c in enumerate(layout.table.columns)]
        for index,column in positions:
            if column.vocabulary:
                for row,value in zip(converted,self.names(column.vocabulary,[row[index] for row in converted])):
                    row[index]=value
            elif column.enum:
                self.codes(column.enum,[row[index] for row in converted])
        return converted

    def versions(self,layout,rows,seq,present):
        width=len(layout.key_columns)
        current={}
        for row in rows:
            key=row[:width]
            if key in current:
                raise RuntimeError(f'{layout.name} holds key {key} twice at snapshot {seq}')
            current[key]=row[width:]
        previous=self.previous.get(layout.name,{})
        if layout.kind=='subject':
            orphans=[key for key in current if key[0] not in present[layout.owner]]
            if orphans:
                raise RuntimeError(f'{layout.name} has rows for absent owners {orphans[:5]}')
            vanished=[key for key in previous if key not in current and key[0] in present[layout.owner]]
            if vanished:
                raise RuntimeError(f'{layout.name} lost rows of live owners {vanished[:5]}')
            return [(*key,*data) for key,data in current.items() if previous.get(key)!=data],current
        if layout.kind=='singleton':
            if list(current)!=[()]:
                raise RuntimeError(f'{layout.name} is a singleton but holds {len(current)} rows')
            return [current[()]] if previous.get(())!=current[()] else [],current
        changed=[(*key,True,*data) for key,data in current.items() if previous.get(key)!=data]
        gone=[(*key,False,*[None]*len(layout.data)) for key in previous if key not in current]
        return changed+gone,current

    def fresh_samples(self,layout,rows):
        known=self.samples.setdefault(layout.name,{})
        width=layout.width
        fresh=[]
        for row in rows:
            key,value=row[:width],row[width:]
            seen=known.get(key)
            if seen is None:
                known[key]=value
                fresh.append(row)
            elif seen[1:]!=value[1:]:
                raise RuntimeError(f'{layout.name} sample {key} changed from {seen} to {value}')
        return fresh

    def check_fixed(self,layout,rows):
        columns=FIXED.get(layout.name)
        if columns is None:
            return
        indexes=[layout.columns.index(name) for name in columns]
        known=self.fixed.setdefault(layout.name,{})
        for row in rows:
            values=tuple(row[i] for i in indexes)
            if known.setdefault(row[0],values)!=values:
                raise RuntimeError(f'{layout.name} {row[0]} changed {columns} from {known[row[0]]} to {values}')

    @timed
    def write(self,built,phase,taken_at,read_ms):
        seq=self.seq
        live=self.live(built.rows)
        present={entity:set(slots.values()) for entity,slots in live.items()}
        colors={identity(live,'province',province,'province','color'):color for province,color in built.colors.items()}
        if set(colors)!=present['province']:
            raise RuntimeError('Province colours and captured provinces differ')
        resolved={}
        for name,rows in built.rows.items():
            layout=self.layouts[name]
            resolved[name]=self.resolve(layout,rows,live)
            self.check_fixed(layout,resolved[name])
        missing=set(self.layouts)-set(resolved)
        if missing:
            raise RuntimeError(f'The capture built no rows for {sorted(missing)}')
        staged={}
        for name,rows in resolved.items():
            layout=self.layouts[name]
            if layout.kind=='sample':
                fresh=self.fresh_samples(layout,rows)
                staged[name]=([(*row[:layout.width],seq,*row[layout.width:]) for row in fresh],None)
            else:
                out,current=self.versions(layout,rows,seq,present)
                staged[name]=(out,current)
        anchors={entity:sorted(idents-self.anchored[entity]) for entity,idents in present.items()}
        with self.connection.transaction(),self.connection.cursor() as cursor:
            if self.run_id is None:
                self.open_run(cursor,built.constants)
            elif built.constants!=self.constants:
                raise RuntimeError(f'Run constants changed from {self.constants} to {built.constants}')
            meta=built.meta
            cursor.execute('insert into snapshot (run_id,seq,phase,game_date,taken_at,read_ms,local_date_time,paused,speed,ui_panel_open,ui_interaction_open,'
                           'ui_map_list_open) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (self.run_id,seq,phase,meta['game_date'],taken_at,read_ms,meta['local_date_time'],meta['paused'],meta['speed'],meta['ui_panel_open'],
                            meta['ui_interaction_open'],meta['ui_map_list_open']))
            cursor.execute('set local session_replication_role = replica')
            for entity,idents in anchors.items():
                if entity=='province':
                    self.copy(cursor,'province',('run_id','province','first_seq','world_id','color'),
                              [(self.run_id,ident,seq,self.world_id,colors[ident]) for ident in idents])
                else:
                    self.copy(cursor,entity,('run_id',entity,'first_seq'),[(self.run_id,ident,seq) for ident in idents])
            for name,(rows,_) in staged.items():
                layout=self.layouts[name]
                stored=self.stored(layout,rows)
                if layout.kind=='sample':
                    self.copy(cursor,name,layout.names,[(self.run_id,*row) for row in stored])
                else:
                    width=len(layout.keys)
                    self.copy(cursor,name,layout.names,[(self.run_id,*row[:width],seq,*row[width:]) for row in stored])
            self.validate(cursor,seq)
        for entity,idents in anchors.items():
            self.anchored[entity].update(idents)
        for name,(_,current) in staged.items():
            if current is not None:
                self.previous[name]=current
        self.seq+=1
        return seq

    @timed
    def validate(self,cursor,seq):
        broken=[label for label,sql in self.checks if cursor.execute(sql,{'run':self.run_id,'seq':seq}).fetchone()[0]]
        if broken:
            raise RuntimeError(f'Snapshot {seq} breaks foreign keys: {broken[:5]}')

    def log_action(self,entry,after):
        action=self.names('action',[entry['action']])[0]
        advisor=self.names('advisor',[entry['advisor']])[0]
        kinds={name:'integer' if isinstance(value,int) else 'text' for name,value in entry['params'].items()}
        with self.connection.transaction(),self.connection.cursor() as cursor:
            known=self.actions.setdefault(action,dict(cursor.execute('select name,value_kind from action_parameter where action=%s',(action,)).fetchall()))
            for name,kind in kinds.items():
                if known.get(name,kind)!=kind:
                    raise RuntimeError(f'{entry["action"]}.{name} is {known[name]}, not {kind}')
                if name not in known:
                    cursor.execute('insert into action_parameter (action,name,value_kind) values (%s,%s,%s)',(action,name,kind))
                    known[name]=kind
            cursor.execute('insert into loop_action (run_id,n,turn,advisor,action,before_seq,after_seq,status,detail,ms,logged_at) '
                           'values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())',
                           (self.run_id,entry['seq'],entry['turn'],advisor,action,entry['snapshot'],after,entry['status'],entry.get('detail'),entry.get('ms')))
            self.copy(cursor,'loop_action_param',('run_id','n','action','name','integer_value','text_value'),
                      [(self.run_id,entry['seq'],action,name,value if kinds[name]=='integer' else None,None if kinds[name]=='integer' else str(value))
                       for name,value in entry['params'].items()])

    def start_heartbeat(self):
        self.beating=threading.Event()
        self.beater=threading.Thread(target=self.beat,daemon=True,name='heartbeat')
        self.beater.start()

    def beat(self):
        with psycopg.connect(self.dsn,autocommit=True) as connection:
            while not self.beating.wait(HEARTBEAT):
                connection.execute('update run set heartbeat_at=now() where run_id=%s',(self.run_id,))

    def flag_game_exit(self,exited_at):
        with psycopg.connect(self.dsn,autocommit=True) as connection:
            connection.execute("update run set ended_at=now(),end_reason='game_crashed',game_exited_at=%s where run_id=%s and ended_at is null",
                               (exited_at,self.run_id))

    def end_run(self,reason,game_exited_at=None):
        if self.beater is not None:
            self.beating.set()
            self.beater.join()
            self.beater=None
        self.connection.execute('update run set ended_at=now(),end_reason=%s,game_exited_at=%s where run_id=%s and ended_at is null',
                                (reason,game_exited_at,self.run_id))


def enumerate_rows(run_id,values):
    return [(run_id,position,value) for position,value in enumerate(values)]


def loose_identity(live,entity,value):
    ident=live[entity].get(value&SLOT)
    return None if ident is None or (value>SLOT and value!=ident) else ident


def identity(live,entity,value,table,column):
    ident=live[entity].get(value&SLOT)
    if ident is None or (value>SLOT and value!=ident):
        raise RuntimeError(f'{table}.{column} refers to {entity} {value}, which this snapshot did not capture')
    return ident
