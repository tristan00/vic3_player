# Loop speed

This records what has been done to cut the time the loop spends on its own scaffolding, what each change measured, and the proof that runs are unchanged. How timing works is in `timing.md`.

Last update: 2026-09-27 14:10, covering runs 269 to 271.

## State

All changes below are live since round collect_67, launched at 13:53:05. Runs 270 and 271 use them. Round collect_66 ran one hour earlier on a first version with slow validation, which run 269 used.

| commit | content |
| --- | --- |
| 7be451d | spans on every function, coverage test, faster snapshot reading, validation, row building and offered actions |
| 396e41c | validation uses index lookups |
| bcc9ddb | faster log file listing, two hot helpers listed instead of timed |

Earlier commits 7b49bf3, d6f8025 and 8f59257 are described at the end. Commit 8f59257, which launches the game while picker training finishes, went live with collect_66.

## Measured live

Mean per call over snapshots 2 to 98, on worlds of similar size.

| span | run 248, 66 states, before any speedup | run 254, 63 states, earlier speedups | run 270, 70 states, now |
| --- | --- | --- | --- |
| whole snapshot, ms | 1039 | 909 | 821 |
| wait for the game's capture, ms | 417 | 461 | 465 |
| holder decode, ms | 104 | 88 | 17 |
| snapshot write, ms | 333 | 173 | 137 |
| validation, ms | 219 | 61 | 20 |
| row building, ms | 113 | 121 | 129 |
| offered actions per pause, ms | 268 | 225 | 120 |
| action dispatch, ms | 368 | 378 | 365 |

Row building did not improve live. Offline it fell from 45 to 32 ms on a 46 state capture. Run 270 builds more rows, and each builder now carries its own span, so the comparison is not like for like. Its breakdown is below.

Validation and offered actions used to grow during a run. Validation scanned every row the run had written to a table. Offered actions reread ruleset data on every pause. Neither does so now. Run 244 spent 380 ms per snapshot on validation over a full hour. An hour-long run on the new code has not finished yet, so the hourly figure is still open.

## Where a snapshot goes now

Run 270, mean per snapshot.

| part | ms | whose time |
| --- | --- | --- |
| wait for the game's capture | 465 | the game |
| memory snapshot decode | 50 | loop |
| holder decode | 17 | loop |
| row building | 129 | loop |
| write: copy to the database | 39 | loop and database |
| write: versions | 29 | loop |
| write: resolve | 23 | loop |
| write: validation | 20 | database |
| write: timing rows | 13 | loop and database |
| write: samples | 10 | loop |

Inside row building the largest parts are ordering rows into column order at 35 ms, grouping child rows at 25 ms, and reading rows at 13 ms.

## Where an action goes now

Run 270, mean per action. These spans are new, so there is no earlier figure.

| part | ms | whose time |
| --- | --- | --- |
| pacing gap before the action | 46 | fixed by the transport |
| prime delay | 100 | fixed by the transport |
| wait for the game's answer | 292 | the game, including its fixed 100 ms cleanup delay |

Actions take about 37 % of an hour of play. The fixed delays were raised on purpose. Commit ee93fb5 set the 300 ms cycle because faster commands were dropped by the game. They are left as they are.

## Changes

| change | before | after | measured on |
| --- | --- | --- | --- |
| Holder decode looks a token up in memory before reading the game | 104 ms | 17 ms | runs 248 and 270 |
| Validation asks the database about the values just written, in one pipeline of prepared statements | 219 ms | 20 ms | runs 248 and 270 |
| Offered actions load their tables over eight connections | 171 ms in sequence for 106 tables | about 130 ms, bounded by the largest table | run 260, snapshot 500, offline |
| Ruleset data, table list and name tables are read once per run | reread on every snapshot | read once | offline |
| A cached lookup no longer opens a span on every hit | about 130 ms per pause | 0 | run 260, 110000 calls per pause |
| Rows are ordered by one prepared getter per row shape | 16 ms | 10 ms | capture of 39000 rows, offline |
| Resolve visits only columns that need a check | 14 ms | 12 ms | offline |
| The action answer is searched in the log text gained since the action started | whole 16 MB window decoded on every poll | only new text | not measured apart |
| Log files are listed with one directory read | 0.39 ms | 0.065 ms | offline, 300 calls |
| A span costs less | 1.2 µs | 0.8 µs | 300000 calls |
| Test suite | 253 tests in 17.4 s | 267 tests in 14.7 s | full suite |

