# Mini-world generation and opening checks

A mini world is a mod with a new small map and vanilla content. Every state copies one vanilla state region, its template. Every country copies one vanilla country, its donor. `interface.world.generate.generate` writes the mod, `manifest.json` and `audit.json` to `<data>/worlds/seed_<seed>_<countries>_<states>`.

Three checks cover a world. The generation audit reads the emitted scripts. The opening building check and the opening relationship check read the loaded game.

| Path | Responsibility |
| --- | --- |
| `interface/world/sampling.py` | Seed, size and slider draws |
| `interface/world/generate.py` | Map, mod files, manifest, rewriting of vanilla scripts outside history |
| `interface/world/vanilla.py`, `source.py` | Vanilla templates, countries and history; template assignment |
| `interface/world/project.py`, `nations.py` | Countries, technologies, laws and every history file |
| `interface/world/buildings.py` | Building projection, expected levels, opening building check |
| `interface/world/military.py`, `cultures.py`, `characters.py` | Fleets, pop cultures, ideology uniformity |
| `interface/world/audit.py` | Generation audit |
| `interface/world/relationships.py` | Opening relationship check |
| `interface/world/cache.py` | World cache |

## Size and sliders

`sampling.world_size` draws every quantity below. A slider fixed on the `loop.run` command line replaces its draw. `python -m interface.world` generates one world from explicit values.

| Quantity | Draw | Effect |
| --- | --- | --- |
| States | 20 to 50 | Every state has an owner |
| Countries | states/8 to states/5, rounded down, at least 2 | 2 to 4 countries at 20 states, 6 to 10 at 50 |
| `tech` | .35 to .65 | Mean technology count. 0 is the lowest count among vanilla recognized and unrecognized countries, .5 the mean of the countries that own the source regions, 1 the highest |
| `tech_variation` | .5 to 1.5 | Spread of technology counts between countries, as a multiple of the spread among the source regions' owners. At 0 every country has the same count |
| `copies` | 0 to 1 | Share of countries that keep the donor's tag and name. The others get an unused `X` tag, a generated name and a one-colour flag |
| `country_economy` | .5 to 1.5 | Spread between countries of productive building levels per person, as a multiple of the spread in the source regions |
| `local_economy` | .5 to 1.5 | The same between the states of one country |
| `source_regions` | 1 to 4 | Number of vanilla strategic regions that supply templates. The map has as many strategic regions |
| `ideology_uniformity` | 0 to 1, per country | Chance that a character's ideology is redrawn with equal weight among the ideologies it qualifies for |
| `primary_culture_share` | 0 to 1, per country | Share of the country's population given its primary cultures |

The two per-country sliders are passed as a range and `project.nations` draws a value for each country.

Productive levels exclude military buildings, government administration, the construction sector and the trade centre. Those types are never scaled. With both economy sliders at 1 nothing is scaled. Scaling stops at the template's capped resources and arable land.

`generate` gives each state a target of 5 to 15 provinces. Countries grow from a capital state to log-normally weighted sizes. Up to about 13 percent of the states, coastal and not capitals, are then handed to a country that does not border them and has a coast of its own.

## Projection rules

History commands pass through `project.history_text`. A vanilla reference survives only when its target is in the world: a country when it is a donor, a state when its template was sampled, a strategic region when it is a source region. A province reference never survives.

