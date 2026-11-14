#!/usr/bin/env python3
"""Fetch topocentric Sun and Earth ephemerides from NASA/JPL Horizons.

The observer is a user-defined site on the Moon (body 301). Horizons returns
apparent azimuth/elevation in the lunar topocentric frame, including the
effect of the site's LOLA elevation above the reference sphere.
"""

from __future__ import annotations

import argparse
import math
import time
from datetime import datetime, timezone

from common import (
    AU_KM,
    C_KM_S,
    HORIZONS_API,
    INTERIM_DIR,
    RAW_DIR,
    ensure_dirs,
    http_get,
    load_sites_enriched,
    log,
    utc_now,
    write_csv,
    write_json,
)

PRIMARY_START = "2026-11-14"
PRIMARY_STOP = "2027-11-14"
LONGTERM_STOP = "2045-07-14"

SCENARIOS = {
    "primary": {
        "start": PRIMARY_START,
        "stop": PRIMARY_STOP,
        "step": "1 h",
        "bodies": ["sun", "earth"],
        "site_filter": lambda site: True,
        "altitude": "actual",
    },
    "datum": {
        "start": PRIMARY_START,
        "stop": PRIMARY_STOP,
        "step": "1 h",
        "bodies": ["sun", "earth"],
        "site_filter": lambda site: site["lat_deg"] <= -60.0,
        "altitude": "zero",
    },
    "longterm": {
        "start": PRIMARY_START,
        "stop": LONGTERM_STOP,
        "step": "6 h",
        "bodies": ["sun", "earth"],
        "site_filter": lambda site: site["lat_deg"] <= -60.0,
        "altitude": "actual",
    },
}

TARGETS = {
    "sun": {"command": "'10'", "quantities": "4"},
    "earth": {"command": "'399'", "quantities": "4,10,20"},
}


def horizons_params(site: dict, body: str, start: str, stop: str, step: str, altitude: str) -> dict:
    alt_km = 0.0
    if altitude == "actual":
        alt_km = float(site["elevation_m"]) / 1000.0 if site.get("elevation_m") is not None else 0.0
    return {
        "format": "text",
        "COMMAND": TARGETS[body]["command"],
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{site['lon_deg']:+.6f},{site['lat_deg']:+.6f},{alt_km:.3f}'",
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": f"'{step}'",
        "QUANTITIES": f"'{TARGETS[body]['quantities']}'",
        "CSV_FORMAT": "'YES'",
        "ANG_FORMAT": "'DEG'",
        "TIME_ZONE": "'UT'",
    }


def parse_horizons(text: str, body: str) -> list[dict]:
    if "$$SOE" not in text or "$$EOE" not in text:
        snippet = " ".join(text.split())[:500]
        raise ValueError(f"Horizons response has no ephemeris block: {snippet}")
    block = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    rows: list[dict] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            stamp = datetime.strptime(parts[0], "%Y-%b-%d %H:%M").replace(tzinfo=timezone.utc)
            azimuth = float(parts[3])
            elevation = float(parts[4])
        except (ValueError, IndexError):
            continue
        row = {
            "utc": stamp.isoformat().replace("+00:00", "Z"),
            "azimuth_deg": round(azimuth, 6),
            "elevation_deg": round(elevation, 6),
            "illum_frac": "",
            "range_au": "",
            "range_km": "",
            "light_time_s": "",
        }
        if body == "earth" and len(parts) >= 8:
            try:
                illum = float(parts[5])
                delta_au = float(parts[6])
                row["illum_frac"] = round(illum, 6)
                row["range_au"] = round(delta_au, 12)
                row["range_km"] = round(delta_au * AU_KM, 3)
                row["light_time_s"] = round(delta_au * AU_KM / C_KM_S, 6)
            except ValueError:
                pass
        rows.append(row)
    if not rows:
        raise ValueError("Horizons ephemeris block parsed to zero rows")
    return rows


def fetch_one(site: dict, body: str, scenario: str, spec: dict, force: bool) -> list[dict]:
    raw_path = RAW_DIR / "horizons" / scenario / f"{site['site_id']}_{body}.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    params = horizons_params(
        site, body, spec["start"], spec["stop"], spec["step"], spec["altitude"]
    )
    if raw_path.exists() and not force:
        text = raw_path.read_text(encoding="utf-8")
        log(f"cached {scenario}/{site['site_id']}/{body}")
    else:
        raw = http_get(HORIZONS_API, params, timeout=120)
        text = raw.decode("utf-8", errors="replace")
        raw_path.write_text(text, encoding="utf-8")
        log(f"fetched {scenario}/{site['site_id']}/{body} ({len(text):,} bytes)")
        time.sleep(1.2)
    rows = parse_horizons(text, body)
    for row in rows:
        row["scenario"] = scenario
        row["site_id"] = site["site_id"]
        row["body"] = body
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default=None)
    parser.add_argument("--sites", nargs="*", default=None)
    args = parser.parse_args()
    ensure_dirs()

    sites = load_sites_enriched()
    # The primary DEM elevation is filled by fetch_terrain.py. If Horizons is
    # run first, load_sites_enriched falls back to 0 km.
    for site in sites:
        if not site.get("elevation_m"):
            log(f"WARNING: no measured elevation for {site['site_id']}; Horizons uses 0 km")

    scenarios = [args.scenario] if args.scenario else list(SCENARIOS)
    all_rows: list[dict] = []
    manifest = []
    for scenario in scenarios:
        spec = SCENARIOS[scenario]
        for site in sites:
            if args.sites and site["site_id"] not in args.sites:
                continue
            if not spec["site_filter"](site):
                continue
            alt_km = (
                float(site["elevation_m"]) / 1000.0
                if spec["altitude"] == "actual"
                else 0.0
            )
            for body in spec["bodies"]:
                rows = fetch_one(site, body, scenario, spec, args.force)
                all_rows.extend(rows)
                manifest.append(
                    {
                        "scenario": scenario,
                        "site_id": site["site_id"],
                        "body": body,
                        "start": spec["start"],
                        "stop": spec["stop"],
                        "step": spec["step"],
                        "altitude_km": alt_km,
                        "rows": len(rows),
                    }
                )

    if not all_rows:
        raise SystemExit("No ephemeris rows fetched")
    fieldnames = [
        "scenario",
        "site_id",
        "body",
        "utc",
        "azimuth_deg",
        "elevation_deg",
        "illum_frac",
        "range_au",
        "range_km",
        "light_time_s",
    ]
    write_csv(INTERIM_DIR / "ephemeris_samples.csv", all_rows, fieldnames)
    write_json(
        RAW_DIR / "horizons" / "fetch_manifest.json",
        {"fetched_at": utc_now(), "requests": manifest, "row_count": len(all_rows)},
    )
    log(f"Wrote {len(all_rows):,} ephemeris rows")


if __name__ == "__main__":
    main()
