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

Every command of the interface is carried by an act, except `pause`, `unpause` and `set_speed`, which the loop issues itself. Every act has a rule and can fire. `tests/test_translate.py` holds this at these levels.

| Level | What must hold |
| --- | --- |
| Commands | All 265 interface commands except the three of time control are reached |
| Acts | All 342 acts are reached, and the rules and the acts are the same set |
| Building types | Every type the government can queue sits in a construct lever or a naval act |
| Diplomatic actions | Every action the game lets a country choose has an act, and so does every action that picks a state; an unknown one stops `offer` with an error |
| Pacts | Every pact the game lets a country end goes to a named act or to `end_standing_pact` |
| Treaty articles | Every article is filed under one of four kinds, and so is every treaty when withdrawing |

The sections "Out of scope" and "Not exercised against the game" at the end say what is deliberately absent and what has not been seen working.

## Levers

93 levers, one weight each, with 341 acts beneath them and the unweighted `answer_event`.

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

Each row is two levers, `raise_<name>` and `lower_<name>`. "Treaty acts" stands for the acts listed under Treaties below.

| Name | Acts when raised | Acts when lowered |
| --- | --- | --- |
| `subsidies` | Subsidise a building | Stop subsidising it |
| `subsidies_statewide` | Subsidise every building of one type in a state, by ownership class | Stop subsidising them |
| `state_ownership` | `nationalise_building`, `reserve_building_type_for_state`, `withdraw_building_from_sale` | `offer_building_for_sale`, `end_state_monopoly` |
| `companies_and_charters` | `establish_company`, `grant_charter`, `grant_charter_for_building_type`, `grant_charter_for_region` | `disband_company`, `revoke_charter`, `revoke_charter_for_building_type`, `revoke_charter_for_region` |
| `import_tariff` | One step toward maximum tariff on a good | One step toward maximum subvention |
| `export_tariff` | Same for exports | Same |
| `commercial_treaties` | Commercial treaty acts, `propose_goods_article`, `propose_goods_quantity_article`, `propose_money_transfer`, `propose_company_monopoly` | `withdraw_commercial_treaty`, `drop_commercial_article_from_treaty` |
| `embargoes` | Embargo a country | Lift the embargo |
| `tax_level` | One step up | One step down |
| `consumption_taxes` | Tax a good | Lift the tax |
| `government_wages` | One step up | One step down |
| `military_wages` | One step up | One step down |
| `institutions` | `raise_institution_level`, `cancel_institution_decrease` | `lower_institution_level`, `cancel_institution_increase` |
| `state_decrees` | Issue a decree in a state | Lift one |
| `government` | Bring an interest group or its party in | Put one out |
| `political_movements` | `bolster_movement`, `stop_suppressing_movement` | `suppress_movement`, `stop_bolstering_movement` |
| `relations` | `improve_relations`, `forgive_obligation`, `fund_lobby`, `stop_damaging_relations`, `end_rivalry`, `stop_supporting_separatists`, `call_off_coup`, `end_standing_pact`, diplomatic treaty acts, `propose_state_article`, `propose_region_article`, `propose_law_commitment`, `propose_subject_transfer`, `propose_ship_transfer` | `damage_relations`, `declare_rivalry`, `expel_diplomats`, `violate_neutrality`, `support_separatists`, `stage_coup`, `stop_improving_relations`, `stop_funding_lobby`, `withdraw_diplomatic_treaty`, `drop_diplomatic_article_from_treaty` |
| `security_treaties` | Security treaty acts | `withdraw_security_treaty`, `drop_security_article_from_treaty` |
| `power_bloc` | `found_power_bloc`, `ask_to_join_power_bloc`, `invite_to_power_bloc`, `adopt_bloc_principle`, `replace_bloc_principle`, `subjugate_bloc_member`, `force_bloc_regime_change`, `force_bloc_religion`, `add_bloc_culture`, bloc treaty acts | `leave_bloc`, `remove_bloc_member`, `withdraw_bloc_treaty`, `drop_bloc_article_from_treaty` |
| `hold_over_subjects` | `lower_subject_autonomy`, `raise_subject_payments`, `appoint_colonial_governor`, `evangelise_subject`, `change_subject_culture`, `enforce_subject_military_access`, `annex_lapsed_subject`, `end_service_exemption`, `take_back_subject_market`, `end_payment_relief`, `stop_supporting_subject_regime`, `stop_sharing_knowledge`, `withdraw_subject_investment_rights`, `take_state_from_subject` | `raise_subject_autonomy`, `lower_subject_payments`, `exempt_subject_from_service`, `grant_subject_own_market`, `support_subject_regime`, `share_knowledge_with_subject`, `grant_subject_investment_rights`, `grant_independence`, `end_raised_payments`, `stop_evangelising_subject`, `grant_state_to_subject` |
| `confrontations` | See Confrontations below | `withdraw_from_confrontation`, `surrender_war`, `stay_on_the_fence`, `stay_neutral` |
| `colonies` | `establish_colony`, `resume_colony`, `stake_colonial_claim` | `pause_colony`, `give_up_colony` |
| `incorporation` | Start incorporating a state | Stop incorporating it |
| `regular_army` | Recruit a regular battalion | `disband_battalions`, `disband_one_unit`, `disband_army` |
| `mobilisation` | `mobilise_army`, `mobilise_all_armies`, `call_up_conscripts`, `raise_army_conscripts`, `switch_on_mobilisation_option` | `demobilise_army`, `demobilise_all_armies`, `send_conscripts_home`, `switch_off_mobilisation_option` |
| `navy` | `queue_ship`, `queue_ship_for_fleet`, `construct_naval_administration`, `construct_naval_fortification`, `raise_supply_ship_share` | `cancel_queued_ship`, `cancel_queued_ship_for_fleet`, `cancel_ship_order`, `scrap_ship`, `disband_fleet`, `lower_supply_ship_share` |
| `strait_restrictions` | `raise_strait_toll`, `tighten_strait_access`, `narrow_strait_passage` | `lower_strait_toll`, `loosen_strait_access`, `widen_strait_passage` |

