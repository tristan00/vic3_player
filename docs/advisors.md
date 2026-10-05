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

Construction is split by what is built. Nothing else is split by building type. Every other mechanic has one lever, or one for raising and one for lowering where it goes both ways. A lever with a single act shares its name; an act of a lever with several acts never does.

## Coverage

Every command of the interface is carried by an act, except `pause`, `unpause` and `set_speed`, which the loop issues itself. Every act has a rule and can fire. `tests/test_translate.py` holds this at four levels.

| Level | What must hold |
| --- | --- |
| Commands | All 182 interface commands except the three of time control are reached |
| Acts | All 251 acts are reached, and the rules and the acts are the same set |
| Building types | Every type the government can queue sits in a construct lever or a naval act |
| Diplomatic actions | Every action the game lets a country choose has an act; an unknown one stops `offer` with an error |
| Pacts | Every pact the game lets a country end goes to a named act or to `end_standing_pact` |
| Treaty articles | Every article the interface can offer is filed under one of four kinds, and so is every treaty when withdrawing |

The last section lists what the interface itself cannot do yet.

## Levers

91 levers, one weight each, with 250 acts beneath them and the unweighted `answer_event`.

### Construct (12)

The act queues one more level by government construction. The target is the state and the building type.

| Lever | Building types |
| --- | --- |
| `construct_construction_capacity` | Construction sector |
| `construct_infrastructure` | Railway, port, the three canals |
| `construct_food_production` | Rye, wheat, rice, maize and millet farms, vineyard, livestock ranch |
| `construct_plantations` | Coffee, cotton, dye, opium, tea, tobacco, sugar, banana, silk |
| `construct_raw_materials` | Coal, iron, lead, sulfur and gold mines, logging camp, fishing wharf, whaling station, oil rig, rubber plantation |
| `construct_consumer_goods` | Food industry, textile mill, furniture manufactory, art academy, skyscraper |
| `construct_industrial_goods` | Tooling workshop, paper mill, glassworks, steel mill, motor industry, fertilizer plant, explosives factory, synthetics plant, electrics industry, automotive industry, shipyard, power plant |
| `construct_military_goods` | Arms industry, artillery foundry, munition plant |
| `construct_trade_capacity` | Trade centre |
| `construct_bureaucracy` | Government administration |
| `construct_innovation` | University |
| `construct_monuments` | Every buildable monument and the power bloc statue |

Canals, monuments, art academies and skyscrapers are read from the installed game by building group. Naval administrations and naval fortifications are queued by acts of `raise_navy`. Barracks grow through recruitment.

### Queue, pauses and downsizing (7)

| Lever | Acts | Target |
| --- | --- | --- |
| `cancel_queued_construction` | The same | State, building type |
| `raise_construction_priority` | `raise_building_priority`, `raise_ship_priority` | State and building type; position in the ship queue |
| `lower_construction_priority` | `lower_building_priority`, `lower_ship_priority` | The same |
| `downsize_building` | The same | Building |
| `halt_construction` | `halt_construction_queue`, `halt_construction_sector`, `halt_shipbuilding` | None; a construction sector; none |
| `restart_construction` | `restart_construction_queue`, `restart_construction_sector`, `restart_shipbuilding` | The same |
| `cancel_queued_research` | The same | Technology |

### Raised or lowered (27 pairs, 54 levers)

Each row is two levers, `raise_<name>` and `lower_<name>`.

