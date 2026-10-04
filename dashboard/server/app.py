import contextlib
from dataclasses import dataclass
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from interface.recording.spec import ENTITIES, TABLE
from interface.timing import COLUMNS, RECORDER, TRACE, span

from . import actions, blocks, changes, db, graph_tuning, meta, policy, runs, schema, tables, tuning, worlds
from .grid import VALUES, Spec, grid, parse_filters, rows_source
from .models import ActionInfo, EntityInfo, Grid, InitializerInfo, OpenRun, RunInfo, RunReward, Series, SeriesChoice

LOG=logging.getLogger('dashboard')
DIST=Path(__file__).resolve().parents[1]/'ui'/'dist'


@contextlib.asynccontextmanager
async def lifespan(_app):
    db.open_pool()
    try:
        yield
    finally:
        db.close_pool()


app=FastAPI(title='vic3 dashboard',version='2',lifespan=lifespan)
app.add_middleware(GZipMiddleware,minimum_size=2048)


@app.get('/api/worlds')
def world_inventory():
    return worlds.inventory()


@app.get('/api/tuning/world')
def graph_tuning_results()->graph_tuning.GraphTracking:
    return graph_tuning.results()


@app.get('/api/tuning/{model}')
def tuning_results(model:tuning.Literal['histogram','row'])->tuning.Results:
    return tuning.results(model)


@app.get('/tuning/world/{asset:path}',include_in_schema=False)
def world_graph_asset(asset:str):
    return FileResponse(tuning.graph_asset(asset),headers={'Cache-Control':'no-cache'})


@app.get('/api/worlds/{key}')
def world_detail(key:str,run:int|None=None):
    return found(worlds.detail(key,run),'world')


@app.get('/api/runs/{run_id}/world')
def run_world(run_id:int):
    return {'key':str(found(db.value('select world_id from run where run_id=%s',(run_id,)),'run'))}


@app.exception_handler(ValueError)
async def bad_request(_request,error):
    return JSONResponse(status_code=400,content={'detail':str(error)})


@app.middleware('http')
async def timing(request:Request,call_next):
    if not request.url.path.startswith('/api/'):
        return await call_next(request)
    trace=[]
    with span(request.method,'dashboard',logging.DEBUG) as whole:
        token=TRACE.set(trace)
        values=VALUES.set(request.query_params.get('values'))
        try:
            response=await call_next(request)
        finally:
            VALUES.reset(values)
            TRACE.reset(token)
            whole.name=f'{request.method} {request.scope["route"].path}'
    ms=whole.ms
    slowest=sorted(trace,key=lambda item:-item[1])[:6]
    LOG.warning('API %s %s %d %.0fms %s',request.method,request.url.path+('?'+request.url.query if request.url.query else ''),response.status_code,ms,
                ' '.join(f'{name}={took:.0f}ms' for name,took in slowest))
    response.headers['Server-Timing']=', '.join([f'total;dur={ms:.0f}']+[f'{name};dur={took:.0f}' for name,took in slowest])
    return response


@dataclass
class Page:
    filters:list
    sort:str|None
    desc:bool
    offset:int
    limit:int

    @db.timed
    def args(self):
        return self.filters,self.sort,self.desc,self.offset,self.limit


@db.timed
def page(f:list[str]=Query([]),sort:str|None=None,desc:bool=False,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000))->Page:
    return Page(parse_filters(f),sort,desc,offset,limit)


@db.timed
def found(value,what):
    if value is None:
        raise HTTPException(404,f'no {what}')
    return value


@db.timed
def entity_kind(kind):
    if kind not in ENTITIES:
        raise HTTPException(404,f'no entity kind {kind}')
    return kind


@db.timed
def table_name(table):
    if table not in TABLE:
        raise HTTPException(404,f'no table {table}')
    return table


@db.timed
def at(grid,run_id,seq):
    grid.seq,grid.last_seq,grid.game_date=tables.snapshot_at(run_id,seq)
    return grid


