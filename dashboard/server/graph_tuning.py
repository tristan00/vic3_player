from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time

import psutil
from pydantic import BaseModel

from advisors.models.entity_graph.schema import GRAPH_VERSION
from interface.common import timed, timed_often
from .tuning import ROOT, read


class GraphEpoch(BaseModel):
    epoch:int
    training_mse:float
    validation_sequence_nrmse:float
    seconds:float


class GraphScores(BaseModel):
    score:float|None=None
    sequence_nrmse:float|None=None
    reward_loss:float|None=None
    mean_pause_entropy:float|None=None
    normalized_candidate_std:float|None=None


class GraphTrial(BaseModel):
    name:str
    state:str
    phase:str
    epoch:int
    epoch_limit:int
    done:int=0
    total:int=0
    best_epoch:int|None=None
    params:dict[str,int|float|str]
    epochs:list[GraphEpoch]
    validation:GraphScores|None=None
    test:GraphScores|None=None
    seconds:float|None=None
    gpu_peak_bytes:int|None=None
    error:str|None=None


class GraphRun(BaseModel):
    id:str
    label:str
    graph_version:int
    state:str
    phase:str
    requested:int
    completed:int
    failed:int
    selected:str|None=None
    evaluating:str|None=None
    updated_at:str
    error:str|None=None
    trials:list[GraphTrial]


class GraphTracking(BaseModel):
    current_graph_version:int
    updated_at:str
    runs:list[GraphRun]


@timed_often
def state_of(status):
    state=status['state']
    if state=='running':
        try:
            process=psutil.Process(status['pid'])
            if abs(process.create_time()-status['process_created'])>.01 or not process.is_running():
                return 'interrupted'
        except (psutil.NoSuchProcess,psutil.AccessDenied,KeyError):
            return 'interrupted'
    return state


@timed
def run_results(output):
    path=output/'tracking.json'
    tracking=read(path) if path.exists() else None
    result_files={p.parent.name:p for p in output.glob('*/result.json')}
    results={name:read(path) for name,path in result_files.items()}
    if tracking is None and not results:
        return None
    version=tracking['graph_version'] if tracking else next(iter(results.values())).get('graph_version',1)
    names=tracking['attempts'] if tracking else list(results)
    run_state=state_of(tracking) if tracking else ('complete' if all('test' in r for r in results.values()) else 'interrupted')
    phase=tracking['phase'] if tracking else run_state
    selection=read(output/'selection.json') if (output/'selection.json').exists() else {}
    selected=tracking.get('selected') if tracking else selection.get('selected')
    trials=[]
    modified=path.stat().st_mtime if tracking else max(path.stat().st_mtime for path in result_files.values())
    for name in names:
        folder=output/name
        result=results.get(name)
        if result and result.get('graph_version',1)!=version:
            result=None
        status=read(folder/'status.json') if (folder/'status.json').exists() else None
        progress=read(folder/'progress.json') if (folder/'progress.json').exists() else []
        params=dict((result or status or {}).get('configuration',(tracking or {}).get('configurations',{}).get(name,(tracking or {}).get('configuration',{}))))
        if result and 'effective_batch_size' in result:
            params['effective_batch_size']=result['effective_batch_size']
        epochs=result['epochs'] if result else progress
        trial_state=state_of(status) if status else 'complete' if result else 'pending'
        if run_state in ('failed','interrupted') and trial_state=='running':
            trial_state=run_state
        trial_phase=status['phase'] if status else trial_state
        if run_state=='running' and tracking.get('evaluating')==name and phase=='test' and not (result or {}).get('test'):
            trial_state,trial_phase='running','test'
        trials.append(GraphTrial(name=name,state=trial_state,phase=trial_phase,
                      epoch=status['epoch'] if status else len(epochs),epoch_limit=params.get('epochs',0),
                      done=status.get('done',0) if status else 0,total=status.get('total',0) if status else 0,
                      best_epoch=result.get('best_epoch') if result else status.get('best_epoch') if status else None,
                      params=params,epochs=epochs,validation=(result or {}).get('validation'),test=(result or {}).get('test'),
                      seconds=result.get('seconds') if result else (time.time() if trial_state=='running' else status['updated_at'])-status['started_at'] if status else None,
                      gpu_peak_bytes=(result or status or {}).get('gpu_peak_bytes'),error=(status or {}).get('error')))
        if status:
            modified=max(modified,status['updated_at'])
    if selected is None:
        scored=[trial for trial in trials if trial.validation and trial.validation.score is not None]
        if scored:
            selected=min(scored,key=lambda trial:trial.validation.score).name
    return GraphRun(id=hashlib.sha256(str(output.resolve()).encode()).hexdigest()[:20],
                    label=output.parent.name+' / '+output.name,graph_version=version,state=run_state,phase=phase,
                    requested=len(names),completed=sum(trial.validation is not None for trial in trials),
                    failed=sum(trial.state in ('failed','interrupted') for trial in trials),selected=selected,
                    evaluating=(tracking or {}).get('evaluating'),updated_at=datetime.fromtimestamp(modified,timezone.utc).isoformat(),
                    error=(tracking or {}).get('error'),trials=trials)


@timed
def results():
    outputs={path.resolve() for path in ROOT.glob('entity_graph_*/world_experiments')}
    outputs.update(Path(read(path)['output']).resolve() for path in (ROOT/'entity_graph_tracking').glob('*.json'))
    runs=[run for output in outputs if (run:=run_results(output)) is not None]
    runs.sort(key=lambda run:run.updated_at,reverse=True)
    return GraphTracking(current_graph_version=GRAPH_VERSION,updated_at=datetime.now(timezone.utc).isoformat(),runs=runs)
