import time
from threading import Lock

from advisors.catalogue import LENGTHS
from advisors.data.endgame import HISTORY, OBJECTIVE, REWARD_COMPONENTS, Trajectories
from advisors.data.rewards import HOURS_PER_YEAR, OUTCOMES, scored_runs
from interface.recording.spec import ENTITIES, TABLE
import loop.run

from . import actions as acts, db, names

LOCK=Lock()
LIVE={}
SCORES={}
FROZEN='set transaction isolation level repeatable read read only'
IDENTITY='''select r.run_id,r.source_session,r.started_at,r.ended_at,r.end_reason,r.player_country,count(*),max(s.seq),min(s.game_date),max(s.game_date)
from run r join snapshot s on s.run_id=r.run_id where r.ended_at is not null group by r.run_id'''
RUNS='''select r.run_id,r.started_at,r.ended_at,extract(epoch from coalesce(r.ended_at,now())-r.started_at)::float8/60,r.end_reason,r.end_detail,
r.world_id,r.world_file,r.sizer,r.picker,r.candidates,c.name,a.name,s.snapshots,s.earliest,s.latest
from run r join country_definition c on c.country_definition=r.tag
left join run_advisor p on p.run_id=r.run_id and p.position=0 left join advisor a on a.advisor=p.advisor
cross join lateral (select count(*) as snapshots,min(t.game_date) as earliest,max(t.game_date) as latest from snapshot t where t.run_id=r.run_id) s
where %(run)s::int4 is null or r.run_id=%(run)s order by r.run_id'''
COUNTS='''select run_id,status,count(*),count(*) filter (where unverified) from loop_action
where advisor_action is not null and (%(run)s::int4 is null or run_id=%(run)s) group by 1,2'''
SNAPSHOTS='select seq,phase,game_date,taken_at,read_ms from snapshot where run_id=%s order by seq'
NEIGHBOURS='select (select max(run_id) from run where run_id<%(run)s),(select min(run_id) from run where run_id>%(run)s)'
TREASURY='''select s.game_date,t.money,t.principal,t.credit from player_treasury t join snapshot s on s.run_id=t.run_id and s.seq=t.seq
where t.run_id=%s order by t.seq'''
LOGGED=f'''select l.n,l.turn,s.game_date,d.name,aa.name,a.name,l.status,l.unverified,l.detail,l.ms,l.before_seq,l.after_seq
{acts.JOINED} join snapshot s on s.run_id=l.run_id and s.seq=l.before_seq where l.run_id=%s order by l.n'''
DECIDED='select n,name,integer_value,text_value from loop_decision_param where run_id=%s order by n,name'
ISSUED='''select p.n,p.name,p.integer_value,p.text_value from loop_action_param p join loop_action l on l.run_id=p.run_id and l.n=p.n
where p.run_id=%s and l.advisor_action is null order by p.n,p.name'''
WEIGHTS='select a.name,w.weight,w.centre from run_weight w join advisor_action a using (advisor_action) where w.run_id=%s order by 1'
PAUSES='''select c.seq,s.game_date as date,count(*) as candidates,count(distinct c.predicted_change) as distinct_predictions,
min(c.predicted_change) as lowest,avg(c.predicted_change) as mean,max(c.predicted_change) as highest,
max(c.predicted_change) filter (where c.chosen) as chosen,max(c.actions) filter (where c.chosen) as chosen_actions
from pick_candidate c join snapshot s on s.run_id=c.run_id and s.seq=c.seq where c.run_id=%s group by 1,2 order by 1'''
CANDIDATES='''select c.candidate,c.predicted_change,c.chosen,c.actions,
coalesce((select string_agg(a.name,' → ' order by p.position) from pick_candidate_action p join advisor_action a using (advisor_action)
          where p.run_id=c.run_id and p.seq=c.seq and p.candidate=c.candidate),'') as acts
from pick_candidate c where c.run_id=%s and c.seq=%s order by c.predicted_change desc,c.candidate'''
SIZES='''select c.seq,s.game_date,c.actions,c.predicted_change,c.chosen from size_candidate c join snapshot s on s.run_id=c.run_id and s.seq=c.seq
where c.run_id=%s order by c.seq,c.actions'''
TIMING='select span,calls,errors,total_ms,self_ms,min_ms,p50_ms,p95_ms,p99_ms,max_ms from run_timing where run_id=%s order by span'


