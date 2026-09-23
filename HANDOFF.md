# Handoff, 2026-09-23

## Open problems, most important first

1. **The database layout wastes most of its space.** It is 36 GB for 3,400 snapshots, about 10.7 MB each. Every snapshot stores a full copy of all 388 state tables (a vanilla snapshot is about 1.42M rows).
   - Rows barely change between snapshots: in `interest_group_clout_trend`, 97.8% of a mini snapshot's rows and 89.7% of a vanilla one's are identical to the previous snapshot.
   - History buffers are re-stored in full every time. `interest_group_clout_trend` alone is 6.3 GB, and the country/state trend tables and `state_pop_need` are next.
   - Rows are narrow (about 20 bytes of data, 56 on disk).
   - Ideas, all lossless:
     - store rows with a first/last snapshot range, written only on change;
     - store history as one row per sample;
     - pack small child lists into array columns (not jsonb);
     - use integer ids for metric names.
   - The snapshot is training data: nothing may be removed. `tests/test_coverage.py` and `tests/coverage_baseline.json` guard that.
2. **Vanilla snapshots have no province data.**
   - `Store.world()` (`interface/recording/store.py:82`) stores the map (province image, provinces, adjacencies) only for mini worlds; vanilla sets `world_id=None` (`record.py:45`).
   - `province_block()` (`capture.py:382`) returns '' without a mini world, so `province_state` has 0 rows across all 82 vanilla snapshots.
   - Fix idea:
     - generalise `geography.world_data()` to take the game's `map_data` (95 MB), with regions parsed from `map_data/state_regions`;
     - build the vanilla province list from `province_terrains.txt` and `default.map` (about 40,875 provinces), and measure the capture time.
3. **The Great Wave (ep2, `dlc018_ep2`) is now owned but its actions are unfinished.**
   - Rows N7, N8, N11, N18 and N19 were moved back into scope on `master` (commit `045d33e`) and show as missing.
   - Untested work is on branch **`great-wave-wip`** (commit `111ce81`, not merged):
     - a `ship_setting` capture: a GUI widget over each fleet's ships recording template name, flagship, can-be-flagship, marked-for-retrofit and retrofit progress;
     - actions `assign_flagship`/`unassign_flagship`, `retrofit_fleet`/`cancel_retrofit_fleet`, `retrofit_all`/`cancel_retrofit_all`, `set_default_template`/`set_fleet_template`/`delete_template`.
   - The template offer rule (`templates()`) is still an empty stub.
   - N19 (ship designer) isn't started. The relevant functions are `ShipDesignerPopup.SetShipType`, `ShipDesignerModSlot.OnSelectModificationForSlot`, `CreateTemplate`/`EditTemplate`, `ToggleRetrofit`, `PopupManager.ToggleShipDesignerPopupWithTemplate`.
   - The live test (scratchpad `navy_test.py` on GBR) stopped with "The game did not acknowledge the live capture request" on the first capture. The new ship widget may be the cause, or it may be the intermittent startup timeout seen once before. **Test the branch's capture before merging.**
4. **Catalogue rows still missing:**
   - B10–B12: straits
   - N3: mission sea regions
   - N5: invasion planner
   - N10: bulk ship actions
   - W5: treaty war goals
   - W13: sway offers
   - T1: treaties
   - PB8: bloc customization
   - X8, X9: formation candidacy and unification plays

## State right now

- No round is running, and all game and loop processes are stopped. The hourly reminder cron was deleted.
- `master` is at `045d33e`. The unit suite passes: 163 tests in about 7 s (`.venv/Scripts/python -m unittest discover -s tests -q`).
- Coverage report (`.venv/Scripts/python -m loop.report`): 138 of 155 feasible rows implemented; **92 of 176 actions verified**, up from 47 at the start of the session.
- **Rotation:** 5 minis, then 1 vanilla (see `loop/instruction.txt`). The last vanilla round was r14. Completed minis since then: r16, r17, r18, r19, r20 (r15 crashed and doesn't count). **The next round is vanilla, as `vanilla_r21`.** Consider fixing item 2 first so the vanilla data is complete.
  - Launch detached via WMI:
    `cmd.exe /c cd /d D:\vic3_agent && "C:\Program Files\Git\usr\bin\timeout.exe" 1500 .venv\Scripts\python.exe -m loop.run --minutes 20 [--vanilla] [--tag TAG] > D:\vic3_data\interface\<name>.log 2>&1`
  - A round now starts a new session after an early defeat, until its time budget is used. Each session prints its own counts line.

## What changed this session (all on `master`)

- **Executor:**
  - Ship queue items are reached through our own non-virtualized list in the page-button area, with condition-driven page navigation (12 per page).
  - Each multi-step stage sets an armed flag, and HUD timers turn it into the stage-done flag, so a widget that disappears no longer stalls the action. Abort clears all stage flags.
  - Popups are closed by the deferred clean (0.1 s), and the auto-confirm fires at 0.02 s. Actions that ask for confirmation now work.
  - The action time limit is 5 s (bulk production-method switches took up to 2 s).
  - Log reads tolerate the gap while `debug.log` rotates.
- **Capture:** per-target state picks for diplomatic actions are evaluated in script and stored on each target country, read via `Reader.holders()`, into the `diplomatic_action_state_pick` table.
- **New or repaired actions:**
  - `diplomatic_action_state`: the window's own state list.
  - `reform_government`: groups taken from the reform panel's lists.
  - `form_power_bloc`: identity plus primary principle, with a principles reset first.
  - `pick_principle`: row PB6, not yet exercised.
  - `transfer_battalions`: explicit left/right formations.
  - `set_borrow_setting`: `OnClicked`, then execute.
- **Offer-rule fixes:**
  - capitulation while the overlord fights; war goals during the countdown; the colonize interest tier; treaty ports; bloc invites; privatizable buildings; reverse pacts;
  - reform: marginalized groups, insurrectionary groups, the reform-block modifier, and keeping at least one governing group;
  - raising conscripts only at home; resuming ship construction; DLC-visible principles.
- **DLC:** `dlc_feature()` maps the seven named features (Sphere of Influence: `power_bloc_features`, `lobbies`, `foreign_investment`, `subject_and_bloc_actions`; Voice of the People: `voice_of_the_people_content`, `voice_of_the_people_preorder`, `agitators`) and raises on unknown names. Earlier in the session I wrongly claimed Sphere of Influence was missing; `ep1` is Sphere of Influence and is owned.

## Smaller known issues

- `demand_state` no_effect: the AI declining, and the decline isn't captured.
- `create_company`: the re-establish cooldown and the company limit aren't captured.
- `rehome_formation` while a rehome is already under way; `white_peace` while a peace deal is pending; authority raced within a pause.
- `insurrectionary()` relies on `civil_war` plus `interest_group_movement_support`; `interest_group.civil_war` is never populated.

## Useful scratchpad scripts

Folder: `C:\Users\trist\AppData\Local\Temp\claude\D--vic3-agent\ce3a4ba2-d567-489c-aaa3-559f3178b4a3\scratchpad`

- `trio_test.py TAG action...`: debug campaign, runs the offered combinations and prints before/after state.
- `bloc_probe.py` / `flow_probe.py`: step-by-step probes built by truncating an action's stages with `dataclasses.replace`.
- `debug_live.py`, `navy_test.py`.
- Launch them detached with the same WMI pattern, using profile `development`.
