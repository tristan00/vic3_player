import hashlib
import json
from pathlib import Path

from interface.common import DEFAULT_DATA
from interface.script import blocks, body, fields, scalar

from . import db
from .runs import STATE

ROOTS=(DEFAULT_DATA/'worlds',Path(__file__).resolve().parents[2]/'artifacts/world_fidelity/worlds')


@db.timed
def manifest(raw):
    value=json.loads(raw)
    if not isinstance(value,dict):
        raise ValueError('Manifest must be an object')
    for key,required in (('countries',('tag','name','states','capital')),('states',('key','name','country','provinces','coastal'))):
        if not isinstance(value.get(key),list) or any(not isinstance(item,dict) or not all(k in item for k in required) for item in value[key]):
            raise ValueError(f'Manifest has invalid {key}')
    return value


@db.timed
def catalog():
    entries={}
    manifests={}
    for row in db.rows("select w.world_id,a.data from world w left join world_asset a on a.world_id=w.world_id and a.name='manifest.json' order by w.world_id desc"):
        raw=bytes(row['data']) if row['data'] is not None else None
        key=str(row['world_id'])
        entries[key]={'key':key,'world_id':row['world_id'],'manifest':None,'directory':None,'issue':None}
        if raw is not None:
            try:
                entries[key]['manifest']=manifest(raw)
                manifests[raw]=key
            except (ValueError,UnicodeError):
                entries[key]['issue']='Stored manifest is unreadable'
    for root in ROOTS:
        if not root.exists():
            continue
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            key='local-'+hashlib.sha256(str(directory).encode()).hexdigest()[:16]
            entry={'key':key,'world_id':None,'manifest':None,'directory':directory,'issue':None}
            try:
                raw=(directory/'manifest.json').read_bytes()
                entry['manifest']=manifest(raw)
                if raw in manifests:
                    entries[manifests[raw]]['directory']=directory
                    continue
            except FileNotFoundError:
                entry['issue']='Generation incomplete; no completed manifest'
            except (OSError,ValueError,UnicodeError):
                entry['issue']='Manifest is unreadable'
            entries[key]=entry
    return entries


@db.timed
def run_rows(world_id=None):
    return db.rows(f'''select r.run_id,r.world_id,r.player_country,d.name as country,r.started_at,r.ended_at,r.end_reason,
        {STATE} as status,r.picker,r.progress_step,r.heartbeat_at,
        (select max(seq) from snapshot s where s.run_id=r.run_id) as snapshot,
        (select count(*) from snapshot s where s.run_id=r.run_id) as snapshots,
        (select count(*) from loop_action a where a.run_id=r.run_id) as actions
        from run r join country_definition d on d.country_definition=r.tag
        {'where r.world_id=%s' if world_id is not None else ''} order by r.run_id desc''',
        (world_id,) if world_id is not None else ())


@db.timed
def summary(entry,runs):
    m=entry['manifest']
    return {'key':entry['key'],'world_id':entry['world_id'],'seed':m.get('seed') if m else None,
            'name':f"World {entry['world_id']}" if entry['world_id'] is not None else entry['directory'].name,
            'status':'Incomplete' if entry['issue'] else 'Recorded' if runs else 'Generated' if m else 'Registered',
            'issue':entry['issue'],'countries':len(m.get('countries',[])) if m else None,
            'states':len(m.get('states',[])) if m else None,'sources':m.get('source_region_keys',[]) if m else [],
            'runs':runs,'local':entry['directory'] is not None,
            'provenance':bool(m and any(s.get('template') for s in m.get('states',[])))}


@db.timed
def inventory():
    runs=run_rows()
    return [summary(e,[r for r in runs if r['world_id']==e['world_id']]) for e in catalog().values()]


@db.timed
def script_records(text):
    return {key.removeprefix('s:'):value for key,value in blocks(body(text))} if text else {}


@db.timed
def population(text):
    rows=[]
    for key,value in blocks(text):
        if key=='create_pop':
            rows.append({k:scalar(value,k) for k in ('culture','religion','pop_type','size')})
        else:
            rows.extend(population(body(value)))
    return rows


