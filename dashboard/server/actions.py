from interface.actions.catalogue import BY_NAME
from interface.recording.spec import ENTITIES

from . import db
from .grid import Spec, grid, where_clause
from .models import ParamSpec
from .runs import GROUPS, LOOP_PARAMS, STATUSES

ALIASES={'military_formation':'formation'}
GROUP_VALUES='(values '+','.join(f"('{name}','{group}')" for name,group in GROUPS.items())+') grp(name,grp)'
ACTION_FROM=f'''from loop_action l join action a using (action) join snapshot s on s.run_id=l.run_id and s.seq=l.before_seq
join {GROUP_VALUES} on grp.name=a.name'''


def param_specs(action):
    return [ParamSpec(name=name,kind=kind) for name,_,kind in
            ((spec.partition(':') if ':' in spec else (spec,':',spec)) for spec in (LOOP_PARAMS[action] if action in LOOP_PARAMS else BY_NAME[action].params))]


def entity_of(kind):
    kind=ALIASES.get(kind,kind)
    return kind if kind in ENTITIES else None


@db.timed
def param_columns(matched,params):
    found=db.rows(f'select distinct a.name as action,p.name from loop_action_param p join loop_action l using (run_id,n) join action a on a.action=l.action '
                  f'where (l.run_id,l.n) in ({matched})',params)
    kinds={}
    for f in found:
        kind=next(p.kind for p in param_specs(f['action']) if p.name==f['name'])
        kinds.setdefault(f['name'],entity_of(kind))
    out=[]
    for name,entity in sorted(kinds.items()):
        value='integer_value' if entity else 'coalesce(integer_value::text,text_value)'
        sql=f"(select {value} from loop_action_param p where p.run_id=l.run_id and p.n=l.n and p.name='{name}')"
        out.append(Spec(f'param.{name}','ref',sql,entity=entity,group='params',label=name) if entity else Spec(f'param.{name}','text',sql,group='params',label=name))
    return out


def action_grid(where,params,filters,sort,desc,offset,limit,run_id=None):
    base=([Spec('run','run','l.run_id')] if run_id is None else [])+[
        Spec('n','n','l.n',run=None if run_id else 'run'),Spec('turn','number','l.turn'),Spec('game_date','date','s.game_date'),Spec('action','action','a.name'),
        Spec('group','text','grp.grp'),Spec('status','text','l.status'),Spec('detail','text','l.detail'),Spec('ms','number','l.ms'),
        Spec('before_seq','seq','l.before_seq',run=None if run_id else 'run'),Spec('after_seq','seq','l.after_seq',run=None if run_id else 'run'),
        Spec('logged_at','time','l.logged_at')]
    chosen,extra=where_clause(base,[f for f in filters if not f[0].startswith('param.')])
    columns=','.join(f'{s.sql} as c{i}' for i,s in enumerate(base))
    specs=base+param_columns(f'select g.rid,g.nn from (select l.run_id as rid,l.n as nn,{columns} {ACTION_FROM} {where}) g{chosen}',{**params,**extra})
    first='n' if run_id else 'run'
    return grid(specs,f'{ACTION_FROM} {where}',params,filters,sort or first,True if sort is None else desc,offset,limit,run_id,['n'])


@db.timed
def run_actions(run_id,filters,sort,desc,offset,limit):
    return action_grid('where l.run_id=%(run)s',{'run':run_id},filters,sort,desc,offset,limit,run_id)


def parse_scope(scope):
    if scope=='all':
        return 'all',None
    kind,_,value=scope.partition(':')
    if kind not in ('round','run') or not value.isdigit():
        raise ValueError(f'unknown scope {scope}')
    return kind,int(value)


def scope_sql(scope):
    kind,value=parse_scope(scope)
    if kind=='all':
        return 'r.ended_at is not null',{}
    if kind=='round':
        return 'r.cli_seed=%(scope)s',{'scope':value}
    return 'r.run_id=%(scope)s',{'scope':value}


@db.timed
def action_stats(scope,filters,sort,desc,offset,limit):
    where,params=scope_sql(scope)
    source=f'''from {GROUP_VALUES} left join action a on a.name=grp.name
               left join (loop_action l join run r on r.run_id=l.run_id and {where}) on l.action=a.action
               group by grp.name,grp.grp'''
    specs=[Spec('action','action','grp.name'),Spec('group','text','grp.grp'),Spec('runs','number','count(distinct l.run_id)'),Spec('picks','number','count(l.n)')]
    specs+=[Spec(s,'number',f"count(l.n) filter (where l.status='{s}')") for s in STATUSES]
    specs+=[Spec('ms_median','number',"percentile_cont(.5) within group (order by l.ms) filter (where l.status='done')"),
            Spec('ms_p90','number',"percentile_cont(.9) within group (order by l.ms) filter (where l.status='done')")]
    return grid(specs,source,params,filters,sort or 'picks',True if sort is None else desc,offset,limit,None,['action'])


@db.timed
def action_runs(name,scope,filters,sort,desc,offset,limit):
    where,params=scope_sql(scope)
    source=f'''from loop_action l join action a using (action) join run r on r.run_id=l.run_id join country_definition d on d.country_definition=r.tag
               where a.name=%(name)s and {where} group by l.run_id,d.name'''
    specs=[Spec('run','run','l.run_id'),Spec('country','text','d.name'),Spec('picks','number','count(*)')]
    specs+=[Spec(s,'number',f"count(*) filter (where l.status='{s}')") for s in STATUSES]
    return grid(specs,source,{**params,'name':name},filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run'])


@db.timed
def action_details(name,scope,filters,sort,desc,offset,limit):
    where,params=scope_sql(scope)
    source=f'''from loop_action l join action a using (action) join run r on r.run_id=l.run_id where a.name=%(name)s and {where} group by l.status,l.detail'''
    specs=[Spec('status','text','l.status'),Spec('detail','text','l.detail'),Spec('count','number','count(*)')]
    return grid(specs,source,{**params,'name':name},filters,sort or 'count',True if sort is None else desc,offset,limit,None,['status'])


@db.timed
def action_picks(name,scope,filters,sort,desc,offset,limit):
    where,params=scope_sql(scope)
    return action_grid(f'join run r on r.run_id=l.run_id where a.name=%(name)s and {where}',{**params,'name':name},filters,sort,desc,offset,limit)
