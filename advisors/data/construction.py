from bisect import bisect_right
from collections import defaultdict

from interface.common import timed, timed_often
from .levels import MeanLog
from .rewards import OWNERS, PLAYERS, SNAPSHOTS, built

COUNTS='''select run_id,seq,num_active_government_construction_queue_elements
from player_construction where run_id=any(%s) order by run_id,seq'''
PAUSED='''select c.run_id,c.seq,c.is_construction_paused,c.present
from country_construction_report c join run r on r.run_id=c.run_id and r.player_country=c.country
where c.run_id=any(%s) order by c.run_id,c.seq'''
SECTORS='''with sectors as (
    select distinct b.run_id,b.building from building_history b
    join building_type t on t.building_type=b.building_type
    where b.run_id=any(%s) and t.name='building_construction_sector')
select b.run_id,b.seq,b.building,b.present,b.state,b.levels
from sectors join building_history b using (run_id,building)'''


class ConstructionActivity:
    @timed
    def __init__(self,connection,runs):
        counts={(run,seq):count for run,seq,count in connection.execute(COUNTS,(runs,)).fetchall()}
        pauses={(run,seq):paused if present else None for run,seq,paused,present in connection.execute(PAUSED,(runs,)).fetchall()}
        snapshots=defaultdict(list)
        for run,seq,hour in connection.execute(SNAPSHOTS,(runs,)).fetchall():
            snapshots[run].append((seq,hour))
        self.hours={}
        self.active={}
        self.missing={}
        for run,rows in snapshots.items():
            count,paused=None,None
            states={}
            for seq,hour in sorted(rows):
                count=counts.get((run,seq),count)
                paused=pauses.get((run,seq),paused)
                states[hour]=None if count is None or paused is None else count>0 and not paused
            hours=sorted(states)
            active,missing=[0],[0]
            for first,last in zip(hours,hours[1:]):
                elapsed=last-first
                active.append(active[-1]+elapsed*(states[first] is True))
                missing.append(missing[-1]+elapsed*(states[first] is None))
            self.hours[run]=hours
            self.active[run]=active
            self.missing[run]=missing

    @timed_often
    def integral(self,run,hour,values):
        hours=self.hours[run]
        i=bisect_right(hours,hour)-1
        if hour==hours[i]:
            return values[i]
        return values[i]+(values[i+1]-values[i])*(hour-hours[i])/(hours[i+1]-hours[i])

    @timed_often
    def fraction(self,run,start,end):
        hours=self.hours.get(run,[])
        if end<=start or not hours or start<hours[0] or end>hours[-1]:
            return None
        missing=self.missing[run]
        if self.integral(run,end,missing)>self.integral(run,start,missing):
            return None
        active=self.active[run]
        return (self.integral(run,end,active)-self.integral(run,start,active))/(end-start)

    @timed_often
    def series(self,run):
        hours=self.hours.get(run,[])
        return [(hour,fraction) for hour in hours[1:] if (fraction:=self.fraction(run,hours[0],hour)) is not None]


class ConstructionSectors(MeanLog):
    @timed
    def __init__(self,connection,runs):
        players=dict(connection.execute(PLAYERS,(runs,)).fetchall())
        events=defaultdict(list)
        for run,seq,state,present,country in connection.execute(OWNERS,(runs,)).fetchall():
            events[run].append((seq,0,state,country if present else None))
        for run,seq,building,present,state,levels in connection.execute(SECTORS,(runs,)).fetchall():
            events[run].append((seq,1,building,(state,levels) if present else None))
        snapshots=defaultdict(list)
        for run,seq,hour in connection.execute(SNAPSHOTS,(runs,)).fetchall():
            snapshots[run].append((seq,hour))
        states={}
        for run,rows in snapshots.items():
            changes=dict(built(events[run],players[run],{seq:seq for seq,_ in rows}))
            levels,found=0,{}
            for seq,hour in sorted(rows):
                levels=changes.get(seq,levels)
                found[hour]=levels
            states[run]=found
        super().__init__(states)
