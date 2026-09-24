# Handoff, 2026-09-23 evening

## Blocked on the user
Nothing. Four schema decisions are open (see the review section); until decided, the schema stays as it is.

## State right now
- `master` at the latest commit. Unit suite: 182 tests in about 12 s (`.venv/Scripts/python -m unittest discover -s tests -q`). The suite reinstalls `vic3_test` itself. The installed `vic3` schema matches `schema.sql`.
- Round `mini_r22` was launched at 19:24 (20 minutes). Log: `D:\vic3_data\interface\mini_r22.log`, which ends with `ROUND EXITED code=N` when the process is gone. Rotation: `vanilla_r21` completed (exit 0); `mini_r22` to `mini_r26` are the next five, then `vanilla_r27`.
- Verification, from the database views only (`python -m loop.report`), after the one completed run: 0 of 176 actions verified by the standard, 77 attempted, 99 never attempted, 45 attempted actions have 3 or more verified attempts on that one world and need a second world. Attempt rows: verified 314, invalid 7, unverified 3, no effect 2.
- Nothing from before this session (16:46) counts. The 25 earlier journals are in `D:\vic3_data\interface\loop_before_session` and nothing reads them; the database was reinstalled several times today and holds only runs since the last reinstall.

## Rules the user set today
- A dead run is flagged within one second or it is a critical bug. Measured: game exit noticed by the watcher 33 ms after the OS stamp, run row flagged 156 ms after it; a killed loop listed in `run_lost` within 1.1 s (now 0.6 s with the 100 ms heartbeat and 500 ms threshold).
- Verification is decided only by `verify()` in `loop/effects.py` at runtime and aggregated only by the database views. No counting from journals, logs or by hand, ever.
- A verifier must require the before state to differ from the after state. Two GUI re-check verifiers, a commander hire that passed with no data, and about thirty after-state-only checks were replaced today. `set_speed` has no snapshot evidence and stays unverified; the game reports speed 0 while paused and `game_state.speed` is a run constant.

## What changed today, in order
1. Liveness: `GameCrashed`, `Process` handle with `exited`, `readable`, `exit_time`, `watch`; executor and session loops check it; `Loop.run` routes every exit through `end()`; heartbeat thread; `run_lost`, `run_late_flag`; launcher `loop/launch.cmd`; the `loop` logger at INFO with one line per action; refused captures dumped to `D:\vic3_data\interface\refusals`.
2. Dead flags stored for buildings, formations and wars. Script-side formation columns moved to `formation_report`; `formation_private` keeps the memory columns. Builders refuse a capture where script and memory disagree on the live set.
3. Script captures name objects by slot; `Context.ident` converts every such slot to the memory identity, refusing slots memory lacks.
4. Every memory handle is stored as the identity it names and anchored on first sight (`referenced_only` lists identities never captured). Provinces stay strict.
5. One sample table per trend buffer; rings of the same object differ in capacity.
6. Regional company headquarters buildings (`building_regional_<company type>`), ship template version lists as a child table (`ship_template_version_list`; orphan versions exist), messages without a group (`message_group` nullable).
7. Review-driven: `_at` functions walk the anchor table with one probe per identity; `run.end_reason` is a closed list with `end_detail`; `name_column` dropped (`Stored` reads vocabulary columns from the foreign keys); `tag`, `world_file`, `cli_seed` moved to `run_generated`; the writer's connection uses no prepared statements (generic plans made the foreign-key checks scan whole tables).
8. Verification views `action_run_outcome`, `action_verification`, `verification_summary` over `loop_action`, bounded by `catalogue_action`; `loop.report` reads only them.

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
- A hung-but-alive game is detected by the 5 s stall limits; each `run_days` journal entry records the longest tick gap to decide whether 1 s is feasible.

## Catalogue rows still missing
B10–B12 straits; N3 mission sea regions; N5 invasion planner; N7, N8, N11, N18, N19 (Great Wave navy work; untested code was on the old branch `great-wave-wip`, which is not in this repository's history); N10 bulk ship actions; W5 treaty war goals; W13 sway offers; T1 treaties; PB8 bloc customization; X8, X9 formation candidacy and unification plays.

## Useful scratchpad scripts
Folder: `C:\Users\trist\AppData\Local\Temp\claude\D--vic3-agent\3b26cb9e-043f-4cdf-bad5-5886126b3e4e\scratchpad`
- `inspect_refusal.py [dump]`: for a refused capture, whether the named slot exists in memory, which columns and script lists hold it.
- `inspect_samples.py`, `inspect_ring.py`, `inspect_templates.py`: trend buffers, ring-order check, ship template version lists.
- `formation_probe*.py`, `war_probe.py`: live probes on the `development` profile that run one action and print memory versus script state; launch detached via WMI, they delete their run afterwards.
