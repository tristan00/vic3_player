from interface.recording.spec import ENTITIES, TABLE, TABLES

from . import db
from .actions import action_grid, entity_of, param_specs
from .grid import Spec, grid, recorded
from .models import EntityInfo, Ref, Reference, TableCount, TreatyInfo, TreatyTerm
from .names import LAYOUTS, game_date, key_columns, labels, owned_tables
from interface.actions.catalogue import BY_NAME
from .runs import LOOP_PARAMS


@db.timed
def last_seq(run_id):
    return db.value('select max(seq) from snapshot where run_id=%s',(run_id,))


@db.timed
def keyless(kind):
    return [t for t in owned_tables(kind) if not t.keys and t.kind!='sample' and t.name!=kind+'_history']


@db.timed
def table_grid(run_id,name,seq,versions,filters,sort,desc,offset,limit):
    table=TABLE[name]
    layout=LAYOUTS[name]
    keys=key_columns(table)
    specs=[]
    if versions or table.kind=='sample':
        specs.append(Spec('seq','seq','t.seq'))
        specs.append(Spec('game_date','date','s.game_date'))
    if table.kind=='sample':
        specs+=[Spec('n','number','t.n'),Spec('sample_date','date','t.date')]
    if versions and layout.versioned:
        specs.append(Spec('present','bool','t.present'))
    specs+=[recorded(c,'t') for c in keys]+[recorded(c,'t') for c in table.columns]
    if table.kind=='sample' or versions:
        source=f'from {name} t join snapshot s on s.run_id=t.run_id and s.seq=t.seq where t.run_id=%(run)s and t.seq<=%(seq)s'
        order=['seq','n'] if table.kind=='sample' else [*layout.keys,'seq']
    else:
        pick=','.join(f'x.{k}' for k in layout.keys)
        latest=(f'(select distinct on ({pick}) x.* from {name} x where x.run_id=%(run)s and x.seq<=%(seq)s order by {pick},x.seq desc)' if pick else
                f'(select x.* from {name} x where x.run_id=%(run)s and x.seq<=%(seq)s order by x.seq desc limit 1)')
        source=f'from {latest} t'+(' where t.present' if layout.versioned else '')
        order=layout.keys
    found=grid(specs,source,{'run':run_id,'seq':seq},filters,sort,desc,offset,limit,run_id,order)
    found.keys=layout.keys
    return found


@db.timed
def entity_grid(run_id,kind,seq,gone,filters,sort,desc,offset,limit):
    history=TABLE[kind+'_history']
    specs=[Spec(kind,'ref','h.'+kind,entity=kind,group=kind),Spec('first_seq','seq','e.first_seq',group=kind)]
    if gone:
        specs.append(Spec('present','bool','h.present',group=kind))
    specs+=[recorded(c,'h',kind) for c in history.columns]
    joins=[]
    for i,table in enumerate(keyless(kind)):
        alias=f'j{i}'
        specs+=[recorded(c,alias,table.name,f'{table.name}.{c.name}') for c in table.columns]
        joins.append(f'left join lateral (select * from {table.name} x where x.run_id=h.run_id and x.{kind}=h.{kind} and x.seq<=%(seq)s '
                     f'order by x.seq desc limit 1) {alias} on true')
    source=(f'from (select distinct on ({kind}) * from {history.name} where run_id=%(run)s and seq<=%(seq)s order by {kind},seq desc) h '
            f'join {kind} e on e.run_id=h.run_id and e.{kind}=h.{kind} {" ".join(joins)}'+('' if gone else ' where h.present'))
    return grid(specs,source,{'run':run_id,'seq':seq},filters,sort,desc,offset,limit,run_id,[kind])


@db.timed
def naming_params(kind):
    return sorted({(action,p.name) for action in [*BY_NAME,*LOOP_PARAMS] for p in param_specs(action) if entity_of(p.kind)==kind})


@db.timed
def references(kind):
    return [(t,c) for t in TABLES for c in t.keys+t.columns if c.entity==kind]


@db.timed
def entity_info(run_id,kind,ident,seq=None):
    anchor=db.row(f'select first_seq from {kind} where run_id=%s and {kind}=%s',(run_id,ident))
    if anchor is None:
        return None
    owned=owned_tables(kind)
    pointing=references(kind)
    counts=db.row('select '+','.join([f'(select count(*) from {t.name} where run_id=%(run)s and {kind}=%(id)s) as o{i}' for i,t in enumerate(owned)]
                                     +[f'(select count(*) from {t.name} where run_id=%(run)s and {c.name}=%(id)s) as r{i}' for i,(t,c) in enumerate(pointing)]),
                  {'run':run_id,'id':ident})
    acted=db.value(f'select count(*) from loop_action l join action a using (action) where l.run_id=%(run)s and {NAMED}',{'run':run_id,**naming(kind,ident)})
    present=db.value(f'select present from {kind}_history where run_id=%s and {kind}=%s order by seq desc limit 1',(run_id,ident))
    last=last_seq(run_id)
    treaty=treaty_info(run_id,ident,last if seq is None else min(seq,last)) if kind=='treaty' else None
    title=f'{treaty.first.label or treaty.first.id} — {treaty.second.label or treaty.second.id}' if treaty else labels(run_id,kind,[ident])[ident]
    return EntityInfo(ref=Ref(kind=kind,id=ident,label=title,run=run_id),first_seq=anchor['first_seq'],present=bool(present),last_seq=last,
                      owned=[TableCount(table=t.name,kind=t.kind,owner=kind,keyed=bool(t.keys),rows=counts[f'o{i}']) for i,t in enumerate(owned)],
                      references=[Reference(table=t.name,column=c.name,rows=counts[f'r{i}']) for i,(t,c) in enumerate(pointing) if counts[f'r{i}']],
                      actions=acted,treaty=treaty)


