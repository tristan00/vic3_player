from pathlib import Path

import numpy as np
import torch

from interface.common import timed, timed_often
from .experiment import restore
from .model import collate
from .schema import COMPONENTS, GRAPH_VERSION, HORIZONS
from .source import load
from .world import WorldBuilder, WorldReader, build_world
from .world_data import Identities, action_graph


@timed_often
def baseline(data):
    from advisors.data.rewards import COSTS
    snapshot=data['states'][data['seq']]
    player=data['player']
    gdp=next(r['gdp'] for r in snapshot['country_economy_report'] if r['country']==player)
    sol=next(r['average_standard_of_living_by_population'] for r in snapshot['country_standard_of_living_report'] if r['country']==player)
    population=next(sum(r[k] for k in ('lower_strata','middle_strata','upper_strata')) for r in snapshot['player_population'])
    owned={r['state'] for r in snapshot['state_history'] if r['country']==player}
    types=data['vocabulary']['building_type']
    stock=sum(COSTS[types[r['building_type']]]*r['levels'] for r in snapshot['building_history'] if r['state'] in owned and types[r['building_type']] in COSTS)
    result=np.array([gdp,population,sol,stock],float)
    if not np.isfinite(result).all() or min(result)<=0:
        raise ValueError('Four positive finite baseline measurements are required')
    return result


class Forecaster:
    @timed
    def __init__(self,checkpoint,encoder,device='cuda'):
        self.model,self.checkpoint=restore(Path(checkpoint),device)
        self.encoder=load(Path(encoder))
        if self.checkpoint.get('graph_version')!=GRAPH_VERSION or getattr(self.encoder,'graph_version',None)!=GRAPH_VERSION:
            raise ValueError('Checkpoint or encoder is obsolete; rebuild and fit the recurrent model')
        self.mean=np.array(self.checkpoint['mean'])
        self.scale=np.array(self.checkpoint['scale'])
        self.device=device
        self.reset()

    @timed
    def reset(self):
        self.memory=None
        self.observation=None
        self.run=None
        self.seq=None
        self.pending=False
        self.committed_seq=None
        self.identities=Identities()

    @timed
    def observe(self,data):
        if self.run is not None and data['run']!=self.run:
            raise ValueError('Reset recurrent memory before changing runs')
        if self.seq is not None and data['seq']<=self.seq:
            raise ValueError('Recurrent observations must advance in snapshot order')
        if self.pending:
            raise ValueError('Commit the selected action before advancing to another observation')
        self.raw,self.audit=build_world(data)
        self.data=data
        graph=self.encoder.graph(self.raw)
        graph['identity']=self.identities.graph(self.raw)
        with torch.inference_mode():
            self.observation=self.model.observe(collate([graph],self.device),self.memory,data['dates'][data['seq']])
        self.memory=self.observation.memory
        self.run,self.seq=data['run'],data['seq']
        self.context=WorldBuilder(data)
        self.context.nodes=list(self.raw.nodes)
        self.context.lookup={(n['seq'],n['kind'],n['key']):i for i,n in enumerate(self.context.nodes)}

    @timed
    def propose(self,actions):
        delta=self.encoder.graph(action_graph(self.raw,self.data,actions,self.context))
        with torch.inference_mode():
            return self.model.propose(self.observation,delta)

    @timed
    def commit(self,actions):
        if self.observation is None:
            raise ValueError('Observe a world before committing an action')
        if getattr(self,'committed_seq',None)==(self.run,self.seq):
            raise ValueError('An action was already committed at this snapshot')
        with torch.inference_mode():
            self.memory=self.model.commit(self.observation,self.propose(actions))
        self.pending=False
        self.committed_seq=(self.run,self.seq)

    @timed
    def forecast(self,data,blocks):
        if not blocks:
            raise ValueError('At least one complete candidate block is required')
        if (self.run,self.seq)!=(data['run'],data['seq']):
            self.observe(data)
        if getattr(self,'committed_seq',None)==(self.run,self.seq):
            raise ValueError('Cannot score a past decision after committing it')
        previous=torch.backends.cuda.matmul.allow_tf32
        torch.backends.cuda.matmul.allow_tf32=False
        try:
            with torch.inference_mode():
                ratios=np.stack([self.propose(actions).prediction.cpu().numpy()[0]*self.scale+self.mean for actions in blocks])
        finally:
            torch.backends.cuda.matmul.allow_tf32=previous
        self.pending=True
        current=baseline(data)
        values=np.exp(ratios)*current
        if not np.isfinite(values).all():
            raise ValueError('Forecast exceeds finite output range')
        return {'horizons_days':HORIZONS,'components':COMPONENTS,'baseline':current,'log_ratios':ratios,'values':values,'audit':self.audit}

    @timed
    def from_snapshot(self,snapshot,blocks):
        if self.run is not None and self.run!=snapshot.run_id:
            self.reset()
        if self.seq is not None and snapshot.seq<self.seq:
            raise ValueError('Reset and replay before requesting an earlier decision')
        reader=WorldReader(snapshot.connection,snapshot.run_id)
        if snapshot.seq not in reader.dates:
            raise ValueError('The requested snapshot does not exist')
        if self.seq is not None and self.seq<snapshot.seq and self.pending:
            if self.seq not in reader.actions:
                raise ValueError('The preceding selected action must be recorded before recurrence advances')
            self.commit(reader.actions[self.seq])
        for seq in sorted(at for at in reader.dates if at<=snapshot.seq and (self.seq is None or at>self.seq)):
            data=reader.read(seq)
            self.observe(data)
            if seq<snapshot.seq and seq in reader.actions:
                self.commit(reader.actions[seq])
        return self.forecast(self.data,blocks)
