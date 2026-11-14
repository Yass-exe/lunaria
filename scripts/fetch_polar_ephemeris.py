#!/usr/bin/env python3
"""Fetch Moon body-fixed sub-solar and sub-Earth coordinates for the poles.

Horizons ``QUANTITIES=15`` on the Moon returns the sub-solar selenographic
longitude/latitude; ``QUANTITIES=14`` returns the sub-Earth (sub-observer)
point. Those are exactly the rotating body-fixed directions the illumination
model needs. A body-equator *vector* frame is inertial in its x-axis and would
make the Sun drift at the wrong rate, so it is deliberately not used here.

All endpoints are public; the NASA API key is never sent.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

try:
    from .common import (
        HORIZONS_API,
        INTERIM_DIR,
        RAW_DIR,
        http_get,
        log,
        utc_now,
        write_csv,
        write_json,
    )
except ImportError:
    from common import (
        HORIZONS_API,
        INTERIM_DIR,
        RAW_DIR,
        http_get,
        log,
        utc_now,
        write_csv,
        write_json,
    )

START = "2024-01-01"
STOP = "2026-01-01"
STEP = "6 h"
AU_KM = 149_597_870.7

# body: (target, center, quantity, label)
TARGETS = {
    "sun": ("301", "500@10", "15,20", "Moon sub-solar point and range seen from the Sun"),
    "earth": ("301", "500@399", "14,20", "Moon sub-Earth point and range seen from Earth"),
}


def horizons_params(target: str, center: str, quantity: str) -> dict:
    return {
        "format": "text",
        "COMMAND": f"'{target}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": f"'{center}'",
        "START_TIME": f"'{START}'",
        "STOP_TIME": f"'{STOP}'",
        "STEP_SIZE": f"'{STEP}'",
        "QUANTITIES": f"'{quantity}'",
        "CSV_FORMAT": "'YES'",
        "ANG_FORMAT": "'DEG'",
        "TIME_ZONE": "'UT'",
    }


def parse_subpoints(text: str) -> list[dict]:
    if "$$SOE" not in text or "$$EOE" not in text:
        snippet = " ".join(text.split())[:400]
        raise ValueError(f"Horizons response has no ephemeris block: {snippet}")
    block = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    rows = []
    for raw in block.splitlines():
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 6:
            continue
        try:
            stamp = datetime.strptime(parts[0], "%Y-%b-%d %H:%M").replace(
                tzinfo=timezone.utc
            )
            lon = float(parts[3])
            lat = float(parts[4])
            range_km = float(parts[5]) * AU_KM
        except (ValueError, IndexError):
            continue
        rows.append(
            {
                "utc": stamp.isoformat().replace("+00:00", "Z"),
                "lon_deg": round(lon, 6),
                "lat_deg": round(lat, 6),
                "range_km": round(range_km, 3),
            }
        )
    if not rows:
        raise ValueError("Horizons ephemeris block parsed to zero rows")
    return rows


def fetch(force: bool = False) -> dict:
    manifest = []
    all_rows = []
    for body, (target, center, quantity, label) in TARGETS.items():
        raw_path = RAW_DIR / "horizons" / "polar" / f"{body}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if raw_path.exists() and not force:
            text = raw_path.read_text(encoding="utf-8")
            log(f"cached polar/{body}")
        else:
            text = http_get(
                HORIZONS_API, horizons_params(target, center, quantity), timeout=180
            ).decode("utf-8", errors="replace")
            raw_path.write_text(text, encoding="utf-8")
            log(f"fetched polar/{body} ({len(text):,} bytes)")
        rows = parse_subpoints(text)
        for row in rows:
            row["body"] = body
        all_rows.extend(rows)
        manifest.append(
            {
                "body": body,
                "label": label,
                "rows": len(rows),
                "start": START,
                "stop": STOP,
                "step": STEP,
            }
        )
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        INTERIM_DIR / "polar_ephemeris.csv",
        all_rows,
        ["utc", "body", "lon_deg", "lat_deg", "range_km"],
    )
    write_json(
        RAW_DIR / "horizons" / "polar" / "fetch_manifest.json",
        {"fetched_at": utc_now(), "requests": manifest, "row_count": len(all_rows)},
    )
    log(f"Wrote {len(all_rows):,} sub-point rows")
    return {"rows": len(all_rows), "bodies": len(TARGETS)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(fetch(force=args.force))


if __name__ == "__main__":
    main()
