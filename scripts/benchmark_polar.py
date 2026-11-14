#!/usr/bin/env python3
"""Benchmark the south-polar illumination and scoring pipeline.

Checks, in order:
1. Moon2000 polar-stereographic round-trip geolocation error.
2. Body-fixed vector geometry vs an independent Horizons observer-frame query.
3. Illumination distribution against the analytic no-terrain envelope.
4. Weighted-sum vs weighted-geometric-mean ranking agreement.
5. Legacy six-site illumination values, with explicit discrepancy notes.

Writes data/processed/polar_benchmark.json and prints a compact table.
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    from .common import CONFIG_DIR, HORIZONS_API, INTERIM_DIR, PROCESSED_DIR, http_get, read_json, write_json
    from .polar_model import combine_scores, rank_agreement, score_candidate
except ImportError:
    from common import CONFIG_DIR, HORIZONS_API, INTERIM_DIR, PROCESSED_DIR, http_get, read_json, write_json
    from polar_model import combine_scores, rank_agreement, score_candidate

LUNAR_RADIUS_M = 1_737_400.0
METRICS = PROCESSED_DIR / "polar_cell_metrics.csv"
EPHEMERIS = INTERIM_DIR / "polar_ephemeris.csv"


def projection_round_trip() -> dict:
    """Forward/inverse Moon2000 stereographic error over the study cap."""
    rng = random.Random(42)
    worst = 0.0
    for _ in range(200):
        lat = -90.0 + rng.random() * 10.0
        lon = -180.0 + rng.random() * 360.0
        radius = 2.0 * (LUNAR_RADIUS_M / 1000.0) * math.tan(
            math.radians(90.0 + lat) / 2.0
        )
        x = radius * math.sin(math.radians(lon))
        y = radius * math.cos(math.radians(lon))
        back_lat = -(90.0 - math.degrees(2.0 * math.atan(
            math.hypot(x, y) / (2.0 * (LUNAR_RADIUS_M / 1000.0))
        )))
        back_lon = math.degrees(math.atan2(x, y))
        dlat = abs(back_lat - lat) * 111_000.0
        dlon = abs((back_lon - lon + 180.0) % 360.0 - 180.0) * 111_000.0 * math.cos(math.radians(lat))
        worst = max(worst, math.hypot(dlat, dlon))
    return {
        "samples": 200,
        "max_round_trip_error_m": round(worst, 4),
        "pass": worst < 1.0,
    }


def _parse_horizons_az_el(text: str) -> list[tuple[str, float, float]]:
    block = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    rows = []
    for line in block.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            stamp = datetime.strptime(parts[0], "%Y-%b-%d %H:%M").replace(tzinfo=timezone.utc)
            rows.append((stamp.isoformat().replace("+00:00", "Z"), float(parts[3]), float(parts[4])))
        except ValueError:
            continue
    return rows


def horizons_observer_check(body: str = "sun") -> dict:
    """Compare one body-fixed sub-point series with a topocentric query."""
    if body not in {"sun", "earth"}:
        raise ValueError("body must be 'sun' or 'earth'")
    lat, lon = -89.9, 0.0
    params = {
        "format": "text",
        "COMMAND": "'10'" if body == "sun" else "'399'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon:+.6f},{lat:+.6f},0.0'",
        "START_TIME": "'2024-01-01'",
        "STOP_TIME": "'2024-01-02 18:00'",
        "STEP_SIZE": "'6 h'",
        "QUANTITIES": "'4'",
        "CSV_FORMAT": "'YES'",
        "ANG_FORMAT": "'DEG'",
        "TIME_ZONE": "'UT'",
    }
    text = http_get(HORIZONS_API, params, timeout=120).decode("utf-8", errors="replace")
    observer = _parse_horizons_az_el(text)

    vectors = {}
    with EPHEMERIS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["body"] != body:
                continue
            if row["utc"] < "2024-01-01" or row["utc"] > "2024-01-02T18:00:00Z":
                continue
            lon_s = math.radians(float(row["lon_deg"]))
            lat_s = math.radians(float(row["lat_deg"]))
            unit = np.array(
                [
                    math.cos(lat_s) * math.cos(lon_s),
                    math.cos(lat_s) * math.sin(lon_s),
                    math.sin(lat_s),
                ]
            )
            vectors[row["utc"]] = unit * float(row["range_km"])
    lat_rad, lon_rad = math.radians(lat), math.radians(lon)
    up = np.array([math.cos(lat_rad) * math.cos(lon_rad),
                   math.cos(lat_rad) * math.sin(lon_rad), math.sin(lat_rad)])
    east = np.array([-math.sin(lon_rad), math.cos(lon_rad), 0.0])
    north = np.array([-math.sin(lat_rad) * math.cos(lon_rad),
                      -math.sin(lat_rad) * math.sin(lon_rad), math.cos(lat_rad)])
    diffs = []
    for stamp, az, el in observer:
        vec = vectors.get(stamp)
        if vec is None:
            continue
        topocentric = vec - (LUNAR_RADIUS_M / 1000.0) * up
        unit = topocentric / np.linalg.norm(topocentric)
        our_el = math.degrees(math.asin(float(np.dot(unit, up))))
        our_az = math.degrees(math.atan2(float(np.dot(unit, east)), float(np.dot(unit, north)))) % 360.0
        d_el = abs(our_el - el)
        d_az = abs((our_az - az + 180.0) % 360.0 - 180.0)
        diffs.append((d_el, d_az))
    if not diffs:
        return {"samples": 0, "pass": False, "reason": "no overlapping timestamps"}
    max_el = max(d[0] for d in diffs)
    max_az = max(d[1] for d in diffs)
    return {
        "samples": len(diffs),
        "max_elevation_diff_deg": round(max_el, 5),
        "max_azimuth_diff_deg": round(max_az, 5),
        "pass": max_el < 0.1 and max_az < 0.1,
        "body": body,
        "method": f"Moon body-fixed {body} position with surface parallax vs Horizons topocentric observer at 89.9S, 0E",
    }


def load_metrics() -> dict[str, np.ndarray]:
    cols = {
        "lat_deg": [],
        "lon_deg": [],
        "solar_illumination_fraction": [],
        "earth_visibility_fraction": [],
        "longest_dark_days": [],
        "sunlight_continuity_fraction": [],
        "regional_slope_p90_deg": [],
        "psr_edge_km": [],
        "science_proxy": [],
        "thermal_proxy": [],
        "data_coverage_fraction": [],
    }
    with METRICS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for key in cols:
                value = row.get(key)
                cols[key].append(float(value) if value not in (None, "") else float("nan"))
    return {key: np.asarray(values, dtype=float) for key, values in cols.items()}


def analytic_envelope(ephemeris_path: Path) -> dict:
    """No-terrain solar-illumination fraction by latitude, from Sun vectors."""
    vectors = {"sun": [], "earth": []}
    with ephemeris_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lon_s = math.radians(float(row["lon_deg"]))
            lat_s = math.radians(float(row["lat_deg"]))
            vectors[row["body"]].append(
                [
                    math.cos(lat_s) * math.cos(lon_s),
                    math.cos(lat_s) * math.sin(lon_s),
                    math.sin(lat_s),
                ]
            )
    sun = np.asarray(vectors["sun"])
    sun /= np.linalg.norm(sun, axis=1, keepdims=True)
    bands = {}
    for lat in range(-80, -91, -1):
        lat_rad = math.radians(lat)
        up = np.array([0.0, 0.0, math.sin(lat_rad)])
        # At lon 0, the horizontal component matters: use the full local up.
        up = np.array([math.cos(lat_rad), 0.0, math.sin(lat_rad)])
        elevation = np.degrees(np.arcsin(np.clip(sun @ up, -1.0, 1.0)))
        bands[str(lat)] = {
            "flat_plane_illumination": float(np.mean(elevation > 0.0)),
            "max_solar_elevation_deg": float(np.max(elevation)),
            "min_solar_elevation_deg": float(np.min(elevation)),
        }
    return bands


def distribution(metrics: dict) -> dict:
    illum = metrics["solar_illumination_fraction"]
    earth = metrics["earth_visibility_fraction"]
    dark = metrics["longest_dark_days"]
    coverage = metrics["data_coverage_fraction"]
    return {
        "cells": int(len(illum)),
        "illumination": {
            "min": float(np.nanmin(illum)),
            "median": float(np.nanmedian(illum)),
            "p90": float(np.nanpercentile(illum, 90)),
            "max": float(np.nanmax(illum)),
        },
        "earth_visibility": {
            "min": float(np.nanmin(earth)),
            "median": float(np.nanmedian(earth)),
            "p90": float(np.nanpercentile(earth, 90)),
            "max": float(np.nanmax(earth)),
        },
        "longest_dark_days": {"median": float(np.nanmedian(dark)), "max": float(np.nanmax(dark))},
        "data_coverage": {"median": float(np.nanmedian(coverage)), "min": float(np.nanmin(coverage))},
    }


def scoring_consistency(metrics: dict, sample: int = 20000) -> dict:
    """Compare weighted-sum and geometric-mean rankings on a cell sample."""
    rng = random.Random(42)
    required = (
        "solar_illumination_fraction",
        "earth_visibility_fraction",
        "regional_slope_p90_deg",
        "psr_edge_km",
        "science_proxy",
        "thermal_proxy",
    )
    valid = np.ones(len(metrics["solar_illumination_fraction"]), dtype=bool)
    for key in required:
        valid &= np.isfinite(metrics[key])
    pool = np.flatnonzero(valid)
    take = min(sample, len(pool))
    indices = [int(i) for i in rng.sample(list(pool), take)]
    sum_scores = []
    geo_scores = []
    used = []
    for i in indices:
        result = score_candidate(
            {
                "solar_illumination_fraction": metrics["solar_illumination_fraction"][i],
                "longest_dark_days": metrics["longest_dark_days"][i],
                "sunlight_continuity_fraction": metrics["sunlight_continuity_fraction"][i],
                "earth_visibility_fraction": metrics["earth_visibility_fraction"][i],
                "regional_slope_p90_deg": metrics["regional_slope_p90_deg"][i],
                "psr_edge_km": metrics["psr_edge_km"][i],
                "science_proxy": metrics["science_proxy"][i],
                "thermal_proxy": metrics["thermal_proxy"][i],
                "data_coverage_fraction": metrics["data_coverage_fraction"][i],
            }
        )
        used.append(i)
        sum_scores.append(result["weighted_sum"])
        geo_scores.append(result["weighted_geometric_mean"])
    sum_scores = np.asarray(sum_scores)
    geo_scores = np.asarray(geo_scores)
    order_sum = list(np.argsort(-sum_scores))
    order_geo = list(np.argsort(-geo_scores))
    agreement = rank_agreement(
        [str(used[i]) for i in order_sum], [str(used[i]) for i in order_geo]
    )
    top = 500
    overlap = len(set(order_sum[:top]) & set(order_geo[:top])) / top
    return {
        "sample": len(indices),
        "spearman_rho": round(float(agreement["spearman_rho"]), 4),
        "exact_order_match": bool(agreement["exact_order_match"]),
        "top500_overlap": round(overlap, 4),
        "mean_absolute_gap": round(float(np.mean(np.abs(sum_scores - geo_scores))), 4),
    }


def legacy_comparison(metrics: dict) -> list[dict]:
    sites = read_json(CONFIG_DIR / "sites.json")
    legacy = {}
    legacy_path = PROCESSED_DIR / "criteria_scores.csv"
    if legacy_path.exists():
        with legacy_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["mode"] == "site" and row["criterion_id"] == "solar_illumination":
                    legacy[row["site_id"]] = float(row["raw_value"]) if row.get("raw_value") else None
    if not legacy:
        with legacy_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["criterion"] == "solar_illumination":
                    legacy[row["site"]] = float(row["measured_value"])
    results = []
    for site in sites:
        lat, lon = float(site["lat_deg"]), float(site["lon_deg"])
        if lat > -80.0:
            continue
        distance = np.hypot(
            (metrics["lat_deg"] - lat) * 111.0,
            (metrics["lon_deg"] - lon) * 111.0 * np.cos(np.radians(lat)),
        )
        nearest = int(np.argmin(distance))
        model = float(metrics["solar_illumination_fraction"][nearest])
        old = legacy.get(site["site_id"])
        results.append(
            {
                "site_id": site["site_id"],
                "lat_deg": lat,
                "lon_deg": lon,
                "model_illumination": round(model, 4),
                "legacy_reported": None if old is None else round(old / 100.0, 4),
                "offset_km": round(float(distance[nearest]), 3),
                "note": "legacy value exceeds the no-terrain geometric cap" if old is not None and old / 100.0 > 0.52 else "within flat-plane bounds",
            }
        )
    return results


def main() -> None:
    started = datetime.now(timezone.utc)
    metrics = load_metrics()
    report = {
        "generated_at": started.isoformat(),
        "runtime_seconds_note": "full illumination/score build is ~2 minutes; this benchmark is separate",
        "projection_round_trip": projection_round_trip(),
        "horizons_geometry_cross_check": horizons_observer_check("sun"),
        "horizons_earth_geometry_cross_check": horizons_observer_check("earth"),
        "illumination_distribution": distribution(metrics),
        "analytic_no_terrain_by_latitude": analytic_envelope(EPHEMERIS),
        "scoring_consistency": scoring_consistency(metrics),
        "legacy_comparison": legacy_comparison(metrics),
        "barker_validation": {
            "status": "not_validated",
            "reason": "Exact Barker Site 01/04/07/11 ROI coordinates and 5 m LDEMs are absent.",
        },
    }
    write_json(PROCESSED_DIR / "polar_benchmark.json", report)

    print("POLAR PIPELINE BENCHMARK")
    print("=" * 78)
    rt = report["projection_round_trip"]
    print(f"1. Projection round-trip     max error {rt['max_round_trip_error_m']:.4f} m   [{'PASS' if rt['pass'] else 'FAIL'}]")
    hz = report["horizons_geometry_cross_check"]
    if hz.get("samples"):
        print(f"2. Horizons geometry         n={hz['samples']}, max dEl={hz['max_elevation_diff_deg']:.5f} deg, max dAz={hz['max_azimuth_diff_deg']:.5f} deg   [{'PASS' if hz['pass'] else 'FAIL'}]")
    else:
        print(f"2. Horizons geometry         {hz.get('reason', 'FAILED')}")
    earth_hz = report["horizons_earth_geometry_cross_check"]
    if earth_hz.get("samples"):
        print(f"   Earth geometry            n={earth_hz['samples']}, max dEl={earth_hz['max_elevation_diff_deg']:.5f} deg, max dAz={earth_hz['max_azimuth_diff_deg']:.5f} deg   [{'PASS' if earth_hz['pass'] else 'FAIL'}]")
    else:
        print(f"   Earth geometry            {earth_hz.get('reason', 'FAILED')}")
    d = report["illumination_distribution"]
    print(f"3. Illumination ({d['cells']:,} cells) min/med/p90/max = "
          f"{d['illumination']['min']:.3f}/{d['illumination']['median']:.3f}/"
          f"{d['illumination']['p90']:.3f}/{d['illumination']['max']:.3f}")
    print(f"   Earth visibility med/p90/max = "
          f"{d['earth_visibility']['median']:.3f}/{d['earth_visibility']['p90']:.3f}/"
          f"{d['earth_visibility']['max']:.3f}")
    print("   Analytic no-terrain illumination by latitude:")
    for lat in ("-80", "-84", "-88", "-89", "-90"):
        if lat in report["analytic_no_terrain_by_latitude"]:
            row = report["analytic_no_terrain_by_latitude"][lat]
            print(f"     {lat:>4}S  flat={row['flat_plane_illumination']:.3f}  "
                  f"solar el range {row['min_solar_elevation_deg']:.2f}..{row['max_solar_elevation_deg']:.2f} deg")
    sc = report["scoring_consistency"]
    print(f"4. Sum vs geometric ranking  rho={sc['spearman_rho']:.4f}, top500 overlap={sc['top500_overlap']:.3f}, "
          f"mean gap={sc['mean_absolute_gap']:.4f}   [{'PASS' if sc['spearman_rho'] > 0.9 else 'CHECK'}]")
    print("5. Legacy polar sites (model vs legacy reported illumination):")
    for row in report["legacy_comparison"]:
        print(f"     {row['site_id']:<24} model={row['model_illumination']:.3f}  "
              f"legacy={row['legacy_reported']}  offset={row['offset_km']:.2f} km  {row['note']}")
    print("6. Barker validation          NOT VALIDATED (exact ROIs/5 m LDEMs absent)")
    print("=" * 78)
    print(f"Wrote {PROCESSED_DIR / 'polar_benchmark.json'}")


if __name__ == "__main__":
    main()
