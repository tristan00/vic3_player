from interface.recording.spec import TABLE, TABLES

from . import db
from .grid import Spec, grid, recorded
from .names import LAYOUTS, key_columns


@db.timed
def changed_tables(run_id,seq,filters,sort,desc,offset,limit):
    source=' union all '.join(f"select '{t.name}' as name,'{t.kind}' as kind,{repr(t.owner) if t.owner else 'null'}::text as owner,"
                              f"(select count(*) from {t.name} where run_id=%(run)s and seq=%(seq)s) as rows" for t in TABLES)
    specs=[Spec('table','table','u.name'),Spec('kind','text','u.kind'),Spec('owner','text','u.owner'),Spec('rows','number','u.rows')]
    return grid(specs,f'from ({source}) u where u.rows>0',{'run':run_id,'seq':seq},filters,sort or 'rows',True if sort is None else desc,offset,limit,run_id,['table'])


@db.timed
def table_changes(run_id,seq,name,filters,sort,desc,offset,limit):
    table=TABLE[name]
    layout=LAYOUTS[name]
    match=' and '.join(['p.run_id=t.run_id']+[f'p.{k}=t.{k}' for k in layout.keys])
    earlier,order=('p.n<t.n','p.n desc') if layout.kind=='sample' else ('p.seq<t.seq','p.seq desc')
    specs=[recorded(c,'t') for c in key_columns(table)]
    if layout.versioned:
        specs+=[Spec('present','bool','t.present',group='present',label='now'),Spec('present.before','bool','b.present',group='present',label='before')]
    for c in table.columns:
        now,before=recorded(c,'t',c.name),recorded(c,'b',c.name,f'{c.name}.before')
        now.label,before.label='now','before'
        specs+=[now,before]
    source=f'from {name} t left join lateral (select p.* from {name} p where {match} and {earlier} order by {order} limit 1) b on true where t.run_id=%(run)s and t.seq=%(seq)s'
    return grid(specs,source,{'run':run_id,'seq':seq},filters,sort,desc,offset,limit,run_id,layout.keys or [specs[0].name])
