# Data preparation (Phase 1 – Information Gathering)

`prepare_data.py` downloads the data-layer sources into `data/raw/` and writes cleaned CSVs to `data/clean/`.
It uses only the Python standard library. Before/after counts are written to `data/clean/cleaning_log.txt`.

```bash
python3 prepare_data.py
```

Raw files are downloaded only if they are missing. Delete `data/raw/` to get a fresh snapshot (the snapshot date is in the log).

## Sources

| Raw file | Source | License |
|---|---|---|
| `osm_hiking_routes.json` | OSM, `route=hiking` relations in the Provincia di Trento (Overpass) | ODbL |
| `osm_pois.json` | OSM, `amenity=restaurant`, `tourism=alpine_hut / wilderness_hut` (Overpass) | ODbL |
| `sat_sentieri.kml.zip` | SAT trail catalogue, https://sentieri.sat.tn.it/download/ | ODbL |
| `meteo_stazioni.xml` | Meteotrentino `listaStazioni` | CC-BY |
| `neve_campi.xml` | Meteotrentino `listaCampiNeve` | CC-BY |
| `neve_rilievi.xml` | Meteotrentino `tuttiUltimiRilieviNeve` | CC-BY |

## Clean outputs

| File | One row per | Key |
|---|---|---|
| `trails_osm.csv` | OSM hiking relation | `osm_id`; `reg_ref` = SAT code |
| `trails_sat.csv` | SAT trail | `sat_code` (E101 / O101) |
| `pois_osm.csv` | restaurant / hut | `osm_id` |
| `weather_stations.csv` | Meteotrentino station | `station_code` (T0154) |
| `snow_stations.csv` | snow-observation field | `snow_station_code` (21MB) |
| `snow_observations.csv` | snow observation (station, day) | `snow_station_code` + `date` |

## Cleaning steps

- Durations are converted to minutes (`HH:MM` → int), distances to km, elevations to int. Unparseable values are left empty and counted in the log.
- OSM routes without either `ref` or `reg_ref` are removed, because they cannot be identified.
- OSM distances that imply a speed above 20 km/h (e.g. `distance=1850` with a 40 min duration) were typed in metres; they are divided by 1000 (5 trails). Long multi-day routes (Sentiero della Pace, Alte Vie) are kept as they are.
- For the two SAT codes that appear twice (E396, E731), only the first segment is kept.
- SAT start and end coordinates come from the first and last point of the trail geometry.
- In the snow-field XML the coordinates are UTM 32N, and the fields named `utmlat` / `utmlon` actually contain easting / northing. They are converted to WGS84 lat/lon.
- Meteotrentino uses `///` for "not measured"; these become empty values.

## Facts for the report (snapshot 2026-11-17)

- 1080 SAT trails; 1078 of them match an OSM relation through `reg_ref`.
- `tuttiUltimiRilieviNeve` returned only 10 observations covering the last week. Snow history and rain for the "last 3 days" CQs need another source (decision still open: Open-Meteo or periodic collection).

Not included yet: weather measurements (they depend on the open decision about the reference date) and the geometry of the OSM routes (SAT start/end points are used instead).
