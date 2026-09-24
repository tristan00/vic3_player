# Handoff, 2026-09-24 early morning

## Blocked on the user
Nothing. The schema decisions below are the user's call; the schema stays as it is until decided.

## Rules the user set tonight
- Live tests run on mini worlds. Mini worlds must be representative; where they are not, the generator is fixed rather than the test moved to vanilla. A vanilla live test is allowed only when the feature truly cannot be ported to mini worlds.
- Earlier rules still stand: a dead, stalled or killed run is flagged by the round itself and the watcher tells the agent at once; verification is decided only by `verify()` at runtime and aggregated only by the database views; a verifier must require the before state to differ from the after state.

## What changed since the previous handoff
1. **Strait rows B10, B11, B12 covered**: `set_strait_toll`, `set_strait_access`, `set_strait_allowed`. Strait scope code 80. The strait struct yields access status and permissions per side (bytes 168 to 171) and the toll change dates (176, 184); enum labels added. Rules measured live: a controller of both shores sets everything on the first side; a setting can be changed again exactly 6 months after its change date, the 7-day grace allows only a revert (not offered, memory does not hold the previous value); permissions have no cooldown but are refused while the status is Open; Gibraltar needs both shores. Bug fixed on the way: `player_policy.can_toll_straits` and `can_close_straits` were always false.
2. **Row N19 covered**: `design_ship_template` (ship_type, ship_modification) and `edit_ship_template` (ship_type, index, ship_modification). Editing is refused for base templates, so the edit rule offers only custom templates, addressed by their index among the country's templates of that type ordered by ordinal number (the game's `ShipTemplateList.GetTemplatesOfType` order, confirmed live).
3. **Rows N7, N8 covered**: `retrofit_fleet`, `cancel_retrofit_fleet`, `retrofit_all`, `cancel_retrofit_all`. The formation capture gained `retrofittable` (ships that can retrofit) and `retrofitting`, stored in `formation_report`; `ship_history.version` and `ship_construction_history.version` now reference the template version (they were dropped in `visibility.json` before). Retrofits become possible only after ships were built from a custom template that was then edited, so these rows verify late in a round if at all.
4. **Row N18 covered**: `set_default_ship_template`, `set_fleet_ship_template`, `delete_ship_template`, all by (ship_type, index). Bit 0 of `ship_template_private.flags` is "default for the country" (base templates start at 3, a custom default gets 1 and the base drops to 2). A fleet default shows as a `ship_template_fleet` row of the chosen template, confirmed in memory right after the command. All five template actions share the `templates` key in `loop/run.py` so one pause never mixes them.
5. **Generator convention found and enforced.** A command that returns a `Command` must not declare `valid` (the generator then wraps it in `Execute()` and reports `IsValid()`); a void callback must declare `valid`. `add_war_goal` silently did nothing because of this and `quick_decline_proposal` had the reverse fault; both fixed, and `tests/test_actions.py` resolves every command's return type through the data-type dump.
6. **Mini worlds gave fleets to nations that cannot keep them.** Ship counts came from a vanilla profile, but the naval administration that supports ships needs the `admiralty` technology; nations without it got ships that bled hit points from day one and sank within two years (seen in run 5 of `mini_r29` and in the probe world). `interface/world/nations.py` now creates a fleet only when the nation also builds a naval administration. Checked on two freshly generated worlds (tech 0.3 and 1.2): every fleet has one.
7. Commits: 88d8044, b9e47aa, 14a1479, 1421690, 52e8437.

## State right now
- `master` at 52e8437. Unit suite: 196 tests in about 12 s. Untracked `DASHBOARD_DESIGN_PROCESS.md` belongs to the other session.
- The `vic3` schema was reinstalled twice tonight (22:50 for straits, 23:45 for ship versions and retrofit state). Verification counts start from `mini_r29`'s run onward; `mini_r28` (before the second reinstall) is gone.
- Rounds: `vanilla_r27` done 22:32; `mini_r28` done 23:43; `mini_r29` done 00:11 (ended defeated); `mini_r30` running since 00:19 under the watcher. Two more mini rounds, then vanilla. A first `mini_r30` attempt at 00:18 died in the interpreter's first imports with a `KeyboardInterrupt` one second after launch and was relaunched; cause unknown, it never held a run.
- At 00:20:30 the watcher printed `RUN 7 LOST: no heartbeat for 0.5 s` for the run that had just opened, while two world generations I started were saturating the CPU; the run was alive with a 110 ms old heartbeat when checked and `run_lost` was empty. A heavy concurrent process can delay the heartbeat thread past the limit. Do not generate worlds or run other heavy work beside a round.
- A second Claude session (`vic3-agent-23`) works in this repository on a dashboard design; it agreed not to launch rounds. Commit only your own files.
- The schema design for replacing `game_definition` is in the scratchpad of session 6f1e0bb0 as `definition_design.md`, awaiting the user's decision.

