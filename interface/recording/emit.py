import re
from pathlib import Path

from .spec import CHECKS,CLOSED,ENTITIES,ENUMS,TABLES,VOCABULARIES,Col,I4

HERE=Path(__file__).parent

def kind(column):
    if column.vocabulary:
        return 'int2' if column.vocabulary in CLOSED else 'int4'
    return column.kind


def definition(column,required):
    return f'  {column.name} {kind(column)}'+(' not null' if required else '')


def references(table,columns):
    lines=[]
    for column in columns:
        if column.entity:
            if column.entity not in ENTITIES:
                raise SystemExit(f'{table}.{column.name} references unknown entity {column.entity}')
            lines.append(f'  foreign key (run_id, {column.name}) references {column.entity}')
        elif column.vocabulary:
            if column.vocabulary not in VOCABULARIES:
                raise SystemExit(f'{table}.{column.name} references unknown vocabulary {column.vocabulary}')
            lines.append(f'  foreign key ({column.name}) references {column.vocabulary}')
        elif column.enum:
            if column.enum not in ENUMS:
                raise SystemExit(f'{table}.{column.name} references unknown enum {column.enum}')
            lines.append(f'  foreign key ({column.name}) references {column.enum}')
        elif column.check:
            lines.append(f"  check ({column.name} in ({', '.join(repr(value) for value in CHECKS[column.check])}))")
    return lines


def key_columns(table):
    return ([Col(table.owner,I4,entity=table.owner)] if table.owner else [])+table.keys


def emit(table):
    keys=key_columns(table)
    lines=['  run_id int4 not null']+[definition(k,True) for k in keys]
    if table.kind=='sample':
        lines.append('  n int4 not null')
    lines.append('  seq int4 not null')
    if table.kind=='sample':
        lines.append('  date game_hours')
    versioned=table.kind in ('history','child','listing')
    if versioned:
        lines.append('  present bool not null')
    lines+=[definition(c,not versioned and not c.optional) for c in table.columns]
    names=[c.name for c in keys+table.columns]
    if len(names)!=len(set(names)):
        raise SystemExit(f'{table.name} repeats a column: {names}')
    ordering=[k.name for k in keys]+(['n'] if table.kind=='sample' else ['seq'])
    lines.append(f"  primary key (run_id, {', '.join(ordering)})")
    if table.owner:
        lines.append(f'  foreign key (run_id, {table.owner}) references {table.owner}')
    lines.append('  foreign key (run_id, seq) references snapshot')
    lines+=references(table.name,table.keys+table.columns)
    if versioned and table.columns:
        required=[c.name for c in table.columns if not c.optional]
        if required:
            lines.append(f"  check (present = (num_nulls({', '.join(required)}) = 0))")
        lines.append(f"  check (present or num_nonnulls({', '.join(c.name for c in table.columns)}) = 0)")
    if table.kind in ('subject','singleton') and all(c.optional for c in table.columns):
        raise SystemExit(f'{table.name} has no required column')
    if table.name=='player_budget_line':
        lines.append('  foreign key (direction, line) references budget_line')
    return f'create table {table.name} (\n'+',\n'.join(lines)+'\n);\n'


