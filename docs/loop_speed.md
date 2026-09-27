# Loop speed

This records what has been done to cut the time the loop spends on its own scaffolding, and what each change measured. Nothing here may change what a run does. Every hour the timing tables are reviewed and this document is replaced with the current state.

Last review: 2026-09-27 07:45, covering runs 253 and 254.

## State

Commits 7b49bf3 and d6f8025 are live since round collect_65, launched at 06:59:35. Runs 253 and 254 used them and show no errors.

Commit 8f59257 is not live. It loads when the supervisor next starts a round. The running round is left to end by itself.

## Measured live

Setup:

| step | old code, runs 244 to 252 | run 253 | run 254 |
| --- | --- | --- | --- |
| states in the world | 41 to 93 | 22 | 63 |
| world generation, s | 22 to 56 | 15 | 24 |
| picker training, s | 21 to 25, after the game loaded | 31, during world generation | 31, during world generation |
| game launch and load, s | 31 | 31 | 33 |
| statistics refresh, s | 17.7 to 21.6 | 5.1 | 5.5 |
| previous run ending to this run row opening, s | 87 to 112 | | 67 |

During play, mean over snapshots 2 to 80:

| span | run 248, 66 states | run 250, 41 states | run 254, 63 states |
| --- | --- | --- | --- |
| validation, ms | 215 | 206 | 58 |
| whole write, ms | 324 | 282 | 167 |
| row building, ms | 107 | 82 | 111 |
| action dispatch, ms | 362 | 355 | 350 |

Runs 248 and 254 play worlds of nearly the same size. The write fell by 157 ms per snapshot, all of it validation. Row building is unchanged, as expected.

## Run function, before and after

| measure | old code, runs 247, 248, 250 | new code, runs 253, 254 |
| --- | --- | --- |
| action status | 2380 done, 1 invalid | 2395 done, 1 invalid |
| advisor actions per pause | 10.3, 9.3, 8.7 | 9.7, 10.1 |
| copy calls over snapshots 2 to 80 | 23430, 23405, 23399 | 23423, 23476 |
| end reasons | debt_cap 3 | debt_cap 1, one still playing |
| traceback, stall, crash or block in the round log | none | none |

The copy calls show that a snapshot still writes the same set of tables.

## Changes

| commit | change | before | after | how it was measured |
| --- | --- | --- | --- | --- |
| 7b49bf3 | Statistics refresh runs over eight connections | 17.7 to 21.6 s | 5.1 and 5.5 s | runs 253 and 254 |
| 7b49bf3 | Picker training runs while the world generates | 25 s after the game loaded | up to 16 s added when the world is ready first | runs 253 and 254 |
| d6f8025 | Stray province pixels are filled from their coordinates, not by sweeping the whole map | 6.0 s | 1.1 s | same input, identical output array |
| d6f8025 | The minimap is resized from the image in memory, not decoded again from the file just written | 7.8 s | under 1 s | world hash |
| d6f8025 | Road and sea lane cost maps are built for the box being routed, not the whole map | 8.1 s | 4.6 s | world hash |
| d6f8025 | A rewrite pattern runs on a file only when the file contains the text it needs | 4.8 s | 3.1 s | world hash |
| d6f8025 | Validation asks only about tables the snapshot wrote rows to | 215 ms | 58 ms | run 248 against run 254 |
| 8f59257 | The game launches as soon as the world is ready, while training finishes | launch waited 7 to 16 s for training | not yet measured | pending the next round |

World generation as a whole, three seeds in sequence: 95.0 s before, 64.3 s after.

## Why 8f59257

World generation became faster than training. In run 253 the world was ready after 15 s and the game then waited 16 s for training. In run 254 it waited 7 s. The game needs only the world. Training is needed at the first pick, which comes after the first snapshot.

What to check when it goes live:

| measure | expected |
| --- | --- |
| game launch and load | near 31 s; training uses every core for part of the load, so it may rise |
| picker training | near 31 s |
| previous run ending to this run row opening | 67 s falling to 50 to 60 s |
| `pick_model` row of the run | present, as now |

If the game load grows by more than the wait it removes, revert the commit.

## Proof that runs are unchanged

| change | evidence |
| --- | --- |
| world generation | The 717, 711 and 725 files written for seeds 123456, 777 and 31337 hash to the same SHA-256 before and after. |
| validation | A check reads rows of one table at one run and snapshot. Only `Store.write` puts rows there, so a table it wrote nothing to has nothing to check. A test breaks a foreign key and confirms the check still fires for a written table. |
| statistics refresh | The same tables are analyzed, and `write` still returns only after all of them finish. A test confirms the tables are analyzed. |
| picker training | Same data, same parameters, same model. It is joined before the loop is built, so the run row and the first pick see the trained model as before. |

One thing did change order. The picker and the number of candidates are now drawn from the round's random stream before the world size, not after the run seed. The distributions are the same. A round replayed with the same `--seed` draws different values than it did before commit 7b49bf3. Commit 8f59257 moves no draw.

## The rollover at 06:58

Round collect_63 exited by itself at 06:58:08 with code -1 and no traceback, in the middle of run 252. That run is recorded as loop_lost after 38 minutes of play. The cause is unknown.

The supervisor launched collect_64 at 06:58:14. A script from the fourth review, waiting to stop the old round between runs, stopped collect_64 by mistake 72 seconds into its setup. No run row was open and no run was lost. The supervisor launched collect_65 ten seconds later. The script is not used again, and rounds are left to end by themselves.

## Where setup time goes now

| step | seconds | can it shrink |
| --- | --- | --- |
| game launch and load | 31 to 33 | no, it is the game |
| picker training | 31, overlapped | it no longer holds anything up once 8f59257 is live, unless it outlasts world and game together |
| world generation | 15 to 40 | see candidates |
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
| training features kept between runs | Worth 6 s of training, which no longer holds up the launch. |

## Candidates not yet done

| candidate | cost today | what it needs |
| --- | --- | --- |
| row building per snapshot | 40 to 320 ms, grows with the run and the world | a real capture with its name table, goods codes and orders to profile against; the refusal dumps hold only the tables |
| staging and copy in the write | 50 to 210 ms | same |
| offered actions | 200 to 260 ms per pause | same |
| world generation during play | 15 to 40 s per run | `--pool 1` builds the next world while the current run plays; it competes with the game for CPU and the supervisor arguments are the owner's choice |

## Simplifications and fallbacks noticed

`Fresh.take` and the picker training in `session` both start a one-worker thread pool and poll it once a second to stamp progress. One helper could serve both.

`_absent` is still called for files without any country reference. The call is cheap and keeps its span count comparable with older runs.
