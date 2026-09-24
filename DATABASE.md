# Snapshot database

**Location.** Postgres 17 at `host=127.0.0.1 port=55433`, database `vic3`, schema `public`. The tests use `vic3_test`.

**Source files**, all in `interface/recording/`:

| Part | File |
|---|---|
| Table catalog | `spec.py` |
| Generated SQL | `schema.sql`, produced by `python -m interface.recording.emit` |
| Fixed SQL | `schema_head.sql`, `schema_meta.sql`, `schema_tail.sql` |
| Writer | `store.py` |
| Builders (capture to rows) | `tables.py` |
| Capture wiring | `record.py` |
| Reader used by the rules | `../options/stored.py` |

`store.install(connection)` drops schema `public` and recreates it from `schema.sql`. `Store` refuses to open a database whose `schema_digest` differs from `schema.sql`, so regenerate the SQL and reinstall after any change to `spec.py` or the fixed SQL. Reinstalling deletes every run.

## Model
Each run records a sequence of snapshots, numbered `seq` from 0. Every run-scoped table starts with `run_id`.

### Table kinds
| Kind | Shape | Example |
|---|---|---|
| anchor | `<entity>(run_id, <entity>, first_seq)`: one row per game identity seen in the run | `pop` |
| history | `<entity>_history(run_id, <entity>, seq, present, ...)`: the entity's own attributes | `pop_history` |
| subject | `<entity>_<topic>(run_id, <entity>, seq, ...)`: a 1:1 attribute group, valid while the entity is present | `pop_status`, `country_economy` |
| private subject | `<entity>_private`: memory columns the game shows only to the owner, with rows for the player's objects only | `law_private`, `formation_private` |
| child | `<owner>_<thing>(run_id, <owner>, <key...>, seq, present, ...)`: sets and lists an entity holds | `country_culture`, `ship_template_version_list` |
| listing | `<name>(run_id, <key...>, seq, present, ...)`: sets with no owning entity, mostly the player's view | `player_alert`, `relation` |
| singleton | `player_<topic>(run_id, seq, ...)`: one row per version, the player country's private data | `player_treasury` |
| sample | `<owner>_<trend>_sample(run_id, [<owner>,] [<key>,] n, seq, date, <value>)`: one trend buffer, keyed by the game's sample counter `n` | `interest_group_clout_sample` |

### Time
Every table except samples is insert-only.
- A row is the key's value from its `seq` until the key's next row.
- A row with `present = false` and all data NULL is a tombstone: the key left the capture.
- Subject rows have no `present`. They count only while the owner's history row is present.

### Samples
Every trend buffer of the game is its own sample table with one value column. The buffers of one object are rings of different capacities, so two trends of the same object do not hold the same sample numbers; an interest group's clout ring is longer than its radicals ring.
- `n` is the game's sample counter. Position `p` of a ring of size `s` whose counter is `n` holds sample `n - ((n - 1 - p) mod s)`.
- Samples are written once and never change; the writer raises if a stored sample changes.
- `seq` is the snapshot that first saw the sample.
- `date` is the game date. It is known only for the newest sample of a buffer, because the game's sample spacing is not uniform.

