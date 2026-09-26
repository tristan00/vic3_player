from collections import defaultdict

from interface.options.stored import date_text
from interface.recording.spec import B, ENTITIES, F, H, I2, I4, I8, T, TABLE, Col
from interface.recording.store import Layout

from . import db
from .models import Cell, Column, GameDate, Ref

NUMERIC={F,I2,I4,I8}
LABELS={'country':('country_definition',),'state':('state_region',),'pop':('pop_type',),'building':('building_type',),
        'character':('first_name_key','last_name_key'),'formation':('name_key',)}
NAMES={}
LAYOUTS={name:Layout(table) for name,table in TABLE.items()}


def game_date(hours):
    if hours is None:
        return None
    text=date_text(hours)
    return GameDate(hours=hours,text=text[:-2] if text.endswith('.0') else text)


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


def describe(column):
    return Column(name=column.name,kind=kind_of(column),entity=column.entity)


def key_columns(table):
    owner=[] if table.owner is None else [Col(table.owner,I4,entity=table.owner)]
    return owner+list(table.keys)


def label_columns(kind):
    if kind in LABELS:
        return LABELS[kind]
    table=TABLE[kind+'_history']
    return tuple(column.name for column in table.columns if column.vocabulary)[:1]


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


class Resolver:
    def __init__(self,run_id):
        self.run_id=run_id
        self.refs=defaultdict(set)
        self.vocab=defaultdict(set)
        self.enums=defaultdict(set)
        self.pending=[]

    def add(self,columns,values):
        cells=[]
        for column,value in zip(columns,values):
            cells.append((column,value))
            if value is None:
                continue
            if column.entity:
                self.refs[column.entity].add(value)
            elif column.vocabulary:
                self.vocab[column.vocabulary].add(value)
            elif column.enum:
                self.enums[column.enum].add(value)
        self.pending.append(cells)
        return len(self.pending)-1

    def ref(self,kind,value):
        self.refs[kind].add(value)

    def resolve(self):
        self.labels={kind:labels(self.run_id,kind,ids) for kind,ids in self.refs.items()}
        self.words={name:lookup(name,ids) for name,ids in self.vocab.items()}
        self.codes={name:lookup(name,ids) for name,ids in self.enums.items()}
        return [[self.cell(column,value) for column,value in cells] for cells in self.pending]

    def reference(self,kind,value):
        return Ref(kind=kind,id=value,label=self.labels.get(kind,{}).get(value))

    def cell(self,column,value):
        if value is None:
            return Cell()
        if column.entity:
            return Cell(ref=self.reference(column.entity,value))
        if column.vocabulary:
            return Cell(text=self.words[column.vocabulary].get(value))
        if column.enum:
            return Cell(text=self.codes[column.enum].get(value) or str(value))
        if column.kind==H:
            return Cell(text=game_date(value).text,num=value)
        if column.kind==B:
            return Cell(text='yes' if value else 'no')
        if column.kind in NUMERIC:
            return Cell(num=float(value))
        return Cell(text=str(value))


def entity_kinds():
    return list(ENTITIES)


def owned_tables(kind):
    return [table for table in TABLE.values() if table.owner==kind]
