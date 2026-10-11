import json
import re
from threading import Lock

from interface.common import DEFAULT_GAME
from interface.recording.spec import CLOSED, ENTITIES, TABLE

from . import db

LOCK=Lock()
CATALOG={}
VOCABULARY={}
LABELS={}
MANIFESTS={}
ENGLISH={}
TEXT=re.compile(r'^\s+([\w.-]+):\d*\s+"([^"$\[\]#@£]+)"\s*$',re.M)
FOREIGN='''select s.relname::text,array_agg(a.attname::text order by x.i),t.relname::text
from pg_constraint c join pg_class s on s.oid=c.conrelid join pg_class t on t.oid=c.confrelid
cross join lateral unnest(c.conkey) with ordinality x(k,i) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=x.k
where c.connamespace='public'::regnamespace and c.contype='f' group by c.oid,1,3'''
NAMED="select table_name from information_schema.columns where table_schema='public' and column_name='name'"
COLUMNS='''select table_name,column_name,coalesce(domain_name,data_type) from information_schema.columns
where table_schema='public' order by table_name,ordinal_position'''
PRIMARY='''select s.relname::text,array_agg(a.attname::text order by x.i) from pg_index i join pg_class s on s.oid=i.indrelid
cross join lateral unnest(i.indkey) with ordinality x(k,i) join pg_attribute a on a.attrelid=i.indrelid and a.attnum=x.k
where i.indisprimary and s.relnamespace='public'::regnamespace group by 1'''
FUNCTIONS="select proname::text from pg_proc where pronamespace='public'::regnamespace"


@db.often
def catalog(fresh=False):
    with LOCK:
        if fresh or not CATALOG:
            named={name for name, in db.rows(NAMED)}
            columns={}
            for table,column,kind in db.rows(COLUMNS):
                columns.setdefault(table,{})[column]=kind
            links={}
            for table,keys,target in db.rows(FOREIGN):
                if len(keys)==1 and target in named:
                    links.setdefault(table,{})[keys[0]]=('name',target)
                elif len(keys)==2 and keys[0]=='run_id' and target in ENTITIES:
                    links.setdefault(table,{})[keys[1]]=('entity',target)
            found=dict(columns=columns,links=links,keys=dict(db.rows(PRIMARY)),functions={name for name, in db.rows(FUNCTIONS)})
            CATALOG.clear()
            CATALOG.update(found)
            VOCABULARY.clear()
        return CATALOG


@db.often
def columns(table):
    found=catalog()['columns']
    return found[table] if table in found else catalog(True)['columns'].get(table)


@db.often
def vocabulary(table):
    key=catalog()['keys'][table][0]
    with LOCK:
        if table not in VOCABULARY:
            VOCABULARY[table]=dict(db.rows(f'select "{key}",name from "{table}"'))
        return VOCABULARY[table]


@db.often
def key(table,code):
    found=vocabulary(table)
    if code not in found:
        with LOCK:
            VOCABULARY.pop(table,None)
        found=vocabulary(table)
    if code not in found:
        raise ValueError(f'{table} has no {code}')
    return found[code]


@db.often
def english():
    with LOCK:
        if not ENGLISH:
            for path in sorted((DEFAULT_GAME/'game'/'localization'/'english').rglob('*.yml')):
                ENGLISH.update(TEXT.findall(path.read_text(encoding='utf-8-sig')))
        return ENGLISH


@db.often
def named(table,code,places):
    name=key(table,code)
    if name in places:
        return places[name]
    return english().get(name,name) if table in CLOSED or table=='localization_key' else name


@db.often
def manifest(world):
    with LOCK:
        if world not in MANIFESTS:
            found=db.one("select data from world_asset where world_id=%s and name='manifest.json'",(world,))
            MANIFESTS[world]=json.loads(bytes(found[0]).decode('utf-8')) if found else None
        return MANIFESTS[world]


@db.often
def places(run):
    found=manifest(db.one('select world_id from run where run_id=%s',(run,))[0])
    if found is None:
        return {}
    return {**{state['key']:state['name'] for state in found.get('states',[])},**{country['tag']:country['name'] for country in found.get('countries',[])}}


@db.often
def label_columns(kind):
    known=catalog()
    links=known['links'].get(kind+'_history',{})
    order=[column for column in known['columns'][kind+'_history'] if links.get(column,('',))[0]=='name']
    exact=([column for column in order if column==kind+'_definition'] or [column for column in order if column==kind+'_type'])[:1]
    keyed=[column for column in order if column.endswith('name_key')]
    spec=TABLE[kind+'_history'].columns
    required=[column.name for column in spec if column.vocabulary and not column.optional and column.name in order and column.name not in exact+keyed]
    opening=required[:1] if required and (required[0]==spec[0].name or len(required)==1) else []
    return [[(column,links[column][1]) for column in group] for group in (exact,keyed,opening) if group]


@db.often
def labelled(run,kind,only=None,seq=None):
    groups=label_columns(kind)
    out={}
    if groups:
        known=places(run)
        picked=','.join(f'"{column}"' for group in groups for column,_ in group)
        chosen=''
        params=[run]
        if only is not None:
            chosen+=f' and "{kind}"=any(%s)'
            params.append(list(only))
        if seq is not None:
            chosen+=' and seq<=%s'
            params.append(seq)
        for ident,*codes in db.rows(f'select distinct on ("{kind}") "{kind}",{picked} from {kind}_history where run_id=%s and present{chosen} order by "{kind}",seq desc',params):
            for group in groups:
                taken,codes=codes[:len(group)],codes[len(group):]
                parts=[named(table,code,known) for (_,table),code in zip(group,taken) if code is not None]
                parts=[str(part) for part in parts if part is not None]
                if parts and ident not in out:
                    out[ident]=' '.join(parts)
    return out


@db.often
def labels(run,kind):
    stamp=db.one('select max(seq) from snapshot where run_id=%s',(run,))[0]
    with LOCK:
        found=LABELS.get((run,kind))
    if found and found[0]==stamp:
        return found[1]
    out=labelled(run,kind)
    with LOCK:
        if len(LABELS)>400:
            LABELS.clear()
        LABELS[run,kind]=(stamp,out)
    return out
