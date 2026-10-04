# Advisors

Initializers weigh levers. Pickers judge acts and their targets. Both work only on the advisor catalogue, which is written in a player's terms and shares no name with the interface's command catalogue.

| Path | Responsibility |
| --- | --- |
| `advisors/catalogue.py` | Levers, their acts and each act's parameters |
| `advisors/initializers` | Random, forest and SVR weights, one per lever |
| `advisors/pickers` | Candidate block selection |
| `advisors/data` | State, rewards, histogram primitives and initializer observations |
| `advisors/models` | Estimators, parameters, fitting, prediction and tuning |
| `loop/translate.py` | Maps the interface's available commands onto acts |

Nothing under `advisors/` imports `interface.actions`, `interface.options`, `loop` or `dashboard`, except the entity-graph replay tooling (`replay.py`, `source.py`, `world.py`, `world_data.py`), which is not an initializer or a picker. No lever or act carries the name of an interface command. `tests/test_translate.py` enforces both.

## Levels

| Level | What it is | Example | Decided by |
| --- | --- | --- | --- |
| Lever | A thing the player moves, with its direction | `raise_subsidies` | One weight per run from the initializer |
| Act | What is done to move it | `nationalise_building` under `raise_state_ownership` | Drawn evenly among the lever's acts on offer |
| Target | Which kind, and where or who | a building, a number of levels | Drawn evenly; the picker judges acts and targets together |

Construction is split by what is built. Nothing else is split by building type. Every other mechanic has one lever, or one for raising and one for lowering where it goes both ways. A lever with a single act shares its name.

## Levers

79 levers, one weight each.

### Construct (11)

The act queues one more level by government construction. The target is the state and the building type.

| Lever | Building types |
| --- | --- |
| `construct_construction_capacity` | Construction sector |
| `construct_infrastructure` | Railway, port |
| `construct_food_production` | Rye, wheat, rice, maize and millet farms, vineyard, livestock ranch |
| `construct_plantations` | Coffee, cotton, dye, opium, tea, tobacco, sugar, banana, silk |
| `construct_raw_materials` | Coal, iron, lead, sulfur and gold mines, logging camp, fishing wharf, whaling station, oil rig, rubber plantation |
| `construct_consumer_goods` | Food industry, textile mill, furniture manufactory |
| `construct_industrial_goods` | Tooling workshop, paper mill, glassworks, steel mill, motor industry, fertilizer plant, explosives factory, synthetics plant, electrics industry, automotive industry, shipyard, power plant |
| `construct_military_goods` | Arms industry, artillery foundry, munition plant |
| `construct_trade_capacity` | Trade centre |
| `construct_bureaucracy` | Government administration |
| `construct_innovation` | University |

### Queue and downsizing (4)

These take any building type.

| Lever | Target |
| --- | --- |
| `cancel_queued_construction` | State, building type |
| `raise_construction_priority` | State, building type |
| `lower_construction_priority` | State, building type |
| `downsize_building` | Building |

### Raised or lowered (24 pairs, 48 levers)

Each row is two levers, `raise_<name>` and `lower_<name>`.