A strait moves one step at a time: tolls from none to high, access from open through no military to closed, passage from no enemies through only allies to only the controller.

### Single move (16)

| Lever | Acts |
| --- | --- |
| `change_production_method` | `switch_building_method`, `reset_building_methods` |
| `change_production_method_statewide` | `switch_methods_statewide`, `reset_methods_statewide` |
| `nationalise_statewide` | `buy_out_statewide`, `expropriate_statewide` |
| `relocate_capital` | `relocate_national_capital`, `relocate_market_capital` |
| `trade_territory` | `exchange_states`, `give_state_in_trade`, `ask_state_in_trade` |
| `laws` | `enact_new_law`, `negotiate_over_law`, `abandon_law_enactment`, `impose_law_on_subject`, `repeal_law_amendment` |
| `research_production`, `research_military`, `research_society` | `research_<tree>_technology`, `queue_<tree>_technology` |
| `change_army_equipment` | `upgrade_regular_units`, `upgrade_conscript_units`, `set_standard_unit_type`, `upgrade_every_unit` |
| `change_navy_equipment` | `design_ship`, `redesign_ship`, `set_standard_ship_design`, `set_fleet_ship_design`, `scrap_ship_design`, `refit_fleet`, `cancel_fleet_refit`, `refit_every_fleet`, `cancel_every_refit`, `refit_fleet_in_port`, `refit_every_fleet_in_port`, `refit_ship`, `cancel_ship_refit`, `rebuild_ship_to_design` |
| `disposition_of_forces` | `form_army`, `form_fleet`, `divide_army`, `divide_fleet`, `combine_armies`, `combine_fleets`, `move_battalions`, `move_ships`, `move_ship`, `recruit_commander`, `recruit_commander_for`, `give_command`, `take_away_command`, `promote_officer`, `station_army`, `station_army_at_headquarters`, `station_fleet_in_state`, `rehome_army`, `rebase_fleet`, `send_to_front`, `defend_against_invasion`, `defend_against_invasion_at_sea`, `set_objective`, `clear_objective`, `give_order`, `start_fleet_mission`, `change_fleet_mission`, `change_fleet_mission_area`, `end_fleet_mission`, `plan_invasion`, `plan_seaborne_invasion`, `call_off_invasion`, `embark_troops`, `land_troops`, `set_army_supply_priority`, `set_army_flag`, `set_army_lending`, `send_new_ships_to_fleet`, `send_new_ships_to_reserve`, `recall_fleet_for_repairs`, `appoint_flagship`, `dismiss_flagship` |
| `make_peace` | `offer_peace`, `offer_white_peace`, `accept_peace_offer`, `press_war_goal`, `drop_war_goal` |
| `national_decisions` | `take_national_decision`, `take_journal_option`, `default_on_debt`, `toggle_decision_alert` |
| `interact_with_character` | One act: a character interaction on any character the game lists one for, agitators and exiles included |
| `petition_overlord` | `ask_for_autonomy`, `ask_for_regime_support`, `ask_for_knowledge_sharing`, `ask_for_market_control`, `ask_for_investment_rights`, `ask_for_colonial_governor`, `return_market_control`, `ask_overlord_for_state` |

Laws have one lever. A law another country commits to is a parameter named `commitment`, so no act outside `laws` takes a `law`. Technology trees are read from the installed game's definitions.

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

