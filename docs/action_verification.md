# Command execution and verification

`interface/actions/execute.py` sends one interface command to the game and reads back the game's own verdict. `loop/run.py` records that verdict in `loop_action`, beside the act the command carried. Levers and acts are described in `advisors.md`. Execution works on commands only, and "command" below always means an entry of `interface/actions/catalogue.py`.

The loop decides from PostgreSQL. Each pause is recorded and read back as `interface.options.stored.Stored`; the commands on offer, the candidate blocks and the picker's scores all come from that stored snapshot. Commands reach the game through GUI states injected by the control mod. Nothing under `interface/` or `loop/` imports the dashboard.

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

`interface_clean` starts a state that closes panels, tooltips, menus and the map interaction, and popups too unless the command answered an event. It then runs the scripted GUI `interface_action_done`, which writes `INTERFACE|action|<sequence>|<0 or 1>|<description>` to the debug log and zeroes `interface_action` and `interface_key`. Windows with a known close call carry a state that closes them while `interface_clean` is set. Mode 3 sets `interface_clean` and clears the stage flags, so an aborted request is cleaned up the same way.

## Staged commands and their gate

A staged command opens a panel or a popup with its start calls, then works through its stages. Each stage waits for the flag of the one before, and the final state waits for the last flag. A stage that finds no list item never arms, and the request then runs into the five-second limit.

A command with an `admit` expression decides once whether its first stage can run. When the start has finished, one state evaluates the expression and stores `1` or `0` in `interface_admit`. The first stage requires `1`. A second state acknowledges the request as invalid with the description `absent` when it reads `0`. Both read the same stored value, so a request is either staged or refused and never both. The gate states sit in the window the command opens first. Start states, final states and refusals clear `interface_admit`.

| Command | `admit` asks the game |
| --- | --- |
| `offer_treaty_article`, `demand_treaty_article`, `agree_treaty_article`, `offer_goods_treaty_article`, `demand_goods_treaty_article` | Whether the draft can include this article type between the two countries, `TreatyDraft.CanIncludeArticleType` |
| `offer_sway` | Whether the sway panel lists an offer type at the wanted position |

`absent` expressions refuse in the same way at a later gate. `offer_sway` has one: after its stage, an offer type that shows no offer is refused.

A goods proposal opens the article's input menu from the draft's list, sets the good on the article draft with `ArticleDraft.SetGood` and adds the draft through the states injected at the menu's own add button. It waits for no item of the goods list.

| Timer | Seconds | Use |
| --- | --- | --- |
| `PRIME` | 0.1 | Executor sleep between the two writes |
| Start state | 0.3 | Opening calls of a command that begins from a panel or a selection |
| `STAGE` | 0.15 | Each later stage of a staged command |
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

## Commands that end, replace, embark, invade and sway

Six commands were added so that every act can fire. Their availability rules are in `interface/options/available.py`.

| Command | What it does in the game | Offered when |
| --- | --- | --- |
| `break_pact` | Executes the diplomatic action of a pact that is active, which ends it | The played country began the pact, the game lets that kind be ended by hand, its forced months have passed and its `actor_can_break` trigger does not fail |
| `replace_principle` | Opens an occupied principle slot of our bloc and submits a principle of another group | We lead the bloc and hold a mandate |
| `embark_formation` | Opens the fleet list for an army and embarks it on the chosen fleet | The army holds only marines, is settled and neither embarked nor invading |
| `plan_land_invasion` | Opens the invasion planner for a state, adds the army and starts the invasion | We are at war and the state belongs to an enemy |
| `plan_naval_invasion` | The same with a fleet added first | The same, and the state is coastal |
| `offer_sway` | Opens the sway panel for a country, picks an offer type by position and sends its first offer | We are a main participant, the play is in its manoeuvre phase and the country has taken no side |

The forced months of a pact count from the first snapshot that lists it. A pact already present at the run's first snapshot counts as free. Forced months and `actor_can_break` are read from the installed game's `common/diplomatic_actions`.

## Observed against the game

These were run on a cached mini world in October 2026, mostly in check mode.

