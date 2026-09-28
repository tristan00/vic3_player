import numpy as np

from interface.common import timed, timed_often
from .features import KINDS, Versions, resolve

ACTION='action'
BUILDINGS='player.buildings'
METHODS='player.production_methods'


@timed_often
def entries(batch,lookup):
    found=[]
    for action,params in batch:
        found.append((ACTION,action,1))
        found+=[(f'{action}.{param}',str(resolve(param,kind,params[param],lookup)),1) for param,kind in KINDS[action] if param in params]
    return found


@timed_often
def live_holdings(snapshot):
    levels={building:count for building,_,count in snapshot.buildings()}
    return [(BUILDINGS,kind,count) for _,kind,count in snapshot.buildings()]+[(METHODS,method,levels[building])
            for building,method in snapshot.rows('building_production_method_active','building,production_method') if building in levels]


class Holdings:
    @timed
    def __init__(self,connection,runs):
        self.buildings=Versions(connection,'building_history',['building'],['building_type','state','levels'],runs)
        self.methods=Versions(connection,'building_production_method_active',['building','production_method'],[],runs)

    @timed_often
    def at(self,lookup):
        found,levels=[],{}
        for key in self.buildings.by_run.get(lookup.run,[]):
            now=self.buildings.at(lookup.run,key,lookup.seq)
            if now is not None and lookup.state(now[1])[1]==lookup.player:
                levels[key[0]]=now[2]
                found.append((BUILDINGS,now[0],now[2]))
        found+=[(METHODS,method,levels[building]) for building,method in self.methods.by_run.get(lookup.run,[])
                if building in levels and self.methods.at(lookup.run,(building,method),lookup.seq) is not None]
        return found


class Histograms:
    @timed
    def __init__(self,pauses):
        seen={}
        for found in pauses:
            for name,value in {(name,value) for name,value,_ in found}:
                bins=seen.setdefault(name,{})
                bins[value]=bins.get(value,0)+1
        self.names=sorted(seen)
        self.bins={name:sorted(seen[name],key=lambda value:(-seen[name][value],value)) for name in self.names}
        self.start={}
        self.total=0
        for name in self.names:
            self.start[name]=self.total
            self.total+=len(self.bins[name])
        self.column={(name,value):self.start[name]+position for name in self.names for position,value in enumerate(self.bins[name])}
        self.counts=self.count(pauses)

    @timed_often
    def count(self,pauses):
        counts=np.zeros((len(pauses),self.total),np.float32)
        for row,found in enumerate(pauses):
            for name,value,weight in found:
                if (name,value) in self.column:
                    counts[row,self.column[(name,value)]]+=weight
        return counts

    @timed_often
    def columns(self,sizes):
        return [self.start[name]+position for name in self.names for position in range(sizes.get(name,0))]

    @timed_often
    def labels(self,sizes):
        return [f'{name}={value}' for name in self.names for value in self.bins[name][:sizes.get(name,0)]]
