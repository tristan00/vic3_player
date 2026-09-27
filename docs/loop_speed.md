# Loop speed

This records what has been done to cut the time the loop spends on its own scaffolding, and what each change measured. Nothing here may change what a run does. Every hour the timing tables are reviewed and this document is replaced with the current state.

Last review: 2026-09-27 04:00, covering runs 241 to 244.

## Where a run spent its time before any change

Setup took about 120 seconds from the start of a session to the first action, and every step waited for the one before it.

| setup step | seconds |
| --- | --- |
| world generation | 38 |
| game launch and load | 31 |
| picker training | 25 |
| statistics refresh after the first snapshot | 19 |
| ruleset and geography registration | 3 |
| first capture, validation and write | 2 |

During play, per snapshot:

| step | milliseconds | note |
| --- | --- | --- |
| capture request | 455 | waiting on the game |
| foreign key validation | 250 to 345 | 870 queries, grew with the run |
| row building | 100 to 320 | grew with the run |
| copy into Postgres | 350 to 550 | grew with the run |

Run 244 wrote 434 snapshots and spent 152 seconds in validation alone.

Action dispatch averages 340 ms and the wait between game days is set by the game. Both are pacing against the game and were left alone.

## Changes

| commit | change | before | after | how it was measured |
| --- | --- | --- | --- | --- |
| 7b49bf3 | Statistics refresh runs over eight connections | 17.5 s | 3.6 s | all 287 tables on the production database |
| 7b49bf3 | Picker training runs while the world generates | 25 s after the game loaded | no added wall time | both together finished in 27.7 s, training alone takes 23.5 s |
| d6f8025 | Stray province pixels are filled from their coordinates, not by sweeping the whole map | 6.0 s | 1.1 s | same input, identical output array |
| d6f8025 | The minimap is resized from the image in memory, not decoded again from the file just written | 7.8 s | under 1 s | world hash |
| d6f8025 | Road and sea lane cost maps are built for the box being routed, not the whole map | 8.1 s | 4.6 s | world hash |
| d6f8025 | A rewrite pattern runs on a file only when the file contains the text it needs | 4.8 s | 3.1 s | world hash |
| d6f8025 | Validation asks only about tables the snapshot wrote rows to | 340 ms | 35 to 45 ms on a typical snapshot | snapshots 1, 50, 120 and 401 of run 244 |

World generation as a whole, three seeds in sequence: 95.0 s before, 64.3 s after.

Expected setup after these changes is about 65 seconds: world and training together 25, game 31, registration 3, first snapshot 6.

## Proof that runs are unchanged

| change | evidence |
| --- | --- |
| world generation | The 717, 711 and 725 files written for seeds 123456, 777 and 31337 hash to the same SHA-256 before and after. |
| validation | A check reads rows of one table at one run and snapshot. Only `Store.write` puts rows there, so a table it wrote nothing to has nothing to check. A test breaks a foreign key and confirms the check still fires for a written table. |
| statistics refresh | The same tables are analyzed, and `write` still returns only after all of them finish. A test confirms the tables are analyzed. |
| picker training | Same data, same parameters, same model. It starts earlier and finishes before the game launches. |

One thing did change order. The picker and the number of candidates are now drawn from the round's random stream before the world size, not after the run seed. The distributions are the same. A round replayed with the same `--seed` draws different values than it did before commit 7b49bf3.

## Live verification

The round running when these changes landed, collect_63, loaded the old code and keeps it until it exits. The supervisor starts the next round on the new code. No run has used the new code yet.

Baseline to compare the first new runs against:

| measure | runs 241 to 244 |
| --- | --- |
| end reasons | debt_cap 2, loop_crashed 1, one still running |
| action status | done 3339, no_object 1 |
| actions per snapshot | 5.2 to 7.6 |
| validation per snapshot | 228 to 350 ms |
| statistics refresh | 18.5 to 19.0 s |
| world generation | 23.4 to 54.6 s |
| picker training | 23.3 to 26.0 s |

Known failures that predate the changes: run 241 ended with the game date still moving 3 s after pausing, and round collect_62 exited because the heartbeat process died.

## Candidates not yet done

| candidate | cost today | idea |
| --- | --- | --- |
| row building per snapshot | 100 to 320 ms, growing | find what grows with the run |
| copy into Postgres | 350 to 550 ms, growing | same |
| vanilla map rasters and boxes | 4 to 5 s in the first world of each round | keep the decoded arrays on disk, keyed by the game files |
| log tail polling | 100,000 file reads per run | read only when the file size changed |
| offered actions | 270 to 430 ms per pause | profile the queries |
| world generation during play | 25 s per run | `--pool 1` builds the next world while the current run plays; it competes with the game for CPU and the supervisor arguments are the owner's choice |

## Simplifications and fallbacks noticed

`Fresh.take` and the picker training in `session` both start a one-worker thread pool and poll it once a second to stamp progress. One helper could serve both.

`_absent` is still called for files without any country reference. The call is cheap and keeps its span count comparable with older runs.
