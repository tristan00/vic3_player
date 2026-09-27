# Timing

`interface/timing.py` is the only timing tool in the project. Every duration that is logged, stored or reported comes from a span. It measures with `time.perf_counter_ns`, logs each call on exit, aggregates per span in memory, and the store writes the aggregates to Postgres for every run.

Clock reads that remain elsewhere are deadlines and pacing, such as a timeout or the gap between two actions. None of them produces a reported duration.

## Timing a function

```python
from interface.common import timed, timed_often
from dashboard.server import db

@timed
def capture(reader): ...

@timed_often
def copy(self,cursor,name,columns,rows): ...

@db.timed
def run_actions(run_id): ...
```

| decorator | logs at | stamps watchdog progress | use for |
| --- | --- | --- | --- |
| `timed` | INFO | yes | work that runs a few times per turn or less |
| `timed_often` | DEBUG | no | work that runs many times per snapshot |
| `db.timed` | INFO | no | the dashboard |

All three record the same measurements. `timed_often` exists so that a call made hundreds of times per snapshot is stored without filling the log.

A decorator goes directly above `def`, below `@staticmethod`, `@property` and `@cache`. Below a cache it times only the misses.

Decorating a generator or a coroutine raises `TypeError` at import. Timing that call would measure only the creation of the generator, so time the caller instead.

## Timing a block

```python
from interface.timing import span

with span('advisors.pickers.CatBoostPicker.fit','loop'):
    model.fit(rows)
```

The second argument is the logger name. A third sets the log level.

## Reading a duration in code

A span reports `ms` and `seconds`. While it is open they are the time elapsed so far, after it closes they are its duration.

```python
from interface.timing import current

entry['ms']=round(current().ms)
```

`current()` is the innermost open span, which inside a decorated function is that function. Values stored in the database come from here: `snapshot.read_ms`, `loop_action.ms`, `pick_model.seconds` and `smac_proposal.seconds`.

## Span names

A decorated function is named by its file path under the project root and its qualified name: `interface.recording.store.Store.write`. The name is the same whether the module was imported, run with `-m`, or loaded in a spawned child.

Dashboard requests are named by method and route template: `GET /api/runs/{run_id}/actions`. An API path that matches no route is `GET /api/{path:path}`.

## Log lines

```
interface.recording.store.Store.write 153.2ms
interface.actions.execute.Executor.run FAILED LookupError 48.0ms
```

A call that leaves by raising is logged as FAILED with the exception type and counted as an error. The exception always propagates.

## What is measured per span

| column | meaning |
| --- | --- |
| calls | calls that finished, by returning or raising |
| errors | calls that raised |
| total_ms | wall time summed over calls |
| self_ms | total_ms minus the time of spans opened inside, on the same thread |
| min_ms, max_ms | exact |
| p50_ms, p95_ms, p99_ms | from a log-scale histogram, 8 buckets per doubling; at most 9 % above the exact value, never outside min and max |

Memory per span is bounded by the histogram, so a process can run indefinitely.

A large `self_ms` means time the span spent on work that is not itself a span. For `Loop.run_days`, `GameInterface.ready` and `Executor.run` that is waiting on the game.

## Other processes

One recorder per run holds everything. Spans measured in another process are sent to the loop and merged.

| process | how its spans arrive |
| --- | --- |
| heartbeat | sends what it measured every second over a queue; the store merges it before each write |
| world pool worker | returns its spans with the finished world; merged when the world is taken |
| world built in a thread | same process, recorded directly |

A pooled world may have been built while an earlier run was playing. Its spans belong to the run that takes it.

## Stored tables

Both tables are in `schema_meta.sql`.

`run_timing (run_id, span, ...)` holds the whole run so far. It is rewritten inside every snapshot transaction and once more when the run ends, so a crashed or stalled run keeps everything up to its last snapshot.

`snapshot_timing (run_id, seq, span, calls, errors, total_ms, self_ms, max_ms)` holds the calls that finished since the previous snapshot was written. The write of snapshot `seq` is still open when its rows are stored, so it appears under `seq + 1`. Calls that finish after the last snapshot appear only in `run_timing`.

The recorder is reset at the start of each session, so the first interval of a run holds world generation, picker training and the game launch.

Two spans are still open at the final write and are not stored: `loop.run.session` and `loop.run.Loop.run`. Their duration is `run.ended_at - run.started_at`, and both are logged when they close.

## Reading it

Dashboard, run page, timing tab: both tables for that run.

Dashboard, schema page, dashboard timing: the dashboard process itself, per route, per function and per query call, since it started. Same data at `/api/timing`. Every API response also carries a `Server-Timing` header with its six slowest spans.

```sql
select span, calls, total_ms, self_ms, p95_ms, max_ms
from run_timing where run_id = 242 order by self_ms desc limit 20;

select seq, total_ms / calls as mean_ms, max_ms
from snapshot_timing
where run_id = 242 and span = 'interface.recording.store.Store.write'
order by seq;

select span, sum(total_ms) / sum(calls) as mean_ms, max(p99_ms) as worst_p99_ms
from run_timing group by span order by 2 desc limit 20;
```

## Outside the run

Three monitor processes are not timed: the GPU guard, the supervisor and the watcher. They run apart from the loop, belong to no run, and only poll and sleep.

Raw memory reads are not spans. `Reader.read` and `Reader.array` run thousands of times per snapshot, and a span around each would cost more than the read. The functions that call them are spans: `Reader.table`, `Reader.snapshot`, `Reader.holder`, `Reader.holders`.

## Changing the schema

`Store` refuses to write when the database digest differs from `schema.sql`. A new timing column needs the same change applied to the database and the digest row updated in one transaction, then `schema.sql` regenerated with `interface/recording/emit.py`.
