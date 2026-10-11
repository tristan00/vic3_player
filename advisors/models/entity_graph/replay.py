import heapq

from interface.common import evidence, timed
from interface.options.stored import Stored
from interface.recording.spec import TABLE
from .source import keys
from .world import WORLD_TABLES, WorldReader


class ReplayReader(WorldReader):
    @timed
    def __init__(self,connection,run,stop,chunk_size=16):
        if chunk_size<1:
            raise ValueError(evidence(chunk_size=chunk_size))
        super().__init__(connection,run)
        self.stop=stop
        self.chunk_size=chunk_size
        self.position=-1
        self.loaded=-1
        self.events={}
        self.current={name:{} for name in WORLD_TABLES}
        self.future={name:[] for name in WORLD_TABLES if TABLE[name].kind=='sample'}
        self.ranks={name:{} for name in self.future}
        self.identity={name:keys(TABLE[name]) for name in WORLD_TABLES}
        self.ordered={}

    @timed
    def load(self):
        sequences=[at for at in self.dates if self.loaded<at<=self.stop]
        end=sequences[min(len(sequences),self.chunk_size)-1]
        events={}
        queries=[]
        with self.connection.pipeline():
            for name in WORLD_TABLES:
                table=TABLE[name]
                fields=[*self.identity[name],'seq']
                if table.kind=='sample':
                    fields+=['run_id','n','date']
                elif table.kind in ('history','child','listing'):
                    fields.append('present')
                fields.extend(c.name for c in table.columns)
                columns=','.join('"'+field+'"' for field in fields)
                cursor=self.connection.execute(f'select {columns} from {name} where run_id=%s and seq>%s and seq<=%s order by seq',
                                               (self.run,self.loaded,end),binary=True)
                queries.append((name,fields,cursor))
        for name,fields,cursor in queries:
            identity=self.identity[name]
            for values in cursor.fetchall():
                row=dict(zip(fields,values))
                key=tuple(row[field] for field in identity)
                events.setdefault(row['seq'],[]).append((name,key,row))
        self.events=events
        self.loaded=end

    @timed
    def advance(self,seq):
        if seq<self.position:
            raise ValueError(evidence(seq=seq,position=self.position))
        if seq>self.stop:
            raise ValueError(evidence(seq=seq,stop=self.stop))
        if self.position>=0 and self.dates[seq]<self.dates[self.position]:
            raise ValueError(evidence(seq=seq,position=self.position,date=self.dates[seq],held=self.dates[self.position]))
        while self.position<seq:
            if self.position==self.loaded:
                self.load()
            through=min(seq,self.loaded)
            for at in sorted(at for at in self.events if at<=through):
                for name,key,row in self.events.pop(at):
                    table=TABLE[name]
                    current=self.current[name]
                    if table.kind=='sample':
                        date=row['date']
                        heapq.heappush(self.future[name],(float('-inf') if date is None else date,row['n'],key,row))
                    elif row.pop('present',True):
                        current[key]=row
                    else:
                        current.pop(key,None)
                    self.ordered.pop(name,None)
            self.position=through
        hour=self.dates[seq]
        for name,pending in self.future.items():
            while pending and pending[0][0]<=hour:
                date,n,key,row=heapq.heappop(pending)
                rank=(date,n)
                if key not in self.ranks[name] or rank>self.ranks[name][key]:
                    self.ranks[name][key]=rank
                    self.current[name][key]=row
                    self.ordered.pop(name,None)

    @timed
    def snapshot(self,seq):
        self.advance(seq)
        snapshot={}
        for name in WORLD_TABLES:
            table=TABLE[name]
            if name not in self.ordered:
                ordered=sorted(self.current[name],reverse=table.kind!='sample' and table.owner is None)
                if table.owner and table.keys and table.kind!='sample':
                    ordered.sort(key=lambda key:key[1:],reverse=True)
                    ordered.sort(key=lambda key:key[0])
                self.ordered[name]=[self.current[name][key] for key in ordered]
            rows=self.ordered[name]
            if table.owner and table.kind in ('subject','sample'):
                live=self.current[table.owner+'_history']
                rows=[row for row in rows if (row[table.owner],) in live]
            snapshot[name]=rows
        return snapshot


class ReplaySnapshot(Stored):
    @timed
    def __init__(self,connection,data,shared):
        super().__init__(connection,data['run'],data['seq'],shared)
        self.observed=data['states'][data['seq']]

    @timed
    def read(self,stored):
        if stored not in self.observed or TABLE[stored].kind=='sample':
            return super().read(stored)
        self.shared.wanted.add(stored)
        table=TABLE[stored]
        fields=[*keys(table),'seq',*[col.name for col in table.columns]]
        rows=[tuple(row[field] for field in fields) for row in self.observed[stored]]
        return self.named(stored,[field[:63] for field in fields],rows)

    @timed
    def load(self):
        for stored in sorted(self.shared.wanted):
            if ('table',stored) not in self.cache:
                self.cache['table',stored]=self.read(stored)
