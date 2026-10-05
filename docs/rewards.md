# Rewards and model targets

## The reward

`advisors/data/endgame.py` defines the single reward, `endgame_three_v1`. The forest and SVR initializers, both CatBoost pickers and the dashboard call the same functions.

| Metric | Value |
| --- | --- |
| `stock` | Building levels times the construction cost of their type, summed over the states the played country owns. Types without a construction cost are left out. |
| `population` | Lower, middle and upper strata of the played country, summed. |
| `gdp` | GDP of the played country. |

`T` is the scored interval in game years of 365 days. Each metric is divided by its baseline value, giving `k`, `p` and `g`. For a normalized metric `x`, `dx = (x(end) - x(end - w)) / w` with `w = min(1, T)`.

```text
R = (sqrt(T) * (k + dk) / 2 + 6 * T * dp + (g + dg) / sqrt(T)) / 9
```

| Metric | Part | Weight | Exponent of `T` |
| --- | --- | --- | --- |
| `stock` | `(k + dk) / 2` | 1/9 | 0.5 |
| `population` | `dp` | 6/9 | 1 |
| `gdp` | `(g + dg) / 2` | 2/9 | -0.5 |

A metric contributes its weight times `T` raised to its exponent times its part. The three contributions sum to `R`. Standard of living is not part of the reward.

A value at a time is the latest measurement at or before it, so the last of several snapshots sharing a timestamp counts. When `T` is at most one year the window starts at the baseline and `x(end - w)` is exactly 1.

`breakdown` raises when the interval is not positive, when a baseline is not positive and finite, or when a ratio is negative or not finite. An ending value of zero is valid.

## Scored runs

`scored_runs` and the `ENDED` and `PLAYED` clauses in `advisors/data/rewards.py` choose the runs. A run is scored when it was played on a generated mini world, has ended, and either ended as `time`, `years`, `defeated` or `debt_cap` or holds at least one game year between its first and last snapshot. Vanilla runs are never scored. The interval always ends at the run's last recorded game date.

`Trajectories.reason` leaves a start out when no game time follows it, when a metric has no measurement at or before it, or when a baseline is zero, negative or not finite. Nothing is substituted for a missing baseline.

## Ending outcomes

| End reason | Cause | Reward |
| --- | --- | --- |
| `time` | The round's wall-clock limit passed | Recorded values |
| `years` | The round's limit in game years passed | Recorded values |
| `debt_cap` | At the start of a turn, `principal` in `player_treasury` is positive and at least `credit` | Recorded values |
| `defeated` | The played country owns no state | All three ending values are zero. The values at the start of the window stay as recorded. |
| `ui_stuck`, `game_crashed`, `loop_crashed`, `loop_lost`, `loop_stalled` | The round broke off | Recorded values, and only when at least one game year was recorded |

## Baselines

### Initializers

`advisors/data/weights.py` scores each run from its opening snapshot to its last. `history` keeps a scored run when it has exactly one initializer in `run_advisor` and a positive weight in `run_weight` for every lever being fitted. The fitted levers are all those not switched off with `--weight name=0`. Features are the base-10 logarithms of the lever weights. Both learned initializers raise when no run qualifies.

Fitting uses `normalized` rewards: each reward is replaced by the normal quantile of its rank. The forest's `best_reward` and predictions and the SVR's `predicted_reward` are on that scale. `smac_observation.reward` and `svr_observation.reward` hold the actual reward; `svr_observation` also holds the normalized value and the bootstrap draw count. The forest's proposal is stored with the reward tag `composite`.

### Pickers

Both pickers read every recorded act and its parameters from `loop_action.advisor_action` and `loop_decision_param`. The interval runs from the game date of the act's `before_seq` snapshot to the run's last recorded date. The baseline is read at the first snapshot with that game date, so every act of a pause has the same baseline and the same target.

| Picker | Rows | Target |
| --- | --- | --- |
| `catboost` | One per pause, built in `advisors/models/histogram/data.py` | Reward of the remaining interval |
| `catboost_piecewise` | One per act, built in `advisors/models/row/data.py` | The same reward for every act of the pause, undivided and unweighted |

Row metadata records `before_seq` and `baseline_seq` separately. A pause is also left out when its state features are missing. The target covers everything after the pause; it does not isolate the effect of one act. When it picks, `catboost_piecewise` averages its act predictions over each candidate block.

## Validation and execution

Whether a command or its act validated, verified or executed never enters reward inputs, model features or the selection of training rows. The two training queries read the act, its parameters and `before_seq`. They do not read `loop_action.status`, `detail`, `after_seq` or `ms`, and acts of every status are kept. The reward reads snapshot dates, the three metrics, state ownership and the `run` row: kind, player country, end time and end reason. The only filter on whole runs is the one under Scored runs.