## Schema review findings still open
1. `game_definition` is an entity-attribute-value table of script fields. Design for the replacement: `definition_design.md` in the scratchpad named above.
2. `loop_action_param` is name plus typed value. Alternative: typed parameter columns on `loop_action` with foreign keys to the anchors and vocabularies acted on.
3. `world_asset` stores the map files as bytea (94 MB per vanilla world). Alternative: files on disk under the world digest, a digest per file in the table.
4. Enum tables accept codes without labels (`Store.codes`). Alternative: labels required, unknown codes refused; needs label sources for building_owner_type, event_status, formation_flag, law_phase, privatization_request, slave_basket, treaty_side, war_goal_pressed, wage_level.
5. Polymorphic references without foreign keys: `journal_entry_target` and `event_target`, `building_ownership_history`, `war_goal_history.target_other`, `formation_status.current_location` and `target_location`, `battle_history.invasion`. Alternative: one typed nullable column per target kind with a check that exactly one is set.
6. Smaller: `player_message` and `player_construction_queue_item` keyed by position churn on every shift; `float8` for the game's fixed-point values; `state_pop_need.need` has no vocabulary; the four secondary indexes could be partial on `present`.

## Open questions in the data
- Strait bytes 174 and 175 change over a campaign without any setting change and are not the previous toll rates; unmapped. The save file's `first_previous_toll_rate` and `first_previous_access_status` are not in the 208-byte strait struct.
- `ship_template_private.flags` bit 1 is set on base templates and cleared when a base template stops being the default; its meaning beyond that is unknown.
- `game_state.speed` is enforced as a run constant and was 4 in every run; whether it is the live speed or a setting is unknown.

## Catalogue rows still missing
N3 mission sea regions (`Province.AddSeaRegionToSelectedFleetMissions` with selected fleets); N5 invasion planner (`PopupManager.ShowInvasionPlannerPopup`); N10 bulk ship actions (`ShipSelection.*`); N11 flagship (`Ship.AssignAsFlagship`, `UnassignAsFlagship`, `ToggleFlagshipSignalFlags`, ornaments; no flagship field in the snapshot yet); W5 treaty-article war goals; W13 sway offers (`DiplomaticPlay.CreateSway` through `SwayCountryPanel`); T1 treaties; PB8 bloc customization (`PopupManager.ShowPowerBlocCustomizationPopup`); X8 support a formation candidate (`CountryFormation.SupportCandidate`); X9 unification play (`CountryFormation.ShowUnificationPlayConfirmation`). Every schema change deletes the stored runs, so batch snapshot extensions.

## Useful scratchpad scripts
Folder: `C:\Users\trist\AppData\Local\Temp\claude\D--vic3-agent\6f1e0bb0-aeda-4860-8fdf-391b4b1ab051\scratchpad`
- `templates_mini.py`, `fleet_default_probe3.py`: detached mini-world campaigns (world `seed_994396797_6_24_tech0.95_pop0.59`, country XAC) that record a snapshot, print offers, run and verify the template actions, and read the template fleet vector from memory. That world predates the fleet fix, so its fleet dies within days; generate a new one for further probes.
- `strait_experiment.py`, `strait_cooldown.py`, `strait_live.py`, `designer_live.py`, `designer_probe2.py`, `retrofit_live.py`: the vanilla probes used before the mini-world rule; `designer_probe2.py` drives the ship designer from a hand-written control widget.
- `definition_design.md`: the schema design for replacing `game_definition`.
Previous sessions' folders `...\4ec588be-8fa9-49ae-9ac8-84c83601e0e5\scratchpad` (`stall_drill.py`, `measure_checks.py`) and `...\3b26cb9e-043f-4cdf-bad5-5886126b3e4e\scratchpad` (`inspect_*.py`, `formation_probe*.py`, `war_probe.py`).
