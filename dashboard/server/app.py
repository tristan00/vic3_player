import asyncio
import contextlib
from dataclasses import dataclass
import logging
from pathlib import Path
import time

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loop.run import WEIGHTS

from interface.recording.spec import ENTITIES, TABLE

from . import actions, blocks, changes, db, meta, policy, runs, schema, tables
from .grid import parse_filters
from .models import ActionInfo, EntityInfo, Grid, OpenRun, RunInfo, Series, SeriesChoice

LOG=logging.getLogger('dashboard')
DIST=Path(__file__).resolve().parents[1]/'ui'/'dist'
STAMP_EVERY=1.0


@contextlib.asynccontextmanager
async def lifespan(_app):
    db.open_pool()
    try:
        yield
    finally:
        db.close_pool()


app=FastAPI(title='vic3 dashboard',version='2',lifespan=lifespan)
app.add_middleware(GZipMiddleware,minimum_size=2048)


@app.exception_handler(ValueError)
async def bad_request(_request,error):
    return JSONResponse(status_code=400,content={'detail':str(error)})


@app.middleware('http')
async def timing(request:Request,call_next):
    if not request.url.path.startswith('/api/') or request.url.path=='/api/events':
        return await call_next(request)
    trace=[]
    token=db.TRACE.set(trace)
    started=time.perf_counter()
    try:
        response=await call_next(request)
    finally:
        db.TRACE.reset(token)
    ms=(time.perf_counter()-started)*1000
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

    def args(self):
        return self.filters,self.sort,self.desc,self.offset,self.limit


def page(f:list[str]=Query([]),sort:str|None=None,desc:bool=False,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000))->Page:
    return Page(parse_filters(f),sort,desc,offset,limit)


def found(value,what):
    if value is None:
        raise HTTPException(404,f'no {what}')
    return value


def entity_kind(kind):
    if kind not in ENTITIES:
        raise HTTPException(404,f'no entity kind {kind}')
    return kind


def table_name(table):
    if table not in TABLE:
        raise HTTPException(404,f'no table {table}')
    return table


def at(grid,run_id,seq):
    grid.seq,grid.last_seq,grid.game_date=tables.snapshot_at(run_id,seq)
    return grid


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
    return ActionInfo(action=name,group=runs.GROUPS[name],weight=WEIGHTS.get(name,1),params=actions.param_specs(name))


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


@app.get('/api/policy/scored')
def get_scored(p:Page=Depends(page))->Grid:
    return policy.scored(*p.args())


@app.get('/api/policy/picker-actions')
def get_picker_actions(p:Page=Depends(page))->Grid:
    return policy.picker_actions(*p.args())


@app.get('/api/schema')
def get_schema(p:Page=Depends(page))->Grid:
    return schema.schema_grid(*p.args())


@app.get('/api/events')
async def events(request:Request):
    async def stream():
        last=None
        while not await request.is_disconnected():
            current=await run_in_threadpool(schema.stamp)
            if current!=last:
                last=current
                yield f'event: stamp\ndata: {current}\n\n'
            await asyncio.sleep(STAMP_EVERY)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'cache-control':'no-cache'})


if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')

    @app.get('/{path:path}',include_in_schema=False)
    def spa(path:str):
        if path.startswith('api/'):
            raise HTTPException(404,f'no route /{path}')
        asset=DIST/path
        return FileResponse(asset if path and asset.is_file() and asset.resolve().is_relative_to(DIST) else DIST/'index.html')
