from interface.options.stored import date_text
from interface.recording.spec import B, ENTITIES, F, H, I2, I4, I8, T, TABLE, Col
from interface.recording.store import Layout

from . import db
from .models import GameDate

NUMERIC={F,I2,I4,I8}
LABELS={'country':('country_definition',),'state':('state_region',),'pop':('pop_type',),'building':('building_type',),
        'character':('first_name_key','last_name_key'),'formation':('name_key',)}
NAMES={}
LAYOUTS={name:Layout(table) for name,table in TABLE.items()}


@db.timed
def game_date(hours):
    if hours is None:
        return None
    text=date_text(hours)
    return GameDate(hours=hours,text=text[:-2] if text.endswith('.0') else text)


@db.timed
def kind_of(column):
    if column.entity:
        return 'ref'
    if column.vocabulary:
        return 'vocab'
    if column.enum:
        return 'enum'
    if column.kind==H:
        return 'date'
    if column.kind==B:
        return 'bool'
    if column.kind in NUMERIC:
        return 'number'
    return 'text'


@db.timed
def key_columns(table):
    owner=[] if table.owner is None else [Col(table.owner,I4,entity=table.owner)]
    return owner+list(table.keys)


@db.timed
def label_columns(kind):
    if kind in LABELS:
        return LABELS[kind]
    table=TABLE[kind+'_history']
    return tuple(column.name for column in table.columns if column.vocabulary)[:1]


@db.timed
def vocab_column(kind,name):
    return next(column for column in TABLE[kind+'_history'].columns if column.name==name)


@db.timed
def lookup(table,ids):
    missing=sorted({i for i in ids if i is not None and (table,i) not in NAMES})
    if missing:
        for found in db.rows(f'select {table} as id,name from {table} where {table}=any(%s)',(missing,)):
            NAMES[table,found['id']]=found['name']
    return {i:NAMES.get((table,i)) for i in ids if i is not None}


@db.timed
def labels(run_id,kind,ids):
    ids=sorted({i for i in ids if i is not None})
    if not ids:
        return {}
    if kind=='province':
        return {found['province']:f"#{found['color']:06x}" for found in
                db.rows('select province,color from province where run_id=%s and province=any(%s)',(run_id,ids))}
    names=label_columns(kind)
    if not names:
        return {i:None for i in ids}
    latest=db.rows(f'select distinct on ({kind}) {kind} as id,{",".join(names)} from {kind}_history '
                   f'where run_id=%s and {kind}=any(%s) and present order by {kind},seq desc',(run_id,ids))
    words={}
    for name in names:
        vocabulary=vocab_column(kind,name).vocabulary
        words[name]=lookup(vocabulary,[found[name] for found in latest])
    out={i:None for i in ids}
    for found in latest:
        parts=[words[name].get(found[name]) for name in names]
        out[found['id']]=' '.join(part for part in parts if part) or None
    return out


@db.timed
def owned_tables(kind):
    return [table for table in TABLE.values() if table.owner==kind]
