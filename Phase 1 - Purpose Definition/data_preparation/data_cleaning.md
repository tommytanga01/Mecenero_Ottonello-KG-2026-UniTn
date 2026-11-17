# Data cleaning – Phase 1 (Purpose Definition / Information Gathering)

This file records **what** was cleaned in Phase 1, **why**, and **what it changed**.
Each later phase keeps its own `data_cleaning.md` in its own folder.

- Script: [`prepare_data.py`](prepare_data.py). How to run it, the sources and the licenses are in [`README.md`](README.md).
- Numbers: [`data/clean/cleaning_log.txt`](data/clean/cleaning_log.txt) is generated on every run and is the **source of truth** for counts. The counts below are copied from the run of **2026-11-17** (data snapshot of the same day). If the script is re-run, update them from the log.

## Summary

| Dataset | Raw | Clean | Output file |
|---|---|---|---|
| OSM hiking routes | 1657 | 1485 | `trails_osm.csv` |
| SAT trails | 1082 | 1080 | `trails_sat.csv` |
| OSM POIs (restaurants, huts) | 1860 | 1860 | `pois_osm.csv` |
| Meteotrentino weather stations | 208 | 208 | `weather_stations.csv` |
| Meteotrentino snow fields | 55 | 55 | `snow_stations.csv` |
| Meteotrentino snow observations | 10 | 10 | `snow_observations.csv` |

Rules applied to all datasets:
- Durations become minutes (`HH:MM` → int), distances become km, elevations become integer metres, dates become ISO `YYYY-MM-DD`.
- A value that cannot be parsed is left **empty** (never guessed) and counted in the log.
- Column names are in English, `snake_case`, with the unit in the name (`duration_forward_min`, `length_m`, `distance_km`).

## 1. OSM hiking routes → `trails_osm.csv`

| # | Problem found | Decision | Why | Effect |
|---|---|---|---|---|
| 1.1 | 172 relations have neither `ref` nor `reg_ref` | Removed | Without a number the trail cannot be identified or linked to SAT | 1657 → 1485 |
| 1.2 | `distance` written in metres instead of km (e.g. 627B: `1850` with a 40 min duration) | Divided by 1000 when the implied speed is above 20 km/h | Not physically possible on foot; the duration confirms the unit error | 5 trails fixed: 627B, 177, 419A, SMC, 24 |
| 1.3 | Real multi-day routes (Sentiero della Pace 520 km, Alte Vie) | Kept unchanged | Their distances are correct, and rule 1.2 does not touch them because they have no duration | — |
| 1.4 | Mixed formats in `duration`, `distance`, `ascent` (`"3:45"`, `"12,04 km"`, `"405 m"`) | Parsed to numbers | Needed for CQs like "under N hours" | 1 unparseable duration left empty |
| 1.5 | The trail number is split into `ref` ("101", ambiguous) and `reg_ref` ("E101", SAT code) | Both kept; `reg_ref` is the join key with SAT | "101" exists both East (E101) and West (O101) of the Adige | 1081 routes have `reg_ref` |

Remaining gaps, not fixable from this source: name 59%, duration 22%, ascent 23%, distance 20% missing. SAT covers most of them (see section 2).

## 2. SAT trails → `trails_sat.csv`

| # | Problem found | Decision | Why | Effect |
|---|---|---|---|---|
| 2.1 | Codes E396 and E731 appear twice (two segments each) | Kept the first segment | One row per trail code is needed for identification | 1082 → 1080 |
| 2.2 | No coordinates in the attributes | Start/end point taken from the first/last point of the track | Needed for "near me" and for linking to weather stations | All 1080 trails have start and end coordinates |
| 2.3 | `comuni_toc` is a comma-separated text | Split and re-joined with `\|` | Prepares the link Trail → Municipality (one value per municipality) | — |
| 2.4 | Durations as text (`02:40`) | Converted to minutes | Same as 1.4 | No missing durations |
| 2.5 | `denominaz` (name) is empty for most trails | Kept empty | SAT identifies trails by number; the name can come from OSM | Name missing in 63% |

SAT is the **primary source for trails**: complete durations, min/max elevation, municipalities and mountain group. OSM adds names and the few trails not managed by SAT.

## 3. OSM POIs → `pois_osm.csv`

| # | Problem found | Decision | Why | Effect |
|---|---|---|---|---|
| 3.1 | Some elements are both a hotel (`tourism`) and a restaurant (`amenity`) | Classified as `restaurant` | They were downloaded because they serve food; that is what the CQ asks | 1511 restaurants, 189 alpine huts, 160 wilderness huts |
| 3.2 | Ways/areas have no single point | Used the center computed by Overpass | One point per POI is enough for distance checks | 0 POIs without coordinates |

## 4. Meteotrentino → `weather_stations.csv`, `snow_stations.csv`, `snow_observations.csv`

| # | Problem found | Decision | Why | Effect |
|---|---|---|---|---|
| 4.1 | Stations list includes closed stations (end date set) | Kept, with an `active` flag | Historical stations may be useful; the flag lets us filter | 113 of 208 active |
| 4.2 | Snow fields have UTM 32N coordinates, and the XML tags are swapped (`utmlat` holds the easting, `utmlon` the northing) | Converted to WGS84 lat/lon, reading the tags swapped | All other sources use lat/lon; the swap was verified against a station with known lat/lon (selftest in the script) | 55 fields, all inside Trentino |
| 4.3 | `///` used for "not measured" | Converted to empty | It is a missing value, not a number | — |
| 4.4 | The "latest observations" service returns only the last week | Kept as is for now | Snow history will come from the historical service (see open points) | 10 rows, 3 fields |

## 5. Checks done after cleaning

- All coordinates fall inside Trentino. The one exception is Alta Via 9 (OSM), which crosses into Veneto.
- No duplicated IDs in any file; in no SAT trail is the minimum elevation above the maximum.
- SAT ↔ OSM join through `reg_ref`: **1078 of 1080** SAT trails match.
- On the 1061 matched trails that have a duration in both sources, it is identical in 1018 cases and differs by more than 30 minutes in 8.

## 6. Open points (decisions pending, see Notion "Proposte dati (17/11)")

- Weather measurements (rain, snow) from Open-Meteo for two months (one winter, one summer): months to be chosen.
- Snow history from Meteotrentino (`rilieviNeveDiUnGiornoCsv`) for the winter month, plus the rule linking a trail to a snow field (distance, elevation).
- Trail points every 500 m along the SAT track, and the threshold for "near" a POI.
- Trail duration for CQs: outbound only, or outbound + return.