@db.timed
def treaty_info(run_id,ident,seq):
    row=db.row('select * from treaty_history where run_id=%s and treaty=%s and seq<=%s order by seq desc limit 1',(run_id,ident,seq))
    if row is None:
        return None
    present=row['present']
    if not present:
        seq=row['seq']-1
        row=db.row('select * from treaty_history where run_id=%s and treaty=%s and present and seq<=%s order by seq desc limit 1',(run_id,ident,seq))
    articles=db.rows('select a.treaty_article,k.name,a.source_country,a.target_country from treaty_article_at(%s,%s) a '
                     'join treaty_article_type k using(treaty_article_type) where a.treaty=%s order by k.name,a.treaty_article',(run_id,seq,ident))
    ids={row['first_country'],row['second_country']}|{article[key] for article in articles for key in ('source_country','target_country') if article[key] is not None}
    countries={found['country']:found['name'] for found in db.rows(
        'select distinct on (c.country) c.country,d.name from country_history c left join country_definition d using(country_definition) '
        'where c.run_id=%s and c.country=any(%s) and c.present and c.seq<=%s order by c.country,c.seq desc',(run_id,list(ids),seq))}
    country=lambda value:None if value is None else Ref(kind='country',id=value,label=countries.get(value),run=run_id)
    hours=db.value('select game_date from snapshot where run_id=%s and seq<=%s order by seq desc limit 1',(run_id,seq))
    entered=row['entered_into_force_on']
    status='No longer present' if not present else 'Withdrawn' if row['withdrawn'] else 'Proposed' if entered is None or entered>hours else 'In force'
    return TreatyInfo(seq=seq,first=country(row['first_country']),second=country(row['second_country']),status=status,
                      entered_into_force_on=game_date(entered),binding_period_days=row['binding_period'],
                      binding_until=game_date(entered+row['binding_period']*24) if entered is not None else None,
                      terms=[TreatyTerm(article=Ref(kind='treaty_article',id=a['treaty_article'],label=a['name'],run=run_id),
                                        source=country(a['source_country']),target=country(a['target_country'])) for a in articles])


NAMED=('exists (select 1 from loop_action_param q where q.run_id=l.run_id and q.n=l.n and q.integer_value=%(id)s '
       'and (a.name,q.name) in (select unnest(%(actions)s::text[]),unnest(%(params)s::text[])))')


@db.timed
def naming(kind,ident):
    names=naming_params(kind)
    return {'id':ident,'actions':[a for a,_ in names],'params':[p for _,p in names]}


@db.timed
def entity_actions(run_id,kind,ident,filters,sort,desc,offset,limit):
    return action_grid(f'where l.run_id=%(run)s and {NAMED}',{'run':run_id,**naming(kind,ident)},filters,sort,desc,offset,limit,run_id)


@db.timed
def run_tables(run_id,filters,sort,desc,offset,limit):
    source=' union all '.join(f"select '{t.name}' as name,'{t.kind}' as kind,{repr(t.owner) if t.owner else 'null'}::text as owner,{len(t.keys)} as keys,"
                              f"{len(t.columns)} as columns,(select count(*) from {t.name} where run_id=%(run)s) as rows" for t in TABLES)
    specs=[Spec('table','table','u.name'),Spec('kind','text','u.kind'),Spec('owner','kind','u.owner'),Spec('keys','number','u.keys'),
           Spec('columns','number','u.columns'),Spec('rows','number','u.rows')]
    return grid(specs,f'from ({source}) u',{'run':run_id},filters,sort,desc,offset,limit,run_id,['table'])


@db.timed
def run_kinds(run_id,filters,sort,desc,offset,limit):
    source=' union all '.join(f"select '{k}' as kind,(select count(*) from {k} where run_id=%(run)s) as ever,"
                              f"(select count(*) from (select distinct on ({k}) present from {k}_history where run_id=%(run)s order by {k},seq desc) v where present) as present,"
                              f"{len(owned_tables(k))} as tables" for k in ENTITIES)
    specs=[Spec('kind','kind','u.kind'),Spec('present','number','u.present'),Spec('ever','number','u.ever'),Spec('tables','number','u.tables')]
    return grid(specs,f'from ({source}) u',{'run':run_id},filters,sort,desc,offset,limit,run_id,['kind'])


@db.timed
def snapshot_at(run_id,seq):
    last=last_seq(run_id)
    if last is None:
        return None,None,None
    seq=last if seq is None else min(seq,last)
    return seq,last,game_date(db.value('select game_date from snapshot where run_id=%s and seq=%s',(run_id,seq)))
