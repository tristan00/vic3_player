import re
from functools import cache
from pathlib import Path

from interface.recording import store

from . import db
from .grid import Spec, grid

NUMBERS={'smallint','integer','bigint','real','double precision','numeric'}
TABLES=re.findall(r'^create table (\w+)',(Path(store.__file__).parent/'schema_meta.sql').read_text(encoding='utf-8'),re.M)


@cache
def named_tables():
    return {f['table_name'] for f in db.rows("select table_name from information_schema.columns where column_name='name' and table_schema='public'")}


@cache
def specs(table):
    columns=db.rows('select column_name as name,data_type as type,domain_name as domain from information_schema.columns '
                    "where table_name=%s and table_schema='public' order by ordinal_position",(table,))
    targets={f['name']:f['target'] for f in db.rows('''select a.attname as name,k.confrelid::regclass::text as target from pg_constraint k
        join pg_attribute a on a.attrelid=k.conrelid and a.attnum=k.conkey[1] where k.contype='f' and array_length(k.conkey,1)=1 and k.conrelid=%s::regclass''',(table,))}
    has_run='run_id' in [c['name'] for c in columns]
    out=[]
    for c in columns:
        name=c['name']
        target=targets.get(name)
        if name=='run_id' or target=='run':
            out.append(Spec(name,'run',f't.{name}'))
        elif has_run and (name=='seq' or name.endswith('_seq')):
            out.append(Spec(name,'seq',f't.{name}',run='run_id'))
        elif table=='loop_action' and name=='n':
            out.append(Spec(name,'n',f't.{name}',run='run_id'))
        elif name.endswith('_seed') or name.endswith('_id'):
            out.append(Spec(name,'text',f't.{name}'))
        elif target=='action':
            out.append(Spec(name,'action',f'(select name from action where action=t.{name})'))
        elif target in named_tables():
            key=db.value("select a.attname from pg_index i join pg_attribute a on a.attrelid=i.indrelid and a.attnum=i.indkey[0] "
                         "where i.indrelid=%s::regclass and i.indisprimary",(target,))
            out.append(Spec(name,'text',f'(select name from {target} where {key}=t.{name})'))
        elif c['domain']=='game_hours':
            out.append(Spec(name,'date',f't.{name}'))
        elif c['type'].startswith('timestamp'):
            out.append(Spec(name,'time',f't.{name}'))
        elif c['type']=='boolean':
            out.append(Spec(name,'bool',f't.{name}'))
        elif c['type'] in NUMBERS:
            out.append(Spec(name,'number',f't.{name}'))
        else:
            out.append(Spec(name,'text',f't.{name}'))
    return out


@db.timed
def meta_grid(table,filters,sort,desc,offset,limit,run_id=None):
    found=specs(table)
    keys=db.rows('''select a.attname as name from pg_index i join pg_attribute a on a.attrelid=i.indrelid and a.attnum=any(i.indkey)
                    where i.indrelid=%s::regclass and i.indisprimary''',(table,))
    order=[k['name'] for k in keys] or [found[0].name]
    return grid(found,f'from {table} t',{},filters,sort,desc,offset,limit,run_id,order)