@db.often
def entity_of(kind):
    words=kind.split('_')
    return next((name for name in ('_'.join(words[index:]) for index in range(len(words))) if name in ENTITIES),None)


ENTITY={kind:entity_of(kind) for kinds in acts.KINDS.values() for kind in kinds.values()}


@db.often
def refresh():
    with loop.run.state() as data:
        found=data
    running=loop.run.owner(found)
    phase='lost' if not running and found.get('phase') in ('starting','running') else found.get('phase','absent')
    LIVE['state']={**found,'alive':bool(running),'phase':phase,'date':db.day(found.get('game_hours')),'read':time.time()}


@db.often
def collection():
    return LIVE['state']


@db.often
def frozen(work):
    with db.POOL.connection() as connection,connection.transaction():
        connection.execute(FROZEN)
        return work(connection)


@db.often
def judged(history,run,first,last):
    baseline=history.baseline(run,first)
    reason=history.reason(run,first,last,baseline)
    if reason is not None:
        return None,reason
    try:
        return history.breakdown(run,first,last,baseline),None
    except ValueError as error:
        return None,str(error)


@db.often
def scores(connection):
    found=connection.execute(HISTORY,scored_runs()).fetchall()
    identities={row[0]:row[1:] for row in connection.execute(IDENTITY).fetchall()}
    with LOCK:
        fresh=[row for row in found if identities[row[0]] not in SCORES]
        if fresh:
            history=Trajectories(connection,[run for run,*_ in fresh])
            for run,first,last,_ in fresh:
                SCORES[identities[run]]=judged(history,run,first,last)
        kept={identities[run] for run,*_ in found}
        for identity in [identity for identity in SCORES if identity not in kept]:
            del SCORES[identity]
        return {run:SCORES[identities[run]] for run,*_ in found}


@db.often
def gathered(run):
    params={'run':run}
    live=collection()
    current=live.get('run_id') if live['alive'] else None
    listed,counted,results=frozen(lambda connection:(connection.execute(RUNS,params).fetchall(),connection.execute(COUNTS,params).fetchall(),scores(connection)))
    tallies={}
    for number,status,count,unverified in counted:
        acts.counted(tallies.setdefault(number,{}),status,count,unverified)
    statuses=acts.ordered({status for _,status,_,_ in counted})
    rows=[]
    for number,started,ended,minutes,reason,detail,world,world_file,sizer,picker,candidates,country,initializer,snapshots,first,last in listed:
        state=reason if ended is not None else 'running' if number==current else None
        result,unscored=results.get(number,(None,None))
        parts={part['component']:part['contribution'] for part in result['parts']} if result else {}
        tally=tallies.get(number,{})
        rows.append({'run':number,'started':started,'ended':ended,'minutes':minutes,'end_detail':detail,'world':world,'world_file':world_file,
                     'sizer':sizer,'picker':picker,'candidates':candidates,'country':country,'initializer':initializer,'snapshots':snapshots,
                     'first_date':db.day(first),'last_date':db.day(last),'game_years':None if first is None else (last-first)/HOURS_PER_YEAR,
                     'state':state,'tone':'live' if state=='running' else 'plain' if state in OUTCOMES else 'bad',
                     'attempted':tally.get('attempted',0),**{status:tally.get(status,0) for status in statuses},'unverified':tally.get('unverified',0),
                     'score':result['score'] if result else None,'not_scored':unscored,**{name:parts.get(name) for name in REWARD_COMPONENTS}})
    return {'rows':rows,'statuses':statuses,'components':list(REWARD_COMPONENTS),'objective':OBJECTIVE},results


@db.often
def exists(run):
    return db.one('select 1 from run where run_id=%s',(run,)) is not None


@db.timed
def listing(run=None):
    return gathered(run)[0]


@db.timed
def detail(run):
    columns,recorded=db.query('select * from run where run_id=%s',(run,))
    found,results=gathered(run)
    if not recorded or not found['rows']:
        return None
    links=names.catalog()['links'].get('run',{})
    record={column:names.named(links[column][1],value,names.places(run)) if value is not None and links.get(column,('',))[0]=='name' else value
            for column,value in zip(columns,recorded[0])}
    snapshots=[{'seq':seq,'phase':phase,'date':db.day(date),'year':db.year(date),'taken':taken,'read_ms':read_ms}
               for seq,phase,date,taken,read_ms in db.rows(SNAPSHOTS,(run,))]
    previous,following=db.one(NEIGHBOURS,{'run':run})
    player=record['player_country']
    return {**found,'row':found['rows'][0],'record':record,'snapshots':snapshots,'previous':previous,'next':following,
            'breakdown':results.get(run,(None,None))[0],'player':player}


