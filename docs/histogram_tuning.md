# Whole-block CatBoost tuning

The `catboost` picker predicts the fixed `endgame_three_v1` reward for complete blocks. `advisors.models.histogram.tune` minimizes ten percent normalized reward loss plus ninety percent candidate prediction entropy loss.

## Data and preparation

Collection pauses quarterly, with at most sixteen actions per block including answers. Time advancement is not an action or input. Histogram size matrices contain only action count; recorded, live and frozen-candidate encoders have no sampled-duration column. Production parameters remain installed across the quarterly data reset, and each learned-picker start fits a new estimator.

```powershell
.venv/Scripts/python.exe -m loop.prepare_histogram_tuning --output artifacts/endgame_histogram_data --folds 4 --pauses 300 --candidates 30 --seed 0
```

Launch long preparation through `interface.runner.session._spawn`, the detached process broker. The output directory must be new. Outputs contain features, targets, the fixed reward specification, pause IDs, partitions, sparse candidate histograms, metric configuration, seeds and timings. Datasets prepared with the previous log reward must be regenerated.

Targets use building stock, population and GDP through the equation in `rewards.md`. Starting values are taken from the first snapshot at the pause's timestamp. Duration is the remaining game time from that pause to the final recorded snapshot. Recorded defeat zeroes the terminal metrics. Randomly drawn legacy objective weights and alpha do not control these targets.

Four folds group by complete run. Each recorded row gets one held-out prediction. Up to three hundred held-out pauses per fold receive thirty alternatives. `loop.run.redraw` reconstructs snapshots, recorded weights, available actions, conflicts and pending answers. Blocks obey the sixteen-action cap and retain parameters. Alternatives are frozen across trials, including changes to histogram selection. Unseen bins remain absent, matching live prediction.

Invalid partitions, zero reward variance, mismatched shapes and nonfinite data fail explicitly. Action validation and execution results never select training rows or features.

## Search objective

Fold reward loss is held-out RMSE divided by the training reward standard deviation. Overall reward loss weights folds by held-out row count. Entropy averages sampled pauses equally. At each pause, sort predictions into groups with maximum span `1e-6 * fold_training_reward_std`. With `n` candidates and fraction `p` in each group:

```text
pause_entropy = -sum(p * log(p)) / log(n)
entropy_loss = 1 - mean(pause_entropy)
score = 0.1 * reward_loss + 0.9 * entropy_loss
```

Lower is better. All predictions tied yield zero entropy. Repeated candidates remain repeated observations. Magnifying an outlier without changing ties cannot improve entropy. Differentiation does not establish correct ranking.

## Search and installation

Defaults are four hundred trials, eight fitting threads and a hard thirty-second wall deadline per trial. The deadline includes startup, preparation, fitting and prediction. Timed-out workers cannot win. Complete folds retain every requested tree; a tree/depth budget caps expensive settings.

Whole-block and row searches share CatBoost ranges and conditional rules, except whole-block tree count is tunable while row models keep fifty trees. Histogram inclusion and most-common-bin counts add whole-block controls. The installed configuration initializes the search; later proposals use the repository's random-forest surrogate and expected improvement.

Search records contain the input hash, reward specification, bounds, incumbent and deadlines. Requests and results identify each trial, and status identifies the best completed score. Cancellation prevents installation. Different data or rewards require a new search.

Finalization requires completed trials, matching data and reward, and a consistent best finite score. It reproduces winner metrics under the deadline, fits all rows separately, reloads the estimator and verifies exact prediction equality before atomically installing parameters and sizes.

Focused checks cover partitions, entropy, encoding, redraws, deadlines, parameter parity, worker reproducibility and finalization. Keep each test invocation below twenty seconds; full searches run separately through the broker.
