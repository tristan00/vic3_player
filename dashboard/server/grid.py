from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime

from interface.recording.spec import B, F, H, I2, I4, I8, T

from . import db
from .models import Cell, Grid, GridColumn, Ref
from .names import game_date, labels

NUMERIC={F,I2,I4,I8}
TRUE={'yes','true','1'}
VALUES=ContextVar('values',default=None)


@dataclass
class Spec:
    name:str
    kind:str
    sql:str
    entity:str|None=None
    group:str|None=None
    label:str|None=None
    run:str|None=None
    hidden:bool=False


@db.timed
def recorded(column,prefix,group=None,name=None):
    source=f'{prefix}.{column.name}'
    label=column.name
    name=name or column.name
    if column.entity:
        return Spec(name,'ref',source,entity=column.entity,group=group,label=label)
    if column.vocabulary:
        return Spec(name,'text',f'(select name from {column.vocabulary} where {column.vocabulary}={source})',group=group,label=label)
    if column.enum:
        return Spec(name,'text',f'(select name from {column.enum} where {column.enum}={source})',group=group,label=label)
    if column.kind==H:
        return Spec(name,'date',source,group=group,label=label)
    if column.kind==B:
        return Spec(name,'bool',source,group=group,label=label)
    if column.kind in NUMERIC:
        return Spec(name,'number',source,group=group,label=label)
    return Spec(name,'text',source,group=group,label=label)


@db.timed
def parse_filters(raw):
    out=[]
    for item in raw or []:
        name,sep,value=item.partition(':')
        if not sep:
            raise ValueError(f'filter {item} is not column:value')
        out.append((name,value))
    return out


@db.timed
def typed(spec,value):
    if value=='∅':
        return None
    if spec.kind in ('number',):
        return float(value)
    if spec.kind in ('ref','run','seq','n','date','round'):
        return int(value)
    if spec.kind=='bool':
        return value in TRUE
    return value


@db.timed
def where_clause(specs,filters):
    index={s.name:i for i,s in enumerate(specs)}
    chosen=defaultdict(list)
    params={}
    for name,value in filters:
        if name not in index:
            raise ValueError(f'no column {name}')
        converted=typed(specs[index[name]],value)
        if converted is None:
            chosen[name].append(f'g.c{index[name]} is null')
        else:
            chosen[name].append(f'g.c{index[name]}=%(f{len(params)})s')
            params[f'f{len(params)}']=converted
    clauses=[f'({" or ".join(found)})' for found in chosen.values()]
    return (' where '+' and '.join(clauses)) if clauses else '',params


@db.timed
def grid(specs,source,params,filters=(),sort=None,desc=False,offset=0,limit=100,run_id=None,order=None):
    inner=f'select {",".join(f"{s.sql} as c{i}" for i,s in enumerate(specs))} {source}'
    if VALUES.get() is not None:
        return distinct(specs,inner,params,filters,VALUES.get(),limit,run_id)
    where,extra=where_clause(specs,filters)
    names=[s.name for s in specs]
    if sort is not None and sort not in names:
        raise ValueError(f'no column {sort}')
    ordering=[f'g.c{names.index(sort)} {"desc" if desc else "asc"} nulls last'] if sort else []
    ordering+=[f'g.c{names.index(name)}' for name in (order or names[:1]) if name!=sort]
    bound={**params,**extra,'limit':limit,'offset':offset}
    total=db.value(f'select count(*) from ({inner}) g{where}',bound)
    found=db.rows(f'select * from ({inner}) g{where} order by {",".join(ordering)} limit %(limit)s offset %(offset)s',bound)
    shown=[i for i,s in enumerate(specs) if not s.hidden]
    return Grid(columns=[GridColumn(name=specs[i].name,label=specs[i].label or specs[i].name,kind=specs[i].kind,entity=specs[i].entity,group=specs[i].group) for i in shown],
                rows=[[row[i] for i in shown] for row in cells(specs,[[f[f'c{i}'] for i in range(len(specs))] for f in found],run_id)],total=total,offset=offset,run=run_id)


@db.timed
def distinct(specs,inner,params,filters,column,limit,run_id):
    names=[s.name for s in specs]
    if column not in names:
        raise ValueError(f'no column {column}')
    at=names.index(column)
    where,extra=where_clause(specs,[(name,value) for name,value in filters if name!=column])
    grouped=f'select g.c{at} as value,count(*) as rows from ({inner}) g{where} group by 1'
    bound={**params,**extra,'limit':limit}
    total=db.value(f'select count(*) from ({grouped}) d',bound)
    found=db.rows(f'select * from ({grouped}) d order by d.rows desc,d.value nulls first limit %(limit)s',bound)
    count=Spec('rows','number','rows')
    return Grid(columns=[GridColumn(name=column,label=specs[at].label or column,kind=specs[at].kind,entity=specs[at].entity),GridColumn(name='rows',label='rows',kind='number')],
                rows=cells([specs[at],count],[[f['value'],f['rows']] for f in found],run_id),total=total,offset=0,run=run_id)


@db.timed
def rows_source(types,rows):
    arrays=','.join(f'%(u{i})s::{kind}[]' for i,kind in enumerate(types))
    return f'from unnest({arrays}) as t({",".join(f"v{i}" for i in range(len(types)))})',{f'u{i}':[row[i] for row in rows] for i in range(len(types))}


@db.timed
def cells(specs,rows,run_id):
    runs=[specs.index(next(s for s in specs if s.name==spec.run)) if spec.run else None for spec in specs]
    wanted=defaultdict(set)
    for row in rows:
        for i,(spec,value) in enumerate(zip(specs,row)):
            if spec.kind=='ref' and value is not None:
                owner=run_id if runs[i] is None else row[runs[i]]
                wanted[owner,spec.entity].add(value)
    named=defaultdict(dict)
    for (owner,kind),ids in wanted.items():
        named[owner][kind]=labels(owner,kind,ids)
    return [[cell(spec,value,named[run_id if runs[i] is None else row[runs[i]]],run_id if runs[i] is None else row[runs[i]])
             for i,(spec,value) in enumerate(zip(specs,row))] for row in rows]


def cell(spec,value,named,run_id):
    if value is None:
        return Cell()
    kind=spec.kind
    if kind=='ref':
        return Cell(ref=Ref(kind=spec.entity,id=value,label=named.get(spec.entity,{}).get(value),run=run_id))
    if kind=='run':
        return Cell(ref=Ref(kind='run',id=value,label=None))
    if kind=='seq':
        return Cell(ref=Ref(kind='snapshot',id=value,label=None,run=run_id))
    if kind=='n':
        return Cell(ref=Ref(kind='action',id=value,label=None,run=run_id))
    if kind=='date':
        return Cell(text=game_date(value).text,num=value)
    if kind=='time':
        return Cell(text=value.isoformat() if isinstance(value,datetime) else str(value))
    if kind=='bool':
        return Cell(text='yes' if value else 'no')
    if kind=='number':
        return Cell(num=float(value))
    return Cell(text=str(value))
