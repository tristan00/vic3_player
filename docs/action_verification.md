# Command execution and verification

`interface/actions/execute.py` sends one interface command to the game and reads back the game's own verdict. `loop/run.py` records that verdict in `loop_action`, beside the act the command carried. Levers and acts are described in `advisors.md`. Execution works on commands only, and "command" below always means an entry of `interface/actions/catalogue.py`.

The loop decides from PostgreSQL. Each pause is recorded and read back as `interface.options.stored.Stored`; the commands on offer, the candidate blocks and the picker's scores all come from that stored snapshot. Commands reach the game through GUI states injected by the control mod. Nothing under `interface/` or `loop/` imports the dashboard.

The collection launches the game without `-debug_mode`. Everything in "Observed against the game" was seen in a game launched that way unless a row says otherwise.

## Request

`Executor.run(name, check=False, **params)` handles one command.

1. `encode` rejects parameters whose names differ from the catalogue entry. Game objects fill up to four typed slots, `interface_p0` to `interface_p3`. A named key becomes a number in `interface_key`, an event its namespace key and ordinal, an integer `interface_n0`, a choice its index in `interface_choice`. A game object, definition or key that cannot be resolved raises `LookupError`: `identity` does so when an object is outside the game database, gone, or found under a different slot.
2. The sequence is read from the game's `interface_seq` and advanced by one. After 2^31 − 1 it returns to 1.
3. The first write sets the parameters, the sequence, `interface_action` (the command's position in the catalogue, counted from one) and `interface_mode` 0.
4. The executor sleeps for `PRIME`, 0.1 s.
5. The second write sets `interface_mode` to 1 to execute or 2 to check, and sets `interface_flip`.
6. `answer` reads the debug log every `POLL`, 5 ms, until the acknowledgement for this sequence is a complete line. It gives up `LIMIT`, 5 s, after the request began; that span includes the prime interval.
7. With an acknowledgement, `run` returns the command name, validity, description and the milliseconds from the first write. Without one, `abort` sets mode 3, waits up to `ABORT_LIMIT`, 1 s, for the log line and zeroes `interface_action`; `run` then raises `LookupError`.

`run` returns as soon as the acknowledgement is read, and `Loop.perform` adds no wait between commands. The loop always executes: nothing in `interface/`, `loop/`, `advisors/` or `dashboard/` passes `check`.

## Game side

`interface/actions/gui.py` generates the states and `interface/runner/control.py` writes them into the control mod when a campaign is launched. A command's states trigger only while `interface_action` holds its code, and then on the mode, the flip bit and the matched game object.

| Catalogue entry | States per flip | Behaviour |
| --- | --- | --- |
| Without a `valid` expression | 2 | Execute stores `IsValid` and `GetDesc` of the command, then runs it. Check stores them only. |
| With a `valid` expression | 3 | Execute calls the callback when the expression holds and stores a refusal when it does not. Check stores the expression's result. |

Every state stores `interface_action_valid` and `interface_action_desc` before it sets `interface_clean`.

Each state first writes the sequence to `interface_fired`, and triggers only while `interface_fired` differs from the current sequence, so a request fires once. The executor keeps one flip bit per command and parameter set and inverts it on every use. Every state exists in two copies, one per flip value, so an identical request triggers the other copy.

A command with a named key or an event waits for `interface_key_ready`. A key widget sets it, and stores the key's name, when `interface_key` holds its code and `interface_mode` is 0. Keys therefore bind during the prime interval. The key trigger turns false once the mode leaves 0, so the next request can bind the same key.

`interface_clean` starts a state that closes panels, tooltips, menus, the map interaction and the lens toolbar, and popups too unless the command answered an event. It then runs the scripted GUI `interface_action_done`, which writes `INTERFACE|action|<sequence>|<0 or 1>|<description>` to the debug log and zeroes `interface_action` and `interface_key`. Windows with a known close call carry a state that closes them while `interface_clean` is set. Mode 3 sets `interface_clean`, so an aborted request is cleaned up the same way.

## Staged commands

A staged command opens a panel or a popup with its start calls, then works through its stages, and its final state waits for the last of them. 112 commands have a start and 90 have stages; the longest has five.

Every flag of this machinery holds the sequence of the request that set it, and every state that waits on a flag compares it with the current sequence. A flag left by an earlier request therefore counts for nothing.

| Flag | Set by | Read by |
| --- | --- | --- |
| `interface_map_go` | The start state, 0.3 s after it began | The gate, the first stage, the final state of a command without stages, the deadline timer |
| `interface_armed<n>` | Stage `n` when it runs its calls | The stage timer, which copies it into `interface_stage<n>` 0.15 s later |
| `interface_stage<n>` | The stage timer | Stage `n + 1`, the final state after the last stage, a later test |
| `interface_tick` | A deadline timer when it ends | The deadline's refusal |

The start state triggers only while the request has not fired. The game rebuilds a list when a command changes it, a merge of two formations for example, and a rebuilt list item would otherwise start the finished command a second time.

## Refusals without the five-second wait

A request is refused early in three ways. Each stores validity 0 and a description, and then cleans up like any other request.

| Mechanism | Catalogue field | When it refuses | Description stored |
| --- | --- | --- | --- |
| Gate | `admit`, with `prepare` and `reason` | Once, when the start has finished: `prepare` runs, then the expression is stored as `1` or `0` in `interface_admit`. The first stage requires `1`; `0` refuses. Both read the same stored value, so a request is either staged or refused and never both. | The `reason` expression, or `absent` when the command has none |
| Later test | `absent` | After a named stage, while the next stage has not begun, when the entry's expression holds | The entry's own expression, filled with the request's values, or `absent` |
| Deadline | `deadline` | When the final state has not fired within the allowed time after the start finished, or after the mode flip for a command without a start | `absent` |

The allowed time of a deadline is the command's `deadline` plus 0.2 s for each stage; `LISTED`, 0.5 s, is the value every command uses. A deadline timer stores its own request's sequence when it starts and publishes that sequence in `interface_tick` when it ends, so it can refuse only the request that started it. Every timer and every refusal sits in a widget of its own.

A deadline turns "the game's list holds no such entry" into a refusal in about one second. 91 commands carry one: the map-list and lens commands, the building browser forms, charters, transfers and merges, single ships and units, state picks, every treaty draft command, the sways and the war goals. The gate is used by the 36 treaty draft commands.

| Command family | `admit` asks the game | `prepare` |
| --- | --- | --- |
| Treaty proposals on a new draft without an input | The two conditions of the game's own add button: the article type is available between the two countries, `ArticleType.IsAvailable`, and the draft can include it, `TreatyDraft.CanIncludeArticleType`. The reason is the text of whichever fails | `TreatyDraft.ResetAll` |
| Treaty proposals whose article needs an input | That the article type is available; the filled draft is then judged by `TreatyDraft.CanIncludeArticleDraft`, whose text is the refusal's description | `TreatyDraft.ResetAll` |
| Adding to a treaty | That the treaty is not enforced, not under threat and calls in no obligation, and the two conditions above | None |
| Removing from a treaty | The same three conditions on the treaty, and that the draft holds the article | None |

The game keeps a treaty draft per country after its panel closes. Every command that opens a new draft empties it before the gate decides and again in its cleanup, so one proposal never carries the articles of another.

| Timer | Seconds | Use |
| --- | --- | --- |
| `PRIME` | 0.1 | Executor sleep between the two writes |
| Start state | 0.3 | Opening calls of a command that begins from a panel or a selection |
| `STAGE` | 0.15 | Each later stage of a staged command |
| `LISTED` | 0.5 | Deadline of a command, plus 0.2 per stage |
| `CLEAN_DELAY` | 0.1 | Cleanup before the acknowledgement is logged |
| `TRANSPORT_WAIT` | 0.3 | Wait for a transport fleet |
| `TRANSPORT_EXPIRE` | 0.5 | Clears the transport flag when nothing else has |
| Confirmation answer | 0.02 | Answers a confirmation popup, a production-method confirmation or a player message after it opens |

## Memory writes

The control variables are script variables of the played country. `Reader.variables` finds them through the current player's variable store on every call and raises when one is missing. No address is kept across a sleep or a wait.

`Reader.write_variables` is the only writer of control variables. It suspends the game process, resolves the addresses, writes, and resumes in a `finally` block. Both request writes, the abort and the abort cleanup use it, and so does `Reader.request_capture`. The game is suspended for the lookup and the write only; the prime interval and the acknowledgement wait run with the game live.

A capture is acknowledged in memory instead of the log. `Reader.captured` resolves the addresses again on every 2 ms poll until `interface_capture_done` is 2 and `interface_capture` is 0.

## Acknowledgement

`GameInterface.log_mark` and `log_since` read the debug log through `LogTail` in `interface/runner/tail.py`. The tail follows `debug*.log` across rotations, polls every 50 ms on its own thread and once more on every read.

`answer` returns only when the acknowledgement line has ended. `verification` then requires exactly one acknowledgement for the sequence in the text logged since the request's mark, with a payload of `0|` or `1|` followed by the description. Several acknowledgements, or any other payload, raise `RuntimeError`. The description is cleaned by `plain`.

## Transport

Five commands are marked `transport` in the catalogue: `station_formation`, `rehome_formation`, `station_selected`, `deploy_to_front` and `set_strategic_objective`. Their states set `interface_transport`, and cleanup waits until it is cleared.

States injected into the transport planner pick a fleet whose transport command is valid, start the transport, and log `INTERFACE|transport|<sequence>|started …` or `refused …`. If the flag is still set after `TRANSPORT_WAIT`, the planner logs `no fleet …`.

When the log holds a transport line for the request's sequence, the last such line decides. `started` is valid; `refused` and `no fleet` are invalid; the description becomes `transport <result>`. Any other text raises `RuntimeError`. Lines for other sequences are ignored. Without a transport line the acknowledgement's own validity stands.

## Commands by what they reach

The catalogue holds 265 commands. Their availability rules are in `interface/options/available.py`. Where a rule cannot decide a condition from the snapshot it offers the command and the game refuses.

| Area | Commands | Offered when |
| --- | --- | --- |
| Production methods | `reset_building_production_methods`, `reset_production_methods` | A building's methods differ from the ones most levels of its type use in the country, and a tie sets no standard; the state form goes through the lens option and the game's list |
| Capitals | `move_capital`, `move_market_capital` | No play, no war, no recent move; an incorporated state that is a homeland of a primary culture, or any incorporated state for the market capital when we own the market |
| Nationalisation | `bulk_expropriate_state` | The law in force allows nationalising without compensation |
| Charters | `grant_building_charter`, `revoke_building_charter`, `grant_region_charter`, `revoke_region_charter` | The company type's building types and extension types, or a colonisable region; the command picks from the game's own lists of possible and active charters |
| Formations | `create_fleet`, `split_army`, `split_fleet`, `merge_armies`, `merge_fleets`, `transfer_ships`, `transfer_ship`, `disband_unit` | A naval headquarters; formations with enough units or ships that are not invading or refitting |
| Fleets | `station_fleet`, `rehome_fleet`, `change_naval_mission_type`, `toggle_naval_mission_region`, `defend_invasion_fleet` | Coastal own states; another naval headquarters; a fleet on a mission; an invasion of us |
| Ships | `assign_flagship`, `unassign_flagship`, `retrofit_ship`, `cancel_retrofit_ship`, `change_ship_template`, `retrofit_fleet_and_station`, `retrofit_all_and_station`, `cancel_ship_for` | A ship type that can be a flagship; another design of the ship's type; a fleet with ships to refit |
| Diplomatic actions with states | `diplomatic_action_first_state`, `diplomatic_action_second_state`, `diplomatic_action_states` | The game listed the state for that side of the action and the action is allowed; an action with states on both sides is a trade |
| Plays | `start_play_country`, `start_play_state`, `start_play_liberation` | A liberation names a country the installed game can create from the target's states. A play for a goal the game allows only in debug mode, regime change in the installed game, is not offered; nor is unification |
| War goals | `add_war_goal_country`, `add_war_goal_state`, `add_war_goal_liberation`, `add_war_goal_article`, `add_goods_war_goal`, `add_state_war_goal`, `add_region_war_goal`, `add_law_war_goal` | Our own play before its countdown; the draft is found by holder, target, article and input. Nationalisation is demanded only of a country that owns buildings here, a treaty port only in a state that can be ours, non-colonisation only for a region with unclaimed land |
| Sways | Twelve, see below | We are a main participant, the play is in its manoeuvre phase and the country has taken no side |
| Pacts | `break_pact` | A pact we began, or a two-sided pact the other country began whose `target_can_break` does not fail, after its forced months |
| Treaties | See below | The other country has no proposal pending with us |

The forced months of a pact count from the first snapshot that lists it. A pact already present at the run's first snapshot counts as free. Forced months, `actor_can_break` and `target_can_break` are read from the installed game's `common/diplomatic_actions`.

### Sways

The game's sway panel first lists kinds of offer. A command picks its kind by comparing the kind's name with the game's own localisation key for it, then finds the offer by its content.

| Command | Kind, by localisation key | Offer matched by | Offered for |
| --- | --- | --- | --- |
| `offer_sway` | `OBLIGATIONS` | The first one listed | Every swayable country |
| `offer_sway_ally` | `SWAY_TYPE_CALL_ALLY` | The first one listed | A country we hold an alliance or a defensive pact with |
| `offer_sway_state` | `SWAY_TYPE_TRANSFER_STATE` | The state | Each of our states |
| `offer_sway_subject` | `SWAY_TYPE_TRANSFER_SUBJECT` | The subject | Each of our subjects whose subject type the game does not bar from sways |
| `offer_sway_pact` | `SWAY_TYPE_DIPLOMATIC_PACT` | The pact type | Pacts the installed game marks `can_be_used_in_sway_offers = yes`; it marks none |
| `offer_sway_subjection` | `SWAY_TYPE_BECOME_SUBJECT` | The pact type | Subject types marked `can_offer_to_become_in_sway_offers = yes`, protectorate and tributary, where the ranks and country types allow the other country to be our overlord |
| `offer_sway_goal_country`, `offer_sway_goal_state` | `WARGOALS` | The war goal type, then its target | The goal types and targets of the war-goal rule |
| `offer_sway_<input>_article` for goods, state, region, law | `WARGOALS` | The enforced article, then its input | Enforceable articles with that input |

`SLOTS` in `loop/run.py` lets a block hold one sway.

### Treaties

A proposal is a row of the game's treaty table whose start date is empty. The rules count only rows with a start date as treaties in force, and offer nothing to a country that has a proposal pending with us in either direction.

| Commands | What the proposal holds |
| --- | --- |
| `offer_treaty_article`, `demand_treaty_article`, `agree_treaty_article` | One article without an input |
| `offer_goods_treaty_article`, `demand_goods_treaty_article` | One article and a good, at the game's default quantity |
| `offer_<input>_treaty_article`, `demand_<input>_treaty_article` for `state`, `region`, `law`, `subject`, `ship`, `monopoly`, `money`, `goods_amount` | One article and its input. A quantity is one of five shares between the smallest and the largest the game accepts, set with `ArticleDraft.SetQuantity` |
| `offer_timed_treaty_article`, `demand_timed_treaty_article`, `agree_timed_treaty_article` | One article and one of the game's six binding periods |
| `offer_obliged_treaty_article`, `demand_obliged_treaty_article`, `agree_obliged_treaty_article` | One article and an obligation owed, called in or asked for |
| `threaten_treaty_article` | A demanded article with a threat of naval hostilities; offered when the expansion that provides the threat is installed |
| `work_out_treaty_article` | A demanded article after the game's "make this work" has added articles on our side |
| `exchange_treaty_articles` | An article we give and an article we demand |
| `amend_<side>_treaty_article`, `amend_drop_<side>_treaty_article` | An article added to, or a renegotiable article removed from, a treaty in force or a proposal made to us |
| `withdraw_treaty` | Withdrawal from a treaty in force that is not enforced on us |

`treaty_articles` offers an article between two countries when none of these triggers fails: the article's `visible` and `possible`, its `can_ratify`, and the trigger of each of its `requirement_to_maintain` blocks, evaluated with the giving country as `source_country` and `first_country` and the other as `target_country` and `second_country`. A condition on a saved scope the evaluator was not given counts as undecided.

Strait conditions are decided from the recorded strait endpoints. The snapshot records a strait's endpoints only when the played country borders it. So the played country is known to border a strait or not, unless it occupies foreign land, while another country that borders none of the recorded straits stays undecided as long as some strait has no recorded endpoints.

## Observed against the game

These were run on a cached mini world in October 2026, in a game launched without `-debug_mode`. "Executed" means the command ran, the game acknowledged it as valid and the next snapshot showed nothing left open. "Valid" means the game's verdict in check mode.

| Commands | Observed |
| --- | --- |
| The decision loop | Three runs of 150 to 250 s on the last builds executed 192 to 226 commands each. None went without an acknowledgement and none left anything open. The last, on the final build, executed 192 commands in 201 s: 184 done and 8 refused, four with the game's own reason and four as `absent`. An earlier run had one request without an acknowledgement, a treaty demand, before the treaty commands had a deadline |
| `reset_building_production_methods`, `reset_production_methods`, `move_market_capital` | Executed. The market capital rule matched the game for all 14 own states. A state the game did not list for a reset was refused as `absent` in 1.0 s. While the rule counted buildings, six of seven statewide resets in one loop run were refused that way; counting levels and leaving ties out keeps the one the game accepted and drops the six |
| `move_capital` | Refused by the game for every state, as the rule expected: none was a homeland of the primary culture |
| `diplomatic_action_second_state` | Executed: a colonial claim on the picked state appeared in the next snapshot. An unlisted state was refused as `absent` |
| `create_fleet`, `split_army`, `split_fleet`, `merge_armies`, `merge_fleets`, `transfer_ships`, `transfer_ship`, `disband_unit`, `station_fleet`, `rehome_fleet` | Executed; the formations and ship counts in the next snapshot changed accordingly. Each also ran valid directly after a check of the same command, and a request sent straight after a merge was judged on its own time |
| `assign_flagship`, `unassign_flagship`, `change_ship_template`, `retrofit_fleet_and_station`, `cancel_ship_for` | Executed. With a flagship named, another ship was refused until the game's five-year lock ends |
| `retrofit_ship`, `cancel_retrofit_ship`, `retrofit_all_and_station` | Refused by the game: no ship was outdated or being refitted |
| `offer_treaty_article`, `demand_treaty_article` | Executed; each proposal appeared as a pending treaty row with its article |
| `offer_goods_treaty_article`, `offer_money_treaty_article`, `demand_money_treaty_article`, `offer_state_treaty_article`, `demand_state_treaty_article`, `offer_ship_treaty_article`, `offer_goods_amount_treaty_article` | Executed, with the input in the pending row |
| `offer_timed_treaty_article`, `demand_timed_treaty_article`, `offer_obliged_treaty_article`, `demand_obliged_treaty_article` | Executed; the pending row carried the chosen binding period |
| `work_out_treaty_article` | Executed: the pending proposal held the demanded article and three articles the game added on our side. Where the game had nothing to add it refused with its own text |
| `exchange_treaty_articles` | Executed: the pending proposal held the article we give and the article we demand |
| `threaten_treaty_article` | Executed for a demanded trade privilege; valid for six of ten sampled demands |
| `amend_offer_treaty_article`, `amend_demand_treaty_article` | Executed three times in loop runs; refused once by the game for the article's own condition |
| Treaty refusals | The game's own reasons came back in about 0.55 s: power projection, rank, relations, debt, control of a strait, a proposal already pending |
| A demand the other country had declined a quarter earlier | In three of four games the game no longer listed the article. Before the treaty commands had a deadline the request ran into the five-second limit; with it, and with both conditions of the add button holding, it ended as `absent` in 1.3 s |
| `start_play_country` for a humiliation | Executed |
| `add_war_goal_state`, `add_war_goal_article`, `add_goods_war_goal`, `add_law_war_goal` | Executed in our own play. For that play the game listed two kinds of goal, conquering a state and enforcing a treaty article, and no goal on a country |
| `offer_sway`, `offer_sway_state` | Valid for every sampled country and state; `offer_sway_state` executed. A second sway in the same play was refused: we were already swaying another country |
| `offer_sway_goal_state`, `offer_sway_goods_article` | Valid for every sampled request |
| `offer_sway_goal_country`, `offer_sway_law_article` | Valid for one of four and two of five sampled requests |
| `offer_sway_pact`, `offer_sway_subjection` | The game's panel listed three kinds of offer, obligations, war goals and state transfers, and no pact and no subjection |
| `add_state_war_goal`, `add_region_war_goal`, `offer_sway_state_article`, `offer_sway_region_article` | Every sampled request ended as `absent` before the rules were narrowed to possible treaty ports and regions with unclaimed land; the test world has neither in reach |
| `bulk_expropriate_state` | Not offered: the law in force forbids it. With debug mode the game's refusal was seen when it was forced |
| `grant_building_charter`, `revoke_building_charter` | With debug mode, after console commands gave a company slot: a monopoly charter was granted and recorded, the granted type left the game's list, and revoking was refused until the charter's five-year lock ends |
| `character_interaction` | With debug mode: all 74 interactions the rule offered, on rulers, heirs, commanders, politicians, magnates and executives, were valid |
| `start_play_country` for regime change | Valid with debug mode only. The game marks that war goal as a debug goal, and without debug mode its goal panel never lists it |

Not seen valid in any game: `start_play_liberation` and `add_war_goal_liberation` (generated worlds define no country that can be created), the region charters, `change_naval_mission_type`, `toggle_naval_mission_region` and `defend_invasion_fleet` (no crewed fleet, no invasion), ending a pact another country began, removing an article from a treaty, `agree_treaty_article` and `agree_timed_treaty_article` (relations were too low for an alliance or a defensive pact, and the game said so), `demand_ship_treaty_article`, `add_war_goal_country`, `add_state_war_goal`, `add_region_war_goal`, the treaty inputs law, region, subject and monopoly, and the sways with an ally, a subject, a pact, a subjection, a state article or a region article.

One request crashed the game: an input command sent by hand with an article that takes no such input. The rules pair each input command only with articles that require that input.

The game keeps an ended pact in its object table until the next month begins. A snapshot taken before then still lists it.

## Recorded outcomes

`Loop.perform` executes one command and `Loop.note` records it through `Store.log_action`. The `loop_action` row holds the command, the act it carried, the snapshot it was drawn from, the snapshot taken afterwards, the status, a detail text and the milliseconds. The command's parameters go to `loop_action_param` and the act's to `loop_decision_param`. The loop's own `set_speed` and `unpause` are recorded under the advisor `loop` with no act. The opening `pause` in `Loop.play` is not recorded.

| Status | Meaning | Written |
| --- | --- | --- |
| `no_object` | `Executor.run` raised `LookupError`: a parameter could not be resolved, or no acknowledgement arrived | At once, with no later snapshot |
| `invalid` | Acknowledged as invalid; the detail is the game's description, or `absent` from a gate without a reason, a later test or a deadline | At once, with no later snapshot |
| `raced` | Invalid for the reason the caller named. Only `unpause` names one, `running` | At once, with no later snapshot |
| `ui_leftover` | Acknowledged as valid, but the next snapshot shows a panel, interaction, map list or window open, or the answered event or proposal still waiting | After the next snapshot |
| `done` | Acknowledged as valid with nothing left over | After the next snapshot |

Valid commands wait in a pending list. After the block, `turn_actions` takes a `post_action` snapshot. If anything is open, every pending command of the pause becomes `ui_leftover`; otherwise each answer is checked against the events and proposals still waiting. Time control is settled the same way against the `post_run` snapshot. A pause in which no command was valid takes no `post_action` snapshot.

Commands that cannot share a pause are grouped in `SLOTS` in `loop/run.py`; a block holds at most one command of each group. The groups keep, for example, a merge and a disbanding of formations, two capital moves, two charters or two sways apart. Two commands that name the same game object cannot share a pause either, and `linked` extends that: a command on a treaty also claims the treaty's other country, so an amendment and a new proposal to that country stay apart.

Some outcomes end the run.

| Condition | Result |
| --- | --- |
| A lookup failed and the played country owns no state | The run ends `defeated`; the command is not recorded |
| `NO_OBJECT_STREAK`, 5, `no_object` results in a row | `perform` raises and the run ends |
| `STUCK_SNAPSHOTS`, 2, snapshots in a row with something open | The run ends `ui_stuck` |
| A malformed or repeated acknowledgement | `perform` does not catch the error and the run ends |

## What outcomes never do

Whether a command or its act validated, verified or executed never enters reward inputs, model features or the selection of training rows. The training queries in `advisors/models/histogram/data.py` and `advisors/models/row/data.py` read the act, its parameters and `before_seq` from `loop_action`. They do not read `status`, `detail`, `after_seq` or `ms`, and they keep acts of every status. Time control carries no act, so it never appears in a block, a feature or a training row. The filter on whole runs is described in `rewards.md`.

A refused act therefore stays in the training rows as an act that was taken. That is why the rules are kept as close to the game as the snapshot allows.

## Tests

`tests/test_verification.py` checks that:

- key widgets bind only in mode 0 and set `interface_key_ready`;
- `write_variables` resolves addresses inside the suspension on every call, also after the store has moved, and resumes the game after a failed lookup or write;
- capture requests go through `write_variables`;
- a request with no acknowledgement makes four protected writes, ending with the abort and its cleanup, and raises `LookupError`;
- consecutive requests advance the game's sequence by one and sleep only for the prime interval;
- validity and description come back as the game logged them;
- an acknowledgement for another sequence, a malformed one and a repeated one all raise;
- a transport result overrides the acknowledgement only for the same sequence, and an unknown result raises;
- every execute and check state of every command stores validity before cleanup.

`tests/test_actions.py` checks the catalogue and the generated GUI text, and that every game function a command names exists in the game's data types.

`tests/test_reach.py` checks, for the game side:

- the gate's one decision feeds both the first stage and the refusal, sits where the command first opens and is forgotten afterwards;
- a proposal is admitted on the two conditions of the game's own button, a refused one carries the game's reason, and every new draft is emptied before the gate decides and again on leaving;
- every command with a deadline is refused when its request runs out, a deadline can refuse only its own request, and a staged command gets time for each stage;
- every stage flag and the start flag count only for the request that set them, and a command opens once and never again after it has fired;
- a later test stops once the next stage has begun and is written for the request;
- every sway picks its kind of offer by the game's name for it and carries no panel position.

It checks, for the rules: pacts and their forced months, pacts another country began, state picks, sways and their phase, unification and debug-only goals, the ratification filter, the strait conditions, the naval threat's expansion, treaty ports, non-colonisation regions, nationalisation demands, the standard production method, the one-sway group and the link from a treaty to its other country.

`tests/test_tail.py` and `tests/test_log_tail.py` check that the log tail follows rotations without losing or repeating lines. `tests/test_loop.py` checks that an answer whose event or proposal is still waiting counts as unanswered. `tests/test_quarterly.py` checks that advancing a quarter issues only the loop's own `unpause`.
