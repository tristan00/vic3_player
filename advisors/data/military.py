from collections import defaultdict

from interface.common import evidence, timed
from .levels import MeanLog
from .rewards import PLAYERS, SNAPSHOTS

MANPOWER_PER_UNIT=1000
UNITS='''with owned as (
    select distinct h.run_id,h.combat_unit from combat_unit_history h
    join run r on r.run_id=h.run_id and r.player_country=h.country where h.run_id=any(%s))
select h.run_id,h.seq,h.combat_unit,h.present,h.country,h.manpower
from owned join combat_unit_history h using (run_id,combat_unit)
order by h.run_id,h.seq,h.combat_unit'''


class MilitaryStrength(MeanLog):
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
        states={}
        for run,rows in snapshots.items():
            units,found={},{}
            manpower=0
            for seq,hour in sorted(rows):
                for unit,value in events[run,seq]:
                    manpower+=value-units.pop(unit,0)
                    if value:
                        units[unit]=value
                found[hour]=manpower/MANPOWER_PER_UNIT
            states[run]=found
        super().__init__(states)