| Name | Acts when raised | Acts when lowered |
| --- | --- | --- |
| `subsidies` | Subsidise a building | Stop subsidising it |
| `subsidies_statewide` | Subsidise every building of one type in a state, by ownership class | Stop subsidising them |
| `state_ownership` | `nationalise_building`, `reserve_building_type_for_state`, `withdraw_building_from_sale` | `offer_building_for_sale`, `end_state_monopoly` |
| `companies_and_charters` | `establish_company`, `grant_charter` | `disband_company`, `revoke_charter` |
| `import_tariff` | One step toward maximum tariff on a good | One step toward maximum subvention |
| `export_tariff` | Same for exports | Same |
| `commercial_treaties` | `propose_commercial_article`, `propose_goods_article` | Withdraw from a commercial treaty |
| `embargoes` | Embargo a country | Lift the embargo |
| `tax_level` | One step up | One step down |
| `consumption_taxes` | Tax a good | Lift the tax |
| `government_wages` | One step up | One step down |
| `military_wages` | One step up | One step down |
| `institutions` | `raise_institution_level`, `cancel_institution_decrease` | `lower_institution_level`, `cancel_institution_increase` |
| `state_decrees` | Issue a decree in a state | Lift one |
| `government` | Bring an interest group or its party in | Put one out |
| `political_movements` | `bolster_movement`, `stop_suppressing_movement` | `suppress_movement`, `stop_bolstering_movement` |
| `relations` | `improve_relations`, `forgive_obligation`, `fund_lobby`, `stop_damaging_relations`, `end_rivalry`, `stop_supporting_separatists`, `call_off_coup`, `end_standing_pact`, `propose_diplomatic_article` | `damage_relations`, `declare_rivalry`, `expel_diplomats`, `violate_neutrality`, `support_separatists`, `stage_coup`, `stop_improving_relations`, `stop_funding_lobby`, `withdraw_diplomatic_treaty` |
| `security_treaties` | Propose a treaty with a security article | Withdraw from a treaty that holds one |
| `power_bloc` | `found_power_bloc`, `ask_to_join_power_bloc`, `invite_to_power_bloc`, `adopt_bloc_principle`, `replace_bloc_principle`, `propose_bloc_article`, `subjugate_bloc_member`, `force_bloc_regime_change`, `force_bloc_religion`, `add_bloc_culture` | `leave_bloc`, `remove_bloc_member`, `withdraw_bloc_treaty` |
| `hold_over_subjects` | `lower_subject_autonomy`, `raise_subject_payments`, `appoint_colonial_governor`, `evangelise_subject`, `change_subject_culture`, `enforce_subject_military_access`, `annex_lapsed_subject`, `end_service_exemption`, `take_back_subject_market`, `end_payment_relief`, `stop_supporting_subject_regime`, `stop_sharing_knowledge`, `withdraw_subject_investment_rights` | `raise_subject_autonomy`, `lower_subject_payments`, `exempt_subject_from_service`, `grant_subject_own_market`, `support_subject_regime`, `share_knowledge_with_subject`, `grant_subject_investment_rights`, `grant_independence`, `end_raised_payments`, `stop_evangelising_subject` |
| `confrontations` | `demand_of_country`, `demand_for_state`, `add_demand`, `make_demand_primary`, `sway_country`, `back_initiator`, `back_target`, `lean_towards_initiator`, `lean_towards_target` | `withdraw_from_confrontation`, `surrender_war`, `stay_on_the_fence`, `stay_neutral` |
| `colonies` | `establish_colony`, `resume_colony` | `pause_colony`, `give_up_colony` |
| `incorporation` | Start incorporating a state | Stop incorporating it |
| `regular_army` | Recruit a regular battalion | `disband_battalions`, `disband_army` |
| `mobilisation` | `mobilise_army`, `mobilise_all_armies`, `call_up_conscripts`, `raise_army_conscripts`, `switch_on_mobilisation_option` | `demobilise_army`, `demobilise_all_armies`, `send_conscripts_home`, `switch_off_mobilisation_option` |
| `navy` | `queue_ship`, `queue_ship_for_fleet`, `construct_naval_administration`, `construct_naval_fortification`, `raise_supply_ship_share` | `cancel_queued_ship`, `cancel_ship_order`, `scrap_ship`, `disband_fleet`, `lower_supply_ship_share` |
| `strait_restrictions` | `raise_strait_toll`, `tighten_strait_access`, `narrow_strait_passage` | `lower_strait_toll`, `loosen_strait_access`, `widen_strait_passage` |

