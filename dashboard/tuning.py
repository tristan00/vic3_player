from threading import Lock

from interface.runner.session import process
from tuning import ACTIVE, ROOT, weighting
from tuning.metrics import SPEC, loss
from tuning.storage import read

from . import db

LOCK=Lock()
TRIALS={}


@db.often
def state_of(status):
    if status is None:
        return None
    return 'interrupted' if status['state']=='running' and process(status) is None else status['state']


@db.often
def optional(path):
    return read(path) if path.is_file() else None


@db.often
def installed():
    return {path.stem:read(path) for path in sorted(ACTIVE.glob('*.json'))}


@db.often
def searches():
    return sorted((path for path in ROOT.iterdir() if path.is_dir() and (path/'request.json').is_file()),reverse=True) if ROOT.is_dir() else []


@db.often
def searched(search,model):
    for directory in searches():
        if directory.name==search and model in read(directory/'request.json')['models'] and (directory/model/'weighting.json').is_file():
            return directory/model
    return None


@db.timed
def listing():
    active=installed()
    rows=[]
    for directory in searches():
        request=read(directory/'request.json')
        job=optional(directory/'status.json')
        for model in request['models']:
            status=optional(directory/model/'status.json')
            weights=optional(directory/model/'weighting.json')
            winner=optional(directory/model/'winner.json')
            rows.append({'search':directory.name,'model':model,'job':state_of(job),'state':state_of(status),
                         'finished':len(list((directory/model).glob('trial_*.json'))),'requested':request['trials'],
                         'winner':winner['trial'] if winner else None,'winner_loss':winner['metrics']['score'] if winner else None,
                         'installed':str((directory/model).resolve())==active.get(model,{}).get('search'),
                         'differentiation_weight':weights['weights']['differentiation'] if weights else None,
                         'reward_weight':weights['weights']['reward'] if weights else None,
                         'points_per_run':request['points_per_run'],'threads':request['threads'],'memory_gb':request['memory_gb'],'seed':request['seed'],
                         'seconds':job.get('seconds') if job else None})
    shown=[{'model':model,'trial':found['trial'],'search':found['search'],'installed_at':found['installed_at'],'threads':found['threads'],
            **{'validation_'+key:value for key,value in found['validation'].items()},
            **{key+'_weight':value for key,value in found['weighting']['weights'].items()}} for model,found in active.items()]
    return {'rows':rows,'installed':shown,'metric':{key:value for key,value in SPEC.items() if not isinstance(value,str)}}


@db.often
def trial(path):
    stamp=path.stat().st_mtime_ns
    with LOCK:
        found=TRIALS.get(path)
        if found is None or found[0]!=stamp:
            found=TRIALS[path]=(stamp,read(path))
        return found[1]


@db.timed
def detail(search,model):
    directory=searched(search,model)
    if directory is None:
        return None
    weights=weighting.current(directory)
    rows=[]
    baseline=None
    measures=[]
    settings=[]
    for path in sorted(directory.glob('trial_*.json')):
        found=trial(path)
        metrics=found.get('metrics')
        config=found['config']
        flags=[key for key in config if key.startswith('feature.')]
        proposal=found.get('proposal') or {}
        if found.get('baseline'):
            baseline={**found['baseline'],'loss':loss(found['baseline'],weights['weights'])}
        measures+=[key for key in metrics or {} if key!='score' and key not in measures]
        settings+=[key for key in config if '.' not in key and key not in settings]
        rows.append({'trial':found['trial'],'state':found['state'],'loss':loss(metrics,weights['weights']) if metrics else None,
                     **{key:value for key,value in (metrics or {}).items() if key!='score'},
                     'seconds':found.get('seconds'),'peak_memory_gb':found.get('peak_memory_gb'),'method':proposal.get('method'),
                     'predicted_score':proposal.get('predicted_score'),'uncertainty':proposal.get('uncertainty'),
                     'features_used':sum(config[key]!='off' for key in flags),'features':len(flags),
                     **{key:value for key,value in config.items() if '.' not in key},
                     'interrupted_step':found.get('interrupted_step'),'error':found.get('error')})
    status=optional(directory/'status.json')
    winner=optional(directory/'winner.json')
    active=installed().get(model,{})
    return {'search':search,'model':model,'status':status,'state':state_of(status),'weights':weights,'baseline':baseline,
            'winner':winner['trial'] if winner else None,'installed':active.get('trial') if active.get('search')==str(directory.resolve()) else None,
            'request':read(directory.parent/'request.json'),'rows':rows,'measures':measures,'settings':settings}


@db.timed
def configuration(search,model,number):
    directory=searched(search,model)
    if directory is None or not (directory/f'trial_{number:05d}.json').is_file():
        return None
    found=trial(directory/f'trial_{number:05d}.json')
    return {'trial':number,'config':found['config'],'proposal':found.get('proposal')}


@db.timed
def reweigh(search,model,revision,weights):
    directory=searched(search,model)
    if directory is None:
        return None
    return weighting.update(directory,revision,weights)