### Identity and references
- Entities are keyed by the game's full identity, `slot | generation << 24`. Generation 0 is common, so a bare slot number and a generation-0 identity look alike.
- Memory fields hold full identities. Script and GUI captures name objects by slot; the builders turn every such slot into the identity the memory capture holds in that slot (`Context.ident`) and refuse a capture where the script names a slot memory does not hold.
- Every reference to an entity has a foreign key to that entity's anchor. A reference to nothing is NULL.
- A reference is stored as exactly the identity the game holds. The game keeps handles to objects that are gone (a general to a disbanded formation, a cultural community to a removed state, a war goal to a vanished play) and to objects that do not exist yet (a play's fronts carry the identity of the war that will start). Such an identity gets an anchor row on first sight, so its history may start later or have ended earlier. `referenced_only` lists identities with an anchor but no history row; a war reserved by a play is expected there, anything else is a capture gap.
- Provinces are the exception: a province reference must name a captured province, because provinces never change.
- Game sentinels (−1, and 65535 for some province fields) are declared per column in `spec.py` and stored as NULL.
- Relations, pacts, treaties and diplomatic actions are keyed by their ordered country pair, which never changes within a run.
- Provinces carry `(province, color)` per run, with a foreign key to `world_province`.

### Dead objects
Buildings, formations and wars stay in game memory for a while after they end, with the game's own `dead` flag set. Their history tables carry `dead`. Script-side captures skip dead objects, so a player table filled from script covers exactly the live objects: `formation_report` and `building_private` have rows for the player's live objects only, and the builders refuse a capture where the two sides disagree.

### Names and codes
- Every name column references a typed vocabulary table `(<name> identity, name unique)`, for example `goods`, `law_type` or `building_type`. Which columns are names is read from the foreign keys (`Stored` does this from `pg_constraint`).
  - Closed vocabularies are filled from the game's definition folders when a ruleset is registered.
  - Building types also include the runtime-generated `building_<company_type>` and `building_regional_<company_type>` names.
  - The writer refuses a name that isn't defined in the run's ruleset.
  - Free text (localization keys, scope names, UI windows, advisors, actions) goes in open vocabularies that the writer fills as it meets new values.
- Every game code references its enum table `(<enum> int2, name)`. A code met for the first time is added with a NULL name.
- Budget lines reference `budget_line(direction, line, name)`.

### Public and player data
`interface/visibility.json` decides what is captured for every owner and what only for the player. The schema follows it:
- Public tables are complete for every owner.
- `_private` subjects and the `player_*` tables hold the player's data only.
- The player is `run.player_country`, fixed for the run.
- Country metrics go to `country_<topic>` if they are public and to `player_<topic>` otherwise.
- Memory-side `_private` tables follow the owner column and include dead objects. Script-side player tables (`character_status`, `formation_report`, `building_private`, the `_report` metric tables) cover the objects the player's script scope iterates. The two sides are stored separately because their coverage differs.

Dropped duplicate metrics are listed in `spec.DROPPED_COUNTRY_METRICS` and `spec.DROPPED_STATE_METRICS`. The builders assert each one equals its replacement at capture.

### Fixed tables
- **World:** `world`, `world_province`, `world_adjacency` and `world_asset`. Vanilla and generated worlds are registered the same way, from the game's or the mod's `map_data`.
- **Ruleset:** `ruleset`, `ruleset_definition` (the load order of each definition folder) and `game_definition` (a verbatim key/value mirror of script fields, read by the rules). Also `event_definition_option`, `building_production_method`, `dlc` and `capture_gap`.
- **Run:** `run`, `run_generated` (generated worlds only: `tag`, `world_file`, `cli_seed`, `run_seed`, budget and profile), `run_advisor`, `run_game_rule`, `snapshot` and `ui_open_window`.
- **Loop:** `catalogue_action` (the actions of the catalogue, registered when a loop starts), `loop_action`, `loop_action_param`, and `action_parameter` (the declared parameters of each action).

## Verification
Whether an action attempt worked is decided at runtime by `verify()` in `loop/effects.py`, which compares the snapshot before the attempt with the snapshot after it. Its result is the `status` of the attempt's `loop_action` row: `verified`, `unverified` (no verifier or no evidence), `invalid`, `no_object`, `no_effect`, `raced` or `ui_leftover`. Nothing else decides it, and no count is made outside the database.

| View | Content |
|---|---|
| `action_run_outcome` | per run and action: verified, unverified, failed and raced attempts, and the run's world (`vanilla_<tag>`, the generated world's name, or `attached`) |
| `action_verification` | per catalogue action, over the last 3 runs that attempted it: attempts, distinct worlds with a verified attempt, and `verified_by_standard` |
| `verification_summary` | verified actions, catalogue actions, actions never attempted |