## Sampled objective

`loop/run.py` still draws four weights and an exponent for every run with `draw_objective` and stores them in the `objective_*` columns of `run`. No initializer, picker or dashboard score reads them. The policy run page lists them as the legacy recorded objective.

`advisors/data/rewards.py` supplies the reward with `built`, `value_at`, `scored_runs`, its SQL fragments and `COSTS`, and supplies the run page's outcome charts with `series`. Its log-growth functions `mean_log`, `growth`, `reward`, `combine`, `breakdown`, `outcomes` and `rewards` have no caller outside the tests.

## Dashboard

`reward_scores` in `dashboard/server/runs.py` scores every scored run with `endgame.outcomes`. `dashboard/server/policy.py` builds two tables from it, and a third route explains one run.

| Route | Content |
| --- | --- |
| `/api/policy/runs` | One row per run: years, window, and for each metric the ending ratio, recent change, part, weight, exponent, time factor and contribution, then the reward. A run without a score keeps its row with those cells empty. |
| `/api/policy/configs` | One row per initializer and picker: runs, scored runs, median reward, median ending change of each metric in percent, median final-year change of each metric in percent per year, median years. Unscored runs count as runs and stay out of the medians. |
| `/api/policy/runs/{run_id}/reward` | The breakdown of one run from its opening snapshot. `?seq=` starts at the first snapshot sharing that snapshot's game date. |

The reward route answers 404 for a missing run or snapshot. Without a score it returns no parts and an `unavailable_reason`: the run has not ended, is not a scored run, has no game time after the snapshot, lacks a starting metric, or has a baseline that is not positive and finite. It builds `Trajectories` for the one run on every request and calls the same `breakdown` as the model targets.

`dashboard/ui/src/components/Reward.tsx` shows the baseline snapshot, the years, the window and the table of parts. `dashboard/ui/src/routes/PolicyRun.tsx` shows it for the run under "Rewards & outcomes" and, with `seq`, for a decision snapshot of a learned picker. Recorded picker predictions, initializer proposals and observations, model settings and feature importances are shown as stored. Only reward breakdowns are calculated on request.

### Score cache

`reward_scores` holds one lock for the whole call. It reads each scored run's first date, last date and end reason, recalculates only the runs that are new or whose three values changed, and forgets runs that are no longer scored. A run that cannot be scored is remembered by its three values and not retried. Requests arriving together wait for the lock and reuse the result. A failed calculation leaves the previous state for the next request. Opening a new connection pool discards the cache. Editing recorded metric values without changing those three values is not noticed until the dashboard restarts.

### Refresh

While the tab is visible, `dashboard/ui/src/lib/live.ts` requests `/api/stamp` three seconds after the previous request finished, with a ten-second timeout. A hidden tab stops and cancels the request in flight; it asks again as soon as it is shown. The stamp changes with the newest run, the number of open runs, the latest end time, and the newest run's last snapshot and command numbers. A changed stamp refreshes every live request on the page.

`latestRequest` in `dashboard/ui/src/lib/requests.ts` runs one request at a time for each data hook. A refresh that arrives during a request is queued once behind it, so a slow first load still finishes. Leaving the page cancels the request and its queued refresh.

Every `/api/` response carries a `Server-Timing` header with its total and its six slowest spans, and the same figures go to the dashboard log.

## Model caches

Each learned picker owns a `TrainingCache` that lives as long as the loop process. It keeps, per run, the features, the years and the three reward parts; the target is computed from years and parts on every load. Each learned-picker start fits a new estimator with the installed `parameters.json`.

A run is reloaded when its first date, last date or end reason changes, so a change from `debt_cap` to `defeated` alone reloads it. Runs that are no longer scored are dropped. A failed load does not mark runs as loaded. A different DSN clears the cache. A database replaced under the same DSN is recognised only through those three values, so restart the loop process after replacing one.

`python -m advisors.models.row.prepare` and `python -m loop.prepare_histogram_tuning` store the reward specification `OBJECTIVE` with the data they write.

## Tests

| File | Covers |
| --- | --- |
| `tests/test_endgame_reward.py` | The equation, intervals under a year, duplicate timestamps, the window start, defeat, zero endings, zero baselines and zero duration, run and pause baselines, both picker datasets, cache reload on a changed end reason, dashboard breakdowns against training targets |
| `tests/test_training_cache.py` | Reuse, changed and removed runs, a different DSN, failed loads, targets unchanged by other runs |
| `tests/test_dashboard_cache.py` | Reuse and refresh of scores, simultaneous requests, a failed refresh |
| `dashboard/ui/tests/requests.test.mjs` | Queued refreshes, cancellation on leaving, recovery after a failed request, polling that stops while hidden |
| `tests/test_loop.py` | The debt cap, rank normalization, initializer proposals |
