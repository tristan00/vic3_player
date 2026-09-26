from . import db
from .actions import ACTION_SELECT, action_rows
from .models import BlockDetail, BlockLog, BlockRow, Count, Facet, Scope, StatusCount
from .names import game_date
from .runs import STATUSES, snapshot_row

KIND="case when bool_and(v.name='loop') then 'time' when bool_and(a.name='choose_event_option') then 'events' else 'decision' end"
BLOCKS=f'''
select l.before_seq,max(l.after_seq) as after_seq,min(l.turn) as turn,s.game_date,{KIND} as kind,count(*) as actions,coalesce(sum(l.ms),0) as ms,
       array_agg(a.name order by l.n) as names,{",".join(f"count(*) filter (where l.status='{status}') as {status}" for status in STATUSES)}
from loop_action l join action a using (action) join advisor v using (advisor) join snapshot s on s.run_id=l.run_id and s.seq=l.before_seq
where l.run_id=%s group by l.before_seq,s.game_date
'''


def block_row(found):
    return BlockRow(before_seq=found['before_seq'],after_seq=found['after_seq'],turn=found['turn'],game_date=game_date(found['game_date']),kind=found['kind'],
                    actions=found['actions'],ms=found['ms'],names=found['names'],statuses=[StatusCount(status=s,count=found[s]) for s in STATUSES])


@db.timed
def run_blocks(run_id,offset,limit,kind=None):
    where='where b.kind=%s' if kind else ''
    params=[run_id,*([kind] if kind else [])]
    total=db.value(f'select count(*) from ({BLOCKS}) b {where}',params)
    found=db.rows(f'select * from ({BLOCKS}) b {where} order by b.before_seq desc limit %s offset %s',[*params,limit,offset])
    kinds=[Facet(value=f['kind'],count=f['count']) for f in db.rows(f'select b.kind,count(*) as count from ({BLOCKS}) b group by 1 order by 2 desc',(run_id,))]
    return BlockLog(scope=Scope(text=f'every block of actions run {run_id} chose, newest first'+(f', {kind} blocks' if kind else ''),
                                detail='a block is every action chosen from one snapshot and executed before the next; decision blocks are the advisor’s picks, '
                                       'event blocks answer pending events, time blocks run game days'),
                    total=Count(value=total,noun='blocks',population='matching the filter'),rows=[block_row(f) for f in found],kinds=kinds)


@db.timed
def block_detail(run_id,seq):
    found=db.row(f'select * from ({BLOCKS}) b where b.before_seq=%s',(run_id,seq))
    if found is None:
        return None
    actions=action_rows(db.rows(f'{ACTION_SELECT} where l.run_id=%s and l.before_seq=%s order by l.n',(run_id,seq)))
    before=snapshot_row(db.row('select s.*,0 as actions from snapshot s where s.run_id=%s and s.seq=%s',(run_id,seq)))
    after=None if found['after_seq'] is None else snapshot_row(db.row('select s.*,0 as actions from snapshot s where s.run_id=%s and s.seq=%s',(run_id,found['after_seq'])))
    previous=db.value('select max(before_seq) from loop_action where run_id=%s and before_seq<%s',(run_id,seq))
    following=db.value('select min(before_seq) from loop_action where run_id=%s and before_seq>%s',(run_id,seq))
    return BlockDetail(block=block_row(found),actions=actions,before=before,after=after,previous=previous,next=following)
