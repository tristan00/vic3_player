from advisors.random_smac_weighting import COMPONENTS, DEBT_CAP_FROM_RUN, breakdown

from . import db
from .grid import Spec, grid, rows_source
from .runs import STATE, goal, reward_changes

PARTS=('gain','gain_per_years_alpha','normalized','contribution')
LABELS={'gain':'gain','gain_per_years_alpha':'gain / years^alpha','normalized':'normalized','contribution':'weighted'}
INITIALIZER='(select a.name from run_advisor ra join advisor a using (advisor) where ra.run_id=r.run_id and ra.position=0)'


@db.timed
def weights(filters,sort,desc,offset,limit):
    specs=[Spec('run','run','r.run_id'),Spec('action','action','a.name'),Spec('weight','number','w.weight'),
           Spec('initializer','text',INITIALIZER),
           Spec('method','text',f"case when {INITIALIZER}='random_smac_weighting' then p.method end",label='SMAC selection')]
    source='from run_weight w join run r using (run_id) join action a using (action) left join smac_proposal p using (run_id)'
    return grid(specs,source,{},filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run','action'])


@db.timed
def configs(filters,sort,desc,offset,limit):
    specs=[Spec('initializer','text',INITIALIZER),Spec('picker','text','r.picker'),Spec('runs','number','count(*)'),
           Spec('open','number','count(*) filter (where r.ended_at is null)'),Spec('first_run','run','min(r.run_id)'),Spec('last_run','run','max(r.run_id)')]
    source=f'from run r where r.run_id>=%(first)s group by {INITIALIZER},r.picker'
    return grid(specs,source,{'first':DEBT_CAP_FROM_RUN},filters,sort,desc,offset,limit,None,['initializer','picker'])


@db.timed
def run_policies(filters,sort,desc,offset,limit):
    changes=reward_changes()
    found=db.rows(f'''select r.run_id,{STATE} as state,{INITIALIZER} as initializer,r.picker,r.candidates,r.objective_gdp,r.objective_population,r.objective_sol,
                             r.objective_alpha from run r''')
    width=2+len(COMPONENTS)*len(PARTS)+1
    rows=[]
    for f in found:
        policy=[f['run_id'],f['state'],f['initializer'],f['picker'],f['candidates'],f['objective_gdp'],f['objective_population'],f['objective_sol'],f['objective_alpha']]
        if f['run_id'] not in changes:
            rows.append(policy+[None]*width)
            continue
        years,parts=breakdown(changes,goal(f),f['run_id'])
        rows.append(policy+[years,parts[0]['years_alpha'],*[p[k] for p in parts for k in PARTS],sum(p['contribution'] for p in parts)])
    columns=[('run','run',None,'run'),('state','text',None,'state'),('initializer','text','policy','initializer'),('picker','text','policy','picker'),('candidates','number','policy','candidates'),
             *[(f'objective_{c}','number','objective',c) for c in (*COMPONENTS,'alpha')],('years','number','time','years'),('years_alpha','number','time','years^alpha'),
             *[(f'{c}.{k}','number',c,LABELS[k]) for c in COMPONENTS for k in PARTS],('reward','number','reward','reward')]
    specs=[Spec(name,kind,f't.v{i}',group=group,label=label) for i,(name,kind,group,label) in enumerate(columns)]
    source,params=rows_source(['int4','text','text','text','int4',*['float8']*(len(columns)-5)],rows)
    return grid(specs,source,params,filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run'])


@db.timed
def pauses(run_id,filters,sort,desc,offset,limit):
    chosen='max(c.{0}) filter (where c.chosen)'
    specs=[Spec('seq','seq','c.seq'),Spec('game_date','date','s.game_date'),Spec('candidates','number','count(*)'),
           Spec('distinct_predictions','number','count(distinct c.predicted_change)'),Spec('min','number','min(c.predicted_change)',group='predicted'),
           Spec('mean','number','avg(c.predicted_change)',group='predicted'),Spec('max','number','max(c.predicted_change)',group='predicted'),
           Spec('spread','number','max(c.predicted_change)-min(c.predicted_change)',group='predicted'),
           Spec('candidate','number',chosen.format('candidate'),group='chosen'),Spec('predicted','number',chosen.format('predicted_change'),group='chosen'),
           Spec('actions','number',chosen.format('actions'),group='chosen')]
    source='from pick_candidate c join snapshot s on s.run_id=c.run_id and s.seq=c.seq where c.run_id=%(run)s group by c.seq,s.game_date'
    return grid(specs,source,{'run':run_id},filters,sort or 'seq',desc,offset,limit,run_id,['seq'])


@db.timed
def candidates(run_id,seq,filters,sort,desc,offset,limit):
    specs=[Spec('rank','number','rank() over (order by c.predicted_change desc)',label='Rank'),
           Spec('block','text',"(select string_agg(a.name,' → ' order by p.position) from pick_candidate_action p join action a using (action) "
                "where p.run_id=c.run_id and p.seq=c.seq and p.candidate=c.candidate)",label='Action block (execution order)'),
           Spec('predicted_change','number','c.predicted_change',label='Predicted score'),Spec('chosen','bool','c.chosen',label='Chosen'),
           Spec('gap','number','max(c.predicted_change) over ()-c.predicted_change',label='Gap to best'),
           Spec('candidate','number','c.candidate',label='Block ID'),Spec('actions','number','c.actions',label='Actions')]
    source='from pick_candidate c where c.run_id=%(run)s and c.seq=%(seq)s'
    return grid(specs,source,{'run':run_id,'seq':seq},filters,sort or 'rank',desc,offset,limit,run_id,['rank','candidate'])


@db.timed
def picker_actions(filters,sort,desc,offset,limit):
    specs=[Spec('action','action','a.name'),Spec('offered','number','count(*)'),Spec('chosen','number','count(*) filter (where c.chosen)'),
           Spec('offered_share','number','count(*)::float8/sum(count(*)) over ()'),
           Spec('chosen_share','number','(count(*) filter (where c.chosen))::float8/nullif(sum(count(*) filter (where c.chosen)) over (),0)')]
    source='from pick_candidate_action p join pick_candidate c using (run_id,seq,candidate) join action a using (action) group by a.name'
    return grid(specs,source,{},filters,sort or 'offered',True if sort is None else desc,offset,limit,None,['action'])
