# Handoff, 2026-09-23 evening

## Blocked on the user
Nothing. Four schema decisions are open (see the review section); until decided, the schema stays as it is.

## State right now
- `master` at the latest commit. Unit suite: 181 tests in about 12 s (`.venv/Scripts/python -m unittest discover -s tests -q`). The suite reinstalls `vic3_test` itself.
- The vanilla rotation round `vanilla_r21` was launched at 18:34 (third attempt; the first two were refused captures, both fixed). Its log is `D:\vic3_data\interface\vanilla_r21.log`; it ends with `ROUND EXITED code=N`.
- **The working tree's `schema.sql` is newer than the schema installed in `vic3`.** The round runs on the installed schema. After the round ends, reinstall (`store.install`) before launching anything; `Store` refuses a digest mismatch. Reinstalling deletes the stored runs, which is allowed.
- Rotation: `vanilla_r21` is the pending vanilla round. If it completed (exit code 0 and a counts line), the next five rounds are mini (`mini_r22` onward); if not, relaunch it as `vanilla_r21`.
- Coverage: 95 of 176 actions verified (`.venv/Scripts/python -m loop.report`). Today's rounds: 782 verified of 819 action entries.

## Detection of dead runs (the user's rule: flagged within one second, or it is a critical bug)
Everything is measured and stored, not promised. See DATABASE.md, section "Run liveness".
- Game process gone: a watcher thread probes the process handle and one readable word of the executable every 50 ms. Measured: noticed 33 ms after the OS exit stamp, run row flagged 156 ms after it. The round then continues with a fresh session; three crashes in a row stop it.
- Loop process killed: heartbeat every 100 ms; `run_lost` lists the run after 500 ms of silence with the last heartbeat as the stop time; the next loop start closes it as `loop_lost`. The launcher `loop/launch.cmd` appends `ROUND EXITED code=N` to the round log whatever happened.
- Loop exception: the run ends as `loop_crashed` with `end_detail`, and a refused capture is dumped whole to `D:\vic3_data\interface\refusals\<time>.pkl` first.
- Defeat: `dead()` confirms over three reads spaced 200 ms.
- Still bounded by 5 s, not 1 s: a game that is alive but frozen (date stall, action timeout). Each `run_days` journal entry now records the longest tick gap so the stall limit can be set from data.
- `run_late_flag` must stay empty; a `CRITICAL` or `LATE FLAG` log line is a critical bug.

## What changed today, in order
1. Liveness: `GameCrashed`, `Process` handle with `exited`, `readable`, `exit_time`, `watch`; executor and session loops check it; `Loop.run` routes every exit through `end()`; heartbeat thread; `run_lost`, `run_late_flag`; launcher script; `loop` logger at INFO with one line per action.
2. Dead flags stored for buildings, formations and wars. Script-side formation columns moved to `formation_report`; `formation_private` keeps the memory columns. Builders refuse a capture where script and memory disagree on the live set.
3. Script captures name objects by slot; `Context.ident` converts every such slot to the memory identity, refusing slots memory lacks.
4. Every memory handle is stored as the identity it names and anchored on first sight (`referenced_only` lists identities never captured). Provinces stay strict. The game holds stale handles (general to disbanded formation, cultural community to removed state, war goal to vanished play) and forward handles (front sides carry the identity of the war a play will start).
5. One sample table per trend buffer; rings of the same object differ in capacity.
6. Regional company headquarters buildings (`building_regional_<company type>`) added to the generated building names.
7. Review-driven: `_at` functions walk the anchor table with one probe per identity; `run.end_reason` is a closed list with `end_detail`; `name_column` dropped (`Stored` reads vocabulary columns from the foreign keys); `tag`, `world_file`, `cli_seed` moved to `run_generated`.

## Schema review findings still open
The review (adversarial, against the user's standard) found these; each alternative costs real work and is the user's call:
1. `game_definition` is an entity-attribute-value table of script fields. Alternative: one typed table per definition folder (about forty) and a rewrite of `Stored.definitions` and the readers in `interface/options`.
2. `loop_action_param` is name plus typed value. Alternative: typed parameter columns on `loop_action` (or a child table per action) with foreign keys to the anchors and vocabularies acted on.
3. `world_asset` stores the map files as bytea (94 MB per vanilla world). Alternative: files on disk under the world digest, a digest per file in the table.
4. Enum tables accept codes without labels (`Store.codes`). Alternative: labels required, unknown codes refused; needs label sources for the enums the memory layout does not name (building_owner_type, event_status, formation_flag, law_phase, privatization_request, slave_basket, treaty_side, war_goal_pressed, wage_level).
5. Polymorphic references without foreign keys: `journal_entry_target` and `event_target` (scope_type + scope_target), `building_ownership_history` (owner_type + owner), `war_goal_history.target_other`, `formation_status.current_location` and `target_location`, `battle_history.invasion`. Alternative: one typed nullable column per target kind with a check that exactly one is set.
6. Smaller: `player_message` and `player_construction_queue_item` keyed by position churn on every shift; `float8` for the game's fixed-point values; `state_pop_need.need` has no vocabulary; the four secondary indexes could be partial on `present`.

## Catalogue rows still missing
B10–B12 straits; N3 mission sea regions; N5 invasion planner; N7, N8, N11, N18, N19 (Great Wave navy work; untested code was on the old branch `great-wave-wip`, which is not in this repository's history); N10 bulk ship actions; W5 treaty war goals; W13 sway offers; T1 treaties; PB8 bloc customization; X8, X9 formation candidacy and unification plays.

## Useful scratchpad scripts
Folder: `C:\Users\trist\AppData\Local\Temp\claude\D--vic3-agent\3b26cb9e-043f-4cdf-bad5-5886126b3e4e\scratchpad`
- `inspect_refusal.py [dump]`: for a refused capture, whether the named slot exists in memory, which columns and script lists hold it.
- `inspect_samples.py`, `inspect_ring.py`: trend buffer contents and ring-order check.
- `formation_probe.py`, `formation_probe2.py`, `formation_probe3.py`, `war_probe.py`: live probes on the `development` profile (mini world generated on the spot, or vanilla GBR) that run one action and print memory versus script state; launch detached via WMI, they delete their run afterwards.
