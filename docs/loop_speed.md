# Loop speed

This records what has been done to cut the time the loop spends on its own scaffolding, and what each change measured. Nothing here may change what a run does. Every hour the timing tables are reviewed and this document is replaced with the current state.

Last review: 2026-09-27 07:10, covering runs 248 to 253.

## State

The speedups are live since round collect_65, launched at 06:59:35. Run 253 is the first run on the new code and is playing without errors.

## Measured live

Setup, from the round starting to the first snapshot being written:

| step | old code, runs 244 to 252 | run 253 |
| --- | --- | --- |
| world generation | 22 to 56 s | 15 s, a small world of 22 states |
| picker training | 21 to 25 s, after the game loaded | 31 s, during world generation |
| game launch and load | 31 s | 31 s |
| statistics refresh | 17.7 to 21.6 s | 5.1 s |
| whole setup | 87 to 112 s between runs | 71 s including process start |

During play, mean over snapshots 2 to 80:

| span | run 247 | run 248 | run 250 | run 253 |
| --- | --- | --- | --- | --- |
| validation, ms | 211 | 215 | 206 | 41 |
| whole write, ms | 299 | 324 | 282 | 90 |
| action dispatch, ms | 356 | 362 | 355 | 351 |

Run 253 plays a smaller world than the others, so its capture and row building times are not comparable. Validation and the write are lower by more than world size explains. The write minus validation fell from about 90 ms to 50 ms, and that part is world size.

Training is slower when it shares the machine with world generation, 31 s against 23 s alone. It still finishes before the game would have been ready for it.

## Run function, before and after

| measure | runs 247, 248, 250 | run 253 |
| --- | --- | --- |
| action status | 2380 done, 1 invalid | 616 done, 1 invalid |
| advisor actions per pause | 10.3, 9.3, 8.7 | 9.5 |
| copy calls over snapshots 2 to 80 | 23430, 23405, 23399 | 23423 |
| traceback, stall, crash or block in the round log | none | none |

The copy calls show that a snapshot still writes the same set of tables.

End reasons on the old code since 03:08: time 2, debt_cap 6, loop_lost 1. Run 253 has not ended yet.

## What happened at the rollover

Round collect_63 exited by itself at 06:58:08 with code -1 and no traceback, in the middle of run 252. That run is recorded as loop_lost after 38 minutes of play. The cause is unknown. Nothing from these reviews was acting on the loop at that moment.

The supervisor launched collect_64 on the new code at 06:58:14. A script from this review, which was waiting for the running run to end so that the old round could be stopped between runs, saw run 252 closed and stopped the round that was running. That was collect_64, 72 seconds into its setup. No run row was open, so no run was lost, but one setup was wasted. The supervisor launched collect_65 ten seconds later. The script is not used again.

The supervisor counts two round exits within ten minutes. It blocks at four.

## Changes

| commit | change | before | after | how it was measured |
| --- | --- | --- | --- | --- |
| 7b49bf3 | Statistics refresh runs over eight connections | 17.5 s | 3.6 s offline, 5.1 s live | all 287 tables on the production database; run 253 |
| 7b49bf3 | Picker training runs while the world generates | 25 s after the game loaded | no added wall time | run 253: training ended 16 s after the world and before the game launch finished |
| d6f8025 | Stray province pixels are filled from their coordinates, not by sweeping the whole map | 6.0 s | 1.1 s | same input, identical output array |
| d6f8025 | The minimap is resized from the image in memory, not decoded again from the file just written | 7.8 s | under 1 s | world hash |
| d6f8025 | Road and sea lane cost maps are built for the box being routed, not the whole map | 8.1 s | 4.6 s | world hash |
| d6f8025 | A rewrite pattern runs on a file only when the file contains the text it needs | 4.8 s | 3.1 s | world hash |
| d6f8025 | Validation asks only about tables the snapshot wrote rows to | 210 ms | 41 ms | snapshots 2 to 80, runs 247 to 250 against run 253 |

World generation as a whole, three seeds in sequence: 95.0 s before, 64.3 s after.

## Proof that runs are unchanged

| change | evidence |
| --- | --- |
| world generation | The 717, 711 and 725 files written for seeds 123456, 777 and 31337 hash to the same SHA-256 before and after. |
| validation | A check reads rows of one table at one run and snapshot. Only `Store.write` puts rows there, so a table it wrote nothing to has nothing to check. A test breaks a foreign key and confirms the check still fires for a written table. |
| statistics refresh | The same tables are analyzed, and `write` still returns only after all of them finish. A test confirms the tables are analyzed. |
| picker training | Same data, same parameters, same model. It starts earlier and finishes before the game launches. |

One thing did change order. The picker and the number of candidates are now drawn from the round's random stream before the world size, not after the run seed. The distributions are the same. A round replayed with the same `--seed` draws different values than it did before commit 7b49bf3.

## Where setup time goes now

| step | seconds | can it shrink |
| --- | --- | --- |
| game launch and load | 31 | no, it is the game |
| picker training | 31, overlapped | only the part that outlasts world generation counts |
| world generation | 15 to 40, overlapped | see candidates |
| closing the previous game | 4 | no |
| registration | 3 | small |
| first snapshot with statistics refresh | 9 | the refresh is bounded by its largest table at 2.8 s |

## Looked at and left alone

| item | finding |
| --- | --- |
| action dispatch | Three quarters of actions take 230 to 300 ms and the rest 700 to 1300 ms. The floor is a fixed 100 ms wait plus the game's answer. This is pacing against the game. |
| log tail | 136,000 polls in 30 minutes cost 0.75 s per snapshot interval, mostly on its own thread or inside waits that would sleep anyway. Skipping reads when the size is unchanged would alter how a rotated log is detected. |
| death check while days run | Reads game memory 500 times per snapshot interval, all inside the wait for the game. No wall time to save. |
| vanilla map rasters | 5 s once per round. A disk cache would add invalidation logic for a saving of seconds per round. |
| picker model reuse | The objective is drawn anew for every run and every run adds training rows, so a trained model cannot be kept. |

## Candidates not yet done

| candidate | cost today | what it needs |
| --- | --- | --- |
| training features kept between runs of a round | 6 s per run | rows of finished runs never change, so only new runs need reading; matters only when training outlasts world generation |
| row building per snapshot | 40 to 320 ms, grows with the run and the world | a real capture with its name table, goods codes and orders to profile against; the refusal dumps hold only the tables |
| staging and copy in the write | 50 to 210 ms | same |
| offered actions | 200 to 260 ms per pause | same |
| world generation during play | 15 to 40 s per run | `--pool 1` builds the next world while the current run plays; it competes with the game for CPU and the supervisor arguments are the owner's choice |

## Simplifications and fallbacks noticed

`Fresh.take` and the picker training in `session` both start a one-worker thread pool and poll it once a second to stamp progress. One helper could serve both.

`_absent` is still called for files without any country reference. The call is cheap and keeps its span count comparable with older runs.
