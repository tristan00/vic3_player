from interface.common import evidence

from . import db, names, runs

FIGURES=('goods_sales','goods_cost','dividends','cash_reserves','balance_subsidies','trade_revenue','tariffs','tolls','subventions',
         'supply_ship_construction','military_ship_construction','income_taxes','slave_upkeep')
VIEWS=('levels','methods','staffing','money','ownership','queue')
RUN='select player_country,ruleset_id from run where run_id=%s'
SHOTS='select seq,game_date from snapshot where run_id=%s order by seq'
BUILT='''select building,seq,building_type,state,case when present and not dead then levels else 0 end
from building_history where run_id=%s order by building,seq'''
HELD='select state,seq,case when present then country end from state_history where run_id=%s order by state,seq'
FLOWS=f'select building,seq,staffing,{",".join(FIGURES)} from building_flow where run_id=%s and building=any(%s) order by building,seq'
USED='''select building,production_method,seq,present from building_production_method_active
where run_id=%s and building=any(%s) order by building,production_method,seq'''
SHARES='''select building_ownership,seq,case when present then building end,owner_kind,owner_country,owner_company,levels
from building_ownership_history where run_id=%s order by building_ownership,seq'''
QUEUED='''select private,position,seq,case when present then state end,building_type from player_construction_queue_item
where run_id=%s order by private,position,seq'''
SECTORS="select name,value from game_definition where ruleset_id=%s and folder='common/buildings' and field='building_group'"
PARENTS="select name,value from game_definition where ruleset_id=%s and folder='common/building_groups' and field='parent_group'"
FIXED="select name from game_definition where ruleset_id=%s and folder='common/buildings' and field='expandable' and value='no'"
CATALOGUE='''select t.name,m.name,g.name from building_production_method c join building_type t using (building_type)
join production_method m using (production_method) join production_method_group g using (production_method_group) where c.ruleset_id=%s'''


@db.often
def spread(rows,at,size):
    out={}
    for key,seq,value in rows:
        out.setdefault(key,[None]*size)[at[seq]:]=[value]*(size-at[seq])
    return out


@db.often
def frame(connection,run):
    player,ruleset=connection.execute(RUN,(run,)).fetchone()
    shots=connection.execute(SHOTS,(run,)).fetchall()
    dates=sorted({date for _,date in shots})
    place={date:index for index,date in enumerate(dates)}
    at={seq:place[date] for seq,date in shots}
    size=len(dates)
    holder=spread(connection.execute(HELD,(run,)).fetchall(),at,size)
    built=spread([(building,seq,(kind,state,levels)) for building,seq,kind,state,levels in connection.execute(BUILT,(run,)).fetchall()],at,size)
    mine={}
    for building,line in built.items():
        kept=[value if value and value[2] and value[1] in holder and holder[value[1]][day]==player else None for day,value in enumerate(line)]
        if any(kept):
            mine[building]=kept
    return {'run':run,'player':player,'ruleset':ruleset,'at':at,'size':size,'mine':mine,'holder':holder,
            'dates':[db.day(date) for date in dates],'years':[db.year(date) for date in dates]}


@db.often
def described(found):
    english=names.english()
    sectors=dict(db.rows(SECTORS,(found['ruleset'],)))
    parents=dict(db.rows(PARENTS,(found['ruleset'],)))
    fixed={name for name, in db.rows(FIXED,(found['ruleset'],))}
    places=names.labels(found['run'],'state')
    kinds={}

    def kind(code):
        if code not in kinds:
            name=names.key('building_type',code)
            sector=sectors.get(name)
            while sector in parents:
                sector=parents[sector]
            kinds[code]={'type':english.get(name,name),'sector':english.get(sector,sector),'expandable':'no' if name in fixed else 'yes'}
        return kinds[code]

    return kind,lambda code:{'kind':'state','id':code,'label':places[code]}


@db.often
def gathered(found,cells,share=False):
    size=found['size']
    rows={}
    for key,made,day,top,bottom,building in cells:
        if key not in rows:
            rows[key]={**made(),'building':None,'last':-1,'top':[0]*size,'bottom':[0]*size,'seen':[False]*size}
        row=rows[key]
        row['top'][day]+=top
        row['bottom'][day]+=bottom
        row['seen'][day]=True
        if day>=row['last']:
            row['last'],row['building']=day,building
    out=[]
    for row in rows.values():
        top,bottom,seen=row.pop('top'),row.pop('bottom'),row.pop('seen')
        del row['last']
        row['values']=[None if not on or share and not below else round(100*above/below,1) if share else above if isinstance(above,int) else round(above,2)
                       for on,above,below in zip(seen,top,bottom)]
        if share:
            row['weights']=[below if on else None for on,below in zip(seen,bottom)]
        out.append(row)
    return out


