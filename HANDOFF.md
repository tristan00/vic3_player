# Handoff, 2026-09-24 early morning

## Blocked on the user
Nothing. The schema decisions below are the user's call; the schema stays as it is until decided.

## What changed since the previous handoff
1. **Strait rows B10, B11, B12 are covered.** Three actions: `set_strait_toll` (strait, level NoTolls/LowTolls/MediumTolls/HighTolls), `set_strait_access` (strait, state, Open/NoMilitary/Closed) and `set_strait_allowed` (strait, state, NoEnemies/OnlyAllies/OnlyController). The Strait scope code is 80. The strait memory struct now yields `first_access_status`, `first_access_permissions`, `second_access_status`, `second_access_permissions` (bytes 168 to 171), `first_last_toll_rate_change` and `second_last_toll_rate_change` (dates at 176 and 184) next to the toll rates and access change dates already mapped; enum labels include `high_tolls`, `open/no_military/closed` and `all/no_enemies/only_allies/only_controller`. `common/strait_definitions` is parsed for the full-control requirements. Rules measured live as the Ottomans: a controller of both shores sets everything on the first side whichever state is passed; a setting can be changed again exactly 6 months after its change date (7-day grace allows only a revert to the previous value, which memory does not hold, so nothing is offered during the grace week); permissions have no cooldown but are refused while the side's status is Open; Gibraltar needs both shores for tolls and for closing. Verified live: toll and status changes recorded and `verify()` true.
2. **Bug fixed:** `player_policy.can_toll_straits` and `can_close_straits` were always false (the builder compared against `can_toll` while the capture writes `toll` and `close`).
3. **Row N19 is covered:** `design_ship_template` (ship_type, ship_modification) opens the ship designer, selects the type, selects the modification in its slot and creates a template. Offer rule: available ship types, non-utility slots from the type's `modifications` block, modifications whose unlocking technology is acquired and that are absent from the latest version of every own template of that type. Verifier: one more own `ship_template` row. Verified live twice as Britain.
4. **Generator convention found and enforced.** An action whose command returns a `Command` must not declare `valid`: the generator then wraps the command in `Execute()` and reports `IsValid()`. An action whose command is a void callback must declare `valid`. With `valid` set, a `Command` was emitted as a bare callback and silently did nothing; `add_war_goal` had that bug (fixed by dropping its `valid`), and `quick_decline_proposal` had the reverse (void without `valid`, fixed with `Proposal.GetActor.IsValid`). `tests/test_actions.py` now resolves every command's return type through the game's data-type dump and fails on either mismatch.
5. Commits: 88d8044 (straits), b9e47aa (designer and convention).

## State right now
- `master` at b9e47aa, working tree clean apart from files of the other session (see below). Unit suite: 192 tests in about 12 s.
- The `vic3` schema was reinstalled at about 22:50 for the strait columns; every run before that is gone. Verification counts start from the runs after it.
- Round `mini_r28` launched at 23:20 under the watcher (Monitor). Rotation: `vanilla_r27` completed at 22:32 (2 runs, ended by time); no mini round has completed since, so the next four rounds are mini, then vanilla.
- A second Claude session (`vic3-agent-23`) works in this repository. It launched and killed a round named `dash_seed` (22:50 to 22:58, deleted its run) and agreed to launch no rounds; it reverted its `geography.py` edit and removed `dashboard/`. Commit only your own files.
- The schema design for replacing `game_definition` is written out in the scratchpad of session 6f1e0bb0 as `definition_design.md` (one typed table per definition folder, child tables for lists, text triggers, typed modifier rows, 63 tables). It awaits the user's decision.

## Rules the user set
- A dead, stalled or killed run is flagged by the round itself, and the agent is told at once by the watcher. Nobody watches by hand, and a 20-minute reminder is never the way a failure is found. Anything slower than the limits in `loop/instruction.txt` is a critical bug.
- Verification is decided only by `verify()` in `loop/effects.py` at runtime and aggregated only by the database views. No counting from journals, logs or by hand, ever.
- A verifier must require the before state to differ from the after state.

