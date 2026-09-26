from collections import defaultdict
import threading

from interface.actions.catalogue import BY_NAME, GROUP
from interface.recording.spec import ENTITIES
from loop.run import WEIGHTS

from . import db
from .models import (ActionDetail, ActionLog, ActionRow, ActionStat, ActionStats, ActionType, Count, DetailCount, Facet, Param, ParamSpec, Ref, RunStatus, Scope,
                     StatusCount)
from .names import game_date, labels
from .runs import GROUPS, LOOP_PARAMS, STATUSES, group_statuses, iso, snapshot_row, status_counts

ALIASES={'military_formation':'formation'}
CACHE={}
CACHE_LOCK=threading.Lock()


def param_specs(action):
    return [ParamSpec(name=name,kind=kind) for name,_,kind in
            ((spec.partition(':') if ':' in spec else (spec,':',spec)) for spec in (LOOP_PARAMS[action] if action in LOOP_PARAMS else BY_NAME[action].params))]


def entity_of(kind):
    kind=ALIASES.get(kind,kind)
    return kind if kind in ENTITIES else None


ACTION_SELECT='''
select l.run_id,l.n,l.turn,a.name as action,v.name as advisor,l.status,l.detail,l.ms,l.before_seq,l.after_seq,l.logged_at,s.game_date
from loop_action l join action a using (action) join advisor v using (advisor) join snapshot s on s.run_id=l.run_id and s.seq=l.before_seq
'''


@db.timed
def action_rows(found):
    if not found:
        return []
    keys=[(f['run_id'],f['n']) for f in found]
    params=defaultdict(list)
    for p in db.rows('select run_id,n,name,integer_value,text_value from loop_action_param where (run_id,n) in (select unnest(%s::int4[]),unnest(%s::int4[])) '
                     'order by run_id,n,name',([k[0] for k in keys],[k[1] for k in keys])):
        params[p['run_id'],p['n']].append(p)
    wanted=defaultdict(lambda:defaultdict(set))
    kinds={}
    for f in found:
        spec={p.name:p.kind for p in param_specs(f['action'])}
        for p in params[f['run_id'],f['n']]:
            entity=entity_of(spec[p['name']])
            kinds[f['run_id'],f['n'],p['name']]=(spec[p['name']],entity)
            if entity and p['integer_value'] is not None:
                wanted[f['run_id']][entity].add(p['integer_value'])
    named={(run,kind):labels(run,kind,ids) for run,by_kind in wanted.items() for kind,ids in by_kind.items()}
    out=[]
    for f in found:
        resolved=[]
        for p in params[f['run_id'],f['n']]:
            kind,entity=kinds[f['run_id'],f['n'],p['name']]
            value=p['integer_value'] if p['integer_value'] is not None else p['text_value']
            ref=None
            if entity and p['integer_value'] is not None and value in named[f['run_id'],entity]:
                ref=Ref(kind=entity,id=value,label=named[f['run_id'],entity][value])
            resolved.append(Param(name=p['name'],kind=kind,text=str(value),ref=ref))
        out.append(ActionRow(run_id=f['run_id'],n=f['n'],turn=f['turn'],action=f['action'],group=GROUPS[f['action']],advisor=f['advisor'],status=f['status'],
                             detail=f['detail'],ms=f['ms'],before_seq=f['before_seq'],after_seq=f['after_seq'],game_date=game_date(f['game_date']),
                             logged_at=iso(f['logged_at']),params=resolved))
    return out


def action_where(run_id,action=None,group=None,status=None):
    clauses,params=['l.run_id=%s'],[run_id]
    if action:
        clauses.append('a.name=%s')
        params.append(action)
    if group:
        clauses.append('a.name=any(%s)')
        params.append([name for name,g in GROUPS.items() if g==group])
    if status:
        clauses.append('l.status=%s')
        params.append(status)
    return ' where '+' and '.join(clauses),params


@db.timed
def run_log(run_id,offset,limit,action=None,group=None,status=None):
    where,params=action_where(run_id,action,group,status)
    total=db.value(f'select count(*) from loop_action l join action a using (action) {where}',params)
    found=db.rows(f'{ACTION_SELECT} {where} order by l.n desc limit %s offset %s',[*params,limit,offset])
    names=db.rows('select a.name as value,count(*) as count from loop_action l join action a using (action) where l.run_id=%s group by 1 order by 2 desc',(run_id,))
    groups=defaultdict(int)
    for f in names:
        groups[GROUPS[f['value']]]+=f['count']
    described=[part for part in (action and f'action {action}',group and f'group {group}',status and f'status {status}') if part]
    return ActionLog(scope=Scope(text=f'every action run {run_id} logged, newest first'+(', '+', '.join(described) if described else ''),
                                 detail='game date is the date of the snapshot the action was chosen from'),
                     total=Count(value=total,noun='actions',population='matching the filters'),rows=action_rows(found),
                     actions=[Facet(**f) for f in names],groups=[Facet(value=g,count=c) for g,c in sorted(groups.items(),key=lambda i:-i[1])],
                     statuses=status_counts('where a.run_id=%s',(run_id,)))


@db.timed
def action_detail(run_id,n):
    found=db.rows(f'{ACTION_SELECT} where l.run_id=%s and l.n=%s',(run_id,n))
    if not found:
        return None
    action=action_rows(found)[0]
    batch=action_rows(db.rows(f'{ACTION_SELECT} where l.run_id=%s and l.before_seq=%s and l.n<>%s order by l.n',(run_id,action.before_seq,n)))
    before=snapshot_row(db.row('select * from snapshot where run_id=%s and seq=%s',(run_id,action.before_seq)))
    after=None if action.after_seq is None else snapshot_row(db.row('select * from snapshot where run_id=%s and seq=%s',(run_id,action.after_seq)))
    return ActionDetail(action=action,batch=batch,before=before,after=after)


