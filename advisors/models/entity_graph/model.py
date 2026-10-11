from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from interface.common import evidence, timed, timed_often


@dataclass(frozen=True)
class Configuration:
    width: int=48
    layers: int=3
    operator: str='relational_mean'
    dropout: float=.1
    learning_rate: float=.0015
    weight_decay: float=.0001
    epochs: int=24
    patience: int=6
    seed: int=41
    sequence_length: int=4
    action_layers: int=2

    @timed_often
    def mapping(self):
        return asdict(self)


class Layer(nn.Module):
    @timed_often
    def __init__(self,width,relations,operator,dropout):
        super().__init__()
        self.operator=operator
        self.message=nn.Linear(width,width,bias=False)
        self.relation=nn.Embedding(relations,width)
        self.edge=nn.Linear(1,width,bias=False)
        self.update=nn.Linear(width*2,width)
        self.norm=nn.LayerNorm(width)
        self.dropout=nn.Dropout(dropout)
        if operator=='relational_attention':
            self.query=nn.Linear(width,width,bias=False)

    @timed_often
    def forward(self,h,batch):
        source,target=batch['edge_index']
        aggregate=torch.zeros_like(h)
        if source.numel():
            message=self.message(h)[source]
            if self.operator!='untyped_mean':
                message=message*torch.sigmoid(self.relation(batch['relation']))
            message=F.silu(message+self.edge(batch['weight'][:,None]))
            if self.operator=='relational_attention':
                score=(self.query(h)[target]*message).sum(1)/(h.shape[1]**.5)
                maximum=torch.full((len(h),),-torch.inf,device=h.device)
                maximum.scatter_reduce_(0,target,score,reduce='amax',include_self=True)
                weight=(score-maximum[target]).exp()
                denominator=torch.zeros(len(h),device=h.device).index_add_(0,target,weight)
                message=message*(weight/denominator[target].clamp_min(1e-8))[:,None]
                aggregate.index_add_(0,target,message)
            else:
                aggregate.index_add_(0,target,message)
                degree=torch.bincount(target,minlength=len(h)).to(h.dtype).clamp_min(1)
                aggregate=aggregate/degree[:,None]
        return self.norm(h+self.dropout(F.silu(self.update(torch.cat((h,aggregate),1)))))


@dataclass(frozen=True)
class Memory:
    nodes: torch.Tensor
    global_state: torch.Tensor
    hour: float

    @timed_often
    def detach(self):
        return Memory(self.nodes.detach(),self.global_state.detach(),self.hour)


@dataclass(frozen=True)
class Observation:
    memory: Memory
    nodes: torch.Tensor
    identities: torch.Tensor
    player: torch.Tensor
    world: torch.Tensor


@dataclass(frozen=True)
class Proposal:
    prediction: torch.Tensor
    identities: torch.Tensor
    nodes: torch.Tensor
    global_state: torch.Tensor


