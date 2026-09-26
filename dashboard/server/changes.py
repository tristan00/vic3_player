from interface.recording.spec import TABLE, TABLES

from . import db
from .actions import ACTION_SELECT, action_rows
from .models import ChangeRow, Scope, SnapshotChanges, TableChanges, TableCount
from .names import LAYOUTS, Resolver, describe, key_columns
from .runs import snapshot_row

CHANGING=[t for t in TABLES if t.kind in ('history','child','listing','subject','singleton','sample')]


def previous_sql(layout):
    match=' and '.join(['p.run_id=t.run_id']+[f'p.{k}=t.{k}' for k in layout.keys])
    earlier,order=('p.n<t.n','p.n desc') if layout.kind=='sample' else ('p.seq<t.seq','p.seq desc')
    return f'select {",".join(["true as found"]+[f"p.{c} as b{i}" for i,c in enumerate(layout.data)])} from {layout.name} p where {match} and {earlier} order by {order} limit 1'


@db.timed
def snapshot_changes(run_id,seq):
    snap=db.row('select s.*,(select count(*) from loop_action a where a.run_id=s.run_id and a.after_seq=s.seq) as actions from snapshot s '
                'where s.run_id=%s and s.seq=%s',(run_id,seq))
    if snap is None:
        return None
    prior=db.row('select s.*,0 as actions from snapshot s where s.run_id=%s and s.seq=%s',(run_id,seq-1))
    counts=db.row('select '+','.join(f'(select count(*) from {t.name} where run_id=%(run)s and seq=%(seq)s) as t{i}' for i,t in enumerate(CHANGING)),
                  {'run':run_id,'seq':seq})
    tables=sorted([TableCount(table=t.name,kind=t.kind,owner=t.owner,rows=counts[f't{i}']) for i,t in enumerate(CHANGING) if counts[f't{i}']],
                  key=lambda t:(-t.rows,t.table))
    actions=action_rows(db.rows(f'{ACTION_SELECT} where l.run_id=%s and l.after_seq=%s order by l.n',(run_id,seq)))
    detail=('the recorder stores a row only when it differs from the previous snapshot, so these rows are everything that changed since snapshot '
            f'{seq-1}; the actions listed were executed between the two snapshots, and game time may also have passed')
    return SnapshotChanges(scope=Scope(text=f'every recorded change at snapshot {seq} of run {run_id}',
                                       detail=detail if prior else 'the first snapshot of a run records everything as new'),
                           snapshot=snapshot_row(snap),previous=None if prior is None else snapshot_row(prior),tables=tables,actions=actions)


@db.timed
def table_changes(run_id,seq,name,offset,limit):
    table=TABLE[name]
    layout=LAYOUTS[name]
    total=db.value(f'select count(*) from {name} where run_id=%s and seq=%s',(run_id,seq))
    present='t.present' if layout.versioned else 'true'
    selected=([f't.{k} as k{i}' for i,k in enumerate(layout.keys)]+[f'{present} as present']+[f't.{c} as a{i}' for i,c in enumerate(layout.data)]
              +['b.found']+[f'b.b{i}' for i in range(len(layout.data))])
    order=','.join(f't.{k}' for k in layout.keys) or 't.seq'
    found=db.rows(f'''select {",".join(selected)} from {name} t left join lateral ({previous_sql(layout)}) b on true
                      where t.run_id=%s and t.seq=%s order by {order} limit %s offset %s''',(run_id,seq,limit,offset))
    keys=key_columns(table)
    width=range(len(layout.data))
    resolver=Resolver(run_id)
    pending=[]
    for f in found:
        key_cells=resolver.add(keys,[f[f'k{i}'] for i in range(len(layout.keys))])
        after=resolver.add(table.columns,[f[f'a{i}'] for i in width])
        prior=resolver.add(table.columns,[f[f'b{i}'] for i in width]) if f['found'] else None
        changed=[layout.data[i] for i in width if not f['found'] or f[f'b{i}']!=f[f'a{i}']]
        pending.append((key_cells,f['present'],after,prior,changed))
    cells=resolver.resolve()
    return TableChanges(table=name,kind=table.kind,owner=table.owner,keys=[describe(c) for c in keys],columns=[describe(c) for c in table.columns],
                        rows=[ChangeRow(keys=cells[k],present=p,cells=cells[a],before=None if b is None else cells[b],changed=changed)
                              for k,p,a,b,changed in pending],total=total)
