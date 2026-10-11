from advisors.catalogue import ACTIONS, LEVERS

from . import db

LEVER={action.name:action.lever for action in ACTIONS}
KINDS={action.name:dict(action.params) for action in ACTIONS}
CATALOGUED={lever.name for lever in LEVERS}
JOINED='''from loop_action l join action a on a.action=l.action join advisor d on d.advisor=l.advisor
left join advisor_action aa on aa.advisor_action=l.advisor_action'''
WEIGHTS='''select a.name,count(*),min(w.weight),percentile_cont(.5) within group (order by w.weight),max(w.weight)
from run_weight w join advisor_action a using (advisor_action) group by 1'''


@db.often
def ordered(statuses):
    return sorted(statuses,key=lambda status:(status!='done',status))


@db.often
def counted(entry,status,count,unverified):
    entry[status]=entry.get(status,0)+count
    entry['attempted']=entry.get('attempted',0)+count
    entry['unverified']=entry.get('unverified',0)+unverified


@db.often
def filled(entries,statuses):
    for entry in entries:
        for name in ('attempted','unverified',*statuses):
            entry.setdefault(name,0)
    return entries


@db.timed
def summary(run=None):
    where,params=('and l.run_id=%s',(run,)) if run is not None else ('',())
    acts={action.name:{'act':action.name,'lever':action.lever,'domain':action.domain,'commands':[]} for action in ACTIONS}
    statuses=set()
    for act,command,status,count,unverified in db.rows(f'''select aa.name,a.name,l.status,count(*),count(*) filter (where l.unverified)
            {JOINED} where l.advisor_action is not null {where} group by 1,2,3''',params):
        entry=acts.setdefault(act,{'act':act,'lever':None,'domain':None,'commands':[]})
        if command not in entry['commands']:
            entry['commands'].append(command)
        counted(entry,status,count,unverified)
        statuses.add(status)
    spread={act:(runs,ms) for act,runs,ms in db.rows(f'''select aa.name,count(distinct l.run_id),percentile_cont(.5) within group (order by l.ms)
            {JOINED} where l.advisor_action is not null {where} group by 1''',params)}
    for name,entry in acts.items():
        entry['runs'],entry['ms']=spread.get(name,(0,None))
        entry['commands']=', '.join(sorted(entry['commands']))
    return {'rows':filled(list(acts.values()),ordered(statuses)),'statuses':ordered(statuses)}


@db.timed
def commands():
    found={}
    statuses=set()
    for command,act,advisor,status,count,unverified in db.rows(f'''select a.name,aa.name,d.name,l.status,count(*),count(*) filter (where l.unverified)
            {JOINED} group by 1,2,3,4'''):
        entry=found.setdefault(command,{'command':command,'acts':[],'levers':[],'advisors':[]})
        if act is not None and act not in entry['acts']:
            entry['acts'].append(act)
            if act in LEVER and LEVER[act] not in entry['levers']:
                entry['levers'].append(LEVER[act])
        if advisor not in entry['advisors']:
            entry['advisors'].append(advisor)
        counted(entry,status,count,unverified)
        statuses.add(status)
    spread={command:(runs,ms) for command,runs,ms in db.rows(f'''select a.name,count(distinct l.run_id),percentile_cont(.5) within group (order by l.ms)
            {JOINED} group by 1''')}
    for name,entry in found.items():
        entry['runs'],entry['ms']=spread[name]
        entry['advisors']=', '.join(sorted(entry['advisors']))
        entry['acts'].sort()
        entry['levers'].sort()
    return {'rows':filled(list(found.values()),ordered(statuses)),'statuses':ordered(statuses)}


@db.timed
def levers():
    found=summary()
    statuses=found['statuses']
    out={lever.name:{'lever':lever.name,'domain':lever.domain,'acts':len(lever.acts)} for lever in LEVERS}
    for row in found['rows']:
        if row['lever'] is not None:
            entry=out.setdefault(row['lever'],{'lever':row['lever'],'domain':row['domain'],'acts':0})
            entry['acts']+=row['lever'] not in CATALOGUED
            for name in ('attempted','unverified',*statuses):
                entry[name]=entry.get(name,0)+row[name]
    filled([entry for name,entry in out.items() if name in CATALOGUED],statuses)
    for name,runs,low,middle,high in db.rows(WEIGHTS):
        out.setdefault(name,{'lever':name,'domain':None,'acts':None}).update(weighted_runs=runs,weight_min=low,weight_median=middle,weight_max=high)
    return {'rows':list(out.values()),'statuses':statuses}


@db.timed
def by_lever(run):
    out={}
    for act,status,count in db.rows('''select aa.name,l.status,count(*) from loop_action l join advisor_action aa using (advisor_action)
            where l.run_id=%s group by 1,2''',(run,)):
        if act in LEVER:
            entry=out.setdefault(LEVER[act],{'attempted':0,'done':0})
            entry['attempted']+=count
            entry['done']+=count if status=='done' else 0
    return out


@db.timed
def detail(name):
    action=next((action for action in ACTIONS if action.name==name),None)
    per_run={}
    per_command={}
    statuses=set()
    for run,command,status,count,unverified in db.rows(f'''select l.run_id,a.name,l.status,count(*),count(*) filter (where l.unverified)
            {JOINED} where aa.name=%s group by 1,2,3''',(name,)):
        counted(per_run.setdefault(run,{'run':run}),status,count,unverified)
        counted(per_command.setdefault(command,{'command':command}),status,count,unverified)
        statuses.add(status)
    if action is None and not per_run:
        return None
    statuses=ordered(statuses)
    responses=db.records(f'''select l.status,l.unverified,l.detail,count(*) as count,count(distinct l.run_id) as runs,max(l.run_id) as last_run
        {JOINED} where aa.name=%s group by 1,2,3 order by 4 desc''',(name,))
    recent=db.records(f'''select l.run_id as run,l.n,s.game_date as date,a.name as command,l.status,l.unverified,l.detail,l.ms
        {JOINED} join snapshot s on s.run_id=l.run_id and s.seq=l.before_seq where aa.name=%s order by l.run_id desc,l.n desc limit 100''',(name,))
    params={}
    if recent:
        for run,n,key,integer,text in db.rows('''select p.run_id,p.n,p.name,p.integer_value,p.text_value from loop_decision_param p
                where (p.run_id,p.n) in (select * from unnest(%s::int4[],%s::int4[])) order by p.name''',([row['run'] for row in recent],[row['n'] for row in recent])):
            params.setdefault((run,n),[]).append({'name':key,'value':text if integer is None else integer,'entity':None,'label':None})
    for row in recent:
        row['date']=db.day(row['date'])
        row['params']=params.get((row['run'],row['n']),[])
    return {'act':name,'lever':action.lever if action else None,'domain':action.domain if action else None,
            'parameters':[{'name':key,'kind':kind} for key,kind in action.params] if action else [],'responses':responses,
            'commands':filled(list(per_command.values()),statuses),'runs':filled(sorted(per_run.values(),key=lambda entry:-entry['run']),statuses),
            'statuses':statuses,'recent':recent}
