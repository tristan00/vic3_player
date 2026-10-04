from collections import defaultdict
import math
from operator import itemgetter

import numpy as np

from interface.common import timed, timed_often
from .schema import GRAPH_VERSION


@timed_often
def logarithm(value):
    return math.copysign(math.log1p(abs(value)),value)


class Survey:
    @timed_often
    def __init__(self):
        self.categories=set()
        self.numeric=defaultdict(lambda:[0.,0.,0])
        self.kinds=set()
        self.relations=set()

    @timed
    def add(self,graph):
        self.relations.update(edge[2] for edge in graph.edges)
        columns=defaultdict(list)
        for node in graph.nodes:
            self.kinds.add(node['kind'])
            for key,value in node['attrs'].items():
                if isinstance(value,str):
                    self.categories.add((key,value))
                else:
                    columns[key].append(value)
        for key,values in columns.items():
            values=np.asarray(values,np.float64)
            numbers=np.copysign(np.log1p(np.abs(values)),values)
            found=self.numeric[key]
            found[0]+=float(numbers.sum())
            found[1]+=float(np.square(numbers).sum())
            found[2]+=len(numbers)

    @timed
    def merge(self,mapping):
        self.categories.update(mapping['categories'])
        self.kinds.update(mapping['kinds'])
        self.relations.update(mapping['relations'])
        for key,(a,b,n) in mapping['numeric'].items():
            found=self.numeric[key]
            found[0]+=a
            found[1]+=b
            found[2]+=n

    @timed_often
    def mapping(self):
        return {'categories':sorted(self.categories),'numeric':dict(self.numeric),
                'kinds':sorted(self.kinds),'relations':sorted(self.relations)}


class Encoder:
    @timed
    def __init__(self,surveys):
        self.graph_version=GRAPH_VERSION
        numeric=defaultdict(lambda:[0.,0.,0])
        categories=set()
        kinds=set()
        relations=set()
        for survey in surveys:
            categories.update(tuple(item) for item in survey['categories'])
            kinds.update(survey['kinds'])
            relations.update(survey['relations'])
            for key,(a,b,n) in survey['numeric'].items():
                item=numeric[key]
                item[0]+=a
                item[1]+=b
                item[2]+=n
        tokens=[('unknown','all')]
        tokens.extend(('category',key,value) for key,value in sorted(categories))
        tokens.extend(('unknown',key) for key in sorted({key for key,value in categories}))
        tokens.extend((prefix,key) for key in sorted(numeric) for prefix in ('number','present'))
        self.tokens={token:i for i,token in enumerate(tokens)}
        self.kinds={key:i+1 for i,key in enumerate(sorted(kinds))}
        self.relations={key:i+1 for i,key in enumerate(sorted(relations))}
        self.stats={key:(a/n,max(math.sqrt(max(0,b/n-(a/n)**2)),.1)) for key,(a,b,n) in numeric.items()}

    @timed_often
    def attributes(self,node,normalize=True):
        ids=[]
        values=[]
        for key,value in node['attrs'].items():
            if isinstance(value,str):
                index=self.tokens.get(('category',key,value),self.tokens.get(('unknown',key),0))
                ids.append(index)
                values.append(1.)
            elif key in self.stats:
                mean,scale=self.stats[key]
                ids.extend((self.tokens[('number',key)],self.tokens[('present',key)]))
                values.extend((max(-8.,min(8.,(logarithm(value)-mean)/scale)) if normalize else logarithm(value),1.))
        return np.asarray(ids,np.int32),np.asarray(values,np.float32)

    @timed
    def graph(self,graph,normalize=True,dtype=np.float32):
        return {**Features(graph).encode(self,normalize,dtype),**self.structure(graph)}

    @timed
    def structure(self,graph):
        count=len(graph.nodes)
        edges=graph.edges
        weights=np.fromiter(map(itemgetter(3),edges),np.float64,len(edges))
        weights=(np.copysign(np.log1p(np.abs(weights)),weights)/5).astype(np.float32)
        return {'identity':np.arange(count,dtype=np.int64),
                'kind':np.array([self.kinds.get(n['kind'],0) for n in graph.nodes],np.int16),
                'current':np.array([n['seq']==graph.nodes[graph.block]['seq'] for n in graph.nodes]),
                'action':np.array([n['kind']=='action' for n in graph.nodes]),
                'edge_index':graph.connections(),
                'relation':np.fromiter((self.relations.get(r,0) for r in map(itemgetter(2),edges)),np.int16,len(edges)),
                'weight':weights,
                'player':graph.player,'block':graph.block,'world_nodes':graph.block if graph.nodes[graph.block]['kind']=='action_block' else count,
                'nodes':count,'audit':graph.audit}


