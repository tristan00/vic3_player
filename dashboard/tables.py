from interface.recording.spec import ENTITIES, ENUMS, TABLE, VOCABULARIES

from . import db, names

LIMIT=500
ESTIMATED=200000
WHOLE=('smallint','integer','bigint')
NUMERIC=(*WHOLE,'real','double precision','numeric')
PLAIN={'game_hours':'date','boolean':'bool','timestamp with time zone':'time','timestamp without time zone':'time','bytea':'bytes'}


@db.often
def numeric(kind):
    return kind in NUMERIC


@db.often
def whole(kind):
    return kind in WHOLE


@db.often
def kind_of(column,kind,link,per_run):
    if link:
        return 'name' if link[0]=='name' else 'entity:'+link[1]
    if column=='run_id':
        return 'run'
    if per_run and whole(kind) and (column=='seq' or column.endswith('_seq')):
        return 'seq'
    return PLAIN.get(kind) or ('int' if whole(kind) else 'num' if numeric(kind) else 'text')


@db.often
def group(name):
    if name in TABLE:
        return TABLE[name].kind
    return 'entity' if name in ENTITIES else 'vocabulary' if name in VOCABULARIES or name in ENUMS else 'record'


@db.timed
def listing():
    known=names.catalog(True)
    rows=[]
    for name,estimate,size in db.rows('''select c.relname::text,c.reltuples::int8,pg_total_relation_size(c.oid) from pg_class c
            where c.relnamespace='public'::regnamespace and c.relkind='r' order by 1'''):
        columns=known['columns'][name]
        spec=TABLE.get(name)
        rows.append({'table':name,'kind':group(name),'owner':spec.owner if spec else None,'scope':spec.scope if spec else None,
                     'per_run':'run_id' in columns,'columns':len(columns),'rows':estimate if estimate>=0 else None,'megabytes':size/2**20})
    return {'rows':rows}


@db.often
def reader(table):
    spec=TABLE.get(table)
    if spec is None:
        return None
    function=(table.removesuffix('_history') if spec.kind=='history' else table)+'_at'
    return function if function in names.catalog()['functions'] else None


@db.often
def shown(run,table,columns,found,seq=None):
    links=names.catalog()['links'].get(table,{})
    types=names.columns(table)
    known=names.places(run) if run is not None else {}
    kinds=[kind_of(column,types[column],links.get(column),run is not None) for column in columns]
    labels={kind:names.labelled(run,kind[7:],{row[index] for row in found for index,other in enumerate(kinds) if other==kind and row[index] is not None},seq)
            for kind in set(kinds) if kind.startswith('entity:') and run is not None}
    out=[]
    for row in found:
        entry={}
        for column,kind,value in zip(columns,kinds,row):
            if value is None:
                entry[column]=None
            elif kind=='name':
                entry[column]={'id':value,'label':names.named(links[column][1],value,known)}
            elif kind.startswith('entity:'):
                entry[column]={'id':value,'label':labels.get(kind,{}).get(value)}
            elif kind=='date':
                entry[column]=db.day(value)
            else:
                entry[column]=value
        out.append(entry)
    return [{'name':column,'kind':kind} for column,kind in zip(columns,kinds)],out


@db.often
def condition(run,table,column,text,index,params):
    link=names.catalog()['links'].get(table,{}).get(column)
    kind=names.columns(table)[column]
    if link or kind=='game_hours' or whole(kind):
        params[f'f{index}']=int(text)
    elif numeric(kind):
        params[f'f{index}']=float(text)
    elif kind=='boolean':
        if text not in ('true','false'):
            raise ValueError(f'{column} is true or false')
        params[f'f{index}']=text=='true'
    else:
        params[f'f{index}']=text
    label=text
    if link and link[0]=='name':
        label=names.named(link[1],int(text),names.places(run) if run is not None else {})
    elif link and run is not None:
        label=names.labels(run,link[1]).get(int(text),text)
    return f't."{column}"=%(f{index})s',{'column':column,'value':text,'label':label}


@db.often
def chartable(table):
    known=names.catalog()
    columns=names.columns(table)
    keys=known['keys'].get(table,[])
    links=known['links'].get(table,{})
    sampled='n' in keys and 'date' in columns
    if 'run_id' not in keys or not (sampled or ('seq' in keys and 'seq' in columns)):
        return []
    return [column for column,kind in columns.items() if numeric(kind) and column not in keys and column not in links and column!='seq']


