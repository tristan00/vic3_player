from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging
from pathlib import Path
import psycopg

from ..common import evidence, progress, timed, timed_often
from ..timing import COLUMNS, INTERVAL_COLUMNS, RECORDER
from .spec import CLOSED,ENTITIES,TABLES,VOCABULARIES

DSN='host=127.0.0.1 port=55433 dbname=vic3 user=postgres'
SCHEMA=Path(__file__).parent/'schema.sql'
LOG=logging.getLogger('interface')
SLOT=0xffffff
FIXED={'pact_history':('first_country','second_country'),'treaty_history':('first_country','second_country'),
       'diplomatic_action_history':('first_country','second_country')}
ANALYZERS=8
COHERENCE_TEXT={'type','country','state_region'}


@timed_often
def digest():
    return hashlib.sha256(SCHEMA.read_bytes()).digest()


@timed
def install(connection):
    connection.execute('drop schema public cascade')
    connection.execute('create schema public')
    connection.execute(SCHEMA.read_text(encoding='utf-8'))
    connection.execute('insert into schema_digest (digest) values (%s)',(digest(),))


class Layout:
    @timed_often
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
        offset=len(self.key_columns)+(2 if self.kind=='sample' else 0)
        self.length=offset+len(table.columns)
        placed=list(enumerate(self.key_columns))+[(offset+position,column) for position,column in enumerate(table.columns)]
        self.checked=[(index,column) for index,column in placed if column is None or column.sentinels or column.entity or column.vocabulary in CLOSED]


