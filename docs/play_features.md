# Demand target features

Blocks containing `demand_of_country` or `demand_for_state` carry features of the target. `demand_of_country` uses its country parameter. `demand_for_state` uses the owner of its state at the block's starting snapshot. These are the catalogue's `PLAY_ACTIONS`.

| Feature | Value |
| --- | --- |
| `play.relations` | Relation score between player and target |
| `play.gdp_ratio` | Player GDP divided by target GDP |
| `play.prestige_ratio` | Player prestige divided by target prestige |
| `play.truce` | Either side has an unexpired truce |
| `play.player_truce_days` | Days remaining on the player's truce |
| `play.target_truce_days` | Days remaining on the target's truce |
| `play.land_border` | Player-owned land borders target-owned land |
| `play.adjacent_states` | Distinct target-owned states bordering player-owned land |
| `play.target_state_adjacent` | The targeted state borders player-owned land |
| `play.pacts` | Pact types between player and target, with direction |
| `play.treaty_articles` | Article types of their active treaties, with direction |

Each column carries the act, for example `play.land_border=demand_for_state` and `play.pacts=demand_of_country.outgoing.rivalry`. Which columns reach the model is decided by the installed histogram sizes.

Missing metrics and zero denominators are numeric missing values. A known country without a relation record has neutral relations. Land adjacency comes from `world_adjacency` province edges combined with province ownership at the snapshot. Withdrawn treaties and treaties not yet in force are excluded.

Historical lookups use the latest record at or before the block's starting snapshot; live lookups read the same tables with the same calculations.
