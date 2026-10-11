from contextlib import asynccontextmanager
import logging
from pathlib import Path as Folder
from threading import Event, Thread
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from psycopg.errors import DataError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as Refused
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import FileResponse, Response

from interface.common import evidence
from . import actions, buildings, db, names, runs, tables, tuning, worlds

LOG=logging.getLogger('dashboard')
DIST=Folder(__file__).resolve().parent/'ui'/'dist'
INDEX=DIST/'index.html'
STARTED=time.time()
PERIOD=2
LARGEST=2**31-1
COMPRESSED=1000
ID=Annotated[int,Path(ge=1,le=LARGEST)]
IDENT=Annotated[int,Path(ge=-LARGEST-1,le=LARGEST)]
SEQ=Annotated[int,Path(ge=0,le=LARGEST)]
ASOF=Annotated[int|None,Query(ge=0,le=LARGEST)]
OFFSET=Annotated[int,Query(ge=0,le=LARGEST)]
LIMIT=Annotated[int,Query(ge=1,le=tables.LIMIT)]


class Weights(BaseModel):
    revision:int
    differentiation:float
    reward:float


class Logged:
    def __init__(self,inner):
        self.inner=inner

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope['path'].startswith('/api/'):
            await self.inner(scope,receive,send)
            return
        started=time.perf_counter()
        asked=scope['method']+' '+scope['raw_path'].decode('ascii','backslashreplace')+('?'+scope['query_string'].decode('ascii','backslashreplace') if scope['query_string'] else '')
        sent=[]

        async def watched(message):
            if message['type']=='http.response.start':
                sent.append(message['status'])
            await send(message)

        try:
            await self.inner(scope,receive,watched)
        except Exception as error:
            LOG.exception('%s 500 %.1fms %s',asked,(time.perf_counter()-started)*1000,type(error).__name__)
            if sent:
                raise
            await db.reply({'detail':f'{type(error).__name__}: {error}'},500)(scope,receive,send)
            return
        LOG.info('%s %s %.1fms',asked,sent[0] if sent else 'unanswered',(time.perf_counter()-started)*1000)


def watch(stop):
    while not stop.wait(PERIOD):
        try:
            runs.refresh()
        except Exception:
            LOG.exception(evidence())


@asynccontextmanager
async def lifespan(_):
    db.open_pool()
    names.catalog()
    runs.refresh()
    stop=Event()
    Thread(target=watch,args=(stop,),name='collection',daemon=True).start()
    yield
    stop.set()
    db.close_pool()


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(GZipMiddleware,minimum_size=COMPRESSED,compresslevel=5)
app.add_middleware(Logged)


@app.exception_handler(Refused)
@db.often
def refused(request,error):
    return db.reply({'detail':str(error.detail)},error.status_code,error.headers)


@app.exception_handler(RequestValidationError)
@db.often
def invalid(request,error):
    return db.reply({'detail':'; '.join(f"{'.'.join(str(part) for part in problem['loc'][1:]) or problem['loc'][0]}: {problem['msg']}" for problem in error.errors())},422)


@app.exception_handler(tuning.weighting.Conflict)
@db.often
def conflicting(request,error):
    return db.reply({'detail':str(error)},409)


@app.exception_handler(ValueError)
@app.exception_handler(DataError)
@db.often
def rejected(request,error):
    return db.reply({'detail':str(error)},400)


@db.often
def found(value,what):
    if value is None:
        raise HTTPException(404,evidence(what=what))
    return db.reply(value)


@db.often
def filters(request):
    return [(name[2:],value) for name,value in request.query_params.multi_items() if name.startswith('f.')]


@db.often
def known(run:ID):
    if not runs.exists(run):
        raise HTTPException(404,evidence(run=run))
    return run


RUN=Annotated[int,Depends(known)]


@app.get('/api/collection')
@db.often
def collection():
    return db.reply({**runs.collection(),'server_started':STARTED})


@app.get('/api/runs')
@db.often
def run_listing():
    return db.reply(runs.listing())


@app.get('/api/runs/{run}')
@db.often
def run_detail(run:RUN):
    return found(runs.detail(run),f'run {run}')


@app.get('/api/runs/{run}/series')
@db.often
def run_series(run:RUN):
    return db.reply(runs.series(run))


@app.get('/api/runs/{run}/buildings')
@db.often
def run_buildings(run:RUN):
    return db.reply(buildings.series(run))


@app.get('/api/runs/{run}/actions')
@db.often
def run_actions(run:RUN):
    return db.reply(runs.actions(run))