class Store:
    @timed
    def __init__(self,dsn=DSN):
        self.dsn=dsn
        self.connection=psycopg.connect(dsn,autocommit=True,prepare_threshold=None)
        self.connection.execute('set synchronous_commit = off')
        stored=self.connection.execute('select digest from schema_digest').fetchone()
        if stored is None or bytes(stored[0])!=digest():
            raise RuntimeError(evidence(database=stored and bytes(stored[0]).hex(),schema_sql=digest().hex()))
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
        self.connection.prepared_max=len(self.checks)
        self.run_id=None
        self.ruleset_id=None
        self.world_id=None
        self.session=None

    @timed_often
    def enum_names(self):
        return sorted({column.enum for table in TABLES for column in table.keys+table.columns if column.enum})

    @timed
    def validation(self):
        rows=self.connection.execute("""
            select c.conrelid::regclass::text, c.confrelid::regclass::text,
                   array(select a.attname from unnest(c.conkey) with ordinality k(n,i) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n order by k.i),
                   array(select format_type(a.atttypid,a.atttypmod) from unnest(c.conkey) with ordinality k(n,i) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n order by k.i),
                   array(select a.attname from unnest(c.confkey) with ordinality k(n,i) join pg_attribute a on a.attrelid=c.confrelid and a.attnum=k.n order by k.i)
            from pg_constraint c where c.connamespace='public'::regnamespace and c.contype='f'""").fetchall()
        checks=[]
        for table,target,columns,kinds,keys in rows:
            if table not in self.layouts and table not in ENTITIES:
                continue
            given=','.join(f'%s::{kind}[]' for kind in kinds)
            match=' and '.join(f'r.{key} = v.c{position}' for position,key in enumerate(keys))
            checks.append((table,f'{table}({",".join(columns)}) -> {target}',columns,
                           f'select exists (select 1 from unnest({given}) v({",".join(f"c{position}" for position in range(len(keys)))}) '
                           f'where not exists (select 1 from {target} r where {match}))'))
        return checks

    @timed_often
    def copy(self,cursor,name,columns,rows):
        progress(f'copy {name}')
        if rows:
            with cursor.copy(f'copy {name} ({",".join(columns)}) from stdin') as copy:
                for row in rows:
                    copy.write_row(row)

    @timed_often
    def names(self,vocabulary,names):
        fresh=sorted({name for name in names if name is not None and name not in self.vocabulary[vocabulary]})
        if fresh:
            if vocabulary in CLOSED:
                raise RuntimeError(evidence(vocabulary=vocabulary,fresh=fresh[:5]))
            self.vocabulary[vocabulary].update(self.connection.execute(
                f'insert into {vocabulary} (name) select unnest(%s::text[]) on conflict (name) do update set name=excluded.name returning name,{vocabulary}',
                (fresh,)).fetchall())
        return [None if name is None else self.vocabulary[vocabulary][name] for name in names]

    @timed_often
    def codes(self,enum,values):
        fresh=sorted({value for value in values if value is not None}-self.enums[enum])
        if fresh:
            self.connection.execute(f'insert into {enum} ({enum}) select unnest(%s::int2[]) on conflict do nothing',(fresh,))
            self.enums[enum].update(fresh)

    @timed
    def ruleset(self,identity,members,definitions,event_options,event_effects,building_methods,dlc,gaps,enums,lines,effects):
        found=self.connection.execute('select ruleset_id from ruleset where digest=%s',(identity,)).fetchone()
        self.members={}
        for vocabulary,folders in VOCABULARIES.items():
            if folders:
                names=[name for folder in folders for name in members[folder]]
                if len(names)!=len(set(names)):
                    raise RuntimeError(evidence(vocabulary=vocabulary,folders=folders))
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
                raise RuntimeError(evidence(enum=enum,clash=clash))
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
            self.copy(cursor,'event_definition_option_effect',('ruleset_id','event_type','option','position','effect','detail'),
                      [(ruleset_id,self.vocabulary['event_type'][event],option,position,effect,detail) for event,option,position,effect,detail in event_effects])
            self.copy(cursor,'building_production_method',('ruleset_id','building_type','production_method_group','production_method'),
                      [(ruleset_id,self.vocabulary['building_type'][b],self.vocabulary['production_method_group'][g],self.vocabulary['production_method'][m])
                       for b,g,m in building_methods])
            self.method_effects(cursor,ruleset_id,effects)
            self.copy(cursor,'dlc',('ruleset_id','name'),[(ruleset_id,name) for name in dlc])
            self.copy(cursor,'capture_gap',('ruleset_id','kind','subject','detail'),[(ruleset_id,*row) for row in gaps])
        self.ruleset_id=ruleset_id
        return ruleset_id

    @timed
    def method_effects(self,cursor,ruleset_id,effects):
        words=self.vocabulary
        self.copy(cursor,'production_method_goods',('ruleset_id','production_method','goods','direction','scaling','amount'),
                  [(ruleset_id,words['production_method'][m],words['goods'][g],d,s,v) for m,g,d,s,v in effects['goods']])
        self.copy(cursor,'production_method_employment',('ruleset_id','production_method','pop_type','scaling','amount'),
                  [(ruleset_id,words['production_method'][m],words['pop_type'][p],s,v) for m,p,s,v in effects['employment']])
        self.copy(cursor,'production_method_modifier',('ruleset_id','production_method','target','scaling','modifier','value'),
                  [(ruleset_id,words['production_method'][m],*rest) for m,*rest in effects['modifiers']])
        self.copy(cursor,'production_method_requirement',('ruleset_id','production_method','kind','key'),
                  [(ruleset_id,words['production_method'][m],k,key) for m,k,key in effects['requirements']])
        self.copy(cursor,'production_method_profession_ratio',('ruleset_id','production_method','pop_type','ratio'),
                  [(ruleset_id,words['production_method'][m],words['pop_type'][p],r) for m,p,r in effects['ratios']])

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
            for name,content in assets.items():
                self.copy(cursor,'world_asset',('world_id','name','data'),[(world_id,name,content)])
            self.copy(cursor,'world_province',('world_id','color','state_region','terrain','area_pixels','x','y'),
                      [(world_id,int(p['color'][1:],16),region,terrain,p['area_pixels'],p['x'],p['y']) for p,region,terrain in zip(provinces,regions,terrains)])
            self.copy(cursor,'world_adjacency',('world_id','first_color','second_color','shared_border_pixels'),
                      [(world_id,*sorted((int(e['first'][1:],16),int(e['second'][1:],16))),e['shared_border_pixels']) for e in adjacencies])
        self.world_id=world_id
        return world_id

    @timed
    def recent_tags(self,count):
        return [name for name, in self.connection.execute('select d.name from run r join country_definition d on d.country_definition=r.tag order by run_id desc limit %s',(count,))]

    @timed
    def begin_run(self,started_at,kind,advisors,tag,world,cli_seed,run_seed,years,minutes,profile,pool,runs_requested,generated,weights,centres,sizer,picker,candidates,objective,proposal=None,size_model=None,pick_model=None):
        self.connection.execute("update run set ended_at=heartbeat_at,end_reason='loop_lost' where ended_at is null")
        self.pending={'started_at':started_at,'kind':kind,'advisors':list(advisors),'tag':tag,'world':world,'cli_seed':cli_seed,'run_seed':run_seed,'years':years,'minutes':minutes,'profile':profile,'pool':pool,
                      'runs_requested':runs_requested,'generated':generated,'weights':dict(weights),'centres':dict(centres),
                      'sizer':sizer,'picker':picker,'candidates':candidates,'objective':objective,'proposal':proposal,'size_model':size_model,'pick_model':pick_model}
        self.run_id=self.constants=None
        self.seq=0
        self.anchored={entity:set() for entity in ENTITIES}
        self.previous,self.samples,self.fixed={},{},{}

    @timed
    def open_run(self,cursor,constants):
        pending=self.pending
        tag=self.names('country_definition',[pending['tag']])[0]
        run_id=cursor.execute('insert into run (run_id,kind,source_session,started_at,heartbeat_at,progress_at,progress_step,world_id,ruleset_id,player_country,'
                              'game_speed,first_start,custom_rng_seed,tag,world_file,cli_seed,run_seed,years,minutes,profile,pool,runs_requested,'
                              'world_seed,countries,states,pop,concentration,landmasses,climate,relief,density,diversity,diplomacy,ideology,sizer,picker,candidates,objective_gdp,objective_population,objective_sol,objective_alpha,objective_stock) '
                              'values ((select coalesce(max(run_id),0)+1 from run),%s,%s,%s,now(),now(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning run_id',
                              (pending['kind'],self.session,pending['started_at'],'open_run',self.world_id,self.ruleset_id,constants['player_country'],
                               constants['game_speed'],constants['first_start'],constants['custom_rng_seed'],tag,pending['world'],pending['cli_seed'],
                               pending['run_seed'],pending['years'],pending['minutes'],pending['profile'],pending['pool'],pending['runs_requested'],
                               *[None if pending['generated'] is None else pending['generated'][k] for k in ('seed','countries','states','pop','concentration','landmasses','climate','relief','density','diversity','diplomacy','ideology')],pending['sizer'],pending['picker'],pending['candidates'],pending['objective'][0]['gdp'],pending['objective'][0]['population'],pending['objective'][0]['sol'],pending['objective'][1],pending['objective'][0]['stock'])).fetchone()[0]
        names=sorted(pending['weights'])
        self.copy(cursor,'run_weight',('run_id','advisor_action','weight','centre'),
                  [(run_id,action,pending['weights'][name],pending['centres'].get(name)) for name,action in zip(names,self.names('advisor_action',names))])
        self.copy(cursor,'run_advisor',('run_id','position','advisor'),enumerate_rows(run_id,self.names('advisor',pending['advisors'])))
        if pending['proposal'] is not None:
            {'random_forest_weighting':self.record_forest_proposal,'random_svr_weighting':self.record_svr_proposal}[pending['proposal']['initializer']](cursor,run_id,pending['proposal'])
        for step in ('size','pick'):
            if pending[step+'_model'] is not None:
                pauses,runs,seconds,params,importance=pending[step+'_model']
                cursor.execute(f'insert into {step}_model (run_id,pauses,runs,seconds,{",".join(params)}) values ({",".join(["%s"]*(4+len(params)))})',(run_id,pauses,runs,seconds,*params.values()))
                self.copy(cursor,step+'_importance',('run_id','feature','importance'),[(run_id,feature,value) for feature,value in importance])
        self.copy(cursor,'run_game_rule',('run_id','game_rule_setting'),[(run_id,rule) for rule in self.names('game_rule_setting',constants['game_rules'])])
        self.run_id=run_id
        self.constants=constants

    @timed
    def record_size(self,seq,predictions,chosen):
        with self.connection.cursor() as cursor:
            self.copy(cursor,'size_candidate',('run_id','seq','actions','predicted_change','chosen'),
                      [(self.run_id,seq,length,predicted,length==chosen) for length,predicted in predictions])

    @timed
    def record_pick(self,seq,batches,predictions,chosen):
        with self.connection.cursor() as cursor:
            self.copy(cursor,'pick_candidate',('run_id','seq','candidate','actions','predicted_change','chosen'),
                      [(self.run_id,seq,index,len(batch),predicted,index==chosen) for index,(batch,predicted) in enumerate(zip(batches,predictions))])
            names=[name for batch in batches for name in batch]
            codes=iter(self.names('advisor_action',names))
            self.copy(cursor,'pick_candidate_action',('run_id','seq','candidate','position','advisor_action'),
                      [(self.run_id,seq,index,position,next(codes)) for index,batch in enumerate(batches) for position,_ in enumerate(batch)])

    @timed
    def record_forest_proposal(self,cursor,run_id,proposal):
        cursor.execute('insert into forest_proposal (run_id,reward,method,observations,best_reward,predicted_reward,uncertainty,expected_improvement,beat_probability,candidates,seconds) '
                       'values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                       (run_id,proposal['reward'],proposal['method'],proposal['observations'],proposal['best_reward'],proposal['predicted_reward'],proposal['uncertainty'],
                        proposal['expected_improvement'],proposal['beat_probability'],proposal['candidates'],proposal['seconds']))
        self.copy(cursor,'forest_observation',('run_id','observed_run','reward'),[(run_id,observed,reward) for observed,reward in proposal['observed']])
        self.copy(cursor,'forest_candidate',('run_id','rank','predicted_reward','uncertainty','expected_improvement','beat_probability'),
                  [(run_id,*row) for row in proposal['candidate_rows']])
        self.copy(cursor,'forest_importance',('run_id','dimension','importance'),[(run_id,name,value) for name,value in proposal['importance']])

    @timed
    def record_svr_proposal(self,cursor,run_id,proposal):
        cursor.execute('insert into svr_proposal (run_id,method,observations,c,epsilon,predicted_reward,bounded,seconds) values (%s,%s,%s,%s,%s,%s,%s,%s)',
                       (run_id,proposal['method'],proposal['observations'],proposal['c'],proposal['epsilon'],proposal['predicted_reward'],proposal['bounded'],proposal['seconds']))
        self.copy(cursor,'svr_observation',('run_id','observed_run','reward','normalized_reward','draws'),[(run_id,*row) for row in proposal['observed']])
        self.copy(cursor,'svr_coefficient',('run_id','dimension','linear','squared','chosen'),[(run_id,*row) for row in proposal['coefficients']])

    @timed_often
    def live(self,rows):
        live={}
        for entity in ENTITIES:
            idents=[row[0] for row in rows.get(entity+'_history',())]
            slots={ident&SLOT:ident for ident in idents}
            if len(slots)!=len(idents):
                raise RuntimeError(evidence(entity=entity,idents=len(idents),slots=len(slots)))
            live[entity]=slots
        return live

    @timed_often
    def resolve(self,layout,rows,live,referenced):
        out=[]
        for row in rows:
            if len(row)!=layout.length:
                raise RuntimeError(evidence(table=layout.name,values=len(row),length=layout.length))
            values=list(row)
            for index,column in layout.checked:
                if column is None:
                    values[index]=identity(live,layout.owner,values[index],layout.name,layout.owner)
                    continue
                value=values[index]
                if value is not None and value in column.sentinels:
                    value=None
                if column.entity and value is not None:
                    if column.entity=='province':
                        value=identity(live,'province',value,layout.name,column.name)
                    else:
                        referenced[column.entity].add(value)
                if column.vocabulary and value is not None and column.vocabulary in CLOSED and value not in self.members[column.vocabulary]:
                    raise RuntimeError(evidence(table=layout.name,column=column.name,value=value,vocabulary=column.vocabulary))
                values[index]=value
            out.append(tuple(values))
        return out

    @timed_often
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

    @timed_often
    def versions(self,layout,rows,seq,present):
        width=len(layout.key_columns)
        current={}
        for row in rows:
            key=row[:width]
            if key in current:
                raise RuntimeError(evidence(table=layout.name,key=key,seq=seq))
            current[key]=row[width:]
        previous=self.previous.get(layout.name,{})
        if layout.kind=='subject':
            orphans=[key for key in current if key[0] not in present[layout.owner]]
            if orphans:
                raise RuntimeError(evidence(table=layout.name,orphans=orphans[:5]))
            vanished=[key for key in previous if key not in current and key[0] in present[layout.owner]]
            if vanished:
                raise RuntimeError(evidence(table=layout.name,vanished=vanished[:5]))
            return [(*key,*data) for key,data in current.items() if previous.get(key)!=data],current
        if layout.kind=='singleton':
            if list(current)!=[()]:
                raise RuntimeError(evidence(table=layout.name,rows=len(current)))
            return [current[()]] if previous.get(())!=current[()] else [],current
        changed=[(*key,True,*data) for key,data in current.items() if previous.get(key)!=data]
        gone=[(*key,False,*[None]*len(layout.data)) for key in previous if key not in current]
        return changed+gone,current

    @timed_often
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
                raise RuntimeError(evidence(table=layout.name,key=key,seen=seen,value=value))
        return fresh

    @timed_often
    def check_fixed(self,layout,rows):
        columns=FIXED.get(layout.name)
        if columns is None:
            return
        indexes=[layout.columns.index(name) for name in columns]
        known=self.fixed.setdefault(layout.name,{})
        for row in rows:
            values=tuple(row[i] for i in indexes)
            if known.setdefault(row[0],values)!=values:
                raise RuntimeError(evidence(table=layout.name,key=row[0],columns=columns,known=known[row[0]],values=values))

    @timed
    def write(self,built,phase,taken_at,read_ms):
        seq=self.seq
        live=self.live(built.rows)
        present={entity:set(slots.values()) for entity,slots in live.items()}
        colors={identity(live,'province',province,'province','color'):color for province,color in built.colors.items()}
        if set(colors)!=present['province']:
            raise RuntimeError(evidence(colors=len(colors),provinces=len(present['province']),differing=sorted(set(colors)^present['province'])[:5]))
        resolved={}
        referenced=defaultdict(set)
        for name,rows in built.rows.items():
            progress(f'resolve {name}')
            layout=self.layouts[name]
            resolved[name]=self.resolve(layout,rows,live,referenced)
            self.check_fixed(layout,resolved[name])
        missing=set(self.layouts)-set(resolved)
        if missing:
            raise RuntimeError(evidence(missing=sorted(missing)))
        staged={}
        for name,rows in resolved.items():
            progress(f'stage {name}')
            layout=self.layouts[name]
            if layout.kind=='sample':
                fresh=self.fresh_samples(layout,rows)
                staged[name]=([(*row[:layout.width],seq,*row[layout.width:]) for row in fresh],None)
            else:
                out,current=self.versions(layout,rows,seq,present)
                staged[name]=(out,current)
        anchors={entity:sorted((idents|referenced[entity])-self.anchored[entity]) for entity,idents in present.items()}
        opening=self.run_id is None
        with self.connection.transaction(),self.connection.cursor() as cursor:
            if opening:
                self.open_run(cursor,built.constants)
            elif built.constants!=self.constants:
                raise RuntimeError(evidence(held=self.constants,built=built.constants))
            meta=built.meta
            cursor.execute('insert into snapshot (run_id,seq,phase,game_date,taken_at,read_ms,local_date_time,paused,speed,ui_panel_open,ui_interaction_open,'
                           'ui_map_list_open) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (self.run_id,seq,phase,meta['game_date'],taken_at,read_ms,meta['local_date_time'],meta['paused'],meta['speed'],meta['ui_panel_open'],
                            meta['ui_interaction_open'],meta['ui_map_list_open']))
            cursor.execute('set local session_replication_role = replica')
            written={}
            for entity,idents in anchors.items():
                if entity=='province':
                    written[entity]=(('run_id','province','first_seq','world_id','color'),[(self.run_id,ident,seq,self.world_id,colors[ident]) for ident in idents])
                else:
                    written[entity]=(('run_id',entity,'first_seq'),[(self.run_id,ident,seq) for ident in idents])
            for name,(rows,_) in staged.items():
                progress(f'convert {name}')
                layout=self.layouts[name]
                stored=self.stored(layout,rows)
                if layout.kind=='sample':
                    written[name]=(layout.names,[(self.run_id,*row) for row in stored])
                else:
                    width=len(layout.keys)
                    written[name]=(layout.names,[(self.run_id,*row[:width],seq,*row[width:]) for row in stored])
            for name,(columns,rows) in written.items():
                self.copy(cursor,name,columns,rows)
            self.record_timing(cursor,seq)
            self.validate(cursor,seq,written)
            cursor.execute('update run set heartbeat_at=clock_timestamp(),progress_at=clock_timestamp(),progress_step=%s where run_id=%s',(phase,self.run_id))
        if opening:
            self.analyze([name for name,(_,rows) in written.items() if rows])
        for entity,idents in anchors.items():
            self.anchored[entity].update(idents)
        for name,(_,current) in staged.items():
            if current is not None:
                self.previous[name]=current
        self.seq+=1
        return seq

    @timed
    def record_timing(self,cursor,seq=None):
        cursor.execute('delete from run_timing where run_id=%s',(self.run_id,))
        self.copy(cursor,'run_timing',('run_id',*COLUMNS),[(self.run_id,*row) for row in RECORDER.totals()])
        if seq is not None:
            self.copy(cursor,'snapshot_timing',('run_id','seq',*INTERVAL_COLUMNS),[(self.run_id,seq,*row) for row in RECORDER.drain()])

    @timed
    def analyze(self,tables):
        with ThreadPoolExecutor(ANALYZERS) as pool:
            list(pool.map(self.analyze_batch,[tables[start::ANALYZERS] for start in range(ANALYZERS)]))

    @timed
    def analyze_batch(self,tables):
        with psycopg.connect(self.dsn,autocommit=True) as connection:
            for table in tables:
                progress(f'analyze {table}')
                connection.execute(f'analyze {table}')

    @timed
    def validate(self,cursor,seq,written):
        asked=[]
        turned={}
        with self.connection.pipeline():
            for table,label,columns,sql in self.checks:
                names,rows=written.get(table,((),()))
                if not rows:
                    continue
                if table not in turned:
                    turned[table]=dict(zip(names,zip(*rows)))
                values=[value for value in set(zip(*(turned[table][column] for column in columns))) if None not in value]
                if not values:
                    continue
                progress(f'validate {label}')
                asked.append((label,self.connection.execute(sql,[list(column) for column in zip(*values)],prepare=True)))
        broken=[label for label,answer in asked if answer.fetchone()[0]]
        if broken:
            raise RuntimeError(evidence(seq=seq,broken=broken[:5]))

    @timed_often
    def parameters(self,cursor,vocabulary,code,label,params):
        kinds={name:'integer' if isinstance(value,int) else 'text' for name,value in params.items()}
        known=self.actions.setdefault((vocabulary,code),dict(cursor.execute(f'select name,value_kind from {vocabulary}_parameter where {vocabulary}=%s',(code,)).fetchall()))
        for name,kind in kinds.items():
            if known.get(name,kind)!=kind:
                raise RuntimeError(evidence(label=label,name=name,known=known[name],kind=kind))
            if name not in known:
                cursor.execute(f'insert into {vocabulary}_parameter ({vocabulary},name,value_kind) values (%s,%s,%s)',(code,name,kind))
                known[name]=kind
        return [(name,value if kinds[name]=='integer' else None,None if kinds[name]=='integer' else str(value)) for name,value in params.items()]

    @timed
    def log_action(self,entry,after):
        action=self.names('action',[entry['action']])[0]
        advisor=self.names('advisor',[entry['advisor']])[0]
        decision=entry['decision']
        chosen=None if decision is None else self.names('advisor_action',[decision[0]])[0]
        with self.connection.transaction(),self.connection.cursor() as cursor:
            params=self.parameters(cursor,'action',action,entry['action'],entry['params'])
            decided=[] if decision is None else self.parameters(cursor,'advisor_action',chosen,decision[0],decision[1])
            cursor.execute('insert into loop_action (run_id,n,turn,advisor,action,advisor_action,before_seq,after_seq,status,detail,ms,unverified,logged_at) '
                           'values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())',
                           (self.run_id,entry['seq'],entry['turn'],advisor,action,chosen,entry['snapshot'],after,entry['status'],entry.get('detail'),entry.get('ms'),entry['unverified']))
            self.copy(cursor,'loop_action_param',('run_id','n','action','name','integer_value','text_value'),[(self.run_id,entry['seq'],action,*row) for row in params])
            self.copy(cursor,'loop_decision_param',('run_id','n','advisor_action','name','integer_value','text_value'),[(self.run_id,entry['seq'],chosen,*row) for row in decided])

    @timed_often
    def verify_action(self,n):
        self.connection.execute('update loop_action set unverified=false where run_id=%s and n=%s',(self.run_id,n))

    @timed
    def end_run(self,reason,detail=None,game_exited_at=None):
        if self.run_id is not None:
            self.connection.execute('update run set ended_at=now(),end_reason=%s,end_detail=%s,game_exited_at=%s where run_id=%s and ended_at is null',
                                    (reason,detail,game_exited_at,self.run_id))
            with self.connection.transaction(),self.connection.cursor() as cursor:
                self.record_timing(cursor)

    @timed
    def measures(self,keys):
        known=dict(((kind,level,name),ident) for ident,kind,level,name in self.connection.execute('select coherence_measure,kind,level,name from coherence_measure'))
        fresh=sorted(set(keys)-known.keys())
        if fresh:
            known.update(((kind,level,name),ident) for ident,kind,level,name in self.connection.execute(
                'insert into coherence_measure (kind,level,name) select * from unnest(%s::text[],%s::text[],%s::text[]) returning coherence_measure,kind,level,name',
                [list(column) for column in zip(*fresh)]))
        return known

    @timed
    def coherence_values(self,cursor,prefix,key,countries,states):
        countries=[(tag,row['type'],name,value) for tag,row in countries.items() for name,value in row.items() if name not in COHERENCE_TEXT]
        states=[(row['state_region'],row['country'],row['type'],name,value) for row in states for name,value in row.items() if name not in COHERENCE_TEXT]
        ids=self.measures({('country','country',name) for *_,name,_ in countries}|{('state','state',name) for *_,name,_ in states})
        self.copy(cursor,f'{prefix}_country',(key[0],'tag','country_type','coherence_measure','value'),
                  [(key[1],tag,kind,ids['country','country',name],defined(value)) for tag,kind,name,value in countries])
        self.copy(cursor,f'{prefix}_state',(key[0],'state_region','tag','country_type','coherence_measure','value'),
                  [(key[1],region,tag,kind,ids['state','state',name],defined(value)) for region,tag,kind,name,value in states])

    @timed
    def coherence_geography(self,cursor,prefix,key,geography):
        objects=[(level,name,position,value) for level,columns in geography['objects'].items() for name,values in columns.items() for position,value in enumerate(values)]
        shares=[(kind[:-1],name,numerator,denominator) for kind in ('ratios','checks') for name,(numerator,denominator) in geography[kind].items()]
        ids=self.measures({('object',level,name) for level,name,*_ in objects}|{(kind,kind,name) for kind,name,*_ in shares})
        self.copy(cursor,f'{prefix}_object',(key[0],'coherence_measure','position','value'),
                  [(key[1],ids['object',level,name],position,defined(value)) for level,name,position,value in objects])
        self.copy(cursor,f'{prefix}_share',(key[0],'coherence_measure','numerator','denominator'),
                  [(key[1],ids[kind,kind,name],numerator,denominator) for kind,name,numerator,denominator in shares])

    @timed
    def record_reference(self,build,countries,states,geography):
        with self.connection.transaction(),self.connection.cursor() as cursor:
            reference=cursor.execute('insert into coherence_reference (build,measured_at) values (%s,now()) returning coherence_reference',(build,)).fetchone()[0]
            self.coherence_values(cursor,'coherence_reference',('coherence_reference',reference),countries,states)
            self.coherence_geography(cursor,'coherence_reference',('coherence_reference',reference),geography)
        return reference

    @timed
    def record_coherence(self,build,countries,states,measured_ms):
        with self.connection.transaction(),self.connection.cursor() as cursor:
            cursor.execute('insert into run_coherence (run_id,build,measured_ms) values (%s,%s,%s)',(self.run_id,build,measured_ms))
            self.coherence_values(cursor,'run_coherence',('run_id',self.run_id),countries,states)

    @timed
    def world_coherent(self):
        return self.connection.execute('select 1 from world_coherence where world_id=%s',(self.world_id,)).fetchone() is not None

    @timed
    def record_world_coherence(self,geography):
        with self.connection.transaction(),self.connection.cursor() as cursor:
            cursor.execute('insert into world_coherence (world_id) values (%s)',(self.world_id,))
            self.coherence_geography(cursor,'world_coherence',('world_id',self.world_id),geography)


@timed_often
def defined(value):
    return None if value is None or value!=value else float(value)


@timed_often
def enumerate_rows(run_id,values):
    return [(run_id,position,value) for position,value in enumerate(values)]


def identity(live,entity,value,table,column):
    if live[entity].get(value&SLOT)!=value:
        raise RuntimeError(evidence(table=table,column=column,entity=entity,value=value,slot=value&SLOT,generation=value>>24))
    return value
