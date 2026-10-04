from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel

from interface.common import timed, timed_often

ROOT=Path(__file__).resolve().parents[2]/'artifacts'
SOURCES={'histogram':('histogram_entropy_*/search','Whole-block CatBoost',4),
         'row':('row_tuning_entropy_*','Piecewise CatBoost',3)}


@timed
def graph_asset(asset):
    if not re.fullmatch(r'(report\.html|review\.json|accessibility\.json|audit_\d+_\d+\.json|map_\d+_\d+\.png|full_world/audit\.json|graphs/full_world\.(html|json\.gz))',asset):
        raise HTTPException(404,'No graph review asset')
    choices=list(ROOT.glob('entity_graph_spatial_*/review.json'))
    if not choices:
        raise HTTPException(404,'No full-world graph review yet')
    root=max(choices,key=lambda path:path.stat().st_mtime_ns).parent.resolve()
    path=(root/asset).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404,'No graph review asset')
    return path


class Trial(BaseModel):
    trial:int
    state:str
    score:float|None=None
    reward_loss:float|None=None
    rmse:float|None=None
    entropy:float|None=None
    entropy_loss:float|None=None
    seconds:float
    params:dict[str,int|float|str]
    histograms:int|None=None
    bins:int|None=None


class Results(BaseModel):
    model:str
    title:str
    search:str
    phase:str
    state:str
    finished:int
    requested:int
    completed:int
    timeouts:int
    best:int|None
    installed:int|None
    baseline:float
    seconds_limit:float
    reward_weight:float
    entropy_weight:float
    ranges:dict[str,list[int|float|str]|int]
    updated_at:str
    trials:list[Trial]
    best_sizes:dict[str,int]|None=None


@timed_often
def read(path):
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise HTTPException(503,'Results are being updated; refreshing shortly') from error


@lru_cache(maxsize=4096)
@timed_often
def trial_file(path,modified):
    return read(path)


@timed
def results(model:Literal['histogram','row']):
    pattern,title,digits=SOURCES[model]
    choices=[path for path in ROOT.glob(pattern) if (path/'search.json').is_file() and (path/'status.json').is_file()]
    if not choices:
        raise HTTPException(404,'No tuning results yet')
    source=max(choices,key=lambda path:(path/'search.json').stat().st_mtime_ns)
    config=read(source/'search.json')
    status=read(source/'status.json')
    job=source.parent/'job.json' if model=='histogram' else source/'job.json'
    stage=read(job) if job.exists() else {'phase':'tune','state':'unknown'}
    trials=[]
    best_sizes=None
    for number in range(status['finished']):
        path=source/f'trial_{number:0{digits}d}.json'
        row=trial_file(path,path.stat().st_mtime_ns)
        trials.append(Trial(trial=number,state=row['stop'] or 'completed',score=row.get('score'),reward_loss=row.get('reward_loss'),
                            rmse=row.get('rmse'),entropy=row.get('mean_pause_entropy'),entropy_loss=row.get('entropy_loss'),
                            seconds=row['wall_seconds'],params=row['params'],histograms=row.get('histograms'),bins=row.get('bins')))
        if status['best'] and number==status['best']['trial']:
            best_sizes=row.get('sizes')
    installed=None
    if (source/'deployment.json').exists():
        deployment=read(source/'deployment.json')
        installed=deployment['winner']['trial'] if model=='histogram' else deployment['winner_trial']
    return Results(model=model,title=title,search=source.relative_to(ROOT).as_posix(),phase=stage['phase'],state=stage['state'],
                   finished=status['finished'],requested=status['requested'],completed=status['completed_fits'],
                   timeouts=sum(row.state=='time_limit' for row in trials),best=status['best']['trial'] if status['best'] else None,
                   installed=installed,baseline=config['validation']['constant']['score'],seconds_limit=config['seconds_per_trial'],
                   reward_weight=config['validation']['reward_weight'],entropy_weight=config['validation']['entropy_weight'],
                   ranges=config.get('ranges',{}),
                   updated_at=datetime.now(timezone.utc).isoformat(),trials=trials,best_sizes=best_sizes)
