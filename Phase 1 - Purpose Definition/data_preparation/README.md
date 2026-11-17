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

## Cleaning

What was cleaned, why, and the before/after counts are documented in [`data_cleaning.md`](data_cleaning.md), together with the checks done and the open points.
