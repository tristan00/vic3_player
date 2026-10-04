# Interest group leader features

The whole-block CatBoost picker receives the ideologies and character traits of the interest group leaders an advisor action concerns.

| Histogram | Contribution per relevant leader |
| --- | --- |
| `interest_group.leader_ideologies` | One count for the leader's recorded ideology |
| `interest_group.leader_traits` | One count for each distinct assigned character trait |

The bin carries the advisor action, for example `interest_group.leader_ideologies=negotiate_with_interest_group.ideology_reformer`. Each distinct leader counts once per action; repeating the action in a block adds the counts again. Counts are not weighted by clout.

| Advisor action | Leaders counted |
| --- | --- |
| `negotiate_with_interest_group`, `invite_to_government`, `dismiss_from_government` | Leader of the targeted interest group |
| `invite_party_to_government`, `dismiss_party_from_government` | Leaders of every group in the referenced member's party and country |
| `enact_<law group>`, `impose_law` | Leaders of all interest groups in the law's country; an imposed law uses the subject country |
| `cancel_enactment`, `repeal_amendment` | Leaders of all player interest groups |
| `bolster_movement`, `stop_bolstering_movement`, `suppress_movement`, `stop_suppressing_movement` | Leaders of player groups with positive support clout for that movement |
| Actions with a character parameter | The targeted character, when an interest group has that character as its leader |

Law and party actions are the catalogue's `LAW_ACTIONS` and `PARTY_ACTIONS`; group, character and movement parameters are recognized by their declared kinds.

Leader identity comes from `interest_group_history.leader`, ideology from `character_history.ideology`, traits from `character_assigned_trait`. Historical training resolves every relationship at or before the block's starting snapshot; live scoring reads the same records. A missing group, leader or character contributes nothing and creates no synthetic bin.