def at_function(table):
    keys=[k.name for k in key_columns(table)]
    data=[c.name for c in table.columns]
    columns=', '.join(keys+['seq']+data)
    picked=', '.join('l.'+name for name in keys+['seq']+data)
    returns=', '.join(f'"{name}" {typ}' for name,typ in [(k.name,kind(k)) for k in key_columns(table)]+[('seq','int4')]+[(c.name,kind(c)) for c in table.columns])
    owner=table.owner
    subkeys=[k.name for k in table.keys]
    if table.kind=='singleton':
        body=f'select {columns} from {table.name} where run_id = run and seq <= at order by seq desc limit 1'
    elif owner is None:
        latest=(f"select distinct on ({', '.join(keys)}) {columns}, present from {table.name} where run_id = run and seq <= at "
                f"order by {', '.join(k+' desc' for k in keys)}, seq desc")
        body=f'select {columns} from ({latest}) latest where present'
    else:
        if subkeys:
            latest=(f"select distinct on ({', '.join(subkeys)}) {columns}, present from {table.name} t where t.run_id = run and t.{owner} = a.{owner} and t.seq <= at "
                    f"order by {', '.join(k+' desc' for k in subkeys)}, t.seq desc")
        else:
            latest=(f"select {columns}{'' if table.kind=='subject' else ', present'} from {table.name} t where t.run_id = run and t.{owner} = a.{owner} and t.seq <= at "
                    f"order by t.seq desc limit 1")
        alive=(f", lateral (select present from {owner}_history h where h.run_id = run and h.{owner} = a.{owner} and h.seq <= at order by h.seq desc limit 1) o"
               if table.kind=='subject' else '')
        live='o.present' if table.kind=='subject' else 'l.present'
        body=f'select {picked} from {owner} a{alive}, lateral ({latest}) l where a.run_id = run and {live}'
    name=table.name[:-len('_history')] if table.kind=='history' else table.name
    return f'create function {name}_at(run int4, at int4) returns table ({returns}) language sql stable as $$\n  {body}\n$$;\n'


def anchor(name):
    extra=''
    if name=='province':
        extra=('  world_id int4 not null,\n  color int4 not null,\n'
               '  foreign key (run_id, world_id) references run (run_id, world_id),\n  foreign key (world_id, color) references world_province,\n'
               '  unique (run_id, color),\n')
    return (f'create table {name} (\n  run_id int4 not null references run,\n  {name} int4 not null,\n  first_seq int4 not null,\n{extra}'
            f'  primary key (run_id, {name}),\n  foreign key (run_id, first_seq) references snapshot\n);\n')


def vocabulary(name):
    size='int2' if name in CLOSED else 'int4'
    return f'create table {name} (\n  {name} {size} generated by default as identity primary key,\n  name text not null unique\n);\n'


def enum(name):
    return f'create table {name} (\n  {name} int2 primary key,\n  name text unique\n);\n'


def referenced_only():
    parts=[f"  select run_id, '{name}' as entity, {name} as identity, first_seq from {name} a\n"
           f"  where not exists (select 1 from {name}_history h where h.run_id = a.run_id and h.{name} = a.{name})" for name in ENTITIES if name!='province']
    return 'create view referenced_only as\n'+'\n  union all\n'.join(parts)+';\n'


def main():
    order=[t for t in TABLES if t.kind in ('history','child','listing','singleton')]+[t for t in TABLES if t.kind=='subject']
    parts=[(HERE/'schema_head.sql').open().read().rstrip()+'\n\n','\n'.join(vocabulary(name) for name in sorted(VOCABULARIES)),'\n'+'\n'.join(enum(name) for name in ENUMS),
           '\n'+(HERE/'schema_meta.sql').open().read().rstrip()+'\n\n','\n'.join(anchor(name) for name in ENTITIES),'\n'+'\n'.join(emit(t) for t in TABLES),
           '\n'+'\n'.join(at_function(t) for t in order),
           '\n'+''.join(f'create index {t.name}_seq on {t.name} using brin (run_id, seq) with (autosummarize = on);\n' for t in TABLES),
           '\n'+referenced_only(),
           '\n'+(HERE/'schema_tail.sql').open().read().rstrip()+'\n']
    sql=''.join(parts)
    names=re.findall(r'create table (\w+)',sql)
    if len(names)!=len(set(names)):
        raise SystemExit(f'duplicate tables {sorted(n for n in set(names) if names.count(n)>1)}')
    columns={}
    for table in TABLES:
        for column in key_columns(table)+table.columns:
            columns.setdefault(column.name,set()).add(kind(column))
    clashes={name:types for name,types in columns.items() if len(types)>1}
    if clashes:
        raise SystemExit(f'one name, several types: {clashes}')
    open('D:/vic3_agent/interface/recording/schema.sql','w',newline='\n').write(sql)
    widest=sorted(((len(t.columns)+len(t.keys),t.name) for t in TABLES),reverse=True)[:6]
    print(len(names),'tables',len(ENTITIES),'entities',len(order),'functions','widest',widest)


if __name__=="__main__":
    main()
