from interface.actions.catalogue import BY_NAME
from interface.recording.spec import TABLE

from . import db
from .actions import ACTION_SELECT, action_rows, entity_of, param_specs
from .models import (Count, EntityDetail, EntityList, EntityRow, EntityTable, KeyedVersions, Scope, Series, TableCount,
                     Version)
from .names import LAYOUTS, Resolver, describe, game_date, owned_tables
from .runs import LOOP_PARAMS, numeric

ACTIONS_PER_ENTITY=200


def naming_params(kind):
    return sorted({(action,p.name) for action in [*BY_NAME,*LOOP_PARAMS] for p in param_specs(action) if entity_of(p.kind)==kind})


def data_select(layout,prefix='h'):
    return [f'{prefix}.{c} as a{i}' for i,c in enumerate(layout.data)]


def data_values(layout,found):
    return [found[f'a{i}'] for i in range(len(layout.data))]


@db.timed
def entity_list(run_id,kind,seq,offset,limit,gone):
    table=TABLE[kind+'_history']
    layout=LAYOUTS[table.name]
    last=db.value('select max(seq) from snapshot where run_id=%s',(run_id,))
    if last is None:
        return None
    seq=last if seq is None else min(seq,last)
    at=db.value('select game_date from snapshot where run_id=%s and seq=%s',(run_id,seq))
    latest=(f'select distinct on (h.{kind}) h.{kind} as id,h.present,{",".join(data_select(layout))} from {table.name} h '
            f'where h.run_id=%s and h.seq<=%s order by h.{kind},h.seq desc')
    keep='' if gone else 'where v.present'
    total=db.value(f'select count(*) from ({latest}) v {keep}',(run_id,seq))
    found=db.rows(f'select v.*,e.first_seq from ({latest}) v join {kind} e on e.run_id=%s and e.{kind}=v.id {keep} order by v.id limit %s offset %s',
                  (run_id,seq,run_id,limit,offset))
    resolver=Resolver(run_id)
    for f in found:
        resolver.ref(kind,f['id'])
    pending=[resolver.add(table.columns,data_values(layout,f)) for f in found]
    cells=resolver.resolve()
    rows=[EntityRow(ref=resolver.reference(kind,f['id']),first_seq=f['first_seq'],present=f['present'],cells=cells[i]) for f,i in zip(found,pending)]
    return EntityList(scope=Scope(text=f'every {kind} of run {run_id} as the recorder knew it at snapshot {seq}'+('' if gone else ', still present'),
                                  detail='each row is the latest recorded version at or before this snapshot'),
                      kind=kind,seq=seq,game_date=game_date(at),total=Count(value=total,noun=kind.replace('_',' ')+'s',population='at this snapshot'),
                      columns=[describe(c) for c in table.columns],rows=rows)


def snapshot_dates(run_id):
    return {f['seq']:f['game_date'] for f in db.rows('select seq,game_date from snapshot where run_id=%s',(run_id,))}


@db.timed
def entity_table(run_id,kind,ident,name,dates):
    table=TABLE[name]
    if table.owner!=kind or table.kind=='sample':
        return None
    layout=LAYOUTS[name]
    extra=[f't.{c.name} as k{i}' for i,c in enumerate(table.keys)]
    present='t.present' if layout.versioned else 'true as present'
    order=','.join([f't.{c.name}' for c in table.keys]+['t.seq'])
    found=db.rows(f'select {",".join(extra+["t.seq",present]+data_select(layout,"t"))} from {name} t where t.run_id=%s and t.{kind}=%s order by {order}',
                  (run_id,ident))
    resolver=Resolver(run_id)
    groups={}
    for f in found:
        key=tuple(f[f'k{i}'] for i in range(len(table.keys)))
        groups.setdefault(key,[]).append((f['seq'],f['present'],resolver.add(table.columns,data_values(layout,f))))
    keyed=[(resolver.add(table.keys,list(key)),versions) for key,versions in groups.items()]
    cells=resolver.resolve()
    return EntityTable(table=name,kind=table.kind,keys=[describe(c) for c in table.keys],columns=[describe(c) for c in table.columns],rows=len(found),
                       groups=[KeyedVersions(keys=cells[k],versions=[Version(seq=s,game_date=game_date(dates[s]),present=p,cells=cells[i]) for s,p,i in versions])
                               for k,versions in keyed])


def sample_series(run_id,kind,ident,table):
    layout=LAYOUTS[table.name]
    found=db.rows(f'select seq,n,date,{",".join(data_select(layout,"t"))} from {table.name} t where t.run_id=%s and t.{kind}=%s order by n',(run_id,ident))
    out=[]
    for i,column in enumerate(table.columns):
        points=[f for f in found if f[f'a{i}'] is not None]
        if numeric(column) and points:
            out.append(Series(table=table.name,column=column.name,label=f'{table.name}.{column.name}',title=column.name.replace('_',' '),x='sample',xs=[f['n'] for f in points],
                              values=[f[f'a{i}'] for f in points],seqs=[f['seq'] for f in points],hours=[f['date'] for f in points],
                              scope=Scope(text=f'{column.name} samples the game kept for {kind} {ident}',detail='in sample order')))
    return out


@db.timed
def entity_detail(run_id,kind,ident):
    anchor=db.row(f'select first_seq from {kind} where run_id=%s and {kind}=%s',(run_id,ident))
    if anchor is None:
        return None
    dates=snapshot_dates(run_id)
    owned=owned_tables(kind)
    counts=db.row('select '+','.join(f'(select count(*) from {t.name} where run_id=%(run)s and {kind}=%(id)s) as t{i}' for i,t in enumerate(owned)),
                  {'run':run_id,'id':ident})
    tables=[TableCount(table=t.name,kind=t.kind,owner=kind,rows=counts[f't{i}']) for i,t in enumerate(owned) if counts[f't{i}'] and t.kind!='sample']
    series=[s for t in owned if t.kind=='sample' for s in sample_series(run_id,kind,ident,t)]
    history=entity_table(run_id,kind,ident,kind+'_history',dates)
    names=naming_params(kind)
    acted=db.rows(f'''{ACTION_SELECT} where l.run_id=%s and exists (select 1 from loop_action_param p where p.run_id=l.run_id and p.n=l.n
                      and p.integer_value=%s and (a.name,p.name) in (select unnest(%s::text[]),unnest(%s::text[]))) order by l.n desc limit %s''',
                  (run_id,ident,[a for a,_ in names],[p for _,p in names],ACTIONS_PER_ENTITY)) if names else []
    labelled=Resolver(run_id)
    labelled.ref(kind,ident)
    labelled.resolve()
    versions=history.groups[0].versions if history.groups else []
    return EntityDetail(ref=labelled.reference(kind,ident),first_seq=anchor['first_seq'],last_seq=max(dates),present=bool(versions and versions[-1].present),
                        history=history,tables=tables,series=series,actions=action_rows(acted),
                        scope=Scope(text=f'everything run {run_id} recorded about {kind} {ident}',
                                    detail='each version is a snapshot where something in that table changed; values hold until the next version'))