@db.timed
def buildings(text):
    rows=[]
    for key,value in blocks(text):
        if key=='create_building':
            data=dict(fields(body(value)))
            owners=[v for k,v in blocks(body(value)) if k=='add_ownership']
            levels=sum(int(scalar(v,'levels') or 0) for owner in owners for _,v in blocks(body(owner)))
            rows.append({'type':scalar(value,'building'),'levels':levels if owners else int(scalar(value,'level') or 0),
                         'methods':[s.strip('"') for s in data.get('activate_production_methods',[])]})
        else:
            rows.extend(buildings(body(value)))
    return rows


@db.timed
def detail(key,run=None):
    entry=catalog().get(key)
    if entry is None:
        return None
    runs=run_rows(entry['world_id']) if entry['world_id'] is not None else []
    if run is not None and run not in [r['run_id'] for r in runs]:
        raise ValueError('Run does not belong to this world')
    run=run if run is not None else runs[0]['run_id'] if runs else None
    result=summary(entry,runs)
    m=entry['manifest'] or {}
    result.update(manifest=m,selected_run=run,states=[],countries=m.get('countries',[]),audit=None,directory=str(entry['directory']) if entry['directory'] else None)
    regions={}
    histories={}
    if entry['world_id'] is not None:
        for asset in db.rows("select name,data from world_asset where world_id=%s and (name like 'state_regions/%%' or name like 'history/%%' or name='audit.json')",(entry['world_id'],)):
            text=bytes(asset['data']).decode('utf-8-sig')
            if asset['name']=='audit.json':
                result['audit']=json.loads(text)
            elif asset['name'].startswith('history/'):
                histories[Path(asset['name']).stem]=script_records(text)
            else:
                regions.update(dict(blocks(text)))
    directory=entry['directory']
    result['content_issue']=None
    if directory:
        try:
            for path in (directory/'mod/map_data/state_regions').glob('*.txt'):
                if entry['world_id'] is None:
                    regions.update(dict(blocks(path.read_text(encoding='utf-8-sig'))))
            for folder in ('pops','buildings','states'):
                path=directory/f'mod/common/history/{folder}/interface.txt'
                if folder not in histories and path.exists():
                    histories[folder]=script_records(path.read_text(encoding='utf-8-sig'))
            audit=directory/'audit.json'
            if result['audit'] is None and audit.exists():
                result['audit']=json.loads(audit.read_bytes())
        except (OSError,ValueError,UnicodeError) as error:
            result['content_issue']=f'Cannot read generated contents: {error}'
    country_ids={}
    state_ids={}
    if run is not None:
        country_ids={r['name']:r['country'] for r in db.rows('''select h.country,d.name from
            (select distinct on (country) * from country_history where run_id=%s order by country,seq desc) h
            join country_definition d using (country_definition) where h.present''',(run,))}
        state_ids={}
        for r in db.rows('''select h.state,d.name from
            (select distinct on (state) * from state_history where run_id=%s order by state,seq desc) h
            join state_region d using (state_region) where h.present''',(run,)):
            state_ids.setdefault(r['name'],[]).append(r['state'])
    result['countries']=[{**c,'entity':country_ids.get(c['tag'])} for c in result['countries']]
    for state in m.get('states',[]):
        text=regions.get(state['key'])
        values=dict(fields(body(text))) if text else {}
        resources=[{'type':k,'amount':' '.join(v),'kind':'capped'} for k,v in fields(' '.join(values.get('capped_resources',[])))]
        if text:
            resources.extend({'type':scalar(v,'type'),'amount':scalar(v,'undiscovered_amount'),'kind':'undiscovered'} for k,v in blocks(body(text)) if k=='resource')
        pops=population(body(histories['pops'][state['key']])) if state['key'] in histories.get('pops',{}) else None
        built=buildings(body(histories['buildings'][state['key']])) if state['key'] in histories.get('buildings',{}) else None
        result['states'].append({**state,'entities':state_ids.get(state['key'],[]),'pops':pops,'buildings':built,
            'population':sum(int(p['size']) for p in pops) if pops is not None else None,
            'levels':sum(b['levels'] for b in built) if built is not None else None,
            'traits':[s.strip('"') for s in values.get('traits',[])], 'resources':resources,
            'arable':int(values['arable_land'][0]) if 'arable_land' in values else None,
            'arable_resources':[s.strip('"') for s in values.get('arable_resources',[])],
            'homelands':[s.strip('"') for k,v in fields(body(histories['states'][state['key']])) if k=='add_homeland' for s in v] if state['key'] in histories.get('states',{}) else [],
            'definition_available':text is not None})
    return result