The standard: the action occurred in at least 3 runs, and verified attempts are at least 95 percent of all attempts over the last 3 runs containing the action. `python -m loop.report` prints these views and the static catalogue rows.

## Run liveness
Every run row says whether its loop is alive, whether it is making progress, and how it ended, with the timestamps needed to measure detection.

| Column | Meaning |
|---|---|
| `started_at` | the loop began the run |
| `heartbeat_at` | the loop process's last sign of life, refreshed every 100 ms by a thread with its own connection |
| `progress_at` | the wall time of the main thread's last progress stamp, written by the same thread on every beat |
| `progress_step` | what the main thread was doing at that stamp |
| `longest_step`, `longest_step_ms` | the longest gap between two stamps seen so far in the run, and the step it was in |
| `ended_at` | the run was flagged as over |
| `end_reason` | `time`, `years`, `defeated`, `ui_stuck`, `game_crashed`, `loop_crashed`, `loop_stalled` or `loop_lost` |
| `end_detail` | the error text for `loop_crashed` and `game_crashed`, the step and duration for `loop_stalled` |
| `game_exited_at` | the process exit time reported by the OS, for `game_crashed` |

A progress stamp (`interface.common.progress`) is written by the main thread on entry and exit of every `@timed` function (qualified name), on every tick of the run-days loop, on every poll while waiting for the game to load, close, answer an action or finish a capture, on every foreign-key check, resolved table and copied table of a snapshot write, on every builder, on every action's offer rule, between the steps of the world geometry, and every second while a world is generated or a process is spawned. The process's own liveness and its progress are separate signals on purpose: a thread that beats while the main thread is stuck in a nine-minute query is the failure that motivated the second one.

- **Game exit.** A watcher thread checks the game's process handle every 50 ms: whether the process object is signaled and whether one word of the executable is still readable. Memory becomes unreadable at the start of teardown, hundreds of milliseconds before a large process is signaled, so the watcher flags at teardown start: it writes `ended_at` and `end_reason = 'game_crashed'` at once through its own connection, then waits for the OS exit time and records it in `game_exited_at`. The loop itself also stops at its next game access and logs when it did.
- **Loop crash.** An exception ends the run as `loop_crashed` with the error text, unless the game process is gone or exits within a second, in which case the exception is attributed to the game.
- **Loop stall.** The `Watchdog` thread in `loop/run.py` checks the stamp every 100 ms from process start, before any run exists. When the stamp is older than `STALL_LIMIT` (5 s, `interface/common.py`) it logs `LOOP STALLED` with the step, writes `loop_stalled` and the detail through its own connection if a run row exists, closes the game and exits the process with code 3. A stall before the first snapshot commits leaves no run row; the round log and the launcher's exit code are the record. Measured on 2026-09-23 by locking the `snapshot` table under a running round: flagged 5.1 s after the lock, process exited 3 s later.
- **Loop killed.** Nothing inside the process can write. `run_lost` lists runs with no `ended_at` whose heartbeat is older than half a second; `run_stalled` lists runs with no `ended_at` whose progress stamp is older than 5 s. The next `Store.begin_run` closes lost runs as `loop_lost` with `ended_at = heartbeat_at`.
- **Late detection.** `run_late_flag` lists `game_crashed` runs with no OS exit time or flagged more than a second after it. It must stay empty; a row is a critical bug.
- **Refused captures.** When the builders or the writer refuse a snapshot, `record` dumps the whole capture (memory tables, script lists and maps) to `D:\vic3_data\interface\refusals\<time>.pkl` before raising, so the cause can be read from the data instead of reproduced.

```sql
select * from run_lost;
select * from run_stalled;
select * from run_late_flag;
select run_id, end_reason, end_detail, longest_step, longest_step_ms from run order by run_id;
```