## Schema review findings still open
1. `game_definition` is an entity-attribute-value table of script fields. Design for the replacement: `definition_design.md` in the scratchpad named above.
2. `loop_action_param` is name plus typed value. Alternative: typed parameter columns on `loop_action` with foreign keys to the anchors and vocabularies acted on.
3. `world_asset` stores the map files as bytea (94 MB per vanilla world). Alternative: files on disk under the world digest, a digest per file in the table.
4. Enum tables accept codes without labels (`Store.codes`). Alternative: labels required, unknown codes refused; needs label sources for building_owner_type, event_status, formation_flag, law_phase, privatization_request, slave_basket, treaty_side, war_goal_pressed, wage_level.
5. Polymorphic references without foreign keys: `journal_entry_target` and `event_target`, `building_ownership_history`, `war_goal_history.target_other`, `formation_status.current_location` and `target_location`, `battle_history.invasion`. Alternative: one typed nullable column per target kind with a check that exactly one is set.
6. Smaller: `player_message` and `player_construction_queue_item` keyed by position churn on every shift; `float8` for the game's fixed-point values; `state_pop_need.need` has no vocabulary; the four secondary indexes could be partial on `present`.

## Open questions in the data
- Strait bytes 174 and 175 change over a campaign without any setting change and are not the previous toll rates; unmapped. The save file's `first_previous_toll_rate` and `first_previous_access_status` are not in the 208-byte strait struct.
- `game_state.speed` is enforced as a run constant and was 4 in every run; whether it is the live speed or a setting is unknown.
- `run.longest_step_ms` per run shows how close legitimate steps come to the 5 s stall limit; a step near it gets stamps inside it, the limit does not move.

## Catalogue rows still missing
N3 mission sea regions (`Province.AddSeaRegionToSelectedFleetMissions` with selected fleets); N5 invasion planner (`PopupManager.ShowInvasionPlannerPopup`); N7 fleet retrofit (`MilitaryFormation.RetrofitShips`, `CancelRetrofitShips`) and N8 country-wide (`RetrofitShips`, `CancelRetrofitShips` global), both need ships behind their template's latest version, which `design_ship_template` now produces; N10 bulk ship actions (`ShipSelection.*`); N11 flagship (`Ship.AssignAsFlagship`, `UnassignAsFlagship`, `ToggleFlagshipSignalFlags`, ornaments; no flagship field in the snapshot yet); N18 templates (`ShipTemplate.SetAsDefaultForCountry`, `SetAsDefaultForFleet(fleet)`, `DeleteTemplate`; the scope code for ShipTemplate is not known, likely 72 or 73); W5 treaty-article war goals; W13 sway offers (`DiplomaticPlay.CreateSway` through `SwayCountryPanel`); T1 treaties; PB8 bloc customization (`PopupManager.ShowPowerBlocCustomizationPopup`); X8 support a formation candidate (`CountryFormation.SupportCandidate`); X9 unification play (`CountryFormation.ShowUnificationPlayConfirmation`).

## Useful scratchpad scripts
Folder: `C:\Users\trist\AppData\Local\Temp\claude\D--vic3-agent\6f1e0bb0-aeda-4860-8fdf-391b4b1ab051\scratchpad`
- `strait_experiment.py`, `strait_cooldown.py`: detached Ottoman campaigns that set strait settings through the GUI and diff the strait struct bytes; the second one runs six game months and probes validity across the grace and cooldown windows.
- `strait_live.py`, `designer_live.py`: detached campaigns that record a snapshot, print the offers of the new actions, check and run them, record again and print `verify()`.
- `designer_probe2.py`: drives the ship designer from a hand-written control widget, the reference for what the generated widgets must reproduce.
- `definition_design.md`: the schema design for replacing `game_definition`.
Previous sessions' folders `...\4ec588be-8fa9-49ae-9ac8-84c83601e0e5\scratchpad` (`stall_drill.py`, `measure_checks.py`) and `...\3b26cb9e-043f-4cdf-bad5-5886126b3e4e\scratchpad` (`inspect_*.py`, `formation_probe*.py`, `war_probe.py`).
