# Quarterly collection

Collection plays generated mini worlds one run after another, pauses on the first day of every quarter, and records each pause, each drawn block and each executed command in PostgreSQL. Levers, acts and the pickers are described in `advisors.md`, mini worlds in `mini_world_fidelity_report.md`, command execution in `action_verification.md`, the reward in `rewards.md`.

## Current batch

| Setting | Value |
| --- | --- |
| Runs | 697 completed runs |
| Checkpoint | `D:/vic3_data/interface/collection_levers_91.json` |
| World cache | `D:/vic3_data/interface/world_cache_states50_20261004` |
| Initializers | `random`, `random_smac_weighting`, `random_svr_weighting` |
| Pickers | `first`, `catboost`, `catboost_piecewise` |
| Warmup | 10 runs |
| Run limits | 12 minutes of wall clock, 100 game years |

```powershell
.venv/Scripts/python.exe -m loop.launch --world-cache D:/vic3_data/interface/world_cache_states50_20261004 --runs 697 --minutes 12 --years 100 --advisors random random_smac_weighting random_svr_weighting --pickers first catboost catboost_piecewise --warmup 10 --progress-file D:/vic3_data/interface/collection_levers_91.json
```

The batch started on an empty database. Every run draws one sampling weight for each of the 91 levers and stores them in `run_weight`. The checkpoint counts completed runs. Run IDs also count runs that broke off, so they run ahead of it.

Each run draws its initializer and its picker independently and uniformly from the two lists. While the checkpoint is below the warmup count, the run uses `random` and `first` instead. The `first` picker sees one block per pause. A run with a learned picker draws a candidate count from 8 to 50 once and keeps it.

Batch size, lineup, checkpoint resets and deletion of recorded data are the owner's decisions.

## Timeouts

| Limit | Seconds | Where |
| --- | --- | --- |
| Game clock makes no tick after unpausing | 5 | `TICK_LIMIT` in `loop/run.py` |
| Loop reports no progress | 5 | `STALL_LIMIT` in `interface/common.py` |
| Command acknowledgement | 5 | `LIMIT` in `interface/actions/execute.py` |
| Date still moving after a pause | 3 | `SETTLE_LIMIT` in `loop/run.py` |
| Model training, recording preparation and game loading before a run | 180 | `session` in `loop/run.py` |

Changing any timeout needs the owner's direct approval. That holds during autonomous repair and monitoring too.

## Launch and supervision

`python -m loop.launch` hands its arguments to `loop.run.main`. Without `--no-supervisor` that calls `loop.supervise.start`, which refuses when a supervisor, a collector or the game is already running and otherwise starts `python -m loop.supervise` through `interface.runner.session._spawn`, the detached process broker. Collection therefore outlives the terminal and the agent that launched it. `python -m loop.stop` kills the supervisor, the collector and the game, in that order.

The supervisor holds `supervisor.lock` and writes `D:/vic3_data/interface/supervisor.log`. Every ten seconds it looks for a collector, a `python -m loop.run` process.

| Situation | Supervisor |
| --- | --- |
| No collector, checkpoint at or above `--runs` | Writes `COMPLETE` and exits |
| No collector, checkpoint below `--runs` | Clears `D:/vic3_data/interface/worlds`, starts `loop/launch.cmd` as the next `collect_<n>`, waits sixty seconds |
| More than three collectors ended within 600 seconds | Writes `BLOCKED` and exits without relaunching |

A collector writes `D:/vic3_data/interface/collect_<n>.log` and plays runs until the checkpoint reaches `--runs`. It reads the checkpoint once at its start. After each completed run it closes the game and replaces the checkpoint file through a temporary file. A run that breaks off does not advance the checkpoint. A game crash is retried inside the collector, and the third crash in a row ends it. Any other error ends the collector and the supervisor starts the next one. `Store.begin_run` marks a run that was left open as `loop_lost`.

Arguments and code are fixed for the life of a collector. A change takes effect when the next collector starts with the same checkpoint and the same `--runs`.

The collector's watchdog thread checks every 0.1 seconds. When the supervisor is gone or the loop has reported no progress for five seconds, it marks the run `loop_stalled`, closes the game and exits with code 3.