class Network(nn.Module):
    @timed_often
    def __init__(self,tokens,kinds,relations,configuration):
        super().__init__()
        if configuration.sequence_length<1:
            raise ValueError(evidence(sequence_length=configuration.sequence_length))
        width=configuration.width
        self.configuration=configuration
        self.kinds=kinds
        self.feature=nn.EmbeddingBag(tokens,width,mode='sum',include_last_offset=True,padding_idx=0)
        self.kind=nn.Embedding(kinds,width,padding_idx=0)
        self.norm=nn.LayerNorm(width)
        self.context=nn.Linear(width,width,bias=False)
        self.elapsed=nn.Linear(1,width,bias=False)
        self.node_recurrent=nn.GRUCell(width,width)
        self.world_recurrent=nn.GRUCell(width*2,width)
        self.action_recurrent=nn.GRUCell(width*2,width)
        self.layers=nn.ModuleList(Layer(width,relations,configuration.operator,configuration.dropout) for _ in range(configuration.layers))
        self.action_layers=nn.ModuleList(Layer(width,relations,configuration.operator,configuration.dropout) for _ in range(configuration.action_layers))
        self.head=nn.Sequential(nn.Linear(width*4,width*2),nn.SiLU(),nn.Dropout(configuration.dropout),nn.Linear(width*2,20))

    @timed_often
    def embed(self,batch):
        h=self.feature(batch['tokens'],batch['offsets'],per_sample_weights=batch['values'])
        counts=(batch['offsets'][1:]-batch['offsets'][:-1]).to(h.dtype).clamp_min(1).sqrt()
        return self.norm(h/counts[:,None]+self.kind(batch['kind']))

    @timed_often
    def observe(self,batch,memory,hour):
        if len(batch['player'])!=1 or bool(batch['action'].any()):
            raise ValueError(evidence(players=len(batch['player']),actions=bool(batch['action'].any())))
        h=self.embed(batch)
        ids=batch['identity']
        size=int(ids.max())+1
        if memory is None:
            previous=h.new_zeros((size,h.shape[1]))
            global_state=h.new_zeros((1,h.shape[1]))
            elapsed=0.
        else:
            if hour<memory.hour:
                raise ValueError(evidence(hour=hour,held=memory.hour))
            previous=F.pad(memory.nodes,(0,0,0,max(0,size-len(memory.nodes))))
            global_state=memory.global_state
            elapsed=np.log1p((hour-memory.hour)/24)
        context=self.context(global_state)+self.elapsed(h.new_tensor([[elapsed]]))
        h=self.node_recurrent(h+context,previous[ids])
        for layer in self.layers:
            h=layer(h,batch)
        summed=h.new_zeros((self.kinds,h.shape[1])).index_add(0,batch['kind'],h)
        counts=torch.bincount(batch['kind'],minlength=self.kinds)
        world=(summed/counts.clamp_min(1)[:,None]).sum(0,keepdim=True)/(counts>0).sum().clamp_min(1)
        player=h[batch['player']]
        global_state=self.world_recurrent(torch.cat((player,world),1),global_state)
        state=Memory(previous.index_copy(0,ids,h),global_state,float(hour))
        return Observation(state,h,ids,player,world)

    @timed_often
    def propose(self,observation,proposal):
        device=observation.nodes.device
        count=len(observation.nodes)
        edges=proposal['edge_index']
        touched=np.unique(edges[edges<count])
        selected=np.r_[touched,np.arange(count,count+proposal['nodes'])]
        indices=np.full(count+proposal['nodes'],-1,np.int64)
        indices[selected]=np.arange(len(selected))
        batch=collate([proposal],device)
        batch['edge_index']=torch.as_tensor(indices[edges],dtype=torch.long,device=device)
        touched=torch.as_tensor(touched,dtype=torch.long,device=device)
        h=torch.cat((observation.nodes[touched],self.embed(batch)),0)
        for layer in self.action_layers:
            h=layer(h,batch)
        candidate=h[len(touched):]
        block=candidate[proposal['block']][None]
        acted=candidate[batch['action']].mean(0,keepdim=True)
        global_state=self.action_recurrent(torch.cat((block,acted),1),observation.memory.global_state)
        prediction=self.head(torch.cat((observation.player,observation.world,global_state,block),1)).reshape(1,5,4)
        return Proposal(prediction,observation.identities[touched],h[:len(touched)],global_state)

    @timed_often
    def commit(self,observation,proposal):
        return Memory(observation.memory.nodes.index_copy(0,proposal.identities,proposal.nodes),
                      proposal.global_state,observation.memory.hour)

    @timed_often
    def forward(self,batch,proposal,memory=None,hour=0.):
        observation=self.observe(batch,memory,hour)
        proposed=self.propose(observation,proposal)
        return proposed.prediction,self.commit(observation,proposed)


@timed
def collate(graphs,device):
    starts=np.r_[0,np.cumsum([g['nodes'] for g in graphs])]
    token_starts=np.r_[0,np.cumsum([len(g['tokens']) for g in graphs])]
    arrays={key:np.concatenate([g[key] for g in graphs]) for key in ('tokens','values','kind','current','action','relation','weight')}
    arrays['offsets']=np.r_[np.concatenate([g['offsets'][:-1]+token_starts[i] for i,g in enumerate(graphs)]),token_starts[-1]]
    arrays['edge_index']=np.concatenate([g['edge_index']+starts[i] for i,g in enumerate(graphs)],axis=1)
    arrays['batch']=np.repeat(np.arange(len(graphs)),np.diff(starts))
    arrays['player']=np.array([g['player']+starts[i] for i,g in enumerate(graphs)])
    arrays['block']=np.array([g['block']+starts[i] for i,g in enumerate(graphs)])
    arrays['identity']=np.concatenate([g['identity'] for g in graphs])
    integer={'tokens','offsets','kind','relation','edge_index','batch','player','block','identity'}
    return {key:torch.as_tensor(value,dtype=torch.long if key in integer else None,device=device) for key,value in arrays.items()}