| Name | Acts when raised | Acts when lowered |
| --- | --- | --- |
| `subsidies` | Subsidise a building | Stop subsidising it |
| `state_ownership` | `nationalise_building`, `reserve_building_type_for_state`, `withdraw_building_from_sale` | `offer_building_for_sale`, `end_state_monopoly` |
| `companies_and_charters` | `establish_company`, `grant_charter` | `disband_company`, `revoke_charter` |
| `import_tariff` | One step toward maximum tariff on a good | One step toward maximum subvention |
| `export_tariff` | Same for exports | Same |
| `commercial_treaties` | `propose_commercial_article`, `propose_goods_article` | Withdraw from a treaty whose articles are commercial |
| `embargoes` | Embargo a country | Lift an embargo |
| `tax_level` | One step up | One step down |
| `consumption_taxes` | Tax a good | Lift the tax |
| `government_wages` | One step up | One step down |
| `military_wages` | One step up | One step down |
| `institutions` | One investment level up | One level down |
| `state_decrees` | Issue a decree in a state | Lift one |
| `government` | Bring an interest group or its party in | Put one out |
| `political_movements` | `bolster_movement`, `stop_suppressing_movement` | `suppress_movement`, `stop_bolstering_movement` |
| `relations` | `improve_relations`, `stop_damaging_relations`, `end_rivalry` | `damage_relations`, `declare_rivalry`, `expel_diplomats`, `stop_improving_relations` |
| `security_treaties` | Propose a treaty with a security article | Withdraw from a treaty that holds one |
| `power_bloc` | `found_power_bloc`, `ask_to_join_power_bloc`, `invite_to_power_bloc`, `adopt_bloc_principle` | `leave_bloc`, `remove_bloc_member`, `refund_bloc_principle` |
| `hold_over_subjects` | `lower_subject_autonomy`, `raise_subject_payments`, `end_service_exemption`, `take_back_subject_market` | `raise_subject_autonomy`, `lower_subject_payments`, `exempt_subject_from_service`, `grant_subject_own_market`, `grant_independence` |
| `confrontations` | `demand_of_country`, `demand_for_state`, `add_demand`, `make_demand_primary`, `sway_country` | `withdraw_from_confrontation`, `surrender_war` |
| `colonies` | `establish_colony`, `resume_colony` | `pause_colony`, `give_up_colony` |
| `regular_army` | Recruit a regular battalion | `disband_battalions`, `disband_army` |
| `mobilisation` | `mobilise_army`, `mobilise_all_armies`, `call_up_conscripts`, `raise_army_conscripts`, `switch_on_mobilisation_option` | `demobilise_army`, `demobilise_all_armies`, `send_conscripts_home`, `switch_off_mobilisation_option` |
| `navy` | `queue_ship`, `queue_ship_for_fleet`, `construct_naval_administration` | `cancel_queued_ship`, `scrap_ship`, `disband_fleet` |

Commercial articles are trade privileges, transit rights, investment rights and company monopoly, and per good: goods transfer, no tariffs, no subventions, no trade with the world market. Security articles are alliance, defensive pact, guarantee of independence, military access and military assistance. A treaty proposal carries a `giver` of `us`, `them` or `both`. A treaty holding both kinds counts as a security treaty when withdrawing.

### Single move (12)

| Lever | Acts |
| --- | --- |
| `change_production_method` | Switch the method in one method group of a building |
| `incorporate_state` | Start incorporating a state |
| `laws_power_structure`, `laws_economy`, `laws_human_rights` | `enact_<category>_law`; `negotiate_<category>_law` while a law of that category is being enacted |
| `research_production`, `research_military`, `research_society` | `research_<tree>_technology`, `queue_<tree>_technology` |
| `change_army_equipment` | `upgrade_regular_units`, `upgrade_conscript_units`, `set_standard_unit_type`, `upgrade_every_unit` |
| `disposition_of_forces` | `form_army`, `move_battalions`, `recruit_commander`, `recruit_commander_for`, `give_command`, `take_away_command`, `station_army`, `station_army_at_headquarters`, `rehome_army`, `send_to_front`, `defend_against_invasion`, `set_objective`, `clear_objective`, `give_order`, `start_fleet_mission`, `end_fleet_mission`, `call_off_invasion`, `land_troops`, `set_army_supply_priority`, `plan_invasion`, `embark_troops` |
| `make_peace` | `offer_peace`, `offer_white_peace`, `accept_peace_offer`, `press_war_goal`, `drop_war_goal` |
| `national_decisions` | `take_national_decision`, `take_journal_option` |

Law categories and technology trees are read from the installed game's definitions.

### Answers (4)

| Lever | Acts |
| --- | --- |
| `accept_offers` | `agree_to_treaty`, `accept_proposal`, `accept_call_to_side` |
| `decline_offers` | `refuse_treaty`, `decline_proposal`, `decline_call_to_side` |
| `concede_demand` | Concede a demand made of us |
| `refuse_demand` | Refuse it |

`answer_event` has no weight: an event has one answering act and the picker judges the option.

## Translation

`loop/translate.py` holds one rule per act. A rule reads the commands the interface offers at a pause and returns the act's choices, each with its parameters and every command that carries it. Directions are read from the snapshot: the current tax level, the current tariff step on the good, whether a good is taxed, whether a movement is bolstered. `offer` raises when a choice's parameters differ from the catalogue.

