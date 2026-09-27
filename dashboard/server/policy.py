from advisors.random_smac_weighting import COMPONENTS, DEBT_CAP_FROM_RUN, combine

from . import db
from .grid import Spec, grid, rows_source
from .runs import goal, reward_changes

INITIALIZER='(select a.name from run_advisor ra join advisor a using (advisor) where ra.run_id=r.run_id and ra.position=0)'


@db.timed
def configs(filters,sort,desc,offset,limit):
    specs=[Spec('initializer','text',INITIALIZER),Spec('picker','text','r.picker'),Spec('runs','number','count(*)'),
           Spec('open','number','count(*) filter (where r.ended_at is null)'),Spec('first_run','run','min(r.run_id)'),Spec('last_run','run','max(r.run_id)')]
    source=f'from run r where r.run_id>=%(first)s group by {INITIALIZER},r.picker'
    return grid(specs,source,{'first':DEBT_CAP_FROM_RUN},filters,sort,desc,offset,limit,None,['initializer','picker'])


@db.timed
def scored(filters,sort,desc,offset,limit):
    changes=reward_changes()
    found=db.rows(f'''select r.run_id,{INITIALIZER} as initializer,r.picker,r.candidates,r.objective_gdp,r.objective_population,r.objective_sol,r.objective_alpha
                      from run r where r.run_id=any(%s)''',(list(changes),))
    rows=[]
    for f in found:
        years,change=changes[f['run_id']]
        reward=combine(changes,goal(f))[f['run_id']]
        rows.append([f['run_id'],f['initializer'],f['picker'],f['candidates'],f['objective_gdp'],f['objective_population'],f['objective_sol'],f['objective_alpha'],
                     years,*[change[c] for c in COMPONENTS],reward])
    names=['run','initializer','picker','candidates','objective_gdp','objective_population','objective_sol','objective_alpha','years',
           *[f'{c}_change' for c in COMPONENTS],'reward']
    types=['int4','text','text','int4',*['float8']*(len(names)-4)]
    kinds={'run':'run','initializer':'text','picker':'text'}
    specs=[Spec(name,kinds.get(name,'number'),f't.v{i}') for i,name in enumerate(names)]
    source,params=rows_source(types,rows)
    return grid(specs,source,params,filters,sort or 'run',True if sort is None else desc,offset,limit,None,['run'])


@db.timed
def picker_actions(filters,sort,desc,offset,limit):
    specs=[Spec('action','action','a.name'),Spec('offered','number','count(*)'),Spec('chosen','number','count(*) filter (where c.chosen)'),
           Spec('offered_share','number','count(*)::float8/sum(count(*)) over ()'),
           Spec('chosen_share','number','(count(*) filter (where c.chosen))::float8/nullif(sum(count(*) filter (where c.chosen)) over (),0)')]
    source='from pick_candidate_action p join pick_candidate c using (run_id,seq,candidate) join action a using (action) group by a.name'
    return grid(specs,source,{},filters,sort or 'offered',True if sort is None else desc,offset,limit,None,['action'])