| Command | Observed |
| --- | --- |
| `break_pact` | Valid for improving relations; influence returned from 1225 to 1375 at once. A rivalry four days old was refused with `DIPLO_ACTION_FORCED_DURATION`. A pact that did not exist matched nothing. |
| `offer_sway` | Sent once for real in 0.4 s. The three offer types the panel showed were valid in 0.7 s; positions beyond them returned `absent` in 0.5 s. |
| `offer_treaty_article`, `demand_treaty_article` | All 146 proposals on offer at an opening were acknowledged: 55 valid in 0.7 s, 91 `absent` in 0.5 s. Before the gate, 205 of 1398 such proposals in earlier collection logs ran into the five-second limit. |
| `offer_goods_treaty_article`, `demand_goods_treaty_article` | All 53 sampled proposals were valid in 1.0 s. Before, 108 of 110 in earlier collection logs ran into the limit, because the chosen good was matched by object identity and never matched. |
| `embark_formation` | Acknowledged with the game's refusal: the army held non-marine units and the fleet's marine capacity was too small. |
| `plan_land_invasion`, `plan_naval_invasion` | Acknowledged with the game's refusals: no ships for the land plan across water, no port within reach for the naval plan. No valid invasion was launched. |
| `replace_principle` | Not exercised with a mandate; without one the selection window lists no principle. It shares its stages with `pick_principle`. |

The game keeps an ended pact in its object table until the next month begins. A snapshot taken before then still lists it.

## Recorded outcomes

`Loop.perform` executes one command and `Loop.note` records it through `Store.log_action`. The `loop_action` row holds the command, the act it carried, the snapshot it was drawn from, the snapshot taken afterwards, the status, a detail text and the milliseconds. The command's parameters go to `loop_action_param` and the act's to `loop_decision_param`. The loop's own `set_speed` and `unpause` are recorded under the advisor `loop` with no act. The opening `pause` in `Loop.play` is not recorded.

| Status | Meaning | Written |
| --- | --- | --- |
| `no_object` | `Executor.run` raised `LookupError`: a parameter could not be resolved, or no acknowledgement arrived | At once, with no later snapshot |
| `invalid` | Acknowledged as invalid; the detail is the game's description, or `absent` from a gate | At once, with no later snapshot |
| `raced` | Invalid for the reason the caller named. Only `unpause` names one, `running` | At once, with no later snapshot |
| `ui_leftover` | Acknowledged as valid, but the next snapshot shows a panel, interaction, map list or window open, or the answered event or proposal still waiting | After the next snapshot |
| `done` | Acknowledged as valid with nothing left over | After the next snapshot |

Valid commands wait in a pending list. After the block, `turn_actions` takes a `post_action` snapshot. If anything is open, every pending command of the pause becomes `ui_leftover`; otherwise each answer is checked against the events and proposals still waiting. Time control is settled the same way against the `post_run` snapshot. A pause in which no command was valid takes no `post_action` snapshot.

Some outcomes end the run.

| Condition | Result |
| --- | --- |
| A lookup failed and the played country owns no state | The run ends `defeated`; the command is not recorded |
| `NO_OBJECT_STREAK`, 5, `no_object` results in a row | `perform` raises and the run ends |
| `STUCK_SNAPSHOTS`, 2, snapshots in a row with something open | The run ends `ui_stuck` |
| A malformed or repeated acknowledgement | `perform` does not catch the error and the run ends |

## What outcomes never do

Whether a command or its act validated, verified or executed never enters reward inputs, model features or the selection of training rows. The training queries in `advisors/models/histogram/data.py` and `advisors/models/row/data.py` read the act, its parameters and `before_seq` from `loop_action`. They do not read `status`, `detail`, `after_seq` or `ms`, and they keep acts of every status. Time control carries no act, so it never appears in a block, a feature or a training row. The filter on whole runs is described in `rewards.md`.

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

`tests/test_actions.py` checks the catalogue and the generated GUI text, and that every game function a command names exists in the game's data types. `tests/test_reach.py` checks the availability rules of the six added commands, that the gate's one decision feeds both the first stage and the refusal, and that a goods proposal waits for no list item. `tests/test_tail.py` and `tests/test_log_tail.py` check that the log tail follows rotations without losing or repeating lines. `tests/test_loop.py` checks that an answer whose event or proposal is still waiting counts as unanswered. `tests/test_quarterly.py` checks that advancing a quarter issues only the loop's own `unpause`.