A strait moves one step at a time: tolls from none to high, access from open through no military to closed, passage from no enemies through only allies to only the controller.

### Single move (14)

| Lever | Acts |
| --- | --- |
| `change_production_method` | Switch the method in one method group of a building |
| `change_production_method_statewide` | Switch it for every building of one type in a state, by ownership class |
| `nationalise_statewide` | Nationalise every building of one type in a state, by ownership class |
| `laws` | `enact_new_law`, `negotiate_over_law`, `abandon_law_enactment`, `impose_law_on_subject`, `repeal_law_amendment` |
| `research_production`, `research_military`, `research_society` | `research_<tree>_technology`, `queue_<tree>_technology` |
| `change_army_equipment` | `upgrade_regular_units`, `upgrade_conscript_units`, `set_standard_unit_type`, `upgrade_every_unit` |
| `change_navy_equipment` | `design_ship`, `redesign_ship`, `set_standard_ship_design`, `set_fleet_ship_design`, `scrap_ship_design`, `refit_fleet`, `cancel_fleet_refit`, `refit_every_fleet`, `cancel_every_refit` |
| `disposition_of_forces` | `form_army`, `move_battalions`, `recruit_commander`, `recruit_commander_for`, `give_command`, `take_away_command`, `promote_officer`, `station_army`, `station_army_at_headquarters`, `rehome_army`, `send_to_front`, `defend_against_invasion`, `set_objective`, `clear_objective`, `give_order`, `start_fleet_mission`, `end_fleet_mission`, `plan_invasion`, `plan_seaborne_invasion`, `call_off_invasion`, `embark_troops`, `land_troops`, `set_army_supply_priority`, `set_army_flag`, `set_army_lending`, `send_new_ships_to_fleet`, `send_new_ships_to_reserve`, `recall_fleet_for_repairs` |
| `make_peace` | `offer_peace`, `offer_white_peace`, `accept_peace_offer`, `press_war_goal`, `drop_war_goal` |
| `national_decisions` | `take_national_decision`, `take_journal_option`, `default_on_debt`, `toggle_decision_alert` |
| `interact_with_character` | One act: a character interaction on a ruler, heir, commander or interest group leader |
| `petition_overlord` | `ask_for_autonomy`, `ask_for_regime_support`, `ask_for_knowledge_sharing`, `ask_for_market_control`, `ask_for_investment_rights`, `ask_for_colonial_governor`, `return_market_control` |

Laws have one lever. Technology trees are read from the installed game's definitions.

### Answers (4)

| Lever | Acts |
| --- | --- |
| `accept_offers` | `agree_to_treaty`, `accept_proposal`, `accept_call_to_side` |
| `decline_offers` | `refuse_treaty`, `decline_proposal`, `decline_call_to_side` |
| `concede_demand` | Concede a demand made of us |
| `refuse_demand` | Refuse it |

`answer_event` has no weight: an event has one answering act and the picker judges the option.

## Translation

`loop/translate.py` holds one rule per act. A rule reads the commands the interface offers at a pause and returns the act's choices, each with its parameters and every command that carries it. Directions are read from the snapshot: the current tax level, the current tariff step on the good, whether a good is taxed, whether a movement is bolstered, which way an institution is changing, the strait's present toll and access. `offer` raises when a choice's parameters differ from the catalogue.

### Diplomatic actions and pacts

The game lets a country choose 36 diplomatic actions. `catalogue.ESTABLISHED` names the act for 35 of them, and joining a power bloc goes through `ask_to_join_power_bloc`. An action paid for with an obligation carries the same act as the plain one, as a second command. `catalogue.ENDED` names the act that ends each pact; the two pacts without one, raiding and disapproval, go to `end_standing_pact`, which carries the pact type as a parameter. Only pacts the played country began are ended. Granting independence ends the subject pact.

### Treaties

A proposal holds one article and says who gives: `us`, `them` or `both`.