| Subject | Rule |
| --- | --- |
| Countries | `project.nations` draws a distinct donor for each country, uniformly from the vanilla countries that have a starting history and are not decentralized. The vanilla owners of the sampled templates get no preference. The donor supplies the country definition and per-country history and is the starting point for technologies and laws. Tags kept under `copies`, names and flag colours use a random stream separate from technologies. |
| Capitals | The capital is the state the country grew from, and it is never handed to another country. The definition's `capital` is rewritten to it. `set_capital` and `set_market_capital` are removed from the donor's history. |
| States and population | `source.assignments` gives each state a template from a source region. A coastal template never lands on an inland state. The template supplies resources, arable land, traits, pops, buildings, state history and trade. One country owns the whole state. Pops keep their type, religion and total size. `cultures.population` relabels cultures so that the template owner's primary cultures become the new country's, at the share `primary_culture_share` sets or the template's own share when it is unset. `add_homeland` follows the same mapping. |
| Buildings | `buildings.project` writes one `create_building` per state and type. Direct `level` values and ownership levels of every template record of that type are added up. Production methods and other fields come from the record with the most levels. Ownership levels are multiplied by the state's economic scale and rounded within each ownership block. A type whose unlocking technologies the country lacks is left out whole. |
| Ownership | Country-owned levels go to the generated country of the vanilla owner when that owner is a donor in the world, otherwise to the state's owner. Unscaled types always go to the state's owner. A building owner, such as a financial district, is resolved together with its location: a generated state that copies its vanilla state region and the country that owns that state, or the asset's own state and owner when no state copies it. |
| Companies | A vanilla company is kept when a state copies its headquarters template or holds levels it owns. Its headquarters is the state copying the original headquarters, otherwise the state with the most company-owned levels. The country that owns that state receives `add_company` and the company setup. Every company-owned level, in any country, names that country. |
| Barracks and units | `source.reference` adds to each template one barracks level per non-conscript `combat_unit` that vanilla formations declare in it. These join the declared barracks in one building, unscaled and owned by the state's country. `military.military` drops every army formation and each command that uses its saved scope, so no army is declared. |
| Fleets | A donor fleet is kept only when the country owns a coastal state. Its `hq_region` becomes the strategic region of the country's first coastal state and every state it names becomes that state. Otherwise the fleet and each command using its saved scope are dropped. Other formation commands that name a state, region, province or country are dropped, as is `activate_production_method`. |
| Technologies | `project.tech_counts` sets a count per country from `tech` and `tech_variation`. `nations._techs` starts from the donor's technologies, then adds random researchable ones or removes random ones that nothing held depends on, until the count is exact. The country history lists each technology; tier and era grants are removed. |
| Laws | `project.politics` expands the donor's starting politics into laws and replaces country-specific variants with their parent law. In each law group it activates the law closest in progressiveness to the donor's, among laws without a parent whose unlocking technologies are held. The army model must also allow the country's largest barracks. When that exceeds what peasant levies allow, `standing_army` and `military_drill` are reserved inside the technology count. |
| Institutions | Technologies and laws are written first in the country history. Each `set_institution_investment_level` is wrapped in a `has_institution` condition. |
| Diplomacy and subjects | Donor history in every other per-country folder (diplomacy, diplomatic plays, power blocs, lobbies, governments, characters and the rest) passes through `history_text`. A pact, relation or subject tie survives only when the other country is in the world. `add_liberty_desire` moves to global history under `is_subject = yes`. |
| Treaties and global history | Entries not scoped to a donor follow the same rule, and a state-scoped entry is repeated for every state that copies the template. A command naming an absent target is dropped, so a treaty needs both countries. A block whose `limit` names an absent target is dropped whole. When an `if` or `else_if` is dropped, the `else` branches after it are dropped too, so no alternative runs unguarded. |
| Military deployments | None are written. |
| Scripts outside history | `generate._rewrites` maps donor tags to generated tags in vanilla `common` and `events` scripts. A condition on a state or strategic region becomes a choice among the generated ones that copy it, or `always = no` when none do. Tests for an absent country become `always = no`. Company type conditions and `preferred_headquarters` name generated states only. |

## Generation audit

`audit.audit` reads the emitted history files and writes `audit.json` beside the manifest. It also records source and generated population, levels, excluded levels, arable land and coast for every state.

| Field | Passes when |
| --- | --- |
| `population_structure_preserved` | In every state, pop sizes grouped by everything except culture equal the template's |
| `culture_projection_matches` | The emitted pops equal the records `cultures.population` produced |
| `production_methods_match_projection` | The emitted production methods equal those of the largest eligible template record of each type |
| `duplicate_buildings` | Empty: no state has two records of one building type |
| `ownership_errors` | Empty: every owning building's `region` belongs to its `country` |
| `company_errors` | Empty: every added company has a headquarters in a state its country owns, and every company owner in a building names a company that country adds |
| `coastal_templates_inland` | Zero |

`cache.checked` rejects a world that fails any of these. `generate` only writes the file.