@app.get('/api/runs/{run}/selection')
@db.often
def run_selection(run:RUN):
    return db.reply(runs.selection(run))


@app.get('/api/runs/{run}/timing')
@db.often
def run_timing(run:RUN):
    return db.reply(runs.timing(run))


@app.get('/api/runs/{run}/candidates/{seq}')
@db.often
def run_candidates(run:RUN,seq:SEQ):
    return db.reply(runs.candidates(run,seq))


@app.get('/api/runs/{run}/tables/{table}')
@db.often
def run_table(request:Request,run:RUN,table:str,seq:ASOF=None,at:bool=True,sort:str|None=None,desc:bool=False,offset:OFFSET=0,limit:LIMIT=100):
    if seq is None:
        seq=db.one('select max(seq) from snapshot where run_id=%s',(run,))[0]
    return found(tables.page(table,run,seq,at,filters(request),sort,desc,offset,limit),f'table {table}')


@app.get('/api/runs/{run}/series/{table}')
@db.often
def run_table_series(request:Request,run:RUN,table:str):
    return found(tables.series(run,table,filters(request)),f'table {table}')


@app.get('/api/runs/{run}/entities/{kind}/{ident}')
@db.often
def run_entity(run:RUN,kind:str,ident:IDENT,seq:ASOF=None):
    return found(tables.entity(run,kind,ident,seq),f'{kind} {ident} in run {run}')


@app.get('/api/runs/{run}/entities/{kind}/{ident}/references')
@db.often
def run_entity_references(run:RUN,kind:str,ident:IDENT):
    return found(tables.references(run,kind,ident),f'entity kind {kind}')


@app.get('/api/acts')
@db.often
def act_listing():
    return db.reply(actions.summary())


@app.get('/api/acts/{name}')
@db.often
def act_detail(name:str):
    return found(actions.detail(name),f'act {name}')


@app.get('/api/commands')
@db.often
def command_listing():
    return db.reply(actions.commands())


@app.get('/api/levers')
@db.often
def lever_listing():
    return db.reply(actions.levers())


@app.get('/api/worlds')
@db.often
def world_listing():
    return db.reply(worlds.listing())


@app.get('/api/worlds/{world}')
@db.often
def world_detail(world:ID):
    return found(worlds.detail(world),f'world {world}')


@app.get('/api/worlds/{world}/image/{name:path}')
@db.often
def world_image(world:ID,name:str):
    image=worlds.image(world,name)
    if image is None:
        raise HTTPException(404,evidence(name=name,world=world))
    return Response(image,media_type='image/png')


@app.get('/api/bank')
@db.often
def bank():
    settings=runs.collection().get('settings')
    return db.reply({'banks':[{'directory':directory,**worlds.bank(directory)} for directory in settings['world_cache']] if settings else []})


@app.get('/api/tuning')
@db.often
def tuning_listing():
    return db.reply(tuning.listing())


@app.get('/api/tuning/{search}/{model}')
@db.often
def tuning_detail(search:str,model:str):
    return found(tuning.detail(search,model),f'{model} search {search}')


@app.get('/api/tuning/{search}/{model}/trials/{trial}')
@db.often
def tuning_trial(search:str,model:str,trial:SEQ):
    return found(tuning.configuration(search,model,trial),f'trial {trial} in {model} search {search}')


@app.post('/api/tuning/{search}/{model}/weights')
@db.often
def tuning_weights(search:str,model:str,weights:Weights):
    return found(tuning.reweigh(search,model,weights.revision,{'differentiation':weights.differentiation,'reward':weights.reward}),f'{model} search {search}')


@app.get('/api/tables')
@db.often
def table_listing():
    return db.reply(tables.listing())


@app.get('/api/tables/{table}')
@db.often
def table_page(request:Request,table:str,sort:str|None=None,desc:bool=False,offset:OFFSET=0,limit:LIMIT=100):
    return found(tables.page(table,None,None,False,filters(request),sort,desc,offset,limit),f'table {table}')


@app.api_route('/api/{rest:path}',methods=['GET','POST','PUT','PATCH','DELETE'])
@db.often
def unknown(rest:str):
    raise HTTPException(404,evidence(rest=rest))


app.mount('/assets',StaticFiles(directory=DIST/'assets',check_dir=False))


@app.get('/{rest:path}')
@db.often
def page(rest:str):
    if not INDEX.is_file():
        raise HTTPException(404,evidence(index=INDEX))
    return FileResponse(INDEX,headers={'Cache-Control':'no-store'})