`catalogue.ESTABLISHED` names the act for each diplomatic action a country can choose, and joining a power bloc goes through `ask_to_join_power_bloc`. An action paid for with an obligation carries the same act as the plain one, as a second command. `catalogue.STATE_DEALS` names the act for each action that picks a state; `trade_states` goes to the three acts of `trade_territory`. `catalogue.ENDED` names the act that ends each pact; the two pacts without one, raiding and disapproval, go to `end_standing_pact`, which carries the pact type as a parameter. A two-sided pact the other country began is ended by the same acts. Granting independence ends the subject pact.

### Treaties

Articles are filed under four kinds. Each kind has the same nine acts, under the lever pair shown.

| Kind | Articles | Lever pair |
| --- | --- | --- |
| Security | Alliance, defensive pact, guarantee of independence, support of independence, military access, military assistance, non-piracy, abandon piracy | `security_treaties` |
| Commercial | Trade privilege, transit rights, investment rights, company monopoly, taking on debt, money transfer, toll exemption, no tolls, strait access, no strait closure; per good: goods transfer, no tariffs, no subventions, no trade with the world market | `commercial_treaties` |
| Bloc | Hosting a bloc embassy, joining a bloc | `power_bloc` |
| Diplomatic | Every other article: embassy, succession, recognition, state transfer, treaty port, subject transfer, ship transfer, non-colonisation, law commitment | `relations` |

| Act, with `<kind>` one of the four | What it proposes | Parameters beyond country and article |
| --- | --- | --- |
| `propose_<kind>_article` | One article | Who gives: `us`, `them` or `both` |
| `propose_<kind>_article_for_term` | One article with a binding period | Days, one of the game's six periods; who gives |
| `propose_<kind>_article_with_obligation` | One article with an obligation owed, called in or asked for | The obligation; who gives |
| `demand_<kind>_article_under_threat` | A demanded article backed by a threat of naval hostilities | None |
| `demand_<kind>_article_made_acceptable` | A demanded article after the game's "make this work" has added what the other side wants | None |
| `exchange_<kind>_articles` | An article we give for an article we demand, filed by the one we give | The demanded article |
| `add_<kind>_article_to_treaty` | A new article added to a treaty in force or to a proposal made to us | The treaty; who gives |
| `drop_<kind>_article_from_treaty` | A renegotiable article removed from such a treaty | The treaty; who gives |
| `withdraw_<kind>_treaty` | Withdrawal from a treaty, filed under the first kind any of its articles has | The treaty |

Articles that need an input have acts of their own: `propose_goods_article` (a good), `propose_goods_quantity_article` (a good and a share of the valid quantity), `propose_money_transfer` (a share of the valid amount), `propose_company_monopoly` (a company and a building type), `propose_state_article` (a state), `propose_region_article` (a strategic region), `propose_law_commitment` (a law of the country that commits), `propose_subject_transfer` (a subject), `propose_ship_transfer` (a ship). A share is one of five steps from the smallest to the largest quantity the game accepts. A treaty port is asked only of a state the snapshot marks as a possible port of ours, and a non-colonisation agreement names only a region that still has unclaimed land.

### Confrontations

| Group | Acts of `raise_confrontations` |
| --- | --- |
| Starting a play | `demand_of_country`, `demand_for_state`, `demand_liberation` |
| Adding a demand to our play | `add_demand_on_country`, `add_demand_for_state`, `add_liberation_demand`, `add_article_demand`, `add_goods_article_demand`, `add_state_article_demand`, `add_region_article_demand`, `add_law_article_demand`, `make_demand_primary` |
| Swaying a country | `sway_country`, `sway_ally`, `sway_with_state`, `sway_with_subject`, `sway_with_pact`, `sway_with_war_goal`, `sway_with_state_war_goal`, `sway_with_goods_article`, `sway_with_state_article`, `sway_with_region_article`, `sway_with_law_article` |
| Taking a side in another's play | `back_initiator`, `back_target`, `lean_towards_initiator`, `lean_towards_target` |

A demand names its holder, its target and, for an article demand, the article and its input. A demand to nationalise is made only of a country that owns buildings in our states.

Each sway act belongs to one of the game's kinds of offer, and the command picks that kind by the game's own name for it.

| Act | Kind of offer | What is offered |
| --- | --- | --- |
| `sway_country` | Obligations | The first offer the game lists, an obligation |
| `sway_ally` | Call ally | The call, to a country we hold an alliance or a defensive pact with |
| `sway_with_state` | Transfer states | One of our states |
| `sway_with_subject` | Transfer subject | One of our subjects, unless its subject type is barred from sways |
| `sway_with_pact` | Diplomatic pacts, or becoming a subject | A pact the installed game marks as usable in a sway, or becoming the country's protectorate or tributary where the ranks allow it |
| `sway_with_war_goal`, `sway_with_state_war_goal` | War goals | A war goal for the swayed country, on a country or a state |
| `sway_with_<input>_article` | War goals | An enforced treaty article with its good, state, region or law |