@db.timed
def resolved(run_id,seq):
    chosen,_,_=tables.snapshot_at(run_id,seq)
    return found(chosen,f'snapshot in run {run_id}')


@app.get('/api/open')
def get_open()->list[OpenRun]:
    return runs.open_runs()


@app.get('/api/runs')
def get_runs(p:Page=Depends(page))->Grid:
    return runs.runs_grid(*p.args())


@app.get('/api/rounds')
def get_rounds(p:Page=Depends(page))->Grid:
    return runs.rounds_grid(*p.args())


@app.get('/api/runs/{run_id}')
def get_run(run_id:int)->RunInfo:
    return found(runs.run_info(run_id),f'run {run_id}')


@app.get('/api/runs/{run_id}/record')
def get_run_record(run_id:int)->Grid:
    return meta.run_record(run_id)


@app.get('/api/runs/{run_id}/outcomes')
def get_outcomes(run_id:int)->list[Series]:
    return runs.run_outcomes(run_id)


@app.get('/api/policy/runs/{run_id}')
def get_policy_record(run_id:int)->Grid:
    return meta.policy_record(run_id)


@app.get('/api/policy/runs/{run_id}/pauses')
def get_pauses(run_id:int,p:Page=Depends(page))->Grid:
    return policy.pauses(run_id,*p.args())


@app.get('/api/policy/runs/{run_id}/pauses/{seq}/candidates')
def get_candidates(run_id:int,seq:int,p:Page=Depends(page))->Grid:
    return policy.candidates(run_id,seq,*p.args())


@app.get('/api/policy/runs/{run_id}/reward')
def get_reward(run_id:int,seq:int|None=Query(None,ge=0))->RunReward:
    return found(runs.run_reward(run_id,seq),f'run or snapshot in run {run_id}')


@app.get('/api/runs/{run_id}/groups')
def get_groups(run_id:int,p:Page=Depends(page))->Grid:
    return runs.run_groups(run_id,*p.args())


@app.get('/api/runs/{run_id}/actions')
def get_actions_of_run(run_id:int,p:Page=Depends(page))->Grid:
    return actions.run_actions(run_id,*p.args())


@app.get('/api/runs/{run_id}/blocks')
def get_blocks(run_id:int,p:Page=Depends(page))->Grid:
    return blocks.run_blocks(run_id,*p.args())


@app.get('/api/runs/{run_id}/tables')
def get_run_tables(run_id:int,p:Page=Depends(page))->Grid:
    return tables.run_tables(run_id,*p.args())


@app.get('/api/runs/{run_id}/kinds')
def get_kinds(run_id:int,p:Page=Depends(page))->Grid:
    return tables.run_kinds(run_id,*p.args())


@app.get('/api/runs/{run_id}/tables/{table}')
def get_table(run_id:int,table:str,seq:int|None=None,versions:bool=False,p:Page=Depends(page))->Grid:
    chosen=resolved(run_id,seq)
    return at(tables.table_grid(run_id,table_name(table),chosen,versions,*p.args()),run_id,chosen)


@app.get('/api/runs/{run_id}/entities/{kind}')
def get_entities(run_id:int,kind:str,seq:int|None=None,gone:bool=False,p:Page=Depends(page))->Grid:
    chosen=resolved(run_id,seq)
    return at(tables.entity_grid(run_id,entity_kind(kind),chosen,gone,*p.args()),run_id,chosen)


@app.get('/api/runs/{run_id}/entities/{kind}/{ident}')
def get_entity(run_id:int,kind:str,ident:int)->EntityInfo:
    return found(tables.entity_info(run_id,entity_kind(kind),ident),f'{kind} {ident} in run {run_id}')


@app.get('/api/runs/{run_id}/entities/{kind}/{ident}/actions')
def get_entity_actions(run_id:int,kind:str,ident:int,p:Page=Depends(page))->Grid:
    return tables.entity_actions(run_id,entity_kind(kind),ident,*p.args())


