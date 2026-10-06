from . import db
from .grid import Spec, grid
from .runs import OUTCOMES

KIND="case when bool_and(v.name='loop') then 'time' when bool_and(a.name='choose_event_option') then 'events' else 'decision' end"


@db.timed
def run_blocks(run_id,filters,sort,desc,offset,limit):
    specs=[Spec('before_seq','seq','l.before_seq'),Spec('after_seq','seq','max(l.after_seq)'),Spec('turn','number','min(l.turn)'),
           Spec('game_date','date','s.game_date'),Spec('kind','text',KIND),Spec('actions','number','count(*)'),Spec('ms','number','coalesce(sum(l.ms),0)')]
    specs+=[Spec(name,'number',f'count(*) filter (where {test})') for name,test in OUTCOMES]
    source='''from loop_action l join action a using (action) join advisor v using (advisor) join snapshot s on s.run_id=l.run_id and s.seq=l.before_seq
              where l.run_id=%(run)s group by l.before_seq,s.game_date'''
    return grid(specs,source,{'run':run_id},filters,sort or 'before_seq',True if sort is None else desc,offset,limit,run_id,['before_seq'])
