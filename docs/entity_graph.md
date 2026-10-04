# Recurrent full-world graph model

Graph version 5 uses quarterly blocks without synthetic time-advance actions. Old packed datasets and models must be rebuilt. Each graph contains one current observation; entity and global recurrent states carry run history.

## Observation and action state

Preparation streams snapshots chronologically through the last decision, including intermediate and same-time observations. `build_world(data)` builds the current world. Training and inference keep proposals separate.

Run-local indices use `(kind, key)` pairs and survive reordering. IDs support topology and memory lookup, never numeric features. New identities start at zero; absent identities retain memory for reappearance. Memory resets between runs, epochs and splits and grows with the union of identities.

`Network.observe` combines features, previous state and elapsed time. Node GRUs precede spatial message passing. Player and equal-weight type summaries update global state. Elapsed time uses `log1p(days since the preceding observation)`; same-time frames still update.

`Network.propose` evaluates action deltas using current world embeddings. Blocks retain positions, parameters and typed links. The head returns five horizons by four components. Alternatives never mutate observation memory. `Network.commit` applies only the recorded or selected proposal's global and touched-entity states. Recorded choices remain eligible regardless of validation or execution outcomes.

## World structure

Entities and relationships cover countries, states, provinces, populations, buildings, ownership, markets, politics, diplomacy and military structures. References supply typed edges and inverses; definitions connect named concepts. Referenced identities without live rows become explicit unobserved nodes. No population aggregation, foreign-world deletion, military pruning or neighbor sampling is performed.

UI feeds, action availability, validation, verification, picker predictions and selection flags are excluded from model features and training selection.

Geography includes rasters, wrapping, coastlines, borders and crossings. Game coordinates use a bottom-left origin, raster coordinates a top-left origin. Formations and fronts connect to containing provinces and states, retaining recorded references. Positioned formations have relative-geometry facts to other positioned formations, states and fronts. Nearest-boundary distances retain all ties. Missing positions are audited. Geometry does not establish travel time or access permissions.

## Preparation

`replay.ReplayReader` streams changed rows in 16-observation chunks using pipelined binary queries. Presence, removals, children and visibility match `world.WorldReader`. Samples require both recording sequence and game time to permit visibility. Rewinds and decreasing game time fail.

Construction caches field names, relations and definitions. Encoding groups attributes before NumPy assignment. Numeric values stay float64 until normalization and become float32 afterwards. SciPy supplies connectivity and boundary searches. `ReplaySnapshot` reuses reconstructed rows for candidate generation while other tables remain accessible through the stored reader.

Workers prepare independent runs chronologically. Each frame is encoded once with stable identities. Decision frames include recorded action deltas, labels and alternatives. Each held-out decision receives 30 blocks from `loop.run.redraw`, capped at sixteen actions and containing no synthetic wait. Decisions occur on the first day of each quarter. Graph version checks reject incompatible saved artifacts.

Long jobs use the detached broker. The quarterly reset cancels old-data workers and removes saved source, packed and trained datasets. Earlier experiment reports are historical records only.

## Training and inference

Default width is 48, with three world message rounds, two action rounds and four-observation backpropagation chunks. Training shuffles runs and preserves frame order inside each run. Masked losses accumulate per chunk before clipping and optimization. Entirely unlabelled chunks make no optimizer update. Memory persists between chunks while gradients detach.

Targets span 90, 180, 365, 730 and 1,095 days for GDP, population, standard of living and constructed stock. Masks represent observable outcomes and horizon coverage, never action validation. Run splits remain disjoint. Candidate evaluation uses fixed held-out alternatives.

Inference observes in order, evaluates alternatives from one shared state and commits only the chosen block. Tests cover removals, reappearance, historical actions, topology, visibility, replay, creation and inference. Spatial accessibility probes vary geometry and an ordinary prior action and check later predictions and gradients. Keep test commands below twenty seconds; full training runs separately through the broker.
