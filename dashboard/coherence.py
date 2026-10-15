from collections import Counter, defaultdict
from threading import Lock

import numpy as np

from miniworld.coherence import KS, KS_SCALE, bounds, domain, ks

from . import db

LOCK=Lock()
REFERENCES={}
HEAD='''select c.coherence_reference,x.measured_ms,x.build,c.measured_at,r.world_id from run_coherence x join run r using (run_id)
left join coherence_reference c using (build) where x.run_id=%s'''
EMPTY={'countries':{},'states':{},'objects':{},'shares':{}}
COUNTRIES='''select x.tag,x.country_type,m.name,x.value from {source}_country x join coherence_measure m using (coherence_measure) where x.{key}=%s'''
STATES='''select x.state_region,x.tag,x.country_type,m.name,x.value from {source}_state x join coherence_measure m using (coherence_measure) where x.{key}=%s'''
OBJECTS='''select m.level,m.name,x.value from {source}_object x join coherence_measure m using (coherence_measure) where x.{key}=%s order by x.position'''
SHARES='''select m.kind,m.name,x.numerator,x.denominator from {source}_share x join coherence_measure m using (coherence_measure) where x.{key}=%s'''
RECOGNIZED='recognized'


@db.often
def spread(values):
    found=np.array([v for v in values if v is not None],float)
    if not len(found): return None
    low,q05,median,q95,high=np.quantile(found,[0,.05,.5,.95,1])
    return {'low':float(low),'q05':float(q05),'median':float(median),'q95':float(q95),'high':float(high),'n':len(found)}


@db.timed
def measurements(source,key,ident):
    return {'countries':db.rows(COUNTRIES.format(source=source,key=key),(ident,)),'states':db.rows(STATES.format(source=source,key=key),(ident,))}


@db.timed
def geography(source,key,ident):
    return {'objects':db.rows(OBJECTS.format(source=source,key=key),(ident,)),'shares':db.rows(SHARES.format(source=source,key=key),(ident,))}


@db.timed
def reference(ident):
    with LOCK:
        if ident in REFERENCES: return REFERENCES[ident]
    found={**measurements('coherence_reference','coherence_reference',ident),**geography('coherence_reference','coherence_reference',ident)}
    countries=defaultdict(list);states=defaultdict(list);objects=defaultdict(list)
    for _,kind,name,value in found['countries']:
        if kind==RECOGNIZED: countries[name].append(value)
    for _,_,kind,name,value in found['states']:
        if kind==RECOGNIZED: states[name].append(value)
    for level,name,value in found['objects']: objects[level,name].append(value)
    made={'countries':{name:spread(values) for name,values in countries.items()},'states':{name:spread(values) for name,values in states.items()},
          'objects':{key:np.array([v for v in values if v is not None],float) for key,values in objects.items()},
          'shares':{(kind,name):(numerator,denominator) for kind,name,numerator,denominator in found['shares']}}
    with LOCK:
        REFERENCES[ident]=made
    return made


@db.often
def judged(value,found):
    if value is None: return 'undefined'
    if found is None: return 'no reference'
    return 'below' if value<found['low'] else 'above' if value>found['high'] else 'in range'


@db.often
def compared(name,value,found):
    flag=judged(value,found)
    return {'domain':domain(name),'measure':name,'value':value,'flag':flag,'out':flag in ('below','above'),
            **({key:found[key] for key in ('low','median','high')} if found else {'low':None,'median':None,'high':None})}


@db.timed
def report(run):
    head=db.one(HEAD,(run,))
    if head is None: return None
    ref=EMPTY if head[0] is None else reference(head[0])
    found={**measurements('run_coherence','run_id',run),**geography('world_coherence','world_id',head[4])}
    countries=[{'country':tag,'type':kind,**compared(name,value,ref['countries'].get(name))} for tag,kind,name,value in found['countries']]
    states=[{'state':region,'country':tag,'type':kind,**compared(name,value,ref['states'].get(name))} for region,tag,kind,name,value in found['states']]
    objects=defaultdict(list)
    for level,name,value in found['objects']: objects[level,name].append(value)
    shapes=[]
    for level,name in sorted(set(ref['objects'])|set(objects)):
        vanilla=ref['objects'].get((level,name),np.array([]))
        values=objects.get((level,name),[])
        mine=np.array([v for v in values if v is not None],float)
        distance=ks(vanilla,mine) if len(mine) and len(vanilla) else None
        limit=max(KS,KS_SCALE*np.sqrt(1/len(vanilla)+1/len(mine))) if len(mine) and len(vanilla) else None
        shapes.append({'level':level,'measure':name,'objects':len(values),'undefined':len(values)-len(mine),'median':float(np.median(mine)) if len(mine) else None,
                       'vanilla_objects':len(vanilla),'vanilla_median':float(np.median(vanilla)) if len(vanilla) else None,'distance':distance,'limit':limit,
                       'flag':'no objects' if distance is None else 'differs' if distance>limit else 'similar','out':distance is not None and distance>limit})
    mine={(kind,name):(numerator,denominator) for kind,name,numerator,denominator in found['shares']}
    shares=[]
    for kind,name in sorted(set(ref['shares'])|set(mine)):
        numerator,denominator=ref['shares'].get((kind,name),(0,0))
        low,high=bounds(numerator,denominator,kind=='check') if denominator else (None,None)
        got=mine.get((kind,name))
        value=got[0]/got[1] if got and got[1] else None
        flag='no cases' if value is None else 'no reference' if low is None else 'in band' if low<=value<=high else 'outside'
        shares.append({'kind':kind,'measure':name,'value':value,'cases':got[1] if got else None,'vanilla':numerator/denominator if denominator else None,
                       'low':low,'high':high,'flag':flag,'out':flag=='outside'})
    summary=defaultdict(Counter)
    for row in countries:
        summary[row['country']]['measures']+=row['flag']!='undefined'
        summary[row['country']]['out']+=row['out']
        if row['out']: summary[row['country']][row['domain']]+=1
    domains=sorted({row['domain'] for row in countries})
    types={row['country']:row['type'] for row in countries}
    overview=[{'country':tag,'type':types[tag],'measures':found['measures'],'out':found['out'],'in_range':1-found['out']/found['measures'] if found['measures'] else None,
               **{name:found[name] for name in domains}} for tag,found in sorted(summary.items())]
    return {'run':run,'build':head[2],'reference_measured':head[3],'measured_ms':head[1],'domains':domains,'overview':overview,'countries':countries,'states':states,
            'objects':shapes,'shares':shares,'flagged':{'countries':sum(row['out'] for row in countries),'states':sum(row['out'] for row in states),
                                                        'objects':sum(row['out'] for row in shapes),'shares':sum(row['out'] for row in shares)}}
