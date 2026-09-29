import math

from advisors import random_smac_weighting as smac, random_svr_weighting as svr
from advisors.random_picker import HIGH, LOW
from advisors.random_smac_weighting import COMPONENTS, DEBT_CAP_FROM_RUN, breakdown

from . import db
from .grid import Spec, grid, rows_source
from .runs import STATE, goal, reward_changes

NAMES={'gdp':'GDP','population':'population','sol':'SoL','stock':'built stock'}
PARTS=('gain','gain_times_years_alpha','normalized','contribution')
LABELS={'gain':'log gain','gain_times_years_alpha':'log gain · years^alpha','normalized':'normalized','contribution':'weighted'}
MEDIAN='percentile_cont(0.5) within group (order by {})'
OBJECTIVES=','.join(f'objective_{c}' for c in (*COMPONENTS,'alpha'))
INITIALIZER='(select a.name from run_advisor ra join advisor a using (advisor) where ra.run_id=r.run_id and ra.position=0)'


@db.timed
def weights(filters,sort,desc,offset,limit):
    specs=[Spec('run','run','r.run_id'),Spec('action','action','a.name'),Spec('weight','number','w.weight'),
           Spec('initializer','text',INITIALIZER),
           Spec('method','text',f"case {INITIALIZER} when 'random_smac_weighting' then p.method when 'random_svr_weighting' then v.method end",label='Initializer selection'),
           Spec('svr_linear','number','k.linear',label='SVR linear effect'),Spec('svr_squared','number','k.squared',label='SVR squared effect')]
    source=('from run_weight w join run r using (run_id) join action a using (action) left join smac_proposal p using (run_id) left join svr_proposal v using (run_id) '
            'left join svr_coefficient k on k.run_id=r.run_id and k.dimension=a.name')
    return grid(specs,source,{},filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run','action'])


@db.timed
def initializers():
    shared=[('weight range',f'10^{LOW:g} to 10^{HIGH:g}'),('random before',f'{smac.INITIAL} scored runs'),('random share',f'{smac.RANDOM_SHARE:.0%}')]
    settings=lambda pairs:[{'name':name,'value':str(value)} for name,value in pairs]
    return [{'name':'random','title':'Random','settings':settings(shared[:1])},
            {'name':'random_smac_weighting','title':'SMAC',
             'settings':settings([('trees',smac.TREES),('min runs per leaf',smac.LEAF),('features per split',smac.FEATURES),('trailing runs',smac.TRAILING),*shared])},
            {'name':'random_svr_weighting','title':'SVR',
             'settings':settings([('C',svr.C),('epsilon',svr.EPSILON),*shared])}]


@db.timed
def configs(filters,sort,desc,offset,limit):
    changes=reward_changes()
    scored=[]
    for found in db.rows(f'select run_id,{OBJECTIVES} from run where run_id=any(%s)',(list(changes),)):
        years,parts=breakdown(changes,goal(found),found['run_id'])
        scored.append([found['run_id'],years,sum(p['contribution'] for p in parts),*[100*math.expm1(changes[found['run_id']][1][c]) for c in COMPONENTS]])
    performance,params=rows_source(['int4',*['float8']*(2+len(COMPONENTS))],scored)
    specs=[Spec('initializer','text',INITIALIZER),Spec('picker','text','r.picker'),Spec('runs','number','count(*)'),
           Spec('scored_runs','number','count(p.v0)',label='Scored runs'),
           Spec('median_reward','number',MEDIAN.format('p.v2'),label='Median reward'),
           *[Spec(f'median_{c}_gain','number',MEDIAN.format(f'p.v{i+3}'),label=f'Median {NAMES[c]} gain (%)') for i,c in enumerate(COMPONENTS)],
           *[Spec(f'median_{c}_gain_per_year','number',MEDIAN.format(f'p.v{i+3}/nullif(p.v1,0)'),label=f'Median {NAMES[c]} gain/year (%/yr)') for i,c in enumerate(COMPONENTS)],
           Spec('median_years','number',MEDIAN.format('p.v1'),label='Median years (scored)'),
           Spec('open','number','count(*) filter (where r.ended_at is null)'),Spec('first_run','run','min(r.run_id)'),Spec('last_run','run','max(r.run_id)')]
    source=f'from run r left join (select * {performance}) p on p.v0=r.run_id where r.run_id>=%(first)s group by {INITIALIZER},r.picker'
    return grid(specs,source,{**params,'first':DEBT_CAP_FROM_RUN},filters,sort,desc,offset,limit,None,['initializer','picker'])


@db.timed
def run_policies(filters,sort,desc,offset,limit):
    changes=reward_changes()
    found=db.rows(f'''select r.run_id,{STATE} as state,{INITIALIZER} as initializer,r.picker,r.candidates,{OBJECTIVES} from run r''')
    width=2+len(COMPONENTS)*len(PARTS)+1
    rows=[]
    for f in found:
        policy=[f['run_id'],f['state'],f['initializer'],f['picker'],f['candidates'],*[f[f'objective_{c}'] for c in (*COMPONENTS,'alpha')]]
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
