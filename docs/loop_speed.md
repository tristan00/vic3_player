# Quarterly collection

## Approved configuration

The batch uses `D:/vic3_data/interface/collection_d9690b4774954f66aa474465795a1325.json` and ends at 697 completed rounds. The October 3 extension added 500 rounds to the 197 already completed. The checkpoint counts completed rounds; database run IDs also include failed attempts.

Each round independently draws uniformly from three initializers (`random`, `random_smac_weighting`, `random_svr_weighting`) and three pickers (`first`, `catboost`, `catboost_piecewise`). There is no additional warmup. Learned methods use the shared three-metric reward in `rewards.md`. Initializer baselines are the run opening; picker baselines are the pause's first snapshot. A selected learned picker fits a fresh estimator.

```powershell
.venv/Scripts/python.exe -m loop.launch --world-cache D:/vic3_data/interface/world_cache_politics_20260930 --runs 697 --minutes 12 --years 100 --advisors random random_smac_weighting random_svr_weighting --pickers first catboost catboost_piecewise --progress-file D:/vic3_data/interface/collection_d9690b4774954f66aa474465795a1325.json
```

Rounds are limited to twelve minutes and one hundred game years. A checkpoint of 697 is normal completion. Preserve collected data and completed progress. Batch size, lineup, checkpoint resets, and deletion require the applicable user instruction. Superseded launch artifacts do not override this configuration.

## Timeouts and the latest restart

The game-clock tick limit and execution watchdog are both five seconds. Changing any timeout requires direct user approval, including during autonomous repair or monitoring.

An hourly monitor previously increased the tick limit to thirty seconds without approval. The user stopped that collection and requested deletion of its runs. The database deletion utility removed the three affected runs and dependent records, restoring the checkpoint from 313 to 311. Filesystem cleanup was blocked, so old logs and saves may remain. Those files are not valid training records or evidence of the active batch.

On October 3 at approximately 21:08 Pacific, the user explicitly approved restoring five seconds and restarting. `TICK_LIMIT` was restored to five, twelve focused checks passed in 0.085 seconds, and the detached supervisor relaunched from checkpoint 311. Subsequent run IDs may reuse the deleted tail IDs; identify historical runs by start time as well as ID.

After unpausing, the loop reads native game time and reports progress until the next quarter. More than five seconds without a tick triggers a process-liveness check and `ClockStalled`. Defeat and target-date checks remain active. Clock failures preserve native log tails and session identity under `D:/vic3_data/interface/incidents`. Quarter-completion logs report the longest tick gap. Ordinary action pauses differ from mid-quarter clock stalls.

CPU saturation was observed during the earlier recovery, but its relationship to the historical stalls remains unproven. The old thirty-second recovery report does not establish a resolved cause.

## Startup and supervision

The initializer-only transition began at run 213. The full lineup began after run 284 and checkpoint 276. Its original transition evidence is under `artifacts/full_mix_20261003`.

The first piecewise startup exposed a watchdog stall while training-data conversion overlapped opening-world checks. Startup runs model training, recording preparation, and game readiness concurrently. The main thread reports preparation progress while waiting; all three operations must finish within the existing 180-second preparation bound. The latest restart did not alter that bound.

The startup-fix reload under `artifacts/picker_startup_20261003` completed after run 285 and checkpoint 277. Run 286 selected `random_smac_weighting` and `catboost_piecewise`; advancing snapshots verified that transition.

Arguments and loaded code remain fixed during a loop process. Changes take effect after a restart using the same checkpoint and cumulative target. The checkpoint is written after the game closes and before the next run opens. Launch uses the project's detached process broker, so collection survives the invoking terminal.

Only one collection may run at once. The supervisor restarts failed collectors and stops after repeated rapid exits. Completed rounds update the checkpoint atomically. Crashes remain recorded and do not increment it. The next run marks an abandoned open run as lost.

The hourly automation `keep-victoria-3-collection-running` is paused after the user's stop instruction. Restarting the detached collection supervisor does not re-enable that automation. Any future monitoring must preserve the approved configuration and obtain direct approval before changing timeouts.

Verify a restart using process identities, database heartbeat, snapshots, and advancing game dates. Keep test invocations below twenty seconds. `python -m loop.stop` stops the supervisor, collector, and game. Explicit stop instructions take precedence over recovery behavior.

## Quarterly decisions

The game pauses on January 1, April 1, July 1, and October 1. Decision blocks contain at most sixteen actions, including event and proposal answers. The sampled target ranges from six to sixteen and favors smaller blocks. Conflicts and pause-ending actions can shorten a block. Pending answers take priority and count toward the cap.

Time advancement is infrastructure, never a selectable candidate or action-block feature, and creates no synthetic action row. Speed and unpause commands remain recorded under the loop advisor. The calendar has 365 days; quarters span 90, 91, 92, and 92 days.

A monthly pulse restricted to quarter-start months triggers the native pause handler. The loop waits for the quarter, lets the clock settle, and captures the observation. A pause outside the first day raises an error. Cadence evidence is in `artifacts/quarterly_cadence/probe_result.json` and the optimization probes.

`--advisors` and `--pickers` define available methods. `--warmup N` forces random initialization and the first candidate while fewer than N rounds are complete; the current launch does not request warmup.

## Cached worlds

`D:/vic3_data/interface/world_cache_politics_20260930` contains the completed politics and culture cache. Collection samples worlds uniformly with replacement, chooses a playable country, and starts from original generated files. Opening buildings and relationships are checked after loading.

```powershell
.venv/Scripts/python.exe -m interface.world.cache status --directory D:/vic3_data/interface/world_cache_politics_20260930
.venv/Scripts/python.exe -m interface.world.cache build --directory D:/vic3_data/interface/world_cache_politics_20260930 --count 1000 --workers 12 --seed 2026093001
```

Cache construction uses the detached broker, an exclusive lock, and independent workers. Resume reuses audited worlds. Changing the seed, generator fingerprint, or executable requires a new cache. Manifests contain absolute paths. Collection requires at least one thousand complete, compatible, distinct manifests. Missing or incompatible inputs raise an error. Cache mode cannot combine with sliders, a fixed tag, vanilla mode, or a generation pool. The cache survives temporary-world cleanup.

## Performance

The game retains its 120 FPS cap. Controlled comparisons found no simulation-speed gain from 240 FPS on the same fifteen-country, ninety-five-state world. Repeated 120 FPS baselines measured approximately 13.1 to 13.2 game days per second; world size and competing workload affect throughput.

Execution retains its 100 ms prime interval and native completion checks, with the former inter-action gap and minimum cycle removed. Key callbacks reset so identical consecutive commands can complete. See `action_verification.md`.

Inactive action widgets are hidden. Training, recording preparation, and game readiness overlap during loading. Cached inputs remove generation from transitions. Defeat checks read owned-state counts; each simulation poll reads one date. Background log polling uses fifty milliseconds, with more frequent foreground acknowledgement polling.

Optimization measurements are under `artifacts/loop_optimization`: `collection_baseline.json`, `results.json`, `candidate120.json`, and `report.json`. Native acknowledgement latency differs from complete snapshot capture and database writing. Concurrent and nested spans must not be summed as independent elapsed time. See `timing.md`.