@db.timed
def page(table,run,seq,at,filters,sort,desc,offset,limit):
    columns=names.columns(table)
    if columns is None:
        return None
    known=names.catalog()
    per_run='run_id' in columns
    if per_run and run is None:
        raise ValueError(f'{table} is recorded per run')
    function=reader(table)
    params={'run':run,'seq':seq,'limit':limit,'offset':offset}
    conditions=[]
    at=bool(per_run and at and function)
    if at and db.one('select 1 from snapshot where run_id=%s and seq=%s',(run,seq)) is None:
        raise ValueError(f'run {run} has no snapshot {seq}')
    if at:
        source=f'{function}(%(run)s,%(seq)s) t'
    else:
        source=f'"{table}" t'
        if per_run:
            conditions.append('t.run_id=%(run)s')
    result=db.query(f'select * from {source} where false',params)[0]
    if set(result)-set(columns):
        names.catalog(True)
    echoed=[]
    for index,(column,text) in enumerate(filters):
        if column not in result:
            raise ValueError(f'{table} has no column {column}')
        clause,echo=condition(run if per_run else None,table,column,text,index,params)
        conditions.append(clause)
        echoed.append(echo)
    where=' where '+' and '.join(conditions) if conditions else ''
    if sort is not None and sort not in result:
        raise ValueError(f'{table} has no column {sort}')
    keys=[column for column in known['keys'].get(table,[]) if column in result and column!='run_id']
    ties=[column for column in keys or result if column!=sort]
    order=','.join(([f't."{sort}" {"desc" if desc else "asc"} nulls last'] if sort else [])+[f't."{column}"' for column in ties])
    estimate=db.one("select reltuples::int8 from pg_class where relname=%s and relnamespace='public'::regnamespace",(table,))[0]
    estimated=not per_run and not filters and estimate>ESTIMATED
    total=estimate if estimated else db.one(f'select count(*) from {source}{where}',params)[0]
    found=db.rows(f'select * from {source}{where} order by {order} limit %(limit)s offset %(offset)s',params)
    filled=[] if estimated else db.one(f'select {",".join(f"count(t.{chr(34)}{column}{chr(34)})" for column in result)} from {source}{where}',params)
    described,out=shown(run if per_run else None,table,result,found,seq if at else None)
    spec=TABLE.get(table)
    return {'table':table,'kind':group(table),'owner':spec.owner if spec else None,'per_run':per_run,'at':at,'can_at':bool(per_run and function),
            'columns':described,'rows':out,'total':total,'estimated':estimated,'offset':params['offset'],'limit':params['limit'],'keys':keys,
            'filters':echoed,'chartable':chartable(table),'empty':[column for column,count in zip(result,filled) if total and not count]}


@db.timed
def series(run,table,filters):
    if names.columns(table) is None:
        return None
    columns=chartable(table)
    if not columns:
        raise ValueError(f'{table} has no numeric values over time')
    known=names.catalog()
    keys=[column for column in known['keys'][table] if column not in ('run_id','seq','n')]
    given=dict(filters)
    if set(keys)-set(given):
        raise ValueError(f'{table} needs '+', '.join(sorted(set(keys)-set(given))))
    params={'run':run}
    conditions=['t.run_id=%(run)s']+[condition(run,table,column,given[column],index,params)[0] for index,column in enumerate(keys)]
    sampled='n' in known['keys'][table]
    moment,joined=('t.n','') if sampled else ('s.game_date',' join snapshot s on s.run_id=t.run_id and s.seq=t.seq')
    picked=','.join(f't."{column}"' for column in columns)
    marked='present' in names.columns(table)
    found=db.rows(f'select {moment},{picked}{",t.present" if marked else ""} from "{table}" t{joined} where {" and ".join(conditions)} order by 1',params)
    last=db.one('select max(game_date) from snapshot where run_id=%s',(run,))[0]
    lasting=found and (found[-1][-1] if marked else not keys)
    if not sampled and lasting and found[-1][0]<last:
        found.append((last,*found[-1][1:]))
    return {'table':table,'columns':columns,'axis':'sample' if sampled else 'year','x':[row[0] if sampled else db.year(row[0]) for row in found],
            'values':{column:[row[index+1] for row in found] for index,column in enumerate(columns)}}


@db.timed
def entity(run,kind,ident,seq):
    if kind not in ENTITIES:
        return None
    first=db.one(f'select first_seq from "{kind}" where run_id=%s and "{kind}"=%s',(run,ident))
    if first is None:
        return None
    history=kind+'_history'
    known=names.catalog()
    last=db.one('select max(seq) from snapshot where run_id=%s',(run,))[0]
    seq=last if seq is None else seq
    columns,found=db.query(f'select * from {history} where run_id=%s and "{kind}"=%s order by seq',(run,ident))
    dates=dict(db.rows('select seq,game_date from snapshot where run_id=%s',(run,)))
    if seq not in dates:
        raise ValueError(f'run {run} has no snapshot {seq}')
    described,versions=shown(run,history,columns,found,seq)
    for version in versions:
        version['date']=db.day(dates[version['seq']])
    at=[version for version in versions if version['seq']<=seq]
    related=[]
    for table in TABLE.values():
        if table.owner==kind and table.name!=history and kind in known['columns'].get(table.name,{}):
            count=db.one(f'select count(*) from "{table.name}" where run_id=%s and "{kind}"=%s',(run,ident))[0]
            keys=[column for column in known['keys'][table.name] if column not in ('run_id','seq','n',kind)]
            related.append({'table':table.name,'kind':table.kind,'rows':count,'chart':bool(chartable(table.name)) and not keys})
    return {'run':run,'kind':kind,'id':ident,'label':names.labelled(run,kind,[ident],seq).get(ident),'first_seq':first[0],'seq':seq,'last_seq':last,
            'date':db.day(dates.get(seq)),'columns':[column for column in described if column['name'] not in ('run_id',kind)],
            'current':at[-1] if at else None,'versions':versions,'related':related}


@db.timed
def references(run,kind,ident):
    if kind not in ENTITIES:
        return None
    known=names.catalog()
    out=[]
    for table,links in sorted(known['links'].items()):
        spec=TABLE.get(table)
        for column,(sort,target) in links.items():
            if sort=='entity' and target==kind and 'run_id' in known['columns'][table] and not (spec and spec.owner==kind and column==kind):
                count=db.one(f'select count(*) from "{table}" where run_id=%s and "{column}"=%s',(run,ident))[0]
                if count:
                    out.append({'table':table,'column':column,'rows':count})
    return {'rows':out}
