from contextlib import contextmanager
import time

import numpy as np

from interface.common import timed
from interface.timing import span
from .metrics import loss
from .space import density_scopes, identity
from .tuners import suggester


@timed
def propose(space,history,seed,model,weighting,tuner):
    started=time.monotonic()
    params=tuner['params']
    rng=np.random.default_rng(seed)
    seen={identity(trial['config']) for trial in history}
    scopes=density_scopes(model,space.groups)
    timings={}

    @contextmanager
    def step(name):
        with span(f"tuning.tuners.{tuner['name']}.{name}",'tuning') as timing:
            yield
        timings[name]=timings.get(name,0.)+timing.seconds

    def draw(count):
        with step('draw'):
            candidates=[]
            while len(candidates)<count:
                config,sampling=space.draw(rng,scopes)
                key=identity(config)
                if key not in seen:
                    candidates.append({'index':len(candidates),'config':config,'sampling':sampling})
                    seen.add(key)
            return candidates

    observations=[{'trial':trial['trial'],'state':trial['state'],
                   'score':loss(trial['metrics'],weighting['weights']) if trial['state']=='completed' else params['failure_score']} for trial in history]
    proposal={'tuner':tuner['name'],'method':'random','seed':seed,'observations':len(history),**params,'weighting':weighting,'timings':timings}
    if len(history)<params['random_trials']:
        trace={'candidates':draw(1)}
        config=trace['candidates'][0]['config']
    else:
        with step('load'):
            suggest=suggester(tuner['name'])
        config,found,trace=suggest(space,[trial['config'] for trial in history],np.asarray([observation['score'] for observation in observations]),seed,params,draw,step)
        if all(config['feature.'+name]=='off' for name,group in space.groups.items() if group['role']=='option'):
            config[space.anchor]=space.parameters[space.anchor]['values'][1]
        proposal.update(method=tuner['name'],**found)
    proposal['seconds']=time.monotonic()-started
    return space.canonical(config),proposal,{**proposal,'observations':observations,**trace}
