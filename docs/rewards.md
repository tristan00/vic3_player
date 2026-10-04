# Rewards and model targets

## Fixed three-metric reward

`advisors/data/endgame.py` owns `endgame_three_v1`, shared by the forest and SVR sampler initializers, both CatBoost pickers and the dashboard. Its metrics are constructed building stock, population and GDP. Building stock sums levels times construction costs in states owned by the player.

Let `T` be the scoring interval in game years. Divide each metric by its starting value to get normalized stock `k`, population `p` and GDP `g`. For each normalized metric `x`, define `dx = (x(end) - x(end - w)) / w`, where `w = min(1, T)` years:

```text
R = (sqrt(T) * (k + dk) / 2 + 6*T*dp + (g + dg) / sqrt(T)) / 9
```

The stock part is `(k + dk) / 2`, the population part is `dp`, and the GDP part is `(g + dg) / 2`. Their weights are `1/9`, `6/9` and `2/9`; their duration factors are `T^0.5`, `T` and `T^-0.5`. These fixed values replace the sampled legacy objective for all four learned methods. Living standards do not enter the reward.

## Baselines and ending outcomes

Initializers score complete runs from the exact opening snapshot. Observations retain the actual score; forest and SVR fitting uses rank-normalized scores. Initializer eligibility requires one recorded advisor and positive recorded sampling weights for every action in the fitted space.

Both pickers score the remaining interval from the first snapshot at the pause's game timestamp to the run's final recorded timestamp. All starting values and duration use that pause. Multiple action snapshots at one timestamp share the same reward baseline. Row metadata records the action's `before_seq` separately from the reward's `baseline_seq`.

When the final-year window reaches the interval's beginning, its earlier normalized value is exactly one. Otherwise, use the latest recorded value at or before the window boundary. At duplicate timestamps the last measurement governs the following interval; the first snapshot still defines the baseline.

Recorded defeat sets all three ending values to zero before calculating recent changes. Debt cutoff retains the recorded measurements. Starting values must be positive and finite, and duration must be positive. Zero ending values are valid. Rows with missing or nonpositive starting measurements, no future duration or missing required model state are omitted. There is no synthetic baseline or log floor.

Each row action receives the complete subsequent reward, without action-count division or sample weighting. Histogram rows receive the complete subsequent block reward. These targets associate actions and context with later outcomes without identifying isolated causal credit. Piecewise averaging applies during candidate selection.

## Dashboard

Policy overview and reward tables score completed runs with the shared scorer. Configuration comparisons report median current reward, median ending changes and median final-year changes for the three metrics. Unscorable runs remain visible with no score and are excluded from those medians.

A run's reward page shows its opening baseline snapshot, duration, recent window and each metric's normalized ending value, recent change, reward part, weight, duration exponent, time factor and contribution. A learned picker's decision page shows the same breakdown from the pause's first snapshot, even if the selected decision snapshot comes later at the same timestamp.

`GET /api/policy/runs/{run_id}/reward` returns the run-opening breakdown. Adding `?seq={snapshot}` selects that snapshot's pause. A missing run or snapshot returns 404; unavailable scores include a reason. Both paths use `Trajectories` and the canonical `breakdown` function used by model targets.

Saved predictions, initializer observations, model settings and feature importance remain historical records. They are not recalculated or relabeled as results of newer training. Sampled four-component weights and alpha remain under the collapsed legacy objective record and do not control current scores. `advisors/data/rewards.py` retains legacy calculations and shared trajectory utilities; dashboard reward tables no longer call its log scorer.

## Dashboard loading and refresh

The server shares completed-run scores between policy pages. Each request checks eligible run IDs, start dates, end dates and end reasons, then recalculates only new or changed runs. It drops removed runs and remembers unscorable runs without repeatedly reconstructing them. Concurrent requests share one calculation. Reopening the database pool clears reuse. Editing historical metric values without changing scoring bounds or end reason requires restarting the dashboard.

Visible browser tabs poll `GET /api/stamp` every three seconds after the previous poll finishes. Hidden tabs stop polling and check immediately when shown again. Polling uses short requests instead of permanent event streams that occupy browser connections. Changed stamps queue one refresh behind an active data request; navigation and unmounting cancel obsolete requests. A slow initial load can finish despite incoming live updates.

The October 3 comparison requested policy runs and configuration medians concurrently while collection continued. Request times fell from 1163/1166 ms to 72/73 ms with the completed-run cache populated; both JSON responses were identical. Initial cache population still reconstructs history once. Evidence is in `artifacts/dashboard_loading_20261003`. API timing remains available through `Server-Timing` and the dashboard log.

## Model caches and prepared data

Completed-run model caches retain features and the three unweighted reward parts. Versions include start date, end date and end reason, so changing defeat status reloads targets even when timestamps are unchanged. Removed runs are dropped; a new database DSN clears the cache. Replacing a database at the same DSN requires restarting workers.

Fresh row and histogram preparation records the fixed reward specification. Data prepared for the former log reward must be regenerated before tuning. Existing production hyperparameters remain installed; each learned-picker start fits a new estimator. Model and proposal schemas remain compatible, including the general SMAC composite-reward tag.

Action validation, verification and execution results never enter reward inputs, model features or training-row selection. Checks cover the equation, shortened windows, duplicate timestamps, defeat, zero endings, independent run scores, first-pause baselines, cache invalidation and dashboard breakdowns. Dashboard checks also cover concurrent cache access, failed-refresh recovery, queued requests, navigation cancellation and visibility-aware polling.
