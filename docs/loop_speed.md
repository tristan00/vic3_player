# Loop speed

This records what has been done to cut the time the loop spends on its own scaffolding, and what each change measured. Nothing here may change what a run does. Every hour the timing tables are reviewed and this document is replaced with the current state.

Last review: 2026-09-27 04:45, covering runs 244 and 245.

## Blocked

The speedups are committed but no run has used them. Round collect_63 started at 03:06, before the first commit, and a round keeps the code it loaded until its process exits. It is asked for 1000 runs, so it will not exit by itself soon. The supervisor starts the next round on the new code.

Ending the round is the owner's decision. Until a run has used the new code, live verification cannot start and no further change is stacked on top.

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

During play, per snapshot, from run 245:

| step | milliseconds | note |
| --- | --- | --- |
| capture request | 473 | waiting on the game |
| rest of the memory read | 223 | |
| foreign key validation | 304 | 870 queries |
| row building | 294 | grows with the run |
| copy and staging in the write | 207 | grows with the run |
| offered actions, per pause | 176 | |

Run 244 wrote 520 snapshots in its hour and spent 198 seconds in validation.

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

Expected saving during play is about 260 ms per snapshot, which is 135 seconds over a run the length of run 244.

## Proof that runs are unchanged

| change | evidence |
| --- | --- |
| world generation | The 717, 711 and 725 files written for seeds 123456, 777 and 31337 hash to the same SHA-256 before and after. |
| validation | A check reads rows of one table at one run and snapshot. Only `Store.write` puts rows there, so a table it wrote nothing to has nothing to check. A test breaks a foreign key and confirms the check still fires for a written table. |
| statistics refresh | The same tables are analyzed, and `write` still returns only after all of them finish. A test confirms the tables are analyzed. |
| picker training | Same data, same parameters, same model. It starts earlier and finishes before the game launches. |

One thing did change order. The picker and the number of candidates are now drawn from the round's random stream before the world size, not after the run seed. The distributions are the same. A round replayed with the same `--seed` draws different values than it did before commit 7b49bf3.

## Baseline for live verification

All of these runs used the old code.

| measure | run 243 | run 244 | run 245, still playing |
| --- | --- | --- | --- |
| end reason | debt_cap | time | |
| snapshots | 112 | 520 | 245 |
| actions | 628 | 2750 | 1552 |
| advisor actions per pause | | 7.2 | 9.1 |
| action status | all done | all done | 1551 done, 1 no_object |
| validation per snapshot, ms | 250 | 380 | 304 |
| statistics refresh, s | 18.5 | 19.0 | 17.7 |
| world generation, s | 43.3 | 38.2 | 49.3 |
| picker training, s | 24.4 | 25.4 | 21.4 |

Logs for collect_63 hold no traceback, stall, crash or block. The one failed span is the action that found no game object in run 245, which the loop handles.

Known failures that predate the changes: run 241 ended with the game date still moving 3 s after pausing, and round collect_62 exited because the heartbeat process died.

## Looked at and left alone

| item | finding |
| --- | --- |
| action dispatch | Three quarters of actions take 230 to 300 ms and the rest 700 to 1300 ms. The floor is a fixed 100 ms wait plus the game's answer. This is pacing against the game. |
| log tail | 136,000 polls in 30 minutes cost 0.75 s per snapshot interval, mostly on its own thread or inside waits that would sleep anyway. Skipping reads when the size is unchanged would alter how a rotated log is detected. |
| death check while days run | Reads game memory 500 times per snapshot interval, all inside the wait for the game. No wall time to save. |
| vanilla map rasters | 4 to 5 s once per round. A disk cache would add invalidation logic for a saving of seconds per round. |

## Candidates not yet done

| candidate | cost today | what it needs |
| --- | --- | --- |
| row building per snapshot | 100 to 320 ms, growing | a real capture with its name table, goods codes and orders to profile against; the refusal dumps hold only the tables |
| staging and copy in the write | 150 to 210 ms, growing | same |
| offered actions | 176 ms per pause | same |
| world generation during play | 25 s per run | `--pool 1` builds the next world while the current run plays; it competes with the game for CPU and the supervisor arguments are the owner's choice |

## Simplifications and fallbacks noticed

`Fresh.take` and the picker training in `session` both start a one-worker thread pool and poll it once a second to stamp progress. One helper could serve both.

`_absent` is still called for files without any country reference. The call is cheap and keeps its span count comparable with older runs.