class Features:
    @timed
    def __init__(self,graph):
        grouped={}
        for index,node in enumerate(graph.nodes):
            attrs=node['attrs']
            values=tuple(attrs.values())
            signature=(tuple(attrs),tuple(map(type,values)))
            group=grouped.get(signature)
            if group is None:
                group=grouped[signature]=([],[])
            group[0].append(index)
            group[1].append(values)
        self.count=len(graph.nodes)
        self.groups=[]
        for (names,types),(indices,rows) in grouped.items():
            matrix=np.asarray(rows,object)
            columns=[]
            for column,(name,kind) in enumerate(zip(names,types)):
                categorical=issubclass(kind,str)
                values=matrix[:,column]
                if not categorical:
                    values=values.astype(np.float64)
                    values=np.copysign(np.log1p(np.abs(values)),values)
                columns.append((name,categorical,values))
            self.groups.append((np.asarray(indices,np.int32),columns))

    @timed
    def survey(self,graph):
        numeric=defaultdict(lambda:[0.,0.,0])
        categories=set()
        for indices,columns in self.groups:
            for name,categorical,values in columns:
                if categorical:
                    categories.update((name,value) for value in set(values))
                else:
                    found=numeric[name]
                    found[0]+=float(values.sum())
                    found[1]+=float(np.square(values).sum())
                    found[2]+=len(values)
        return {'categories':sorted(categories),'numeric':dict(numeric),
                'kinds':sorted({node['kind'] for node in graph.nodes}),
                'relations':sorted(set(map(itemgetter(2),graph.edges)))}

    @timed
    def encode(self,encoder,normalize,dtype):
        sizes=np.zeros(self.count,np.int32)
        for indices,columns in self.groups:
            sizes[indices]=sum(1 if categorical else 2 if name in encoder.stats else 0 for name,categorical,values in columns)
        offsets=np.r_[0,np.cumsum(sizes)].astype(np.int32)
        ids=np.empty(offsets[-1],np.int32)
        values=np.ones(offsets[-1],dtype)
        for indices,columns in self.groups:
            positions=offsets[indices].copy()
            for name,categorical,numbers in columns:
                if categorical:
                    unknown=encoder.tokens.get(('unknown',name),0)
                    lookup={value:encoder.tokens.get(('category',name,value),unknown) for value in set(numbers)}
                    ids[positions]=np.fromiter(map(lookup.__getitem__,numbers),np.int32,len(numbers))
                    positions+=1
                elif name in encoder.stats:
                    ids[positions]=encoder.tokens['number',name]
                    ids[positions+1]=encoder.tokens['present',name]
                    if normalize:
                        mean,scale=encoder.stats[name]
                        numbers=np.clip((numbers-mean)/scale,-8,8)
                    values[positions]=numbers
                    positions+=2
        return {'tokens':ids,'values':values,'offsets':offsets}


@timed
def fragment(graph):
    features=Features(graph)
    mapping=features.survey(graph)
    encoder=Encoder([mapping])
    packed={**features.encode(encoder,False,np.float64),**encoder.structure(graph)}
    return {'graph':packed,'encoder':encoder},mapping