121 of the interface's 176 commands are carried. The 55 in `LEFT_OUT` are not: time control, pausing construction and shipbuilding, the bulk forms of subsidising, nationalising and method switching, bankruptcy, straits, abandoning an enactment, imposing a law, repealing an amendment, cancelling an institution change, removing queued research, stopping an incorporation, the supply-ship share, ship queue order, where new ships are sent, ship designs and retrofits, fleet recall, formation flags and lending, promotions, character interactions, obligations, hiding a decision, and taking a side unasked in another's confrontation. A test fails when a command is neither carried nor left out.

Eleven acts are in the catalogue but have no rule, because the interface has no command for them yet: `lower_embargoes`, `stop_damaging_relations`, `end_rivalry`, `stop_improving_relations`, `refund_bloc_principle`, `end_service_exemption`, `take_back_subject_market`, `grant_independence`, `sway_country`, `plan_invasion`, `embark_troops`. `lower_embargoes` is the only lever with no working act.

Other limits inherited from the interface: only investment and trade charters can be granted; a treaty holds one article and a goods transfer has no quantity; unification, regime change and liberation demands are not offered; downsizing reaches only state-owned levels; construction is offered in our own states only. The snapshot does not record whether a peace offer is already accepted, so `accept_peace_offer` carries the toggle as offered.

A quick decline joins a refusal only when the country has one kind of proposal waiting.

## Sampling

Each run has one weight per lever. Within a pause the drawer picks a lever in proportion to its weight among levers that still have a free choice, then one of that lever's acts evenly, then one of the act's targets evenly, then one of the commands that carry it. Events and proposals are answered first: a proposal's answer is chosen between its accepting and declining acts by the weights of their levers.

`--weight name=0` switches a lever off for every initializer.

Conflicts between commands in one pause, pause-ending commands and execution stay in the loop and work on the commands.

## Recording

| Table | Content |
| --- | --- |
| `advisor_action` | Lever and act names |
| `run_weight` | The weight of every lever in a run |
| `loop_action` | Each executed command, with the act it carried; null for the loop's own time control |
| `loop_action_param` | The command's parameters |
| `loop_decision_param` | The act's parameters |
| `pick_candidate_action` | The acts of every scored candidate block |

Initializers read `run_weight`. Pickers read `loop_action.advisor_action` and `loop_decision_param`. The dashboard's policy page lists every act with its lever and the commands that executed it.

## Quarterly decisions

Decisions occur on January 1, April 1, July 1 and October 1. Blocks contain at most sixteen acts, including event and proposal answers. Ordinary target sizes are drawn from six through sixteen; conflicts can shorten them.

Each round draws one initializer and one picker independently and uniformly from its configured lists. Warmup rounds use random initialization and the first picker. Collection configuration is described in `loop_speed.md`.

| Picker | Selection |
| --- | --- |
| `first` | First generated candidate |
| `catboost` | Largest predicted whole-block reward |
| `catboost_piecewise` | Largest mean of individual act predictions |

The first picker draws a single candidate; learned pickers draw between eight and fifty. Equal scores select the first candidate. Identical act and parameter pairs share one prediction within a pause.

## Features and targets

Histogram encoding combines state, holdings, block size and act histograms. The act histogram counts acts; parameter histograms are named `<act>.<parameter>`. The installed histogram sizes were assigned by parameter name from the previous selection and have not been tuned on data recorded under this catalogue.

Row encoding creates one example per recorded decision. State covers finances, population, construction, military, prices, institutions, tariffs and laws. Act features cover the act, its parameters, referenced entities and their immediate categorical attributes. Trait indicators describe targeted characters and interest-group leaders.

Validation, execution status, after-snapshot presence and picker scores never enter features or training-row eligibility.

The forest and SVR initializers and both CatBoost pickers use the fixed three-metric reward in `advisors/data/endgame.py`; see `rewards.md`. Initializers evaluate complete runs from their opening snapshots and rank-normalize rewards. Pickers evaluate reward from the first snapshot of the pause to the run's last recorded timestamp; acts in the same pause receive the same target.

## Models and tuning

`advisors.models.boosting.Regressor` fits whole-block CatBoost; encoding and parameters live in `advisors/models/histogram`. Row fitting uses `advisors.models.row.model`. Each learned-picker start fits a fresh estimator with the installed hyperparameters. Completed-run caches keep features and reward parts; a new DSN clears them.

Whole-block tuning is described in `histogram_tuning.md`. `python -m advisors.models.row.prepare` creates row data. Long preparation and searches run through the detached process broker.