@app.get('/api/runs/{run_id}/snapshots/{seq}/tables')
def get_changed_tables(run_id:int,seq:int,p:Page=Depends(page))->Grid:
    return changes.changed_tables(run_id,seq,*p.args())


@app.get('/api/runs/{run_id}/snapshots/{seq}/tables/{table}')
def get_table_changes(run_id:int,seq:int,table:str,p:Page=Depends(page))->Grid:
    return changes.table_changes(run_id,seq,table_name(table),*p.args())


@app.get('/api/runs/{run_id}/series')
def get_series(run_id:int,table:str,column:str,f:list[str]=Query([]),player:bool=False)->Series:
    return found(runs.series(run_id,table_name(table),column,parse_filters(f),player),f'numeric column {table}.{column}')


@app.get('/api/series')
def get_series_choices()->list[SeriesChoice]:
    return runs.series_choices()


@app.get('/api/meta/{table}')
def get_meta(table:str,run:int|None=None,p:Page=Depends(page))->Grid:
    if table not in meta.TABLES:
        raise HTTPException(404,f'no table {table}')
    return meta.meta_grid(table,*p.args(),run)


@app.get('/api/actions')
def get_action_stats(scope:str='all',p:Page=Depends(page))->Grid:
    return actions.action_stats(scope,*p.args())


@app.get('/api/actions/{name}')
def get_action(name:str)->ActionInfo:
    if name not in runs.GROUPS:
        raise HTTPException(404,f'no action {name}')
    return ActionInfo(action=name,group=runs.GROUPS[name],params=actions.param_specs(name))


@app.get('/api/actions/{name}/runs')
def get_action_runs(name:str,scope:str='all',p:Page=Depends(page))->Grid:
    return actions.action_runs(name,scope,*p.args())


@app.get('/api/actions/{name}/details')
def get_action_details(name:str,scope:str='all',p:Page=Depends(page))->Grid:
    return actions.action_details(name,scope,*p.args())


@app.get('/api/actions/{name}/picks')
def get_action_picks(name:str,scope:str='all',p:Page=Depends(page))->Grid:
    return actions.action_picks(name,scope,*p.args())


@app.get('/api/policy/configs')
def get_configs(p:Page=Depends(page))->Grid:
    return policy.configs(*p.args())


@app.get('/api/policy/runs')
def get_run_policies(p:Page=Depends(page))->Grid:
    return policy.run_policies(*p.args())


@app.get('/api/policy/initializers')
def get_initializers()->list[InitializerInfo]:
    return policy.initializers()


@app.get('/api/policy/weights')
def get_weights(p:Page=Depends(page))->Grid:
    return policy.weights(*p.args())


@app.get('/api/policy/catalogue')
def get_catalogue(p:Page=Depends(page))->Grid:
    return policy.catalogue(*p.args())


@app.get('/api/policy/picker-actions')
def get_picker_actions(p:Page=Depends(page))->Grid:
    return policy.picker_actions(*p.args())


@app.get('/api/schema')
def get_schema(p:Page=Depends(page))->Grid:
    return schema.schema_grid(*p.args())


@app.get('/api/timing')
def get_timing(p:Page=Depends(page))->Grid:
    source,params=rows_source(['text','int8','int8']+['float8']*7,RECORDER.totals())
    specs=[Spec(name,'text' if name=='span' else 'number',f't.v{i}') for i,name in enumerate(COLUMNS)]
    return grid(specs,source,params,*p.args(),None,['span'])


@app.get('/api/stamp')
def get_stamp()->str:
    return JSONResponse(schema.stamp(),headers={'Cache-Control':'no-store'})


@app.api_route('/api/{path:path}',methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'],include_in_schema=False)
@db.timed
def no_route(path:str):
    raise HTTPException(404,f'no route /api/{path}')


if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')

    @app.get('/{path:path}',include_in_schema=False)
    def spa(path:str):
        asset=DIST/path
        return FileResponse(asset if path and asset.is_file() and asset.resolve().is_relative_to(DIST) else DIST/'index.html')
