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

`store.install(connection)` drops schema `public` and recreates it from `schema.sql`. `Store` refuses to open a database whose `schema_digest` differs from `schema.sql`, so regenerate the SQL and reinstall after any change to `spec.py`.

## Model
Each run records a sequence of snapshots, numbered `seq` from 0. Every run-scoped table starts with `run_id`.

### Table kinds
| Kind | Shape | Example |
|---|---|---|
| anchor | `<entity>(run_id, <entity>, first_seq)`: one row per game identity seen in the run | `pop` |
| history | `<entity>_history(run_id, <entity>, seq, present, ...)`: the entity's own attributes | `pop_history` |
| subject | `<entity>_<topic>(run_id, <entity>, seq, ...)`: a 1:1 attribute group, valid while the entity is present | `pop_status`, `country_economy` |
| private subject | `<entity>_private`: columns the game shows only to the owner, with rows for the player's objects only | `law_private` |
| child | `<owner>_<thing>(run_id, <owner>, <key...>, seq, present, ...)`: sets and lists an entity holds | `country_culture`, `state_goods` |
| listing | `<name>(run_id, <key...>, seq, present, ...)`: sets with no owning entity, mostly the player's view | `player_alert`, `relation` |
| singleton | `player_<topic>(run_id, seq, ...)`: one row per version, the player country's private data | `player_treasury` |
| sample | `<name>(run_id, [<owner>,] [<key>,] n, seq, date, ...)`: trend samples keyed by the game's sample counter `n` | `interest_group_sample` |

### Time
Every table except samples is insert-only.
- A row is the key's value from its `seq` until the key's next row.
- A row with `present = false` and all data NULL is a tombstone: the key left the capture.
- Subject rows have no `present`. They count only while the owner's history row is present.

Samples are written once and never change; the writer raises if a stored sample changes.
- `seq` is the snapshot that first saw the sample.
- `date` is the game date. It is known only for the newest sample of a buffer, because the game's sample spacing is not uniform.

### Identity and references
- Entities are keyed by the game's full identity, `slot | generation << 24`.
- Every reference to an entity has a foreign key to that entity's anchor. A reference to nothing is NULL.
- The writer resolves slot-only references to the identity captured in that slot in the same snapshot. It raises if the capture has no such object.
- Game sentinels (−1, and 65535 for some province fields) are declared per column in `spec.py` and stored as NULL.
- Relations, pacts, treaties and diplomatic actions are keyed by their ordered country pair, which never changes within a run.
- Provinces carry `(province, color)` per run, with a foreign key to `world_province`.

### Names and codes
- Every name column references a typed vocabulary table `(<name> identity, name unique)`, for example `goods`, `law_type` or `building_type`. `name_column` lists which column uses which vocabulary.
  - Closed vocabularies are filled from the game's definition folders when a ruleset is registered.
  - Building types also include the runtime-generated `building_<company_type>` names.
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
- Script-side captures over the player's scope (for example `character_status`, taken from `every_scope_character`) cover a different set of objects than the memory-side `_private` tables, which follow the owner column. Neither set is a subset of the other.

Dropped duplicate metrics are listed in `spec.DROPPED_COUNTRY_METRICS` and `spec.DROPPED_STATE_METRICS`. The builders assert each one equals its replacement at capture.

### Fixed tables
- **World:** `world`, `world_province`, `world_adjacency` and `world_asset`.
- **Ruleset:** `ruleset`, `ruleset_definition` (the load order of each definition folder) and `game_definition` (a verbatim key/value mirror of script fields, read by the rules). Also `event_definition_option`, `building_production_method`, `dlc` and `capture_gap`.
- **Run:** `run`, `run_generated` (generated worlds only), `run_advisor`, `run_game_rule`, `snapshot` and `ui_open_window`.
- **Loop:** `loop_action`, `loop_action_param`, and `action_parameter` (the declared parameters of each action).

## Querying
Every timed table except samples has an inlinable function `<table>_at(run, seq)`; a history table's function is named after its entity, as in `pop_at`. It returns the rows live at `seq`, without `run_id` or `present`:

```sql
select * from pop_at(1, 50) where pop = 3;
select p.pop, s.wealth from pop_at(1, 50) p join pop_status_at(1, 50) s using (pop);
select * from player_treasury_at(1, 50);
```

- **Predicates on a key column** push down to the primary key.
- **Predicates on another column** must first find candidate keys through a secondary index. There are four: `pop_history (run_id, location, seq)`, `building_history (run_id, state, seq)`, `state_history (run_id, country, seq)` and `character_history (run_id, country, seq)`.

  ```sql
  select p.* from pop_at(1, 50) p
  where p.pop in (select pop from pop_history where run_id = 1 and location = 3) and p.location = 3;
  ```

- **What changed at a snapshot:** `where run_id = R and seq = S` on any table.
- **Names:** join the vocabulary table, for example `join law_type using (law_type)`.

The rules and the verifier read through `Stored(connection, run_id, seq)`, which calls the `_at` functions, replaces vocabulary ids by names, and memoizes per snapshot.

## Writing
The writer (`Store.write`) handles each snapshot in one transaction:
1. It resolves references, sentinels and names, and diffs every table against the previous snapshot.
2. It inserts the snapshot row.
3. It suspends foreign-key triggers for the transaction (`set local session_replication_role = replica`).
4. It inserts new anchors and changed rows, then runs one generated check per foreign key over this snapshot's rows.
5. Any violation raises and rolls back.

Primary keys, NOT NULL and check constraints are never suspended. Any other writer gets row-by-row foreign-key checks as usual.

The checks read only the latest block ranges through the `brin (run_id, seq)` index on every timed table.

`select delete_run(run_id)` removes a run. The open vocabularies are kept.

## Tests
- `tests/test_store.py` round-trips the writer on `vic3_test` and reinstalls that schema first.
- `tests/test_coverage.py` pushes a complete synthetic capture through every builder, and fails if a captured table has no stored table.
- `tests/memory_stored.py` is an in-memory `Stored` for rule tests: rows are dicts keyed by the schema's column names.
