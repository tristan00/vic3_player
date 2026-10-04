# Timing

`interface/timing.py` measures wall-clock spans using `time.perf_counter_ns`, aggregates durations, and logs completed spans. `interface.common.timed` records at INFO level and updates watchdog progress on entry and exit. `timed_often` records at DEBUG level without updating watchdog progress. Dashboard timing uses its own logger.

Place timing decorators below properties, staticmethod declarations, and caching decorators. Applying the timer below a cache measures misses. Synchronous timing decorators reject generators and coroutines.

`tests/test_timing_coverage.py` checks functions under interface, loop, advisors, and dashboard/server. Each applicable function needs a timing decorator or a specific exemption in `tests/timing_exempt.json`. Exemptions describe hot paths, persistent loops, timers, monitors, declarations, and manually invoked tooling. Stale exemptions fail the check. Nested functions and special methods other than constructors are covered by their callers.

Explicit spans can measure a subsection:

```python
from interface.timing import span

with span('model_fit', 'loop') as elapsed:
    model.fit(features, targets)
```

`elapsed.ms` and `elapsed.seconds` provide current or final duration. `current()` returns the innermost span. Function span names follow source paths relative to the project root. Moving models changes their timing names to their new modules.

The recorder stores calls, errors, total and exclusive durations, exact extrema, and approximate percentiles. Percentiles use eight logarithmic buckets per doubling. Nested spans overlap; concurrent worker spans overlap too. Do not add them to infer elapsed run time. A worker span is not subtracted from the waiting thread's exclusive time.

Exceptions record a failed span and propagate. Recording works when INFO logging is disabled. Only completed spans can be drained. The current snapshot write appears in a later interval, and spans still open at the final write are absent from that write.

`run_timing` stores accumulated run totals. `snapshot_timing` stores calls completed since the previous snapshot write. Their structured schemas are in `interface/recording/schema_meta.sql`. Background workers transfer their timing records for merging into the run recorder.

Game waits include action pacing, dispatch preparation, acknowledgements, captures, time advancement, and pause settling. A wall-clock span around a game wait is not a CPU measurement. Use process and thread CPU measurements when diagnosing utilization.

CatBoost fitting reports iteration progress through `advisors/models/boosting.py`. The row tuner additionally monitors elapsed fitting time and validation error. Tuning logs must reveal a slowdown while the fit is running, not only after it finishes.

The dashboard exposes run and API timings. Compare identical inputs where possible, report the measurement window, and separate preparation, fitting, prediction, and game simulation time. Functional verification must accompany performance comparisons.
