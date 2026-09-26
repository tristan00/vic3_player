from datetime import datetime, timezone

from interface.recording.spec import ENTITIES, TABLES

from . import db
from .actions import ACTION_SELECT, action_rows
from .blocks import run_blocks
from .models import CaptureGap, LivePage, LiveRun, Ref, SchemaColumn, SchemaPage, SchemaTable
from .names import kind_of, key_columns, labels
from .runs import RUN_SELECT, one_run, round_of, run_rows, status_counts

RECENT=40
RECENT_BLOCKS=6
READS=120


@db.timed
def live_page():
    open_runs=db.rows(f'{RUN_SELECT} where r.ended_at is null order by r.run_id desc')
    live=[]
    for run in run_rows(open_runs):
        found=db.row('''select r.player_country,r.progress_step,extract(epoch from now()-r.heartbeat_at) as heartbeat_age,
                               extract(epoch from now()-r.progress_at) as progress_age,
                               (select max(turn) from loop_action a where a.run_id=r.run_id) as turn
                        from run r where r.run_id=%s''',(run.run_id,))
        reads=list(reversed(db.rows('select seq,read_ms from snapshot where run_id=%s order by seq desc limit %s',(run.run_id,READS))))
        player=labels(run.run_id,'country',[found['player_country']])
        live.append(LiveRun(run=run,player=Ref(kind='country',id=found['player_country'],label=player[found['player_country']]),
                            progress_step=found['progress_step'],heartbeat_age_s=float(found['heartbeat_age']),progress_age_s=float(found['progress_age']),
                            turn=found['turn'] or 0,game_start=run.game_from,game_now=run.game_to,
                            statuses=status_counts('where a.run_id=%s',(run.run_id,)),
                            recent=action_rows(db.rows(f'{ACTION_SELECT} where l.run_id=%s order by l.n desc limit %s',(run.run_id,RECENT))),
                            read_ms=[r['read_ms'] for r in reads],read_seq=[r['seq'] for r in reads]))
    latest=db.row('select run_id,cli_seed from run order by run_id desc limit 1')
    return LivePage(now=datetime.now(timezone.utc).isoformat(),live=live,blocks={l.run.run_id:run_blocks(l.run.run_id,0,RECENT_BLOCKS,'decision').rows for l in live},
                    last=None if latest is None or live else one_run(latest['run_id']),
                    round=None if latest is None else round_of(latest['cli_seed']))


def schema_column(column):
    target=column.entity or column.vocabulary or column.enum or column.check
    return SchemaColumn(name=column.name,type=column.kind or column.vocabulary,kind=kind_of(column),target=target,optional=column.optional)


@db.timed
def schema_page():
    ruleset=db.value('select ruleset_id from run order by run_id desc limit 1')
    gaps=[CaptureGap(**f) for f in db.rows('select kind,subject,detail from capture_gap where ruleset_id=%s order by kind,subject',(ruleset,))] if ruleset else []
    return SchemaPage(entities=list(ENTITIES),tables=[SchemaTable(name=t.name,kind=t.kind,owner=t.owner,scope=t.scope,
                                                                  keys=[schema_column(c) for c in key_columns(t)],columns=[schema_column(c) for c in t.columns])
                                                      for t in TABLES],ruleset_id=ruleset,gaps=gaps)


def stamp():
    found=db.row('''select max(run_id) as run,count(*) filter (where ended_at is null) as open,max(ended_at) as ended,
                           (select max(seq) from snapshot s where s.run_id=(select max(run_id) from run)) as seq,
                           (select max(n) from loop_action a where a.run_id=(select max(run_id) from run)) as n
                    from run''')
    return f"{found['run']}.{found['open']}.{found['ended']}.{found['seq']}.{found['n']}"

