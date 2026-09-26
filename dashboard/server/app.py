import asyncio
import contextlib
import logging
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from interface.recording.spec import ENTITIES, TABLE

from . import actions, blocks, changes, db, entities, live, progress, runs
from .models import (BlockDetail, BlockLog, CountryProgress, TradePage, TradeSeries, ActionDetail, ActionLog, ActionStats, ActionType, EntityDetail, EntityList, EntityTable, TableChanges, LivePage, RoundsPage, RunDetail, RunsPage, SchemaPage, Series,
                     SnapshotChanges, SnapshotsPage)

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


app=FastAPI(title='vic3 dashboard',version='1',lifespan=lifespan)
app.add_middleware(GZipMiddleware,minimum_size=2048)


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


def found(value,what):
    if value is None:
        raise HTTPException(404,f'no {what}')
    return value


def entity_kind(kind):
    if kind not in ENTITIES:
        raise HTTPException(404,f'no entity kind {kind}')
    return kind


def scope_of(scope):
    try:
        actions.parse_scope(scope)
    except ValueError as error:
        raise HTTPException(400,str(error))
    return scope


@app.get('/api/live')
def get_live()->LivePage:
    return live.live_page()


@app.get('/api/runs')
def get_runs(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500),sort:str=Query('run_id',pattern='^('+'|'.join(runs.SORTS)+')$'),desc:bool=True,
             kind:str|None=None,end_reason:str|None=None,tag:str|None=None,round:int|None=None)->RunsPage:
    return runs.runs_page(offset,limit,sort,desc,kind,end_reason,tag,round)


@app.get('/api/rounds')
def get_rounds(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500))->RoundsPage:
    return runs.rounds_page(offset,limit)


@app.get('/api/runs/{run_id}')
def get_run(run_id:int)->RunDetail:
    return found(runs.run_detail(run_id),f'run {run_id}')


@app.get('/api/runs/{run_id}/series')
def get_series(run_id:int,table:str,column:str)->Series:
    if table not in TABLE:
        raise HTTPException(404,f'no table {table}')
    return found(runs.series(run_id,table,column),f'numeric column {table}.{column}')


@app.get('/api/runs/{run_id}/actions')
def get_run_actions(run_id:int,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),action:str|None=None,group:str|None=None,
                    status:str|None=None)->ActionLog:
    return actions.run_log(run_id,offset,limit,action,group,status)


@app.get('/api/runs/{run_id}/actions/{n}')
def get_run_action(run_id:int,n:int)->ActionDetail:
    return found(actions.action_detail(run_id,n),f'action {n} in run {run_id}')


@app.get('/api/runs/{run_id}/blocks')
def get_blocks(run_id:int,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500),kind:str|None=Query(None,pattern='^(decision|events|time)$'))->BlockLog:
    return blocks.run_blocks(run_id,offset,limit,kind)


@app.get('/api/runs/{run_id}/blocks/{seq}')
def get_block(run_id:int,seq:int)->BlockDetail:
    return found(blocks.block_detail(run_id,seq),f'block chosen from snapshot {seq} in run {run_id}')


@app.get('/api/runs/{run_id}/snapshots')
def get_snapshots(run_id:int,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500))->SnapshotsPage:
    return runs.snapshots_page(run_id,offset,limit)


@app.get('/api/runs/{run_id}/snapshots/{seq}')
def get_snapshot(run_id:int,seq:int)->SnapshotChanges:
    return found(changes.snapshot_changes(run_id,seq),f'snapshot {seq} in run {run_id}')


@app.get('/api/runs/{run_id}/snapshots/{seq}/tables/{table}')
def get_snapshot_table(run_id:int,seq:int,table:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500))->TableChanges:
    if table not in TABLE:
        raise HTTPException(404,f'no table {table}')
    return changes.table_changes(run_id,seq,table,offset,limit)


@app.get('/api/runs/{run_id}/entities/{kind}')
def get_entities(run_id:int,kind:str,seq:int|None=None,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),gone:bool=False)->EntityList:
    return found(entities.entity_list(run_id,entity_kind(kind),seq,offset,limit,gone),f'snapshot in run {run_id}')


@app.get('/api/runs/{run_id}/entities/{kind}/{ident}')
def get_entity(run_id:int,kind:str,ident:int)->EntityDetail:
    return found(entities.entity_detail(run_id,entity_kind(kind),ident),f'{kind} {ident} in run {run_id}')


@app.get('/api/runs/{run_id}/entities/{kind}/{ident}/tables/{table}')
def get_entity_table(run_id:int,kind:str,ident:int,table:str)->EntityTable:
    if table not in TABLE:
        raise HTTPException(404,f'no table {table}')
    return found(entities.entity_table(run_id,entity_kind(kind),ident,table,entities.snapshot_dates(run_id)),f'{table} rows owned by {kind}')


@app.get('/api/runs/{run_id}/countries')
def get_countries(run_id:int)->CountryProgress:
    return found(progress.country_progress(run_id),f'snapshots in run {run_id}')


@app.get('/api/runs/{run_id}/trade')
def get_trade(run_id:int,market:int|None=None,seq:int|None=None)->TradePage:
    return found(progress.trade_page(run_id,market,seq),f'snapshots in run {run_id}')


@app.get('/api/runs/{run_id}/trade/goods')
def get_trade_goods(run_id:int,market:int,goods:str)->TradeSeries:
    return found(progress.trade_series(run_id,market,goods),f'goods {goods}')


@app.get('/api/actions')
def get_actions(scope:str='all')->ActionStats:
    return actions.action_stats(scope_of(scope))


@app.get('/api/actions/{name}')
def get_action(name:str,scope:str='all')->ActionType:
    return found(actions.action_type(name,scope_of(scope)),f'action {name}')


@app.get('/api/schema')
def get_schema()->SchemaPage:
    return live.schema_page()


@app.get('/api/events')
async def events(request:Request):
    async def stream():
        last=None
        while not await request.is_disconnected():
            current=await run_in_threadpool(live.stamp)
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