def parse_scope(scope):
    if scope=='all':
        return 'all',None
    kind,_,value=scope.partition(':')
    if kind not in ('round','run') or not value.isdigit():
        raise ValueError(f'unknown scope {scope}')
    return kind,int(value)


def scope_sql(kind,value):
    if kind=='all':
        return 'r.ended_at is not null',[]
    if kind=='round':
        return 'r.cli_seed=%s',[value]
    return 'r.run_id=%s',[value]


def scope_text(kind,value):
    if kind=='all':
        return Scope(text='every action of every finished run',detail='runs still going join this view once they end; pick a round or a run to see live ones')
    if kind=='round':
        return Scope(text=f'every action of round {value}, finished and live runs')
    return Scope(text=f'every action of run {value}')


def stamp(kind):
    if kind!='all':
        return None
    found=db.row('select count(*) as runs,max(ended_at) as last from run where ended_at is not null')
    return found['runs'],found['last']


@db.timed
def action_stats(scope):
    kind,value=parse_scope(scope)
    key=stamp(kind)
    with CACHE_LOCK:
        cached=CACHE.get(('stats',scope))
    if key is not None and cached is not None and cached[0]==key:
        return cached[1]
    where,params=scope_sql(kind,value)
    found=db.rows(f'''select a.name as action,l.status,count(*) as count
                      from loop_action l join action a using (action) join run r using (run_id) where {where} group by 1,2''',params)
    spread={f['action']:f for f in db.rows(f'''select a.name as action,count(distinct l.run_id) as runs,
                             percentile_cont(.5) within group (order by l.ms) filter (where l.status='done') as median,
                             percentile_cont(.9) within group (order by l.ms) filter (where l.status='done') as p90
                      from loop_action l join action a using (action) join run r using (run_id) where {where} group by 1''',params)}
    runs=db.value(f'select count(*) from run r where {where}',params)
    per=defaultdict(dict)
    for f in found:
        per[f['action']][f['status']]=f
    rows=[]
    for action,by in per.items():
        total=sum(f['count'] for f in by.values())
        rows.append(ActionStat(action=action,group=GROUPS[action],total=total,runs=spread[action]['runs'],
                               statuses=[StatusCount(status=s,count=by[s]['count'] if s in by else 0) for s in STATUSES],
                               ms_median=spread[action]['median'],ms_p90=spread[action]['p90']))
    rows.sort(key=lambda r:-r.total)
    total=sum(r.total for r in rows)
    statuses=[StatusCount(status=s,count=sum(f['count'] for f in found if f['status']==s)) for s in STATUSES]
    never=sorted(name for name in BY_NAME if GROUP[name]!='time' and name not in per)
    text=scope_text(kind,value)
    result=ActionStats(scope=Scope(text=text.text,detail=(text.detail+'; ' if text.detail else '')+'timings cover done actions only'),
                       total=Count(value=total,noun='actions',population='in this scope'),runs=Count(value=runs,noun='runs',population='in this scope'),
                       statuses=statuses,groups=group_statuses(found),rows=rows,never=never)
    if key is not None:
        with CACHE_LOCK:
            CACHE[('stats',scope)]=(key,result)
    return result


@db.timed
def action_type(name,scope,limit=50):
    if name not in GROUPS:
        return None
    kind,value=parse_scope(scope)
    where,params=scope_sql(kind,value)
    code=db.value('select action from action where name=%s',(name,))
    base=f'from loop_action l join run r using (run_id) where l.action=%s and {where}'
    args=[code,*params]
    counts={f['status']:f['count'] for f in db.rows(f'select l.status,count(*) as count {base} group by 1',args)} if code else {}
    details=[DetailCount(**f) for f in db.rows(f'select l.status,l.detail,count(*) as count {base} and l.status<>%s group by 1,2 order by 3 desc limit 25',
                                                [*args,'done'])] if code else []
    per_run=db.rows(f'''select l.run_id,d.name as tag,l.status,count(*) as count {base.replace("join run r using (run_id)","join run r using (run_id) join country_definition d on d.country_definition=r.tag")}
                        group by 1,2,3 order by 1 desc''',args) if code else []
    runs=defaultdict(dict)
    tags={}
    for f in per_run:
        runs[f['run_id']][f['status']]=f['count']
        tags[f['run_id']]=f['tag']
    run_rows=[RunStatus(run_id=r,tag=tags[r],statuses=[StatusCount(status=s,count=c.get(s,0)) for s in STATUSES],total=sum(c.values()))
              for r,c in sorted(runs.items(),reverse=True)[:limit]]
    recent=action_rows(db.rows(f'{ACTION_SELECT} join run r on r.run_id=l.run_id where l.action=%s and {where} order by l.run_id desc,l.n desc limit %s',
                               [*args,limit])) if code else []
    text=scope_text(kind,value)
    return ActionType(scope=Scope(text=text.text.replace('every action','every '+name),detail=text.detail),action=name,group=GROUPS[name],
                      params=param_specs(name),weight=WEIGHTS.get(name,1),total=Count(value=sum(counts.values()),noun='picks',population='in this scope'),
                      statuses=[StatusCount(status=s,count=counts.get(s,0)) for s in STATUSES],details=details,runs=run_rows,recent=recent)
