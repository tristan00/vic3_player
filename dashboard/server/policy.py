from advisors.catalogue import ACTIONS
from advisors.models import forest, svr
from advisors.initializers.random import HIGH, LOW
from advisors.data.endgame import COMPONENTS
from advisors.data.rewards import DEBT_CAP_FROM_RUN

from . import db
from .grid import Spec, grid, rows_source
from .runs import STATE, reward_scores

NAMES={'gdp':'GDP','population':'population','stock':'building stock'}
PARTS=('end_ratio','recent_change','part','weight','alpha','duration_factor','contribution')
LABELS={'end_ratio':'Ending / start','recent_change':'Final-year change / yr','part':'Reward part','weight':'Weight',
        'alpha':'T exponent','duration_factor':'Time factor','contribution':'Contribution'}
MEDIAN='percentile_cont(0.5) within group (order by {})'
INITIALIZER='(select a.name from run_advisor ra join advisor a using (advisor) where ra.run_id=r.run_id and ra.position=0)'
DOMAINS='(values '+','.join(f"('{action.name}','{action.domain}')" for action in ACTIONS)+') d(name,domain)'
CATALOGUE='(values '+','.join(f"({position},'{action.name}','{action.domain}','{' '.join(param if param==kind else f'{param}:{kind}' for param,kind in action.params)}')"
                              for position,action in enumerate(ACTIONS))+') d(position,name,domain,params)'