Outside the process, `loop/watch.py` polls the round log, these views and the process list four times a second and prints every event; `loop/launch.py` spawns a round detached and runs that watcher on it. The agent runs `loop.launch` under its Monitor tool so every printed line reaches it as it happens.

## Querying
Every timed table except samples has an inlinable function `<table>_at(run, seq)`; a history table's function is named after its entity, as in `pop_at`. It returns the rows live at `seq`, without `run_id` or `present`:

```sql
select * from pop_at(1, 50) where pop = 3;
select p.pop, s.wealth from pop_at(1, 50) p join pop_status_at(1, 50) s using (pop);
select * from player_treasury_at(1, 50);
```

- Functions of tables with an owner walk the owner's anchor table and take the latest row of each identity through one primary-key probe, so their cost grows with the number of identities, not with the run's length. A predicate on the owner column pushes into that probe. Child tables keyed below their owner take the latest row per key within the owner's rows.
- Functions of tables without an owner take the latest row per key with a backward primary-key scan.
- **Predicates on another column** must first find candidate keys through a secondary index. There are four: `pop_history (run_id, location, seq)`, `building_history (run_id, state, seq)`, `state_history (run_id, country, seq)` and `character_history (run_id, country, seq)`.
- **What changed at a snapshot:** `where run_id = R and seq = S` on any table.
- **Names:** join the vocabulary table, for example `join law_type using (law_type)`.
- **A trend:** `select n, date, clout from interest_group_clout_sample where run_id = R and interest_group = G order by n`.

The rules and the verifier read through `Stored(connection, run_id, seq)`, which calls the `_at` functions, replaces vocabulary ids by names, and memoizes per snapshot.

## Writing
The writer (`Store.write`) handles each snapshot in one transaction:
1. It resolves references, sentinels and names, and diffs every table against the previous snapshot.
2. It inserts the run row on the first snapshot, then the snapshot row.
3. It suspends foreign-key triggers for the transaction (`set local session_replication_role = replica`) and nested-loop joins (`set local enable_nestloop = off`).
4. It inserts new anchors (identities present or referenced for the first time) and changed rows, then runs one generated check per foreign key over this snapshot's rows.
5. On the first snapshot it refreshes `heartbeat_at` and `progress_at` as the transaction's last statement, so the run is never listed as lost between its commit and the first beat.
6. Any violation raises and rolls back.

The heartbeat thread starts once the first snapshot has committed, because the run row exists only then.

Primary keys, NOT NULL and check constraints are never suspended. Any other writer gets row-by-row foreign-key checks as usual. The connection uses no server-side prepared statements, so every check is planned with its actual run and snapshot values. Nested loops are off because the rows a check reads were inserted in the same transaction and have no statistics: the planner estimates one row, chooses a nested loop over a materialized inner list, and a 57,000-row check then compares 57,000 by 57,000 rows, which took over 100 s per check and nine minutes per snapshot on a vanilla world. With hash and merge joins the same checks take 0.3 s in total.

The checks read only the latest block ranges through the `brin (run_id, seq)` index on every timed table.

`select delete_run(run_id)` removes a run. The open vocabularies are kept.

## Tests
- `tests/test_store.py` round-trips the writer on `vic3_test`, reinstalls that schema first, and checks references and anchors, the heartbeat and progress columns, `run_lost`, `run_stalled`, the stall flag, the closing of lost runs and the verification views.
- `tests/test_liveness.py` kills a child process and checks that the process handle reports the exit, its readability, its OS exit time and the watcher alert within a second.
- `tests/test_watchdog.py` checks the progress stamps of `@timed` functions, the watchdog's trip (flag, log, game close) with and without a run row, and the watcher's log event parsing.
- `tests/test_coverage.py` pushes a complete synthetic capture through every builder, and fails if a captured table has no stored table.
- `tests/memory_stored.py` is an in-memory `Stored` for rule tests: rows are dicts keyed by the schema's column names.