## Building acceptance contract

The manifest lists for every state its `country`, `buildings` (type to levels) and `excluded_buildings` (type to levels and missing technologies). `buildings.expected` computes the levels: direct `level` plus scaled ownership levels, added over the template's records, including the barracks that army formations imply. A type the owning country lacks the technologies for moves whole to `excluded_buildings`. Both are fixed at generation. Nothing read from the game changes them.

`GameInterface.campaign` in `interface/runner/session.py` refuses a manifest whose states have no `buildings`. Once the campaign has loaded, `GameInterface.campaign_ready` calls `buildings.loaded`. It sums the levels of live buildings in game memory by country, state region and building type, and `buildings.compare` reports every expected entry whose loaded total differs. The report is written to `opening_buildings.json` beside the manifest with `expected_buildings`, `expected_levels`, `actual_levels`, `excluded_levels` and `differences`. Any difference raises.

The comparison is per state and type, so a shortfall in one place cannot be offset by a surplus in another. Buildings in the game that the manifest does not list are ignored.

## Opening relationship check

When the buildings match, `relationships.loaded` reads countries, states, buildings, building ownerships, companies, formations, headquarters and combat units from game memory and writes `opening_relationships.json`. Any error raises.

| Link | Requirement |
| --- | --- |
| Capital | Every country's capital is a state it owns |
| Building ownership | The owned building exists. An owning building exists. An owning country exists |
| Company | Its country owns a state in its headquarters state region. Its headquarters building, when it has one, stands in that state |
| Formation | Its home headquarters belongs to its country, and the country owns a state in that headquarters' strategic region |
| Combat unit | Its building stands in a state owned by the unit's country, and its formation belongs to the same country |
| Units and barracks | In every state, the number of combat units based there equals the expected barracks levels |

## Failure and records

`loop.run.session` launches the campaign without waiting, then runs `prepare_recording` and `campaign_ready` side by side. `session` re-raises a failed check once both have finished and before `Loop` is built, so no run is begun. Registration has finished by then, so the world row exists.

Registration (`geography.mini_world` and `Store.world` in `interface/recording`) stores the map data, the manifest, every generated history file and `audit.json` as `world_asset` rows. After both checks pass, `Store.world_reports` stores the two opening reports the same way. A cached world played again keeps its world row and its reports are overwritten.

## World cache

`python -m interface.world.cache build --directory <directory> --count <n> --workers <w>` relaunches itself detached and logs to `build.log` in the directory. `status` prints progress.

- A cache holds at least 1000 worlds. `build` refuses a smaller count and `Cached` refuses an index with fewer completed worlds.
- `jobs` derives the schedule from the cache seed by calling `world_size` with no slider fixed. A resumed build keeps finished worlds.
- Each world must pass `checked`: the mod is where the manifest says, at least one country is not decentralized and the audit passes.
- `fingerprint` hashes every module in `interface/world` except `cache.py`, `__main__.py` and `__init__.py`, then `interface/script.py`, then the path, size and modification time of `victoria3.exe`. `build` and `Cached` refuse a directory with a different fingerprint. Any change to the generator, including the ranges above, needs a new cache directory.
- `loop.run --world-cache` draws worlds uniformly with replacement and rechecks each one. It cannot be combined with fixed sliders, `--tag`, `--pool` or `--vanilla`. Cached worlds stay on disk. A world generated for a single run is deleted after it.

## What the checks do not establish

- The building check counts levels per state and type. It does not read production methods, employment or owners from the game.
- The audit checks production methods, the location of owning buildings and the existence of company owners in the scripts only. It does not check country owners.
- Excluded types are not checked to be absent, and buildings outside the manifest are not examined.
- The relationship check examines objects that exist. A company, fleet, pact or treaty that the game did not create raises nothing.
- Laws, technologies, institutions, pops and diplomacy are never read back from the game.
- No army is declared, so unit types and formation layout are the game's own and not the donor's. Beyond the links above, only the unit count per state is checked.
- The game log is not searched for script errors.
- Only the cache acts on the audit. A world generated directly for a run can fail it and still be played.
- Nothing compares profitability, employment or military strength with vanilla.
