"""Phase 1 – Information Gathering: download + cleaning of the data layer sources.

Sources (raw files are downloaded once into data/raw/, delete them to re-download):
  - OSM hiking routes (route=hiking relations in Trentino) via Overpass
  - OSM POIs (restaurants, alpine/wilderness huts) via Overpass
  - SAT trail catalogue (KML: attributes + geometry)
  - Meteotrentino: weather stations, snow-field stations, latest snow observations

Output: cleaned CSVs in data/clean/ and the before/after counts in data/clean/cleaning_log.txt.
Run:  python3 prepare_data.py      (stdlib only, Python >= 3.9)
"""
import csv
import json
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
CLEAN = HERE / "data" / "clean"
UA = {"User-Agent": "KG-2026-UniTn-student-project"}

OVERPASS_MIRRORS = ["https://overpass-api.de/api/interpreter",
                    "https://overpass.kumi.systems/api/interpreter",
                    "https://overpass.private.coffee/api/interpreter"]
OVERPASS = OVERPASS_MIRRORS[0]
TRENTINO = 'area["ref:ISTAT"="022"]["admin_level"="6"]->.t;'
SOURCES = {
    "osm_hiking_routes.json": (OVERPASS, f'[out:json][timeout:180];{TRENTINO}rel(area.t)["route"="hiking"];out tags center;'),
    "osm_pois.json": (OVERPASS, f'[out:json][timeout:180];{TRENTINO}('
                                'nwr(area.t)["amenity"="restaurant"];'
                                'nwr(area.t)["tourism"~"^(alpine_hut|wilderness_hut)$"];);out tags center;'),
    "sat_sentieri.kml.zip": ("https://sentieri.sat.tn.it/download/sentierisat.kml.zip", None),
    "meteo_stazioni.xml": ("https://dati.meteotrentino.it/service.asmx/listaStazioni", None),
    "neve_campi.xml": ("https://dati.meteotrentino.it/service.asmx/listaCampiNeve", None),
    "neve_rilievi.xml": ("https://dati.meteotrentino.it/service.asmx/tuttiUltimiRilieviNeve", None),
}
MISSING = {"", "/", "//", "///", "////"}  # Meteotrentino uses slashes for "not measured"

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(msg)


# ---------------------------------------------------------------- download
def download():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, (url, query) in SOURCES.items():
        path = RAW / name
        if path.exists():
            continue
        data = urllib.parse.urlencode({"data": query}).encode() if query else None
        for u in (OVERPASS_MIRRORS if query else [url]):  # public Overpass servers often time out
            try:
                with urllib.request.urlopen(urllib.request.Request(u, data=data, headers=UA), timeout=300) as r:
                    path.write_bytes(r.read())
                break
            except OSError as err:
                print(f"  {u} failed ({err}), trying next")
        else:
            raise SystemExit(f"could not download {name}")
        print(f"downloaded {name} ({path.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------- helpers
def to_minutes(s):
    """'03:45' / '3:45' / '3h45' / '3h' -> 225 / 225 / 225 / 180; anything else -> None."""
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:h]\s*(\d{1,2})?\s*(min|m)?\s*", s or "")
    return int(m.group(1)) * 60 + int(m.group(2) or 0) if m else None


def to_number(s, cast=float):
    """'12.040' / '12,04 km' / '405 m' -> number; anything else -> None."""
    m = re.search(r"-?\d+(?:[.,]\d+)?", s or "")
    return cast(float(m.group().replace(",", "."))) if m else None


def utm32_to_wgs84(easting, northing):
    """UTM zone 32N (WGS84/ETRS89) -> (lat, lon) in degrees. Standard inverse transverse Mercator."""
    a, f, k0 = 6378137.0, 1 / 298.257223563, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x, y = easting - 500000.0, northing
    mu = y / k0 / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
            + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
            + (151 * e1**3 / 96) * math.sin(6 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1, c1 = math.tan(phi1) ** 2, ep2 * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d**3 / 6
           + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120) / math.cos(phi1)
    return round(math.degrees(lat), 6), round(9 + math.degrees(lon), 6)


def it_date(s):
    """'01/01/1921' or '09/11/2026 00:00:00' -> '1921-01-01'; empty -> ''."""
    s = (s or "").strip()
    return datetime.strptime(s[:10], "%d/%m/%Y").date().isoformat() if s else ""


def xml_records(path, tag):
    """Meteotrentino XML -> list of {field: text} for every <tag> element (namespace stripped)."""
    root = ET.parse(path).getroot()
    out = []
    for el in root.iter():
        if el.tag.split("}")[-1] == tag:
            out.append({c.tag.split("}")[-1]: (c.text or "").strip() for c in el})
    return out