A block holds at most one sway, because the game lets a country court one other at a time.

Unification and leadership goals are never demanded or offered. Neither is a goal the game allows only in debug mode, which in the installed game is regime change, nor a play for such a goal: collection runs without debug mode.

### Other rules

A quick decline joins a refusal only when the country has one kind of proposal waiting. `replace_bloc_principle` carries the slot and the new principle. `accept_peace_offer` and `toggle_decision_alert` carry toggles whose present state the snapshot does not record. `start_fleet_mission` is offered to a fleet without a mission and `change_fleet_mission` to a fleet with one, which keeps its area.

## Out of scope

The project owner ruled these out. They have no command and no act, and must not be added.

- Actions that change every building of a type across the whole country.
- All auto-expand actions, including the per-state ones.
- Releasing a country.
- Forming a country, ignoring a formable country, supporting a formation candidate, and unification or leadership plays.

These are left out because they do not change the played country's game:

- Names, colours, flags and ornaments of states, companies, goods, formations, ships and power blocs.
- Saving, loading, game rules, message settings, observing, and switching the played country, which includes switching sides in a revolution and playing as a released country.
- The ruler selector, which a game rule switches off.

## Not exercised against the game

Every command is generated, passes the catalogue tests and has an availability rule. These acts have not been seen valid in a running game. What was observed is in `action_verification.md`.

| Acts | Why |
| --- | --- |
| `demand_liberation`, `add_liberation_demand` | Generated worlds define no country that can be created |
| `grant_charter_for_region`, `revoke_charter_for_region` | No region could be colonised |
| `change_fleet_mission`, `change_fleet_mission_area`, `defend_against_invasion_at_sea` | The fleets had no crew and no invasion took place |
| `expropriate_statewide` | The law in force forbade it; the game's refusal was seen |
| `refit_ship`, `cancel_ship_refit`, `refit_every_fleet_in_port` | No ship was outdated or being refitted; the game's refusal was seen |
| Ending a pact another country began | No such pact existed |
| `drop_<kind>_article_from_treaty` | No case arose |
| Proposals of an article both sides give, plain or for a term | Relations were too low for an alliance or a defensive pact; the game's refusal was seen |
| `demand_<kind>_article_under_threat` | The naval threat was never on offer |
| `propose_region_article`, `propose_law_commitment`, `propose_subject_transfer`, `propose_company_monopoly` | Not sampled, or the world had no subject or company to name |
| `add_demand_on_country` | The game listed no country demand for the plays that were started |
| `add_state_article_demand`, `add_region_article_demand`, `sway_with_state_article`, `sway_with_region_article` | No state could be a treaty port of ours and no region had unclaimed land |
| `sway_ally`, `sway_with_subject`, `sway_with_pact` | No ally, no subject; the game's sway panel listed no pact and no subjection |

One rule is known to offer more than the game accepts. A treaty article that needs the giver to control a strait is offered for every other country when the played country borders no strait, because the snapshot records a strait's endpoints only when the played country borders it. The game refuses it in about half a second. Other conditions the snapshot cannot decide, such as power projection, are offered the same way and refused with the game's reason.

The standard a production method is reset to is taken to be the method most levels of the building type use in the country. A tie sets no standard, and its buildings are not offered a reset.

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

Row encoding creates one example per recorded decision. State covers finances, population, construction, military, prices, institutions, tariffs and laws. Act features cover the act, its parameters, referenced entities and their immediate categorical attributes. Trait indicators describe targeted characters and interest-group leaders. The row encoder raises when a recorded act's parameters differ from the catalogue, so runs recorded under an older catalogue cannot be mixed into its training rows.

Validation, execution status, after-snapshot presence and picker scores never enter features or training-row eligibility.

The forest and SVR initializers and both CatBoost pickers use the fixed three-metric reward in `advisors/data/endgame.py`; see `rewards.md`. Initializers evaluate complete runs from their opening snapshots and rank-normalize rewards. Pickers evaluate reward from the first snapshot of the pause to the run's last recorded timestamp; acts in the same pause receive the same target.

## Models and tuning

`advisors.models.boosting.Regressor` fits whole-block CatBoost; encoding and parameters live in `advisors/models/histogram`. Row fitting uses `advisors.models.row.model`. Each learned-picker start fits a fresh estimator with the installed hyperparameters. Completed-run caches keep features and reward parts; a new DSN clears them.

Whole-block tuning is described in `histogram_tuning.md`. `python -m advisors.models.row.prepare` creates row data. Long preparation and searches run through the detached process broker.