@db.timed
def series(run):
    history,treasury=frozen(lambda connection:(Trajectories(connection,[run]),connection.execute(TREASURY,(run,)).fetchall()))
    components={name:[[db.year(date),value] for date,value in sorted(dict(points.get(run,[])).items())] for name,points in history.points.items()}
    latest={date:(money,principal,credit) for date,money,principal,credit in treasury}
    return {'components':components,
            'treasury':[{'year':db.year(date),'money':money,'principal':principal,'credit':credit} for date,(money,principal,credit) in sorted(latest.items())]}


@db.timed
def actions(run):
    given={}
    for n,name,integer,text in db.rows(DECIDED,(run,))+db.rows(ISSUED,(run,)):
        given.setdefault(n,[]).append((name,integer,text))
    labels={}
    rows=[]
    for n,turn,date,advisor,act,command,status,unverified,detail,ms,before,after in db.rows(LOGGED,(run,)):
        kinds=acts.KINDS.get(act,{})
        params=[]
        for name,integer,text in given.get(n,[]):
            entity=ENTITY.get(kinds.get(name)) if integer is not None else None
            if entity is not None and entity not in labels:
                labels[entity]=names.labels(run,entity)
            params.append({'name':name,'value':text if integer is None else integer,'entity':entity,
                           'label':labels[entity].get(integer) if entity is not None else None})
        rows.append({'n':n,'turn':turn,'date':db.day(date),'advisor':advisor,'act':act,'command':command,'lever':acts.LEVER.get(act),
                     'status':status,'unverified':unverified,'detail':detail,'ms':ms,'before_seq':before,'after_seq':after,'params':params})
    return {'rows':rows}


@db.often
def named(run,table,row):
    links=names.catalog()['links'].get(table,{})
    known=names.places(run)
    return {column:names.named(links[column][1],value,known) if value is not None and links.get(column,('',))[0]=='name' else value for column,value in row.items()}


@db.timed
def selection(run):
    done=acts.by_lever(run)
    weights=[{'lever':lever,'weight':weight,'centre':centre,
              **(done.get(lever,{'attempted':0,'done':0}) if lever in acts.CATALOGUED else {'attempted':None,'done':None})}
             for lever,weight,centre in db.rows(WEIGHTS,(run,))]
    weighted={row['lever'] for row in weights}
    weights+=[{'lever':lever,'weight':None,'centre':None,**counts} for lever,counts in done.items() if lever not in weighted]
    known=names.catalog()
    tables=sorted(table for table,columns in known['columns'].items()
                  if 'run_id' in columns and table in known['keys'] and table!='run' and table not in TABLE and table not in ENTITIES)
    counted=db.rows(' union all '.join(f'select \'{table}\',count(*) from "{table}" where run_id=%(run)s' for table in tables),{'run':run})
    records=[]
    for table,count in counted:
        if count:
            only=db.records(f'select * from "{table}" where run_id=%s',(run,)) if count==1 else []
            records.append({'table':table,'rows':count,'row':{column:value for column,value in named(run,table,only[0]).items() if column!='run_id'} if len(only)==1 else None})
    pauses=db.records(PAUSES,(run,))
    for pause in pauses:
        pause['date']=db.day(pause['date'])
    sizes={}
    for seq,date,actions,predicted,chosen in db.rows(SIZES,(run,)):
        row=sizes.setdefault(seq,{'seq':seq,'date':db.day(date)})
        row[str(actions)]=predicted
        if chosen:
            row.update(chosen=actions,predicted=predicted)
    return {'weights':weights,'records':records,'pauses':pauses,'sizes':list(sizes.values()),'lengths':[str(length) for length in LENGTHS]}


@db.timed
def candidates(run,seq):
    return {'rows':db.records(CANDIDATES,(run,seq))}


@db.timed
def timing(run):
    return {'rows':db.records(TIMING,(run,))}
