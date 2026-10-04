# Action execution and verification

Candidate generation and model scoring read PostgreSQL snapshots. Victoria 3 applies commands through injected native GUI callbacks. The web dashboard is not part of execution or acknowledgement.

## Request lifecycle

`Executor.run` advances the native request sequence, wrapping after the maximum signed 32-bit value. It writes parameters with execution disabled, retains the 100 ms prime interval, then enables execute or check mode. Flip bits and the sequence's fired marker prevent missed or duplicate action triggers.

Key binding runs only while `interface_mode` is zero. Entering execute or check mode resets that trigger before the next request. Consecutive requests can therefore bind the same decree, event namespace, production method or other key. Previously a hidden widget could retain a true trigger after its ready flag was cleared, causing an identical key to wait until timeout.

A new request starts after the previous completion acknowledgement. There is no additional inter-action gap or minimum cycle. The prime interval and native panel, stage, transport and cleanup timers remain. Acknowledgement polling is five milliseconds, with a five-second request limit and a bounded abort wait.

## Memory writes

Country script variables live in movable native storage. Events can move that storage and a player-country change selects a different store. Addresses cannot be retained across delays, callbacks or acknowledgement waits.

Every control-variable write uses `Reader.write_variables`: briefly suspend the game, resolve the current player's variables, write, and resume in a finally block. Parameters, activation, abort, abort cleanup and capture requests use this path. Missing variables raise an error. No suspension spans a prime interval or acknowledgement wait.

Historical relocation evidence remains in `artifacts/performance/crash_dump_evidence.json` and `crash_replay.json`. These explain the protected write path rather than establish current throughput.

## Acknowledgements and recording

Execute and check variants set native validity before deferred cleanup. Completion logs the sequence, literal zero or one, and description, then clears the active action and key. Only complete log records after the request mark are accepted. Missing acknowledgements trigger abort and become lookup failures; malformed or duplicate acknowledgements raise verification errors.

Military transport requires an explicit matching started result. Refused and no-fleet results remain failures even if opening the planner was valid. Another request's transport result cannot override the current result.

The loop records refusals and absent objects immediately. Valid acknowledged actions enter the pending list, then receive a post-action snapshot and checks for unresolved windows, events and proposals before completion is recorded. Outcomes retain their diagnostic meanings.

Execution validity is neither a model feature nor a training-row selection criterion. Time advancement is infrastructure and is excluded from selectable action blocks.

## Verification

`tests/test_verification.py` covers protected writes, resuming after errors, sequences, key reset, priming without extra pacing, transport results and malformed acknowledgements. Generated-GUI tests check callback structure. Tail tests check rotation and incremental reads. Quarterly tests check the calendar and action cap.

The optimization invocation passed 46 tests in 4.908 seconds. Live comparisons use the same 15-country, 95-state world, including repeated commands, alternating keys, panel setup, captures, all four quarterly pauses and year rollover. Fixed configurations also execute twenty identical keyed requests. Evidence is under `artifacts/loop_optimization`; `report.json` records the selected configuration and `rollout.json` records resumed collection progress.
