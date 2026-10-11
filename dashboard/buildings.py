from interface.common import evidence

from . import db, names, runs

SHOTS='select seq,game_date from snapshot where run_id=%s order by seq'
BUILT='''select b.building,b.seq,t.name,b.state,case when b.present then b.levels else 0 end
from building_history b left join building_type t using (building_type) where b.run_id=%s order by b.building,b.seq'''
OWNED='select state,seq,case when present then country end from state_history where run_id=%s order by state,seq'
USED='''select building,production_method,seq,present from building_production_method_active
where run_id=%s order by building,production_method,seq'''
GROUPED='''select t.name,m.production_method,g.name,p.name from building_production_method m join building_type t using (building_type)
join production_method_group g using (production_method_group) join production_method p using (production_method)
where m.ruleset_id=(select ruleset_id from run where run_id=%s)'''


@db.often
def held(rows,at,size):
    out={}
    for key,seq,value in rows:
        out.setdefault(key,[None]*size)[at[seq]:]=[value]*(size-at[seq])
    return out


@db.often
def spans(line):
    out=[]
    for index,value in enumerate(line):
        if value is None:
            continue
        if out and out[-1][1]==index and out[-1][2:]==list(value):
            out[-1][1]=index+1
        else:
            out.append([index,index+1,*value])
    return out


@db.often
def grouping(exact,shared,kind,method):
    if (kind,method) in exact:
        return exact[kind,method]
    if len(shared.get(method,()))!=1:
        raise ValueError(evidence(kind=kind,method=method))
    return next(iter(shared[method]))


@db.timed
def levels(run):
    shots,built,owned,used,grouped=runs.frozen(lambda connection:[connection.execute(sql,(run,)).fetchall() for sql in (SHOTS,BUILT,OWNED,USED,GROUPED)])
    dates=sorted({date for _,date in shots})
    place={date:index for index,date in enumerate(dates)}
    at={seq:place[date] for seq,date in shots}
    size=len(dates)
    english=names.english()
    owner=held(owned,at,size)
    kinds={building:kind for building,_,kind,_,_ in built if kind is not None}
    buildings=[]
    position={}
    for building,line in held([(building,seq,(count,state)) for building,seq,_,state,count in built],at,size).items():
        found=spans([(value[0],value[1],owner[value[1]][day]) if value and value[0] else None for day,value in enumerate(line)])
        if found:
            position[building]=len(buildings)
            buildings.append({'id':building,'type':kinds[building],'spans':found})
    exact={(kind,method):(group,name) for kind,method,group,name in grouped}
    shared={}
    for _,method,group,name in grouped:
        shared.setdefault(method,set()).add((group,name))
    listed={}
    uses=[]
    for (building,method),line in held([((building,method),seq,() if present else None) for building,method,seq,present in used],at,size).items():
        if building in position:
            group,name=grouping(exact,shared,kinds[building],method)
            index=listed.setdefault((english.get(group,group),english.get(name,name)),len(listed))
            uses+=[[position[building],index,start,end] for start,end in spans(line)]
    states=names.labels(run,'state')
    countries=names.labels(run,'country')
    return {'dates':[db.day(date) for date in dates],'years':[db.year(date) for date in dates],
            'types':{kind:english.get(kind,kind) for kind in {entry['type'] for entry in buildings}},
            'states':{state:states.get(state) for state in {span[3] for entry in buildings for span in entry['spans']}},
            'countries':{country:countries.get(country) for country in {span[4] for entry in buildings for span in entry['spans']}},
            'methods':[{'group':group,'method':method} for group,method in listed],'buildings':buildings,'uses':uses}
