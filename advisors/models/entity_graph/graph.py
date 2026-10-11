from collections import Counter, defaultdict
from dataclasses import dataclass
import math
from operator import itemgetter

import numpy as np

from interface.common import evidence, timed, timed_often
from .schema import ENTITY_PARAMETERS, PARAMETERS


@dataclass
class Graph:
    nodes: list
    edges: list
    player: int
    block: int
    audit: dict

    @timed
    def connections(self):
        return np.stack([np.fromiter(map(itemgetter(i),self.edges),np.int32,len(self.edges)) for i in (0,1)])


class Builder:
    @timed_often
    def __init__(self,design,vocabulary,start):
        self.design,self.vocabulary,self.start=design,vocabulary,start
        self.nodes=[]
        self.edges=[]
        self.lookup={}
        self.audit=Counter()
        self.inverse_relations={}

    def node(self,kind,key,seq,hour,attrs):
        identity=(seq,kind,key)
        if identity not in self.lookup:
            self.lookup[identity]=len(self.nodes)
            self.nodes.append({'kind':kind,'key':key,'seq':seq,'hour':hour,
                               'attrs':{'age_days':(self.start-hour)/24,**attrs}})
        return self.lookup[identity]

    def edge(self,source,target,relation,weight=1.,reverse=None):
        if not self.design.edges or source is None or target is None:
            return
        if not math.isfinite(weight):
            raise ValueError(evidence(relation=relation,weight=weight))
        self.edges.append((source,target,relation,float(weight)))
        if self.design.reverse if reverse is None else reverse:
            if relation not in self.inverse_relations:
                self.inverse_relations[relation]='reverse.'+relation
            self.edges.append((target,source,self.inverse_relations[relation],float(weight)))

    def find(self,seq,kind,key):
        return self.lookup.get((seq,kind,key))

    @timed
    def geography(self,raw,seq,hour,geography):
        mapped={}
        terrains={row[0]:row[2] for row in geography['provinces']}
        totals=defaultdict(lambda:defaultdict(float))
        for province,region,terrain,area,x,y in geography['provinces']:
            state=raw['province'].get(province,{}).get('state')
            mapped[province]=state
            target=self.find(seq,'state',state)
            if target is None:
                continue
            total=totals[state]
            total['area_pixels']+=area
            total['x_weighted']+=x*area
            total['y_weighted']+=y*area
            total['terrain_area.'+str(terrain)]+=area
            node=self.find(seq,'province',province)
            if node is not None:
                self.nodes[node]['attrs'].update({'terrain':str(terrain),'area_pixels':float(area),'x':float(x),'y':float(y)})
        for state,total in totals.items():
            attrs=self.nodes[self.find(seq,'state',state)]['attrs']
            area=total.pop('area_pixels')
            attrs['area_pixels']=area
            attrs.update({key:value/area for key,value in total.items()})
        borders=Counter()
        for a,b,weight in geography['adjacency']:
            left,right=mapped.get(a),mapped.get(b)
            water=(terrains.get(a) in ('ocean','lakes'),terrains.get(b) in ('ocean','lakes'))
            if left is not None and right is not None and left!=right and not any(water):
                borders[tuple(sorted((left,right)))]+=weight
            if self.design.geography=='province':
                relation='province.water_border' if all(water) else 'province.coast' if any(water) else 'province.land_border'
                self.edge(self.find(seq,'province',a),self.find(seq,'province',b),relation,weight,True)
        for (a,b),weight in borders.items():
            self.edge(self.find(seq,'state',a),self.find(seq,'state',b),'state.land_border',weight,True)

    @timed
    def candidate(self,actions,seq,hour,player):
        if not actions:
            raise ValueError(evidence(actions=actions,seq=seq))
        block=self.node('action_block','candidate',seq,hour,{'size':float(len(actions))})
        self.edge(self.find(seq,'country',player),block,'candidate.player')
        previous=None
        for position,(name,params) in enumerate(actions):
            if set(params)!=set(PARAMETERS[name]):
                raise ValueError(evidence(name=name,params=params,expected=PARAMETERS[name]))
            attrs={'action':name,'position':float(position)}
            targets=[]
            for param,value in params.items():
                kind=PARAMETERS[name][param]
                if kind in ENTITY_PARAMETERS:
                    entity=ENTITY_PARAMETERS[kind]
                    target=self.find(seq,entity,value)
                    targets.append((param,target))
                    self.audit['entity_references']+=1
                    if target is None:
                        self.audit['unresolved_entity_references']+=1
                        attrs['unobserved_target.'+param]=entity
                else:
                    attrs['parameter.'+param]=float(value) if kind=='int' else str(value)
            node=self.node('action',position,seq,hour,attrs)
            self.nodes[node]['parameters']=dict(params)
            self.edge(node,block,'candidate.member')
            self.edge(previous,node,'candidate.next',reverse=False)
            previous=node
            for param,target in targets:
                self.edge(node,target,'action.parameter.'+param)
            self.edge(node,self.find(seq,'country',player),'action.actor')
            if self.design.action_links=='semantic':
                self.semantic(node,name,params,seq,player)
        return block


@timed_often
def audit(graph,start):
    count=len(graph.nodes)
    if any(node['hour']>start for node in graph.nodes):
        raise ValueError(evidence(start=start,latest=max(node['hour'] for node in graph.nodes)))
    indices=graph.connections()
    if (indices<0).any() or (indices>=count).any():
        raise ValueError(evidence(count=count,lowest=int(indices.min()),highest=int(indices.max())))
    relations=Counter(map(itemgetter(2),graph.edges))
    if any(relation.startswith('temporal.') for relation in relations):
        raise ValueError(evidence(temporal=sorted(relation for relation in relations if relation.startswith('temporal.'))))
    return {'node_types':dict(Counter(n['kind'] for n in graph.nodes)),
            'relations':dict(relations),**graph.audit}
