# Training performance

Both CatBoost pickers fit fresh estimators at each learned-picker start using the fixed `endgame_three_v1` target. The quarterly reset removes observations and saved training/model datasets while retaining production hyperparameters. Earlier variable-duration or log-reward benchmarks do not measure the current data and target.

## Installed configuration

The authoritative files are `advisors/models/row/parameters.json` and `advisors/models/histogram/parameters.json`. Row models retain fifty trees, depth nine, Depthwise growth and one-hot threshold eight. Whole-block models use four hundred trees, depth ten and Depthwise growth. Both use eight threads. Collection fits estimators instead of loading experiment models.

The row configuration came from completed entropy trial 102 in the stopped October 1 search. Its historical fit took 12.866 seconds and its worker took 15.413 seconds. This is provenance for the earlier schema and observations, not a guarantee for current data or reward.

## Runtime paths

The row picker encodes and predicts unique action/parameter pairs once per pause, then restores multiplicity before averaging. Pandas categorical storage preserves strings. Whole-block encoding selects histogram columns directly. Completed-run caches reuse state and the three reward parts and load only new or changed runs. Cache versions include end reason as well as date bounds.

Blocks contain at most sixteen actions, including answers. Decisions occur quarterly. Time advancement is neither an action nor a feature. Whole-block size matrices contain only action count. Both pickers normalize targets to the first snapshot of each pause and use its remaining horizon. Old prepared data require regeneration. Replacing the database requires restarting workers, because a DSN and reused bounds cannot identify a reset.

## Measurement and tuning

Use function timings and training metadata to distinguish loading, encoding, fitting and prediction. Nested and concurrent spans overlap. Keep tests below twenty seconds. Full searches and measurements run through `interface.runner.session._spawn`, the detached process broker.

Row searches fix fifty trees and impose a twenty-second worker wall deadline. Whole-block searches tune tree count within a depth/tree budget and impose a thirty-second deadline. Limits include startup, preparation, fitting and prediction. Incomplete and timed-out fits cannot win, and models are not truncated at a best validation iteration.

The row tuning objective equally blends normalized reward loss and differentiation entropy. Whole-block tuning uses a 10/90 blend over alternatives at held-out pauses. See `advisors.md` and `histogram_tuning.md`. Action validation outcomes never enter features or row eligibility.

Avoid concurrent tuning and collection when measuring throughput. Reproduce winning metrics and saved-model predictions under the applicable deadline before installing parameters. Keep complete runs disjoint across training and validation and record input hashes, configurations and runtime evidence.
