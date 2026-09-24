# Handoff, 2026-09-23 night

## Blocked on the user
Nothing. Four schema decisions are open (see the review section); until decided, the schema stays as it is.

## What happened tonight and what changed
The previous session ended with the user finding a frozen round by eye: its first vanilla snapshot spent nine minutes in the foreign-key checks, the heartbeat thread kept beating the whole time, no run row existed yet, and the agent's only check was a 20-minute reminder. Three separate faults, all fixed and measured:

1. **Stalls are now a detected failure.** The main thread stamps progress everywhere it works or waits (`interface.common.progress`, automatically on every `@timed` function and inside every poll loop). A `Watchdog` thread in `loop/run.py` runs from process start; when the stamp is older than `STALL_LIMIT` (5 s) it logs `LOOP STALLED`, writes `end_reason = 'loop_stalled'` with the step and duration, closes the game and exits with code 3. The run row carries `progress_at`, `progress_step`, `longest_step`, `longest_step_ms`; the view `run_stalled` lists stale runs. Measured live with the `snapshot` table locked under a running round: flagged 5.1 s after the lock, process gone 3 s later, watcher report 9 s after the lock.
2. **Every round is watched from the moment it starts.** `python -m loop.launch <name> <args>` refuses if a loop or game is still running, spawns the round detached through WMI, and runs `loop/watch.py` on it: run opened and ended events with reasons and details, stalled and lost runs, every `Traceback`, `CRITICAL`, `CRASHED`, `REFUSED` log line, a vanished loop process, a game that outlived its round (killed), and the exit line. The agent runs it under the Monitor tool, so every event arrives without polling. The instruction no longer says "do not start background watchers"; it says the opposite.
3. **The nine-minute snapshot is fixed at the cause.** The check queries run against rows inserted in the same transaction, which have no statistics; the planner assumed one row and chose nested loops over a materialized list, 57,000 by 57,000 rows per check. `set local enable_nestloop = off` for the write transaction: all checks on fresh rows take 0.3 s in total.

Also: the heartbeat is refreshed as the last statement of the first snapshot's transaction, so a run is never listed as lost between its commit and the first beat; `launch.cmd` no longer wraps the loop in `timeout.exe` (killing the wrapper lost the exit line; the watchdog and the loop's own budget bound the round).

Commits: c47b1a3, 97b25e6, baf156e, 7f9df51.

## State right now
- `master` at the latest commit. Unit suite: 187 tests in about 12 s (`.venv/Scripts/python -m unittest discover -s tests -q`). The suite reinstalls `vic3_test` itself. The installed `vic3` schema matches `schema.sql`; it was reinstalled tonight and holds only runs since 22:11.
- Round `vanilla_r27` launched at 22:11 under the watcher. Rotation: `vanilla_r21` completed; `mini_r22` to `mini_r26` completed; `vanilla_r27` is the current vanilla round (its earlier attempts were killed and do not count).
- Verification, from the database views only (`python -m loop.report`): the database was reinstalled tonight, so the views start again from the runs of `vanilla_r27` onward.
- Nothing from before 2026-09-23 16:46 counts. The 25 earlier journals are in `D:\vic3_data\interface\loop_before_session` and nothing reads them.

## Rules the user set
- A dead, stalled or killed run is flagged by the round itself, and the agent is told at once by the watcher. Nobody watches by hand, and a 20-minute reminder is never the way a failure is found. Anything slower than the limits in `loop/instruction.txt` is a critical bug.
- Verification is decided only by `verify()` in `loop/effects.py` at runtime and aggregated only by the database views. No counting from journals, logs or by hand, ever.
- A verifier must require the before state to differ from the after state.

## Schema review findings still open
The adversarial review found these; each alternative costs real work and is the user's call:
1. `game_definition` is an entity-attribute-value table of script fields. Alternative: one typed table per definition folder (about forty) and a rewrite of `Stored.definitions` and the readers in `interface/options`.
2. `loop_action_param` is name plus typed value. Alternative: typed parameter columns on `loop_action` (or a child table per action) with foreign keys to the anchors and vocabularies acted on.
3. `world_asset` stores the map files as bytea (94 MB per vanilla world). Alternative: files on disk under the world digest, a digest per file in the table.
4. Enum tables accept codes without labels (`Store.codes`). Alternative: labels required, unknown codes refused; needs label sources for building_owner_type, event_status, formation_flag, law_phase, privatization_request, slave_basket, treaty_side, war_goal_pressed, wage_level.
5. Polymorphic references without foreign keys: `journal_entry_target` and `event_target` (scope_type + scope_target), `building_ownership_history` (owner_type + owner), `war_goal_history.target_other`, `formation_status.current_location` and `target_location`, `battle_history.invasion`. Alternative: one typed nullable column per target kind with a check that exactly one is set.
6. Smaller: `player_message` and `player_construction_queue_item` keyed by position churn on every shift; `float8` for the game's fixed-point values; `state_pop_need.need` has no vocabulary; the four secondary indexes could be partial on `present`.

## Open questions in the data
- `game_state.speed` is enforced as a run constant and was 4 in every run; whether it is the live speed or a setting is unknown. If the game ever starts at another speed, the second snapshot will be refused as a constant change.
- `run.longest_step_ms` per run shows how close legitimate steps come to the 5 s stall limit; a step near it gets stamps inside it, the limit does not move.

## Catalogue rows still missing
B10–B12 straits; N3 mission sea regions; N5 invasion planner; N7, N8, N11, N18, N19 (Great Wave navy work; untested code was on the old branch `great-wave-wip`, which is not in this repository's history); N10 bulk ship actions; W5 treaty war goals; W13 sway offers; T1 treaties; PB8 bloc customization; X8, X9 formation candidacy and unification plays.

## Useful scratchpad scripts
Folder: `C:\Users\trist\AppData\Local\Temp\claude\D--vic3-agent\4ec588be-8fa9-49ae-9ac8-84c83601e0e5\scratchpad`
- `stall_drill.py`: waits for a running round's third snapshot, locks the `snapshot` table for 40 s and prints when the run is flagged. Kills the round; relaunch afterwards.
- `measure_checks.py`: copies a run's first snapshot rows into a new run inside a transaction and times every foreign-key check with nested loops off and on.
Previous session's folder `...\3b26cb9e-043f-4cdf-bad5-5886126b3e4e\scratchpad`: `inspect_refusal.py`, `inspect_samples.py`, `inspect_ring.py`, `inspect_templates.py`, `formation_probe*.py`, `war_probe.py`.
