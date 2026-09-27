from interface.recording.spec import TABLES

from . import db
from .grid import Spec, grid, rows_source
from .names import key_columns, kind_of

NAMES=['table','position','table_kind','owner','scope','column','role','kind','target','optional']


def schema_rows():
    rows=[]
    for t in TABLES:
        for position,(role,c) in enumerate([('key',c) for c in key_columns(t)]+[('data',c) for c in t.columns]):
            rows.append([t.name,position,t.kind,t.owner,t.scope,c.name,role,kind_of(c),c.entity or c.vocabulary or c.enum or c.check,c.optional])
    return rows


ROWS=schema_rows()


@db.timed
def schema_grid(filters,sort,desc,offset,limit):
    source,params=rows_source(['text','int4']+['text']*7+['bool'],ROWS)
    kinds={'table':'table','position':'number','optional':'bool'}
    specs=[Spec(name,kinds.get(name,'text'),f't.v{i}') for i,name in enumerate(NAMES)]
    return grid(specs,source,params,filters,sort,desc,offset,limit,None,['table','position'])


def stamp():
    found=db.row('''select max(run_id) as run,count(*) filter (where ended_at is null) as open,max(ended_at) as ended,
                           (select max(seq) from snapshot s where s.run_id=(select max(run_id) from run)) as seq,
                           (select max(n) from loop_action a where a.run_id=(select max(run_id) from run)) as n
                    from run''')
    return f"{found['run']}.{found['open']}.{found['ended']}.{found['seq']}.{found['n']}"
