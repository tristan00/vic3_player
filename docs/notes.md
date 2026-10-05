# Notes

What the code cannot say for itself: how the collection is run, what the owner has ruled, and what was learned from the running game. This folder is capped at 200 lines.

## Collection

A batch has been running since 5 October 2026, 00:12, on an empty database, under the catalogue of 93 levers and 341 acts.

| Setting | Value |
| --- | --- |
| Runs | 697 completed runs |
| Checkpoint | `D:/vic3_data/interface/collection_levers_93.json` |
| World cache | `D:/vic3_data/interface/world_cache_states50_20261004` |
| Initializers | `random`, `random_smac_weighting`, `random_svr_weighting` |
| Pickers | `first`, `catboost`, `catboost_piecewise` |
| Warmup | 10 runs |
| Run limits | 12 minutes of wall clock, 100 game years |
| Logs | `supervisor.log` and `collect_<n>.log` under `D:/vic3_data/interface` |

```powershell
.venv/Scripts/python.exe -m loop.launch --world-cache D:/vic3_data/interface/world_cache_states50_20261004 --runs 697 --minutes 12 --years 100 --advisors random random_smac_weighting random_svr_weighting --pickers first catboost catboost_piecewise --warmup 10 --progress-file D:/vic3_data/interface/collection_levers_93.json
.venv/Scripts/python.exe -m loop.stop
.venv/Scripts/python.exe -m loop.watch collect_<n> <launch time>
```

Runs 1 to 3 of this batch were recorded before the construction limit existed; the collector was restarted on a run boundary at 00:33 and every later run has it.

A collector keeps the code it started with. A change in the working tree takes effect when the next collector starts, including one the supervisor starts after a crash. To switch on a run boundary, stop the collection right after the checkpoint advances, when no run is open, and launch again with the same arguments.

A healthy launch shows all of these.

- The supervisor, the collector and the game are running, and `supervisor.log` has a `LAUNCHED collect_<n>` line.
- The open row in `run` has a fresh heartbeat and 93 rows in `run_weight`.
- The collector's log gains a `quarterly pause` line for every quarter.
- The checkpoint rises by one for each completed run.

### Changing the catalogue

Runs recorded under one catalogue cannot be read under another: the learned initializers drop runs that lack a weight for a lever, and the row encoder raises on an act it does not know. A changed catalogue therefore starts on an emptied database with a new checkpoint file set to zero. The supervisor does not create a named checkpoint. The checkpoint files of earlier batches count runs that no longer exist and must not be reused.

### World cache

The cache holds 1000 worlds built with seed 2026100450, with 20 to 50 states and 2 to 10 countries each. It is bound to the files under `interface/world`, to `interface/script.py` and to the game binary. Editing any of them makes the collector refuse the cache, and rebuilding takes hours.

```powershell
.venv/Scripts/python.exe -m interface.world.cache build --directory <new directory> --count 1000 --workers 12 --seed 2026100450
```

## Owner's rulings

- Batch size, lineup, checkpoint resets and deletion of recorded data are the owner's decisions.
- No timeout changes without the owner's direct approval. The five are: no clock tick after unpausing 5 s, no loop progress 5 s, command acknowledgement 5 s, date still moving after a pause 3 s, preparation before a run 180 s.
- The game side refuses a request whose target is not in the game's own list after 0.5 s plus 0.2 s per stage. Without it the request waits out the five-second acknowledgement limit.
- No construction is offered while the government queue is a year long or longer, at the pace it is being built.
- The test suite runs on a tenth of the machine's cores at low priority and stays under twenty seconds.
- The game is launched without debug mode, and a command counts as working only when it works that way.

These actions are out of scope and must not be added.

- Changing every building of a type across the whole country.
- Auto-expand, including the per-state form.
- Releasing a country.
- Forming a country, ignoring a formable country, supporting a formation candidate, and unification or leadership plays and war goals.

Names, colours and flags, saving and loading, game rules, observing and switching the played country are left out because they do not change the played country's game.

## What the game does

Learned by running version 1.13.11 without debug mode.

| Area | Behaviour |
| --- | --- |
| Load | A test game takes about two cores and 20 GB while paused, and about 30 s to load |
| GUI | Edited GUI files reload only in debug mode; without it every change needs a relaunch |
| Lists | When a command changes a list the game rebuilds the list's items, and a rebuilt item behaves as newly created |
| Treaties | A country considers one proposal from us at a time and refuses a second |
| Treaties | The game keeps a draft per country after its panel closes |
| Treaties | After a country declined a demand, the game stopped listing that article for it in three of four games, although its add button's conditions held |
| Treaties | "Make this work" adds articles on our side at once; in the one case seen it added three |
| Treaties | An input menu opened for an article that takes no input crashes the game |
| Plays | The game lists only the war goals it allows for the play; a humiliation play listed conquering a state and enforcing a treaty article |
| Plays | Regime change is marked as a debug war goal and never appears without debug mode |
| Sways | We can court one country at a time |
| Sways | The panel lists kinds of offer by availability; obligations, war goals and state transfers were seen, pacts and subjection never |
| Pacts | An ended pact stays in the game's object table until the next month begins |
| Fleets | A named flagship is locked for five years; so is a granted charter |
| Methods | The national standard method of a building type follows building levels, and a tie sets none |
| Straits | The game's strait iterator on a country gives only straits with a land endpoint in it, so endpoints are recorded only for straits the played country borders |
| Construction | Offered without limit, government construction grew the queue to between 7 and 34 years within a few pauses |

### Rules that still offer what the game refuses

- A treaty article that needs the giver to control a strait, for every other country, when the played country borders no strait. Recording every strait's endpoints would settle it.
- Treaty articles whose conditions rest on power projection, rank, relations or strategic adjacency.
- National decisions the game refuses for a missing character or condition.
- Leaving a power bloc inside its lock period.

In the first run of the batch 44 of 334 commands were refused, each with the game's own reason or the one-second answer for a missing list entry, and none went without an acknowledgement.

### Not yet seen working in a game

The test worlds offered no case for these.

- A play or war goal to liberate a country: generated worlds define none that can be created.
- Region charters: no region could be colonised.
- Changing a fleet's mission or its area, and defending against an invasion at sea.
- Seizing a state's buildings without compensation: the law in force forbade it.
- Refitting a single ship: none was outdated.
- Ending a pact another country began, and removing an article from a treaty.
- Treaty articles both sides give: relations were too low for an alliance or a defensive pact.
- Treaty inputs of a law, a region, a subject or a company monopoly.
- A war goal on a country, and state or region articles as war goals or sways: no state could be a treaty port of ours and no region had unclaimed land.
- Sways with an ally, a subject, a pact or subjection.

## Models

- The row model's installed parameters come from entropy trial 102 of the search stopped on 1 October 2026, made on an earlier schema.
- The installed histogram sizes were assigned by parameter name from an earlier selection, with three bins for parameters it never saw. They have not been tuned on data recorded under this catalogue.
- Long preparations and searches go through the detached process broker, and nothing else should run while throughput is measured.

```powershell
.venv/Scripts/python.exe -m loop.prepare_histogram_tuning --output artifacts/endgame_histogram_data --folds 4 --pauses 300 --candidates 30 --seed 0
.venv/Scripts/python.exe -m advisors.models.row.prepare
```