@db.timed
def weights(filters,sort,desc,offset,limit):
    specs=[Spec('run','run','r.run_id'),Spec('domain','text','d.domain'),Spec('action','text','a.name',label='Advisor action'),Spec('weight','number','w.weight'),
           Spec('initializer','text',INITIALIZER),
           Spec('method','text',f"case {INITIALIZER} when 'random_smac_weighting' then p.method when 'random_svr_weighting' then v.method end",label='Initializer selection'),
           Spec('svr_linear','number','k.linear',label='SVR linear effect'),Spec('svr_squared','number','k.squared',label='SVR squared effect')]
    source=(f'from run_weight w join run r using (run_id) join advisor_action a using (advisor_action) join {DOMAINS} on d.name=a.name '
            'left join smac_proposal p using (run_id) left join svr_proposal v using (run_id) '
            'left join svr_coefficient k on k.run_id=r.run_id and k.dimension=a.name')
    return grid(specs,source,{},filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run','action'])


@db.timed
def catalogue(filters,sort,desc,offset,limit):
    specs=[Spec('position','number','d.position'),Spec('domain','text','d.domain'),Spec('action','text','d.name',label='Advisor action'),Spec('parameters','text','d.params'),
           Spec('commands','text',"string_agg(distinct i.name,', ')",label='Interface commands executed'),Spec('executions','number','count(l.n)'),
           Spec('runs','number','count(distinct l.run_id)')]
    source=(f'from {CATALOGUE} left join advisor_action a on a.name=d.name left join loop_action l on l.advisor_action=a.advisor_action '
            'left join action i on i.action=l.action group by d.position,d.name,d.domain,d.params')
    return grid(specs,source,{},filters,sort or 'position',desc,offset,limit,None,['position'])


@db.timed
def initializers():
    shared=[('weight range',f'10^{LOW:g} to 10^{HIGH:g}')]
    learned=[('reward','Building stock + population + GDP'),('reward baseline','Run opening snapshot'),('training target','Rank-normalized reward')]
    settings=lambda pairs:[{'name':name,'value':str(value)} for name,value in pairs]
    return [{'name':'random','title':'Random','settings':settings(shared)},
            {'name':'random_smac_weighting','title':'SMAC',
             'settings':settings([('trees',forest.TREES),('min runs per leaf',forest.LEAF),('features per split',forest.FEATURES),('run history','All scored runs'),*learned,*shared])},
            {'name':'random_svr_weighting','title':'SVR',
             'settings':settings([('C',svr.C),('epsilon',svr.EPSILON),*learned,*shared])}]


@db.timed
def configs(filters,sort,desc,offset,limit):
    scores=reward_scores()
    scored=[]
    for run,result in scores.items():
        parts={part['component']:part for part in result['parts']}
        scored.append([run,result['years'],result['score'],*[100*(parts[c]['end_ratio']-1) for c in COMPONENTS],
                       *[100*parts[c]['recent_change'] for c in COMPONENTS]])
    performance,params=rows_source(['int4',*['float8']*(2+2*len(COMPONENTS))],scored)
    specs=[Spec('initializer','text',INITIALIZER),Spec('picker','text','r.picker'),Spec('runs','number','count(*)'),
           Spec('scored_runs','number','count(p.v0)',label='Scored runs'),
           Spec('median_reward','number',MEDIAN.format('p.v2'),label='Median current reward'),
           *[Spec(f'median_{c}_gain','number',MEDIAN.format(f'p.v{i+3}'),label=f'Median ending {NAMES[c]} change (%)') for i,c in enumerate(COMPONENTS)],
           *[Spec(f'median_{c}_recent_change','number',MEDIAN.format(f'p.v{i+3+len(COMPONENTS)}'),label=f'Median final-year {NAMES[c]} change (%/yr)') for i,c in enumerate(COMPONENTS)],
           Spec('median_years','number',MEDIAN.format('p.v1'),label='Median years (scored)'),
           Spec('open','number','count(*) filter (where r.ended_at is null)'),Spec('first_run','run','min(r.run_id)'),Spec('last_run','run','max(r.run_id)')]
    source=f'from run r left join (select * {performance}) p on p.v0=r.run_id where r.run_id>=%(first)s group by {INITIALIZER},r.picker'
    return grid(specs,source,{**params,'first':DEBT_CAP_FROM_RUN},filters,sort,desc,offset,limit,None,['initializer','picker'])


@db.timed
def run_policies(filters,sort,desc,offset,limit):
    scores=reward_scores()
    found=db.rows(f'''select r.run_id,{STATE} as state,{INITIALIZER} as initializer,r.picker,r.candidates from run r''')
    width=2+len(COMPONENTS)*len(PARTS)+1
    rows=[]
    for f in found:
        policy=[f['run_id'],f['state'],f['initializer'],f['picker'],f['candidates']]
        if f['run_id'] not in scores:
            rows.append(policy+[None]*width)
            continue
        result=scores[f['run_id']]
        parts={part['component']:part for part in result['parts']}
        rows.append(policy+[result['years'],result['window_years'],*[parts[c][k] for c in COMPONENTS for k in PARTS],result['score']])
    columns=[('run','run',None,'run'),('state','text',None,'state'),('initializer','text','policy','initializer'),('picker','text','policy','picker'),('candidates','number','policy','candidates'),
             ('years','number','time','Years'),('window_years','number','time','Recent window (years)'),
             *[(f'{c}.{k}','number',NAMES[c],LABELS[k]) for c in COMPONENTS for k in PARTS],('reward','number','reward','Current reward')]
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
           Spec('block','text',"(select string_agg(a.name,' → ' order by p.position) from pick_candidate_action p join advisor_action a using (advisor_action) "
                "where p.run_id=c.run_id and p.seq=c.seq and p.candidate=c.candidate)",label='Action block (execution order)'),
           Spec('predicted_change','number','c.predicted_change',label='Predicted score'),Spec('chosen','bool','c.chosen',label='Chosen'),
           Spec('gap','number','max(c.predicted_change) over ()-c.predicted_change',label='Gap to best'),
           Spec('candidate','number','c.candidate',label='Block ID'),Spec('actions','number','c.actions',label='Actions')]
    source='from pick_candidate c where c.run_id=%(run)s and c.seq=%(seq)s'
    return grid(specs,source,{'run':run_id,'seq':seq},filters,sort or 'rank',desc,offset,limit,run_id,['rank','candidate'])


@db.timed
def picker_actions(filters,sort,desc,offset,limit):
    specs=[Spec('picker','text','r.picker'),Spec('action','text','a.name',label='Advisor action'),Spec('offered','number','count(*)'),Spec('chosen','number','count(*) filter (where c.chosen)'),
           Spec('offered_share','number','count(*)::float8/sum(count(*)) over (partition by r.picker)'),
           Spec('chosen_share','number','(count(*) filter (where c.chosen))::float8/nullif(sum(count(*) filter (where c.chosen)) over (partition by r.picker),0)')]
    source='from pick_candidate_action p join pick_candidate c using (run_id,seq,candidate) join advisor_action a using (advisor_action) join run r on r.run_id=p.run_id group by r.picker,a.name'
    return grid(specs,source,{},filters,sort or 'offered',True if sort is None else desc,offset,limit,None,['picker','action'])
