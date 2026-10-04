# Advisors

Initializers supply sampling weights, pickers choose among generated blocks, and both work only on advisor actions. An advisor action is a decision a player makes, named by what it does to the country. Interface actions are the GUI commands that carry a decision out. Nothing under `advisors/` imports the interface action or option modules or names an interface action; `tests/test_translate.py` enforces this.

| Path | Responsibility |
| --- | --- |
| `advisors/catalogue.py` | The advisor action catalogue |
| `advisors/initializers` | Random, forest and SVR weights, one per advisor action |
| `advisors/pickers` | Candidate selection |
| `advisors/data` | State, rewards, histogram primitives and initializer observations |
| `advisors/models` | Estimators, parameters, fitting, prediction and tuning |
| `loop/translate.py` | Maps interface options to advisor actions |

Models and shared data must not import initializers or pickers.

## Advisor action catalogue

The catalogue lists 271 actions in 18 domains. Each has a name, a domain and typed parameters.

| Rule | Example |
| --- | --- |
| One action per decision. Commands that carry the same decision share it. | Subsidizing a building from its panel or from a building browser subset is `subsidize_building` |
| A scale is moved, never set. | `raise_taxes`, `lower_taxes`; `raise_import_duty`, `lower_import_duty` |
| A toggle is named by its result. | `grant_monopoly`, `revoke_monopoly` |
| What is created or changed is part of the action when the game defines a small set of kinds. | `expand_iron_mine`, `enact_trade_policy`, `invest_in_schools` |
| Where it happens stays a parameter. | `expand_iron_mine` takes a state |
| Time control and cosmetic commands are not advisor actions. | Pause, speed, formation flags |

| Domain | Actions | Contents |
| --- | --- | --- |
| construction | 64 | One `expand_<building>` per government-buildable building type (55), monuments, queue order, cancelling, downsizing, pausing |
| production | 4 | Advancing or reverting a production method, subsidies |
| ownership | 6 | Nationalizing, privatizing, monopolies |
| budget | 9 | Taxes, wages, consumption taxes, bankruptcy |
| trade | 17 | Import and export duties, trade centre quantity, embargo, strait tolls and access, treaty answers and withdrawal |
| companies | 4 | Establishing, dissolving, charters |
| laws | 29 | One `enact_<law group>` per law group (26), cancelling, imposing, repealing |
| politics | 11 | Movements, negotiation, government membership, decrees |
| institutions | 15 | `invest_in_<institution>` and `divest_from_<institution>` (7 each), halting |
| technology | 7 | Researching and queueing by category |
| army, navy, characters | 62 | Recruitment, mobilization, stationing, ships, templates, commanders |
| diplomacy, plays, war | 32 | Diplomatic actions, power blocs, plays, war goals, peace |
| expansion, journal | 11 | Colonies, incorporation, decisions, journal buttons, event answers |

Building types, law groups, institutions and technology categories are read from the installed game's definitions. A trade centre is built with `expand_trade_center`; its scale is moved with `raise_trade_quantity` and `lower_trade_quantity`.

Import and export duty is one scale per good and direction: maximum, high and low subvention, none, then low, high and maximum tariff.

Two toggles keep a neutral name because the snapshot does not record their state: `toggle_colonization_pause` and `toggle_peace_acceptance`.

## Translation

`loop/translate.py` holds one rule per interface action. A rule takes the snapshot and an interface option and returns the advisor action and its parameters. Directions and toggle results are read from the snapshot: the current tax level, the current duty on the good, whether the monopoly is held.

`offer` groups the options of a pause by advisor action and parameters. A decision keeps every command that carries it. Time control and formation flags have no rule and are never offered. A quick decline is offered as a decline only when the country has one kind of proposal waiting.

Importing the module fails unless every interface action has exactly one rule or one stated reason for being left out. A translation whose parameters differ from the catalogue raises. The tests translate every interface action, check both directions of every scale and toggle, and require every advisor action to be reached.

Conflicts between actions in one pause, pause-ending actions and execution stay in the loop and work on the commands.

## Sampling

Each run has one weight per advisor action. Within a pause the drawer picks an action in proportion to its weight among actions that still have a free decision, then a decision uniformly, then one of its commands uniformly. Events and proposals are answered first: the answer is chosen between the accepting and declining actions by weight.

`--weight name=0` switches an advisor action off for every initializer.

## Recording

| Table | Content |
| --- | --- |
| `advisor_action` | Advisor action names |
| `run_weight` | The weight of every advisor action in a run |
| `loop_action` | Each executed command, with the advisor action it carried; null for the loop's own time control |
| `loop_action_param` | The command's parameters |
| `loop_decision_param` | The advisor action's parameters |
| `pick_candidate_action` | The advisor actions of every scored candidate block |

Initializers read `run_weight`. Pickers read `loop_action.advisor_action` and `loop_decision_param`. Runs recorded before the catalogue have neither and are not used by them. The dashboard's policy page lists the catalogue with the commands that executed each action.

## Quarterly decisions

Decisions occur on January 1, April 1, July 1 and October 1. Blocks contain at most sixteen actions, including event and proposal answers. Ordinary target sizes are drawn from six through sixteen; conflicts can shorten them.

Each round draws one initializer and one picker independently and uniformly from its configured lists. Warmup rounds use random initialization and the first picker. Collection configuration is described in `loop_speed.md`.

| Picker | Selection |
| --- | --- |
| `first` | First generated candidate |
| `catboost` | Largest predicted whole-block reward |
| `catboost_piecewise` | Largest mean of individual action predictions |

The first picker draws a single candidate; learned pickers draw between eight and fifty. Equal scores select the first candidate. Identical action and parameter pairs share one prediction within a pause.

## Features and targets

Histogram encoding combines state, holdings, block size and action histograms. The action histogram counts advisor actions; parameter histograms are named `<advisor action>.<parameter>`. The installed histogram selection was carried over from the interface names by the translation and has not been re-tuned on data recorded under the catalogue.

Row encoding creates one example per recorded decision. State covers finances, population, construction, military, prices, institutions, duties and laws. Action features cover the advisor action, its parameters, referenced entities and their immediate categorical attributes. Trait indicators describe targeted characters and interest-group leaders.

Validation, execution status, after-snapshot presence and picker scores never enter features or training-row eligibility.

The forest and SVR initializers and both CatBoost pickers use the fixed three-metric reward in `advisors/data/endgame.py`; see `rewards.md`. Initializers evaluate complete runs from their opening snapshots and rank-normalize rewards. Pickers evaluate reward from the first snapshot of the pause to the run's last recorded timestamp; actions in the same pause receive the same target.

## Models and tuning

`advisors.models.boosting.Regressor` fits whole-block CatBoost; encoding and parameters live in `advisors/models/histogram`. Row fitting uses `advisors.models.row.model`. Each learned-picker start fits a fresh estimator with the installed hyperparameters. Completed-run caches keep features and reward parts; a new DSN clears them.

Whole-block tuning is described in `histogram_tuning.md`. `python -m advisors.models.row.prepare` creates row data. Long preparation and searches run through the detached process broker.