## A run

`session` draws a world from the cache uniformly with replacement, rechecks it, and plays a country drawn uniformly from the world's manifest. Model training, recording preparation and game loading run side by side. The opening building and relationship checks must pass before the run begins.

`Loop.play` pauses the game, takes the `start` snapshot and then repeats two steps: `turn_actions` executes one block, and `advance_quarter` runs the clock to the next quarter. Before each turn it ends the run when a limit is reached.

| End reason | Condition |
| --- | --- |
| `time` | The wall-clock limit has passed |
| `years` | The game-year limit has passed since the first snapshot |
| `debt_cap` | `principal` in `player_treasury` is positive and at least `credit` |
| `defeated` | The played country owns no state |
| `ui_stuck` | Two snapshots in a row show a panel, interaction, map list or window open |
| `game_crashed`, `loop_crashed`, `loop_stalled`, `loop_lost` | The game or the collector failed |

The wall-clock limit is checked between turns, so a run can exceed it by one turn.

## Quarterly decisions

The control mod's monthly pulse fires the pause in months 0, 3, 6 and 9, so the game pauses on January 1, April 1, July 1 and October 1. The calendar has 365 days and the quarters last 90, 91, 92 and 92 days.

`advance_quarter` sets the fastest speed on the first turn and unpauses on every turn. Both commands are recorded under the advisor `loop` and carry no act. Time advancement is never a candidate, a block member or a model feature. The loop then polls the game date every 20 ms until it reaches the next quarter, waits until the date has stood still for a quarter of a second, and takes the `post_run` snapshot. A pause that does not fall on the first day of the target quarter raises. Each quarter logs its longest gap between ticks.

When the date stops for five seconds the loop checks that the game process is alive and raises `ClockStalled`. `loop/diagnostics.py` then saves the last megabyte of the debug store, the session file and the game's debug, error and game logs to a zip under `D:/vic3_data/interface/incidents`.

A block holds at most sixteen acts. Waiting events and proposals are answered first and count toward the cap. The target size is drawn from six to sixteen with weights that fall as the size grows. Conflicts between commands, a command that ends the pause and a shortage of choices can shorten a block. The draw itself is described in `advisors.md`.

The game keeps a pact it has just ended in memory until the next month begins, so the snapshot taken straight after a block can still list a pact that block ended. Decisions are drawn from the snapshot at the end of the quarter, which no longer lists it.

## Cached worlds

`D:/vic3_data/interface/world_cache_states50_20261004` holds 1000 worlds built with seed 2026100450. They have 20 to 50 states, with a median of 36, and 2 to 10 countries, with a median of 5.

```powershell
.venv/Scripts/python.exe -m interface.world.cache status --directory D:/vic3_data/interface/world_cache_states50_20261004
.venv/Scripts/python.exe -m interface.world.cache build --directory D:/vic3_data/interface/world_cache_states50_20261004 --count 1000 --workers 12 --seed 2026100450
```

A cache is bound to the generator sources under `interface/world`, to `interface/script.py` and to the game binary by its fingerprint; a change to any of them makes `loop.run` refuse the cache. The earlier caches `world_cache_politics_20260930`, `world_cache_levers_20261004` and `world_cache_levers_20261004b` were built for 20 to 100 states and no longer match the generator.

`--world-cache` cannot be combined with world sliders, `--tag`, `--pool` or `--vanilla`.

## Checking a launch

- `loop.watch.roles` lists the supervisor, the round's `launch.cmd`, the collector and the game.
- `supervisor.log` shows `SUPERVISOR STARTED` and `LAUNCHED collect_<n>` with the arguments.
- The open row in `run` has a fresh `heartbeat_at`, and its snapshots and game dates advance.
- `run_weight` holds 91 rows for the run, one per lever in `advisors.catalogue.NAMES`.
- `loop_action.advisor_action` names acts from `advisors.catalogue.ACTIONS`, with their parameters in `loop_decision_param`.
- The collector's log holds a `quarterly pause` line for every quarter.

Keep test invocations below twenty seconds.
