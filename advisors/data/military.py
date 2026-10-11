from bisect import bisect_right
from collections import defaultdict
import math

from interface.common import evidence, timed, timed_often
from .rewards import PLAYERS, SNAPSHOTS

MANPOWER_PER_UNIT=1000
UNITS='''with owned as (
    select distinct h.run_id,h.combat_unit from combat_unit_history h
    join run r on r.run_id=h.run_id and r.player_country=h.country where h.run_id=any(%s))
select h.run_id,h.seq,h.combat_unit,h.present,h.country,h.manpower
from owned join combat_unit_history h using (run_id,combat_unit)
order by h.run_id,h.seq,h.combat_unit'''


class MilitaryStrength:
    @timed
    def __init__(self,connection,runs):
        players=dict(connection.execute(PLAYERS,(runs,)).fetchall())
        events=defaultdict(list)
        for run,seq,unit,present,country,manpower in connection.execute(UNITS,(runs,)).fetchall():
            value=manpower if present and country==players[run] else 0
            if value is None or value<0:
                raise ValueError(evidence(value=value))
            events[run,seq].append((unit,value))
        snapshots=defaultdict(list)
        for run,seq,hour in connection.execute(SNAPSHOTS,(runs,)).fetchall():
            snapshots[run].append((seq,hour))
        self.hours={}
        self.units={}
        self.totals={}
        for run,rows in snapshots.items():
            units,states={},{}
            manpower=0
            for seq,hour in sorted(rows):
                for unit,value in events[run,seq]:
                    manpower+=value-units.pop(unit,0)
                    if value:
                        units[unit]=value
                states[hour]=manpower/MANPOWER_PER_UNIT
            hours=sorted(states)
            totals=[0.]
            for first,last in zip(hours,hours[1:]):
                totals.append(totals[-1]+(last-first)*math.log1p(states[first]))
            self.hours[run]=hours
            self.units[run]=[states[hour] for hour in hours]
            self.totals[run]=totals

    @timed_often
    def mean_log(self,run,start,end):
        hours=self.hours.get(run,[])
        if end<=start or not hours or start<hours[0] or end>hours[-1]:
            return None
        values=[]
        for hour in (start,end):
            i=bisect_right(hours,hour)-1
            values.append(self.totals[run][i]+(hour-hours[i])*math.log1p(self.units[run][i]))
        return (values[1]-values[0])/(end-start)

    @timed_often
    def series(self,run):
        return list(zip(self.hours.get(run,[]),self.units.get(run,[])))
