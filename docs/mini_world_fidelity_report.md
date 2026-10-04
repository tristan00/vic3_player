# Mini-world relationships and opening fidelity

29 September 2026. This replaces the earlier source-text fidelity report and subsequent investigation report.

The generator now projects ownership, countries, military capacity, headquarters, laws, institutions, diplomacy, and state history together. Every generated campaign checks its paused opening buildings and structural relationships before creating a recorded run. Technology exclusions are determined before launching the game and are recorded separately from the eligible building expectations.

## What was wrong

The previous regional tests compared generated scripts with source scripts. They did not establish that the game initialized those buildings. The earlier company probe checked company behavior while its game log contained building, formation, and commander errors.

The saved opening snapshots for old runs 4–17 contained 8,930 levels at locations where generated building history requested 13,132. That historical comparison excluded automatically generated buildings and counted ownership levels, not direct monument levels or barracks implicit in army history. It established a real loss, but was not a complete vanilla building inventory.

Two concrete examples were:

- Old run 16 requested 96 barracks levels for BIC but loaded 68. Combining multiple source owners produced repeated barracks records in Malaya, Cambodia, and Laos; the engine did not add those records together.
- Old run 17 gave COB a Trans-Baikal iron mine whose financial district named Russia as its country and a COB-owned state as its location. The opening mine had zero levels. The other seven sampled player states had no constructed source buildings. Subsistence buildings existed, and gold fields appeared later; the failure concerned the opening constructed economy.

Country selection also preferred source owners, then used other countries as replacements. Military declarations could point to another country's generated state or an absent headquarters. Global scopes, treaties, and state-specific production methods followed inconsistent projection rules. Modernity could leave institutions without their enabling laws or select an army law that caused the engine to reduce barracks levels.

## Projection rules

| Relationship | Current behavior |
| --- | --- |
| Country profile and geography | Sample distinct profiles uniformly from all eligible non-decentralized vanilla countries. Source owners and neighboring countries receive no preference. Identity/name randomness is separate from technology randomness. |
| Country and capital | The generated capital belongs to the generated country. Historical capital and market-capital overrides cannot redirect it to another country's sampled state. |
| State and population | Retain source population records and homelands. Project claims and state variables only through existing references. |
| Buildings sharing a state | Emit one building record per state and type, combining ownership levels. For conflicting production methods, request the largest source record's method set; one merged building cannot have several simultaneous method sets. |
| Private ownership | Resolve the ownership building's location and owning country together. If its original location is absent, establish the ownership building in the asset's generated state under that state's actual country. |
| Company and assets | Keep one company and one coherent headquarters. Use a retained original headquarters when present; otherwise locate it at its largest retained asset footprint. Company-owned assets remain connected to the company, including foreign assets. |
| Barracks and units | Count both explicit barracks and barracks created implicitly by vanilla army declarations. Create that capacity once. Let the game initialize troops from the actual buildings, rather than replaying unrelated donor army declarations and duplicating capacity. |
| Fleets and headquarters | Locate copied fleets and ship location references in owned coastal territory. Omit fleets without an owned coast and remove dependent references to their omitted scopes. |
| Laws and technologies | Use ordinary parent laws for country-specific variants and choose researched laws closest to the requested profile. Preserve the requested technology count. |
| Army law and capacity | Require the selected army law to support the largest retained barracks in the country. Reserve standing army and military drill within the existing technology budget when capacity exceeds peasant levies. |
| Laws and institutions | Initialize laws first. Apply copied institution investment only when the resulting country has that institution. |
| Diplomacy and subjects | Retain projected relationships only when their participants exist. Apply liberty desire after diplomatic initialization and only to an actual subject. |
| Treaties and global history | Project global country/state scopes and treaty participants. Remove commands with missing required endpoints without removing guards and accidentally exposing their alternative branches. |
| Old military deployments | Do not replay deployments to vanilla province/front locations that have no meaning on the generated map. |

The army formation layout and unit mix are initialized by the game from the generated country and its buildings. They are not a reproduction of the donor country's historical order of battle. These checks establish building levels and structural links, not full employment, equal military strength, identical profitability, or exact production methods after the game applies laws.

## Building acceptance contract

Each manifest contains eligible building levels by country, state, and building type. Its separate `excluded_buildings` entries identify levels excluded for missing building technologies and name those technologies. The expected counts are fixed before the game launches; observed losses never lower them.

The opening check compares every eligible location/type against live memory. Equal global totals are insufficient: a loss in one state cannot be hidden by an excess in another. Monuments with direct `level` declarations are included. Unrequested automatic subsistence and ownership buildings do not conceal missing constructed buildings.

A second check verifies capitals, ownership endpoints, company headquarters, formation headquarters, unit countries, unit supporting buildings, and the one-to-one relationship between regular units and barracks levels. A discrepancy aborts campaign startup before a recorded run is created. Legacy manifests without expectations are rejected and must be regenerated.

Both opening reports and every generated history category are archived with the world. This replaces the earlier archive that kept only population, building, and state history.

## Verification

All operational checks below loaded paused at 1 January 1836. The retained run settings were regenerated with the corrected generator; they are new worlds, not repaired historical recordings.

| Check | Eligible levels | Loaded levels | Missing-technology exclusions | Regular units | Checked relationship errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Western Europe, 5 countries / 33 states | 1,537 | 1,537 | 34 | 288 | 0 |
| Old run 17 settings, Siberia, 3 countries / 27 states | 21 | 21 | 0 | 13 | 0 |
| Old run 16 settings, 12 countries / 79 states | 1,385 | 1,385 | 3 | 577 | 0 |
| First relaunched run, 13 countries / 65 states | 506 | 506 | 14 | 234 | 0 |

The final run 16 check also contains no invalid-law replacement messages or history script errors. The run 17 and Western Europe checks contain no history script errors. Unrelated engine/rendering and capture warnings are not represented as a clean entire game log.

The first relaunched run was independently checked against its recorded opening snapshot, run 1 / sequence 0 / phase `start`, with the same 506-of-506 result.

Short verification suites passed: 35 world tests in 8.8 seconds and 59 map, control, archive, and timing tests in 3.1 seconds. A separate projection check over all 14 retained historical layouts passed in 4.5 seconds, checking reference closure, ownership consistency, duplicate elimination, and level accounting. That projection check is explicitly a script check, not a substitute for a game load. Game launches and paused operational inspections ran detached from the agent.

Evidence:

- `artifacts/building_fix/accepted5/result.json`: the three complete paused-load comparisons.
- `artifacts/building_fix/accepted6/result.json`: final run 16 verification after the remaining law-eligibility correction.
- `artifacts/building_fix/matrix.json`: projections of the 14 retained layouts.
- `artifacts/building_fix/relaunch.json`: direct comparison with the new recorded opening snapshot.
- `artifacts/military_investigation/`: evidence captured before the old database records were wiped.

## Reset and running batch

Deleted 18 old runs and 29 stored worlds, including dependent snapshots, training observations, and recorded models. Removed seven old directories from the production and dashboard world catalogs. Before restarting, the database had zero runs and zero worlds.

Started supervised batch `collect_116` with 94 total runs, 10 initial warmup runs, 12 minutes per run, the existing random/SMAC/SVR advisors, and first/CatBoost pickers. New run 1 is using the random advisor and first picker, as required for warmup. Its validated opening reports are present in the world archive.

Reset records are in `artifacts/building_fix/reset.json` and `removed_worlds.json`; the supervisor log is `D:/vic3_data/interface/supervisor.log`.