| Kind | Articles | Proposed by | Withdrawn by |
| --- | --- | --- | --- |
| Security | Alliance, defensive pact, guarantee of independence, support of independence, military access, military assistance, non-piracy, abandon piracy | `raise_security_treaties` | `lower_security_treaties` |
| Commercial | Trade privilege, transit rights, investment rights, company monopoly, taking on debt, toll exemption, no tolls, strait access, no strait closure; per good: goods transfer, no tariffs, no subventions, no trade with the world market | `propose_commercial_article`, `propose_goods_article` | `lower_commercial_treaties` |
| Bloc | Hosting a bloc embassy; membership goes through `ask_to_join_power_bloc` and `invite_to_power_bloc` | `propose_bloc_article` | `withdraw_bloc_treaty` |
| Diplomatic | Every other article: embassy, succession, recognition | `propose_diplomatic_article` | `withdraw_diplomatic_treaty` |

A treaty is withdrawn under the first of these kinds that any of its articles has.

### Other rules

A quick decline joins a refusal only when the country has one kind of proposal waiting. `sway_country` carries the position of the offer type in the game's sway panel and takes the first offer of that type. `replace_bloc_principle` carries the slot and the new principle. `accept_peace_offer` and `toggle_decision_alert` carry toggles whose present state the snapshot does not record.

## What the interface cannot do yet

These have no command, so no act can reach them.

- Diplomatic actions that pick a state: trading states, granting a state to or taking one from a subject, a subject demanding a state, staking a colonial claim.
- Treaty articles that need a quantity, a state, a region, a law, a country, a ship or free text: money transfer, state transfer, treaty port, non-colonisation, law commitment, subject transfer, ship transfer, free text. A company monopoly article needs a company and a building type and is not offered either.
- Treaties of more than one article, counter-offers and renegotiation; a goods transfer has no quantity.
- Ending a pact that another country began.
- Releasing a country, forming a country, moving the capital.
- Creating a fleet, merging formations.
- Charters other than investment and trade.
- Demands for unification, regime change and liberation.
- Construction outside our own states, and downsizing privately owned levels.
- Inviting, exiling or otherwise acting on agitators.
- The auto-expand setting of a building.

Three acts were exercised against the running game only as far as the game's own refusal, because the test world offered no valid case: `embark_troops` (the army held no marines), `plan_invasion` and `plan_seaborne_invasion` (the army could reach no port). `replace_bloc_principle` was not exercised with a mandate in hand.

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

Histogram encoding combines state, holdings, block size and act histograms. The act histogram counts acts; parameter histograms are named `<act>.<parameter>`. The installed histogram sizes were assigned by parameter name from an earlier selection, with three bins for parameters that selection never saw, and have not been tuned on data recorded under this catalogue.

Row encoding creates one example per recorded decision. State covers finances, population, construction, military, prices, institutions, tariffs and laws. Act features cover the act, its parameters, referenced entities and their immediate categorical attributes. Trait indicators describe targeted characters and interest-group leaders.

Validation, execution status, after-snapshot presence and picker scores never enter features or training-row eligibility.

The forest and SVR initializers and both CatBoost pickers use the fixed three-metric reward in `advisors/data/endgame.py`; see `rewards.md`. Initializers evaluate complete runs from their opening snapshots and rank-normalize rewards. Pickers evaluate reward from the first snapshot of the pause to the run's last recorded timestamp; acts in the same pause receive the same target.

## Models and tuning

`advisors.models.boosting.Regressor` fits whole-block CatBoost; encoding and parameters live in `advisors/models/histogram`. Row fitting uses `advisors.models.row.model`. Each learned-picker start fits a fresh estimator with the installed hyperparameters. Completed-run caches keep features and reward parts; a new DSN clears them.

Whole-block tuning is described in `histogram_tuning.md`. `python -m advisors.models.row.prepare` creates row data. Long preparation and searches run through the detached process broker.
