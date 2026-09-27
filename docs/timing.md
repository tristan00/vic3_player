# Timing

`interface/timing.py` is the only timing tool in the project. Every duration that is logged, stored or reported comes from a span. A span measures with `time.perf_counter_ns`, logs on exit, and is aggregated per name in memory. The store writes the aggregates to Postgres for every run.

What the measurements have been used to speed up is in `loop_speed.md`.

## Coverage

Every function in `interface`, `loop`, `advisors` and `dashboard/server` is timed, or it is listed with a reason. `tests/test_timing_coverage.py` enforces this. A new function without a decorator fails the suite until it is decorated or listed in `tests/timing_exempt.json`.

| state | functions |
| --- | --- |
| timed by a decorator | 904 |
| listed by name, inside a timed caller | 67 |
| in a file listed as a whole | 87 |

Reasons a function may be listed:

| reason | meaning |
| --- | --- |
| hot | called more than 2000 times per snapshot or pause, or more than 20000 times per run for setup work; a span costs more than the call |
| loop | runs for the life of its thread, process or run, so its span would never close in time to be stored |
| timer | part of the timing tool or the watchdog stamp |
| monitor | the GPU guard, supervisor, watcher and launchers; they belong to no run |
| declaration | runs while its module is imported, to declare tables and actions |
| tool | the schema generator, run by hand |

Four kinds of function need no listing, because something else times them:

| kind | timed by |
| --- | --- |
| a function defined inside another | the enclosing function |
| a generator | the function that consumes it; decorating one raises `TypeError` at import |
| a method such as `__getitem__` | the caller; `__init__` is timed |
| a dashboard route | the request span, named by method and route |

Call counts behind the `hot` list were measured, not guessed. Offered actions were profiled on 13 stored snapshots, including wartime and late game. The memory reader was profiled on the running game with read-only access. World generation and picker training were each profiled once.

## Waits

Time spent waiting on the game has its own spans, so it no longer appears as unexplained self time.

| span | what it waits for |
| --- | --- |
| `interface.actions.execute.Executor.pace` | the fixed gap before an action may start |
| `interface.actions.execute.Executor.prime` | the fixed 100 ms between writing parameters and firing |
| `interface.actions.execute.Executor.answer` | the game logging the result of the action |
| `interface.actions.execute.Executor.abort` | the game acknowledging an abort |
| `interface.runner.memory.Reader.captured` | the game finishing its capture script |
| `loop.run.Loop.days` | the game running the requested days |
| `loop.run.settle` | the date holding still after a pause |
| `loop.run.running` | the probe that checks whether the game is running |

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
| `timed_often` | DEBUG | no | everything else |
| `db.timed` | INFO | no | the dashboard |

All three record the same measurements. A decorator goes directly above `def`, below `@staticmethod`, `@property` and `@cache`. Below a cache it times only the misses.

## Timing a block

```python
from interface.timing import span

with span('advisors.pickers.CatBoostPicker.fit','loop'):
    model.fit(rows)
```

The second argument is the logger name. A third sets the log level.

## Cached values

`Stored.memo` and the per-run cache in `Shared` open a span only when they compute. The span is named after the function that computes, such as `interface.options.available.state_regions.<locals>.compute`. A cache hit costs no span.

## Cost of a span

A span costs 0.8 microseconds, down from 1.2. The recorder now updates one set of statistics per call and folds it into the run totals when the interval is drained.

One stored snapshot opens about 1500 spans, which is about 1.2 ms. One pause opens about 25000 spans in offered actions, which is about 20 ms.

## Reading a duration in code

A span reports `ms` and `seconds`. While it is open they are the time elapsed so far. After it closes they are its duration.

```python
from interface.timing import current

entry['ms']=round(current().ms)
```

`current()` is the innermost open span. Values stored in the database come from here: `snapshot.read_ms`, `loop_action.ms`, `pick_model.seconds` and `smac_proposal.seconds`.

## Span names

A decorated function is named by its file path under the project root and its qualified name: `interface.recording.store.Store.write`. The name is the same whether the module was imported, run with `-m`, or loaded in a spawned child.

Dashboard requests are named by method and route template: `GET /api/runs/{run_id}/actions`.

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
| p50_ms, p95_ms, p99_ms | from a log-scale histogram, 8 buckets per doubling; at most 9 % above the exact value |

Memory per span is bounded by the histogram, so a process can run indefinitely.

## Work on other threads

| work | thread | the span that waits for it |
| --- | --- | --- |
| world generation | one worker inside `Fresh.take` | `loop.run.Fresh.take` |
| picker training | one worker started by `session` | `loop.run.session` |
| statistics refresh after the first snapshot | eight workers, each an `analyze_batch` span | `interface.recording.store.Store.analyze` |
| table reads for offered actions | eight workers, each read a `Shared.fetch` span | `interface.options.stored.Stored.load` |
| the debug log tail | one thread for the life of the game | none |

A span on a worker thread has no parent, so its time is not subtracted from the span that waits. Spans that overlap in time add up to more than the wall clock.

## Other processes

One recorder per run holds everything. Spans measured in another process are sent to the loop and merged.

| process | how its spans arrive |
| --- | --- |
| heartbeat | sends what it measured every second over a queue; the store merges it before each write |
| world pool worker | returns its spans with the finished world |

## Stored tables

Both tables are in `schema_meta.sql`.

`run_timing (run_id, span, ...)` holds the whole run so far. It is rewritten inside every snapshot transaction and once more when the run ends.

`snapshot_timing (run_id, seq, span, calls, errors, total_ms, self_ms, max_ms)` holds the calls that finished since the previous snapshot was written. The write of snapshot `seq` is still open when its rows are stored, so it appears under `seq + 1`.

Full coverage stores several hundred rows per snapshot where the earlier coverage stored about 44.

Three spans are still open at the final write and are not stored: `loop.run.session`, `loop.run.Loop.run` and the function they call, `Loop.play`, which is listed as a loop.

## Reading it

Dashboard, run page, timing tab: both tables for that run.

Dashboard, schema page, dashboard timing: the dashboard process itself. Same data at `/api/timing`.

```sql
select span, calls, total_ms, self_ms, p95_ms, max_ms
from run_timing where run_id = 270 order by self_ms desc limit 20;

select seq, total_ms / calls as mean_ms, max_ms
from snapshot_timing
where run_id = 270 and span = 'interface.recording.store.Store.write'
order by seq;
```

## Measuring without the game

Three paths can be replayed offline, which is how the speedups in `loop_speed.md` were found and proven.

| path | input |
| --- | --- |
| offered actions | any stored snapshot, read from the database |
| row building | a capture read from the running game with read-only access |
| the snapshot write | the same capture, written to the test database |

## Changing the schema

`Store` refuses to write when the database digest differs from `schema.sql`. A new timing column needs the same change applied to the database and the digest row updated in one transaction, then `schema.sql` regenerated with `interface/recording/emit.py`.