@db.often
def grouping(run,found,used):
    english=names.english()
    catalogue={}
    homes={}
    for kind,method,group in db.rows(CATALOGUE,(found['ruleset'],)):
        catalogue[kind,method]=group
        homes.setdefault(method,set()).add(group)
    lines=[]
    for (building,method),line in spread([((building,method),seq,True if present else None) for building,method,seq,present in used],found['at'],found['size']).items():
        kind=names.key('building_type',next(value[0] for value in found['mine'][building] if value))
        name=names.key('production_method',method)
        if (kind,name) in catalogue:
            group=catalogue[kind,name]
        elif len(homes.get(name,()))==1:
            group=next(iter(homes[name]))
        else:
            raise ValueError(evidence(run=run,building_type=kind,production_method=name))
        lines.append((building,english.get(group,group),english.get(name,name),line))
    return lines


@db.timed
def table(run,view,figure):
    if view not in VIEWS or view=='money' and figure not in FIGURES:
        raise ValueError(evidence(view=view,figure=figure))

    def work(connection):
        found=frame(connection,run)
        sql={'staffing':FLOWS,'money':FLOWS,'methods':USED,'ownership':SHARES,'queue':QUEUED}.get(view)
        return found,connection.execute(sql,(run,list(found['mine'])) if sql in (FLOWS,USED) else (run,)).fetchall() if sql else []

    found,more=runs.frozen(work)
    mine=found['mine']
    kind,state=described(found)
    extra={}
    spot=lambda value:lambda:{**kind(value[0]),'state':state(value[1])}
    if view=='levels':
        cells=((value[:2],spot(value),day,value[2],0,building) for building,line in mine.items() for day,value in enumerate(line) if value)
    elif view=='methods':
        cells=(((value[0],value[1],group,method),lambda value=value,group=group,method=method:{**spot(value)(),'method_group':group,'method':method},day,value[2],0,building)
               for building,group,method,line in grouping(run,found,more) for day,value in enumerate(mine[building]) if value and line[day])
    elif view=='ownership':
        countries=names.labels(run,'country')
        companies=names.labels(run,'company')
        owner=lambda sort,country,company:({'kind':'country','id':country,'label':countries[country]} if sort=='country' else
                                           {'kind':'company','id':company,'label':companies[company]} if sort=='company' and company is not None else sort)
        shares=spread([(key,seq,None if building is None else (building,sort,country,company,levels)) for key,seq,building,sort,country,company,levels in more],found['at'],found['size'])
        cells=(((share[1:4],value[:2]),lambda value=value,share=share:{**spot(value)(),'owner':owner(*share[1:4])},day,share[4],0,share[0])
               for line in shares.values() for day,share in enumerate(line) if share and share[0] in mine for value in [mine[share[0]][day]] if value)
    elif view=='queue':
        queued=spread([((private,position),seq,None if place is None else (code,place)) for private,position,seq,place,code in more],found['at'],found['size'])
        cells=(((private,value),lambda private=private,value=value:{**spot(value)(),'funder':'private' if private else 'government'},day,1,0,None)
               for (private,_),line in queued.items() for day,value in enumerate(line) if value and found['holder'].get(value[1],[None]*found['size'])[day]==found['player'])
    else:
        flows=spread([(row[0],row[1],row[2:]) for row in more],found['at'],found['size'])
        if view=='money':
            extra={'figures':[name for index,name in enumerate(FIGURES) if any(flow and flow[index+1] and mine[building][day] for building,line in flows.items() for day,flow in enumerate(line))]}
        index=0 if view=='staffing' else FIGURES.index(figure)+1
        cells=((value[:2],spot(value),day,flows[building][day][index],value[2],building) for building,line in mine.items() if building in flows
               for day,value in enumerate(line) if value and flows[building][day])
    return {'dates':found['dates'],'years':found['years'],'rows':gathered(found,cells,view=='staffing'),**extra}
