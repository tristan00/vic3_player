# Interest group leader features

The whole-block CatBoost picker receives the ideologies and character traits of the interest group leaders an act concerns.

| Histogram | Contribution per relevant leader |
| --- | --- |
| `interest_group.leader_ideologies` | One count for the leader's recorded ideology |
| `interest_group.leader_traits` | One count for each distinct assigned character trait |

The bin carries the act, for example `interest_group.leader_ideologies=negotiate_economy_law.ideology_reformer`. Each distinct leader counts once per act; repeating the act in a block adds the counts again. Counts are not weighted by clout.

| Act | Leaders counted |
| --- | --- |
| `enact_power_structure_law`, `enact_economy_law`, `enact_human_rights_law` | Leaders of all interest groups in the law's country |
| `raise_government`, `lower_government` | Leader of the named interest group, or of every group in its party when it has one |
| `negotiate_power_structure_law`, `negotiate_economy_law`, `negotiate_human_rights_law` | Leader of the named interest group |
| `bolster_movement`, `stop_bolstering_movement`, `suppress_movement`, `stop_suppressing_movement` | Leaders of player groups with positive support clout for that movement |
| Acts with a character parameter | The named character, when an interest group has that character as its leader |

Law and government acts are the catalogue's `LAW_ACTIONS` and `PARTY_ACTIONS`; group, character and movement parameters are recognized by their declared kinds.

Leader identity comes from `interest_group_history.leader`, ideology from `character_history.ideology`, traits from `character_assigned_trait`. Historical training resolves every relationship at or before the block's starting snapshot; live scoring reads the same records. A missing group, leader or character contributes nothing and creates no synthetic bin.