def write_csv(name, rows, fields):
    CLEAN.mkdir(parents=True, exist_ok=True)
    with open(CLEAN / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    log(f"  -> {name}: {len(rows)} rows")


def missing_report(rows, fields):
    for f in fields:
        n = sum(1 for r in rows if r[f] in (None, ""))
        if n:
            log(f"     missing {f}: {n} ({100 * n // len(rows)}%)")


# ---------------------------------------------------------------- cleaning
def clean_osm_routes():
    els = json.loads((RAW / "osm_hiking_routes.json").read_text())["elements"]
    log(f"\n[OSM hiking routes] raw relations: {len(els)}")
    rows, bad = [], {"duration": 0, "distance": 0, "ascent": 0}
    for e in els:
        t = e.get("tags", {})
        r = {
            "osm_id": e["id"],
            "ref": t.get("ref", ""),
            "reg_ref": t.get("reg_ref", ""),  # SAT code (E101/O101): join key with SAT
            "name": t.get("name", ""),
            "from": t.get("from", ""),
            "to": t.get("to", ""),
            "distance_km": to_number(t.get("distance")),
            "duration_forward_min": to_minutes(t.get("duration:forward")),
            "duration_backward_min": to_minutes(t.get("duration:backward")),
            "ascent_m": to_number(t.get("ascent"), int),
            "descent_m": to_number(t.get("descent"), int),
            "cai_scale": t.get("cai_scale", ""),
            "operator": t.get("operator", ""),
            "network": t.get("network", ""),
            "roundtrip": t.get("roundtrip", ""),
            "center_lat": e.get("center", {}).get("lat"),
            "center_lon": e.get("center", {}).get("lon"),
        }
        for k, src in [("duration", "duration:forward"), ("distance", "distance"), ("ascent", "ascent")]:
            col = {"duration": "duration_forward_min", "distance": "distance_km", "ascent": "ascent_m"}[k]
            if t.get(src) and r[col] is None:
                bad[k] += 1
        rows.append(r)
    # e.g. distance=1850 with a 40 min duration: metres typed instead of km (implied speed > 20 km/h)
    in_metres = [r for r in rows if r["distance_km"] and r["duration_forward_min"]
                 and r["distance_km"] / (r["duration_forward_min"] / 60) > 20]
    for r in in_metres:
        r["distance_km"] = r["distance_km"] / 1000
    log(f"  fixed {len(in_metres)} distances written in metres instead of km: "
        f"{[r['ref'] for r in in_metres]}")
    no_id = [r for r in rows if not r["ref"] and not r["reg_ref"]]
    rows = [r for r in rows if r["ref"] or r["reg_ref"]]
    log(f"  removed {len(no_id)} relations without ref and reg_ref (cannot be identified)")
    log(f"  unparseable values set to empty: {bad}")
    write_csv("trails_osm.csv", rows, list(rows[0]))
    missing_report(rows, ["reg_ref", "name", "distance_km", "duration_forward_min", "ascent_m", "cai_scale"])


def clean_sat():
    import zipfile
    with zipfile.ZipFile(RAW / "sat_sentieri.kml.zip") as z:
        kml = z.read(next(n for n in z.namelist() if n.endswith(".kml")))
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    pms = ET.fromstring(kml).findall(".//k:Placemark", ns)
    log(f"\n[SAT trails] raw placemarks: {len(pms)}")
    rows, seen, dupes = [], set(), []
    for p in pms:
        d = {s.get("name"): (s.text or "").strip() for s in p.findall(".//k:SimpleData", ns)}
        coords = p.find(".//k:coordinates", ns).text.split()
        (lon0, lat0), (lon1, lat1) = (map(float, coords[0].split(",")[:2]), map(float, coords[-1].split(",")[:2]))
        if d["numero"] in seen:
            dupes.append(d["numero"])
            continue
        seen.add(d["numero"])
        rows.append({
            "sat_code": d["numero"],
            "name": d["denominaz"],
            "difficulty": d["difficolta"],
            "start_locality": d["loc_inizio"],
            "end_locality": d["loc_fine"],
            "start_elevation_m": to_number(d["quota_iniz"], int),
            "end_elevation_m": to_number(d["quota_fine"], int),
            "min_elevation_m": to_number(d["quota_min"], int),
            "max_elevation_m": to_number(d["quota_max"], int),
            "length_m": to_number(d["lun_inclin"], int),
            "duration_forward_min": to_minutes(d["t_andata"]),
            "duration_backward_min": to_minutes(d["t_ritorno"]),
            "mountain_group": d["gr_mont"],
            "municipalities": "|".join(c.strip() for c in d["comuni_toc"].split(",") if c.strip()),
            "maintainer": d["competenza"],
            "start_lat": round(lat0, 6), "start_lon": round(lon0, 6),
            "end_lat": round(lat1, 6), "end_lon": round(lon1, 6),
        })
    log(f"  removed {len(dupes)} duplicate sat_code (kept the first segment): {dupes}")
    write_csv("trails_sat.csv", rows, list(rows[0]))
    missing_report(rows, ["name", "duration_forward_min", "max_elevation_m", "municipalities", "mountain_group"])


def clean_osm_pois():
    els = json.loads((RAW / "osm_pois.json").read_text())["elements"]
    log(f"\n[OSM POIs] raw elements: {len(els)}")
    rows = []
    for e in els:
        t = e.get("tags", {})
        lat, lon = e.get("lat", e.get("center", {}).get("lat")), e.get("lon", e.get("center", {}).get("lon"))
        rows.append({
            "osm_id": f'{e["type"]}/{e["id"]}',
            # matched by amenity=restaurant OR tourism=*_hut: a hotel with a restaurant is a restaurant here
            "poi_type": "restaurant" if t.get("amenity") == "restaurant" else t.get("tourism"),
            "name": t.get("name", ""),
            "elevation_m": to_number(t.get("ele"), int),
            "lat": lat, "lon": lon,
        })
    no_pos = [r for r in rows if r["lat"] is None]
    rows = [r for r in rows if r["lat"] is not None]
    log(f"  removed {len(no_pos)} POIs without coordinates")
    write_csv("pois_osm.csv", rows, list(rows[0]))
    missing_report(rows, ["name", "elevation_m"])
    for typ in sorted({r["poi_type"] for r in rows}):
        log(f"     {typ}: {sum(r['poi_type'] == typ for r in rows)}")


def clean_meteo():
    st = xml_records(RAW / "meteo_stazioni.xml", "anagrafica")
    log(f"\n[Meteotrentino weather stations] raw: {len(st)}")
    rows = [{
        "station_code": s["codice"], "name": s["nome"],
        "elevation_m": to_number(s["quota"], int),
        "lat": to_number(s["latitudine"]), "lon": to_number(s["longitudine"]),
        "start_date": it_date(s["inizio"]), "end_date": it_date(s.get("fine")),
        "active": not s.get("fine"),
    } for s in st]
    log(f"  active stations (no end date): {sum(r['active'] for r in rows)}")
    write_csv("weather_stations.csv", rows, list(rows[0]))

    sn = xml_records(RAW / "neve_campi.xml", "anagrafica_neve")
    log(f"\n[Meteotrentino snow fields] raw: {len(sn)}")
    rows = []
    for s in sn:
        # the XML labels are swapped: 'utmlat' holds the easting, 'utmlon' the northing
        lat, lon = utm32_to_wgs84(float(s["utmlat"]), float(s["utmlon"]))
        rows.append({"snow_station_code": s["codice"], "name": s["nome"],
                     "elevation_m": to_number(s["quota"], int), "lat": lat, "lon": lon})
    write_csv("snow_stations.csv", rows, list(rows[0]))

    obs = xml_records(RAW / "neve_rilievi.xml", "rilievo_neve")
    log(f"\n[Meteotrentino snow observations] raw: {len(obs)}")
    val = lambda o, k: to_number(o.get(k)) if o.get(k, "").strip() not in MISSING else None
    rows = [{
        "snow_station_code": o["codStaz"], "date": it_date(o["dataMis"]),
        "snow_depth_cm": val(o, "hs"), "fresh_snow_cm": val(o, "hn"),
        "air_temp_c": val(o, "ta"), "temp_min_c": val(o, "tmin"), "temp_max_c": val(o, "tmax"),
    } for o in obs]
    empty = [r for r in rows if r["snow_depth_cm"] is None and r["fresh_snow_cm"] is None]
    rows = [r for r in rows if r not in empty]
    log(f"  removed {len(empty)} observations without snow depth and fresh snow")
    if rows:
        log(f"  dates covered: {min(r['date'] for r in rows)} .. {max(r['date'] for r in rows)}")
    write_csv("snow_observations.csv", rows, list(rows[0]) if rows else ["snow_station_code"])


def selftest():
    assert to_minutes("03:45") == 225 and to_minutes("3h") == 180 and to_minutes("") is None
    assert to_number("12,04 km") == 12.04 and to_number("405 m", int) == 405 and to_number(None) is None
    assert it_date("09/11/2026 00:00:00") == "2026-11-09"
    # station 'Ala (Convento)' from listaStazioni: est 655530, north 5069007 -> 45.757117, 10.999871
    lat, lon = utm32_to_wgs84(655530, 5069007)
    assert abs(lat - 45.757117) < 1e-4 and abs(lon - 10.999871) < 1e-4, (lat, lon)


if __name__ == "__main__":
    selftest()
    download()
    log(f"Cleaning run {datetime.now():%Y-%m-%d %H:%M}")
    clean_osm_routes()
    clean_sat()
    clean_osm_pois()
    clean_meteo()
    (CLEAN / "cleaning_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