## Proof that runs are unchanged

| change | evidence |
| --- | --- |
| offered actions | 40 stored snapshots from 8 runs give the same 56568 offered combinations on old and new code |
| row building | two captures read from the running game give identical rows on old and new code |
| snapshot write and validation | eight writes of those captures leave 88799 rows with the same digest on old and new code |
| holder decode | five back-to-back reads of the running game are equal between old and new code |
| world and control mod | 764 generated files are identical; the HUD differs only by its random token |
| live action status | runs 269 to 271: 1688 done and 2 invalid, no action without a game object |
| round logs | collect_66 and collect_67 hold no traceback, stall, crash or block |

Validation changed what it asks. It used to look for rows of the snapshot whose target is missing. It now checks that every value written has its target. Only `Store.write` writes those rows, so both catch the same fault. A test writes a value without a target and confirms the refusal.

## The slow validation in collect_66

The first version kept a setting that disabled nested loops inside the snapshot transaction. With the new checks that forced a scan of whole target tables, and validation took 1060 ms per snapshot in run 269. The run is otherwise normal and its data is valid. The setting is removed in 396e41c.

## Rollovers

Both restarts happened between runs, so no run was lost.

| time | what |
| --- | --- |
| 13:34:42 | run 268 ended; collect_65 stopped during its next setup; collect_66 launched at 13:34:48 |
| 13:52:59 | run 269 ended; collect_66 stopped during its next setup; collect_67 launched at 13:53:05 |

## Setup

| step | seconds | can it shrink |
| --- | --- | --- |
| game launch and load | 33 | no, it is the game |
| picker training | 34, overlapped | it holds nothing up unless it outlasts world and game together |
| world generation | 15 to 40 | `--pool 1` builds the next world during play; the supervisor arguments are the owner's choice |
| first snapshot with statistics refresh | 9 | the refresh is bounded by its largest table |
| registration | 3 | small |

## Looked at and left alone

| item | finding |
| --- | --- |
| transport delays | see above; raised on purpose in ee93fb5 |
| frame rate cap of 30 | the transport advances once per frame, so a higher cap would shorten every action and capture; the GPU sits at 12 to 19 % and the guard kills the game above 50 %, so the cap is the owner's protection |
| skipping log reads when the file size is unchanged | Windows reported a stale size for a full 25 s while new data was readable, so the read is required |
| one copy statement per table | 290 statements cost 39 ms per snapshot; batching small tables as inserts would add a second write path |
| pop needs table | its read scans every version a run has written and bounds the parallel load at 80 to 120 ms late in a run; a filter on the player's states was slower |
| statistics refresh in the background | the first offered actions would be planned without statistics on multi-gigabyte tables |
| picker training rows | 6 s of Python with 10 million calls to one lookup; it no longer holds anything up |

## Earlier changes

| commit | change | before | after |
| --- | --- | --- | --- |
| 7b49bf3 | statistics refresh over eight connections | 17.7 to 21.6 s | 5.1 to 8.8 s |
| 7b49bf3 | picker training runs while the world generates | 25 s after the game loaded | overlapped |
| d6f8025 | world generation, three seeds | 95.0 s | 64.3 s |
| 8f59257 | the game launches as soon as the world is ready | waited 7 to 18 s for training | no wait |

Commit 7b49bf3 moved two random draws, so a round replayed with the same `--seed` draws different values than before it.

## Simplifications and fallbacks noticed

| where | note |
| --- | --- |
| `loop.run.build` | a one-line pass to `generate`; the pool and the tests could call `generate` directly |
| `Fresh.take` and `session` | both start a one-worker pool and poll it once a second to stamp progress; one helper could serve both |
| `LogTail.poll` | swallows `PermissionError` and `FileNotFoundError`; a missing log directory is hidden until the log goes quiet |
| `record._event_options` | retries `OSError` for a second before raising |
| `tests/timing_exempt.json` | `Reader.tokens` is listed as hot; after the token lookup it runs far less and could be timed |
