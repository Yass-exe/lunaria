#!/usr/bin/env python3
"""Build tidy site, ephemeris and terrain tables from the raw NASA pulls."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common import (
    INTERIM_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    ROOT,
    ensure_dirs,
    load_criteria,
    load_sites_enriched,
    log,
    read_csv,
    read_json,
    utc_now,
    write_csv,
    write_json,
)
from lunar_geom import haversine_km, horizon_at

STEP_FALLBACK = {"primary": 1.0, "datum": 1.0, "longterm": 6.0}

SOURCE_BY_DEM = {
    "LRO_LOLA_DEM_SPole875_5mp_v04": "SRC-DEM-01",
    "LRO_LOLA_DEM_SPole75_30mp_v04": "SRC-DEM-02",
    "LRO_LOLA_DEM_Global_256ppd_v06": "SRC-DEM-03",
    "LRO_NAC_DEM_14N304E_2mp": "SRC-DEM-04",
    "NAC_DTM_APOLLO17": "SRC-DEM-05",
}


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def longest_run(flags: list[bool], step_hours: float) -> float:
    best = current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best * step_hours


def transitions(flags: list[bool]) -> int:
    if not flags:
        return 0
    return sum(1 for a, b in zip(flags, flags[1:]) if a != b)


def step_hours(rows: list[dict]) -> float:
    if len(rows) < 2:
        return 1.0
    delta = (parse_dt(rows[1]["utc"]) - parse_dt(rows[0]["utc"])).total_seconds() / 3600.0
    return round(delta, 3)


def pct(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = fraction * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    w = pos - lo
    return ordered[lo] * (1 - w) + ordered[hi] * w


def summarize(
    scenario: str,
    site_id: str,
    sun_rows: list[dict],
    earth_rows: list[dict],
    profile: list[float],
    pinpoint_profile: list[float] | None = None,
) -> dict:
    sun_rows = sorted(sun_rows, key=lambda r: r["utc"])
    earth_rows = sorted(earth_rows, key=lambda r: r["utc"])
    step = step_hours(sun_rows) if sun_rows else STEP_FALLBACK.get(scenario, 1.0)

    sun_el = [float(r["elevation_deg"]) for r in sun_rows]
    sun_az = [float(r["azimuth_deg"]) for r in sun_rows]
    sun_up = [e > 0.0 for e in sun_el]
    sun_up5 = [e > 5.0 for e in sun_el]
    sun_horizon = [horizon_at(profile, az) for az in sun_az]
    sun_vis = [e > h for e, h in zip(sun_el, sun_horizon)]
    sun_vis5 = [e > h + 5.0 for e, h in zip(sun_el, sun_horizon)]

    earth_el = [float(r["elevation_deg"]) for r in earth_rows]
    earth_az = [float(r["azimuth_deg"]) for r in earth_rows]
    earth_up = [e > 0.0 for e in earth_el]
    earth_up5 = [e > 5.0 for e in earth_el]
    earth_up10 = [e > 10.0 for e in earth_el]
    earth_horizon = [horizon_at(profile, az) for az in earth_az]
    earth_vis = [e > h for e, h in zip(earth_el, earth_horizon)]
    earth_vis5 = [e > h + 5.0 for e, h in zip(earth_el, earth_horizon)]
    earth_vis10 = [e > h + 10.0 for e, h in zip(earth_el, earth_horizon)]

    if pinpoint_profile:
        psun_horizon = [horizon_at(pinpoint_profile, az) for az in sun_az]
        psun_vis = [e > h for e, h in zip(sun_el, psun_horizon)]
        psun_vis5 = [e > h + 5.0 for e, h in zip(sun_el, psun_horizon)]
        pearth_horizon = [horizon_at(pinpoint_profile, az) for az in earth_az]
        pearth_vis = [e > h for e, h in zip(earth_el, pearth_horizon)]
        pearth_vis5 = [e > h + 5.0 for e, h in zip(earth_el, pearth_horizon)]
        pearth_vis10 = [e > h + 10.0 for e, h in zip(earth_el, pearth_horizon)]
    else:
        psun_vis = psun_vis5 = pearth_vis = pearth_vis5 = pearth_vis10 = []

    range_km = [float(r["range_km"]) for r in earth_rows if r.get("range_km")]
    light_time = [float(r["light_time_s"]) for r in earth_rows if r.get("light_time_s")]
    illum = [float(r["illum_frac"]) for r in earth_rows if r.get("illum_frac")]

    def frac(flags):
        return sum(1 for f in flags if f) / len(flags) if flags else None

    window_start = sun_rows[0]["utc"] if sun_rows else ""
    window_end = sun_rows[-1]["utc"] if sun_rows else ""
    return {
        "scenario": scenario,
        "site_id": site_id,
        "window_start": window_start,
        "window_end": window_end,
        "step_hours": step,
        "sun_samples": len(sun_rows),
        "sun_up_frac": _r(frac(sun_up), 6),
        "sun_up5_frac": _r(frac(sun_up5), 6),
        "sun_mean_elev_deg": _r(sum(sun_el) / len(sun_el) if sun_el else None, 4),
        "sun_min_elev_deg": _r(min(sun_el) if sun_el else None, 4),
        "sun_max_elev_deg": _r(max(sun_el) if sun_el else None, 4),
        "sun_p10_elev_deg": _r(pct(sun_el, 0.10), 4),
        "sun_p90_elev_deg": _r(pct(sun_el, 0.90), 4),
        "sun_longest_lit_h": _r(longest_run(sun_up, step), 2),
        "sun_longest_dark_h": _r(longest_run([not f for f in sun_up], step), 2),
        "sun_transitions": transitions(sun_up),
        "sun_up_terrain_frac": _r(frac(sun_vis), 6),
        "sun_up5_terrain_frac": _r(frac(sun_vis5), 6),
        "sun_longest_lit_terrain_h": _r(longest_run(sun_vis, step), 2),
        "sun_longest_dark_terrain_h": _r(longest_run([not f for f in sun_vis], step), 2),
        "sun_transitions_terrain": transitions(sun_vis),
        "sun_mean_horizon_deg": _r(sum(sun_horizon) / len(sun_horizon) if sun_horizon else None, 3),
        "earth_samples": len(earth_rows),
        "earth_up_frac": _r(frac(earth_up), 6),
        "earth_up5_frac": _r(frac(earth_up5), 6),
        "earth_up10_frac": _r(frac(earth_up10), 6),
        "earth_mean_elev_deg": _r(sum(earth_el) / len(earth_el) if earth_el else None, 4),
        "earth_min_elev_deg": _r(min(earth_el) if earth_el else None, 4),
        "earth_max_elev_deg": _r(max(earth_el) if earth_el else None, 4),
        "earth_p10_elev_deg": _r(pct(earth_el, 0.10), 4),
        "earth_p90_elev_deg": _r(pct(earth_el, 0.90), 4),
        "earth_azimuth_mean_deg": _r(sum(earth_az) / len(earth_az) if earth_az else None, 3),
        "earth_azimuth_span_deg": _r((max(earth_az) - min(earth_az)) if earth_az else None, 3),
        "earth_longest_outage_h": _r(longest_run([not f for f in earth_up], step), 2),
        "earth_up_terrain_frac": _r(frac(earth_vis), 6),
        "earth_up5_terrain_frac": _r(frac(earth_vis5), 6),
        "earth_up10_terrain_frac": _r(frac(earth_vis10), 6),
        "earth_longest_outage_terrain_h": _r(longest_run([not f for f in earth_vis], step), 2),
        "earth_longest_outage_terrain5_h": _r(longest_run([not f for f in earth_vis5], step), 2),
        "earth_longest_outage_terrain10_h": _r(longest_run([not f for f in earth_vis10], step), 2),
        "earth_mean_horizon_deg": _r(sum(earth_horizon) / len(earth_horizon) if earth_horizon else None, 3),
        "earth_range_km_min": _r(min(range_km) if range_km else None, 1),
        "earth_range_km_max": _r(max(range_km) if range_km else None, 1),
        "earth_range_km_mean": _r(sum(range_km) / len(range_km) if range_km else None, 1),
        "earth_light_time_s_mean": _r(sum(light_time) / len(light_time) if light_time else None, 6),
        "earth_light_time_s_max": _r(max(light_time) if light_time else None, 6),
        "earth_illum_frac_mean": _r(sum(illum) / len(illum) if illum else None, 6),
        "pinpoint_sun_up_terrain_frac": _r(frac(psun_vis), 6),
        "pinpoint_sun_up5_terrain_frac": _r(frac(psun_vis5), 6),
        "pinpoint_sun_longest_dark_terrain_h": _r(longest_run([not f for f in psun_vis], step), 2),
        "pinpoint_earth_up_terrain_frac": _r(frac(pearth_vis), 6),
        "pinpoint_earth_up5_terrain_frac": _r(frac(pearth_vis5), 6),
        "pinpoint_earth_up10_terrain_frac": _r(frac(pearth_vis10), 6),
        "pinpoint_earth_longest_outage_terrain5_h": _r(longest_run([not f for f in pearth_vis5], step), 2),
        "relay_required": "yes"
        if (frac(earth_vis5) is not None and frac(earth_vis5) < 0.99)
        else "no",
        "terrain_model": "LOLA/NAC DEM, 5 km radius horizon, 2 m eye height",
    }


def _r(value, digits):
    if value is None:
        return ""
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return round(float(value), digits)
    return ""


def request_aoi(site: dict, half_km: float = 2.0) -> str:
    # Conservative lat/lon box: widen longitude at high latitude so the box is
    # at least 4 km on the ground.
    dlat = half_km / 30.315
    dlon = half_km / (30.315 * max(math.cos(math.radians(site["lat_deg"])), 0.02))
    return (
        f"{site['lat_deg'] - dlat:.4f}..{site['lat_deg'] + dlat:.4f} N, "
        f"{site['lon_deg'] - dlon:.4f}..{site['lon_deg'] + dlon:.4f} E "
        f"(~{2 * half_km:.0f}x{2 * half_km:.0f} km, center {site['lat_deg']:+.4f}, {site['lon_deg']:+.4f})"
    )


def build_gaps(sites: list[dict], terrain: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for site in sites:
        sid = site["site_id"]
        aoi = request_aoi(site)
        res = terrain.get(sid, {}).get("dem_res_nominal_m")
        try:
            res_val = float(res) if res not in (None, "") else 999.0
        except ValueError:
            res_val = 999.0
        polar = site["lat_deg"] <= -60.0

        lroc_priority = "P0" if res_val > 10 else "P1"
        rows.append(
            {
                "site_id": sid,
                "gap_id": f"{sid}-LROC-NAC-DTM",
                "dataset": "LROC NAC stereo DTM",
                "priority": lroc_priority,
                "status": "placeholder",
                "aoi": aoi,
                "desired_resolution": "1-2 m/px",
                "why": "Final slope, boulder and landing-hazard certification; current DEM is "
                + (f"{res_val:g} m/px" if res_val < 900 else "unavailable"),
                "request_spec": "NAC stereo pair + controlled DTM + orthophoto, 4x4 km, 1-2 m/px, plus error map",
                "request_from": "NASA LROC team / PDS Geosciences",
                "placeholder_file": "placeholders/lroc_nac_dtm.csv",
                "acceptance": "Vertical error < 1 m (1 sigma); slope error < 2 deg at 5 m baseline",
            }
        )
        lola_priority = "P0" if res_val > 60 else ("P1" if res_val > 10 else "P3")
        rows.append(
            {
                "site_id": sid,
                "gap_id": f"{sid}-LOLA-DEM",
                "dataset": "LOLA 5-20 m DEM",
                "priority": lola_priority,
                "status": "placeholder",
                "aoi": aoi,
                "desired_resolution": "5 m/px (20 m acceptable)",
                "why": "Independent terrain check and horizon model at landing-pad scale.",
                "request_spec": "LOLA 5 m/px DEM clip + shot-count/error layer for the AOI",
                "request_from": "NASA LOLA team / PDS Geosciences",
                "placeholder_file": "placeholders/lola_5m_dem.csv",
                "acceptance": "Full AOI coverage; no interpolated holes larger than 2 pixels",
            }
        )
        rows.append(
            {
                "site_id": sid,
                "gap_id": f"{sid}-LROC-ORTHO",
                "dataset": "LROC NAC orthophoto",
                "priority": lroc_priority,
                "status": "placeholder",
                "aoi": aoi,
                "desired_resolution": "0.5-1 m/px",
                "why": "Boulder counts, trafficability, and visual validation of the DEM.",
                "request_spec": "Radiometrically calibrated NAC orthomosaic, 0.5-1 m/px",
                "request_from": "NASA LROC team / PDS",
                "placeholder_file": "placeholders/lroc_nac_ortho.csv",
                "acceptance": "Cloud-free, orthorectified to the DTM; geolocation < 5 m",
            }
        )
        rows.append(
            {
                "site_id": sid,
                "gap_id": f"{sid}-DIVINER",
                "dataset": "Diviner thermal maps / temperature time series",
                "priority": "P1",
                "status": "placeholder",
                "aoi": aoi,
                "desired_resolution": "site-scale, full lunar day",
                "why": "Replace the qualitative thermal score; size radiators and survival power.",
                "request_spec": "Diviner bolometric temperature, summer/winter, day/night time series at the AOI",
                "request_from": "NASA Diviner team / PDS",
                "placeholder_file": "placeholders/diviner_thermal.csv",
                "acceptance": "At least 8 local-time bins and a summer/winter pair",
            }
        )
        if polar:
            rows.append(
                {
                    "site_id": sid,
                    "gap_id": f"{sid}-LEND-WEH",
                    "dataset": "LEND water-equivalent hydrogen",
                    "priority": "P1",
                    "status": "placeholder",
                    "aoi": aoi,
                    "desired_resolution": "0.5 deg (or better)",
                    "why": "Turn PSR proximity into an ice-probability estimate.",
                    "request_spec": "LEND WEH map + uncertainty for the polar AOI",
                    "request_from": "NASA LEND team / PDS",
                    "placeholder_file": "placeholders/lend_weh.csv",
                    "acceptance": "Documented footprint and uncertainty; no unconstrained extrapolation",
                }
            )
            rows.append(
                {
                    "site_id": sid,
                    "gap_id": f"{sid}-MINIRF-CPR",
                    "dataset": "Mini-RF / Mini-SAR CPR",
                    "priority": "P2",
                    "status": "placeholder",
                    "aoi": aoi,
                    "desired_resolution": "75-150 m/px",
                    "why": "Test for ice-bearing regolith and radar roughness inside nearby PSRs.",
                    "request_spec": "CPR and S1 mosaics clipped to the AOI",
                    "request_from": "NASA Mini-RF / PDS",
                    "placeholder_file": "placeholders/mini_rf_cpr.csv",
                    "acceptance": "Calibrated CPR with incidence-angle metadata",
                }
            )
        rows.append(
            {
                "site_id": sid,
                "gap_id": f"{sid}-RELAY",
                "dataset": "Relay communications link budget",
                "priority": "P1" if polar or sid == "von_karman" else "P2",
                "status": "placeholder",
                "aoi": aoi,
                "desired_resolution": "n/a",
                "why": "Direct-to-Earth access is intermittent or absent; continuous comms needs a relay.",
                "request_spec": "Relay orbit, data rate, latency, and outage budget for the site",
                "request_from": "Mission architecture / communications team",
                "placeholder_file": "placeholders/relay_link_budget.csv",
                "acceptance": "Documented coverage fraction and worst-case outage",
            }
        )
    return rows


PLACEHOLDER_SCHEMAS = {
    "lroc_nac_dtm.csv": [
        "site_id", "nac_pair_id", "dtm_id", "resolution_m", "acquisition_date",
        "crs", "bbox_w_deg", "bbox_s_deg", "bbox_e_deg", "bbox_n_deg",
        "vertical_error_m", "url", "status", "notes",
    ],
    "lola_5m_dem.csv": [
        "site_id", "product_id", "resolution_m", "epoch", "crs",
        "bbox_w_deg", "bbox_s_deg", "bbox_e_deg", "bbox_n_deg", "url", "status", "notes",
    ],
    "lroc_nac_ortho.csv": [
        "site_id", "nac_pair_id", "ortho_id", "resolution_m", "incidence_deg",
        "solar_azimuth_deg", "bbox_w_deg", "bbox_s_deg", "bbox_e_deg", "bbox_n_deg",
        "url", "status", "notes",
    ],
    "diviner_thermal.csv": [
        "site_id", "product_id", "season", "local_time_hr", "temperature_k",
        "uncertainty_k", "resolution_m", "url", "status", "notes",
    ],
    "lend_weh.csv": [
        "site_id", "product_id", "weh_pct", "uncertainty_pct", "footprint_km",
        "epoch", "url", "status", "notes",
    ],
    "mini_rf_cpr.csv": [
        "site_id", "product_id", "cpr", "s1", "incidence_deg", "resolution_m",
        "url", "status", "notes",
    ],
    "ground_truth.csv": [
        "site_id", "source", "product_id", "lat_deg", "lon_deg", "elevation_m",
        "measurement", "value", "unit", "url", "status", "notes",
    ],
    "relay_link_budget.csv": [
        "site_id", "relay_asset", "orbit", "data_rate_mbps", "coverage_frac",
        "worst_outage_h", "latency_s", "status", "notes",
    ],
}


def write_placeholders() -> None:
    for name, fields in PLACEHOLDER_SCHEMAS.items():
        path = ROOT / "placeholders" / name
        if not path.exists():
            write_csv(path, [], fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    ensure_dirs()

    sites = load_sites_enriched()
    terrain_rows = {row["site_id"]: row for row in read_csv(PROCESSED_DIR / "terrain_summary.csv")}
    psr_rows = {row["site_id"]: row for row in read_csv(PROCESSED_DIR / "psr_proximity.csv")}
    horizons: dict[str, list[float]] = {}
    for row in read_csv(PROCESSED_DIR / "horizon_profiles.csv"):
        horizons.setdefault(row["site_id"], [0.0] * 360)[int(row["azimuth_deg"])] = float(row["horizon_deg"])
    pinpoint_horizons: dict[str, list[float]] = {}
    pinpoint_path = PROCESSED_DIR / "pinpoint_horizon_profiles.csv"
    if pinpoint_path.exists():
        for row in read_csv(pinpoint_path):
            pinpoint_horizons.setdefault(row["site_id"], [0.0] * 360)[
                int(row["azimuth_deg"])
            ] = float(row["horizon_deg"])

    # Site table joins configuration, DEM, terrain, PSR and NASA image counts.
    image_counts: dict[str, int] = defaultdict(int)
    images_path = RAW_DIR / "nasa" / "images.csv"
    if images_path.exists():
        for row in read_csv(images_path):
            image_counts[row["site_id"]] += 1

    site_rows = []
    for site in sites:
        sid = site["site_id"]
        terrain = terrain_rows.get(sid, {})
        psr = psr_rows.get(sid, {})
        site_rows.append(
            {
                "site_id": sid,
                "name": site["name"],
                "short_name": site["short_name"],
                "lat_deg": site["lat_deg"],
                "lon_deg": site["lon_deg"],
                "region": site["region"],
                "site_type": site["site_type"],
                "earth_side": site["earth_side"],
                "elevation_m": site.get("elevation_m", ""),
                "dem_service": site.get("dem_service", ""),
                "dem_label": site.get("dem_label", ""),
                "dem_res_m": site.get("dem_res_m", ""),
                "dem_source_id": SOURCE_BY_DEM.get(site.get("dem_service", ""), ""),
                "slope_median_deg": terrain.get("slope_median_deg", ""),
                "slope_p90_deg": terrain.get("slope_p90_deg", ""),
                "roughness_m": terrain.get("roughness_m", ""),
                "horizon_max_deg": terrain.get("horizon_max_deg", ""),
                "open_sky_frac_5deg": terrain.get("open_sky_frac_5deg", ""),
                "pinpoint_lat_deg": terrain.get("pinpoint_lat_deg", ""),
                "pinpoint_lon_deg": terrain.get("pinpoint_lon_deg", ""),
                "pinpoint_slope_deg": terrain.get("pinpoint_slope_deg", ""),
                "pinpoint_offset_km": terrain.get("pinpoint_offset_km", ""),
                "psr_edge_km_approx": psr.get("psr_edge_km_approx", ""),
                "psr_feature": psr.get("nearest_psr_feature", ""),
                "nasa_image_count": image_counts.get(sid, 0),
                "science_focus": site["science_focus"],
                "heritage": site["heritage"],
                "notes": site["notes"],
            }
        )
    write_csv(PROCESSED_DIR / "sites.csv", site_rows)

    # Ephemeris summary, one row per site and scenario.
    samples_path = INTERIM_DIR / "ephemeris_samples.csv"
    if not samples_path.exists():
        raise SystemExit("No ephemeris samples; run fetch_horizons.py first")
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in read_csv(samples_path):
        grouped[(row["scenario"], row["site_id"], row["body"])].append(row)

    summary_rows = []
    scenarios = sorted({key[0] for key in grouped})
    for scenario in scenarios:
        for site in sites:
            sid = site["site_id"]
            sun = grouped.get((scenario, sid, "sun"), [])
            earth = grouped.get((scenario, sid, "earth"), [])
            if not sun or not earth:
                continue
            profile = horizons.get(sid)
            if not profile or all(v == 0.0 for v in profile):
                profile = [0.0] * 360
            pinpoint_profile = pinpoint_horizons.get(sid)
            summary_rows.append(
                summarize(scenario, sid, sun, earth, profile, pinpoint_profile)
            )
    summary_rows.sort(key=lambda r: (r["scenario"], r["site_id"]))
    summary_fields = [
        "scenario", "site_id", "window_start", "window_end", "step_hours",
        "sun_samples", "sun_up_frac", "sun_up5_frac", "sun_mean_elev_deg",
        "sun_min_elev_deg", "sun_max_elev_deg", "sun_p10_elev_deg", "sun_p90_elev_deg",
        "sun_longest_lit_h", "sun_longest_dark_h", "sun_transitions",
        "sun_up_terrain_frac", "sun_up5_terrain_frac", "sun_longest_lit_terrain_h",
        "sun_longest_dark_terrain_h", "sun_transitions_terrain", "sun_mean_horizon_deg",
        "earth_samples", "earth_up_frac", "earth_up5_frac", "earth_up10_frac",
        "earth_mean_elev_deg", "earth_min_elev_deg", "earth_max_elev_deg",
        "earth_p10_elev_deg", "earth_p90_elev_deg", "earth_azimuth_mean_deg",
        "earth_azimuth_span_deg", "earth_longest_outage_h", "earth_up_terrain_frac",
        "earth_up5_terrain_frac", "earth_up10_terrain_frac",
        "earth_longest_outage_terrain_h", "earth_longest_outage_terrain5_h",
        "earth_longest_outage_terrain10_h", "earth_mean_horizon_deg",
        "earth_range_km_min", "earth_range_km_max", "earth_range_km_mean",
        "earth_light_time_s_mean", "earth_light_time_s_max", "earth_illum_frac_mean",
        "pinpoint_sun_up_terrain_frac", "pinpoint_sun_up5_terrain_frac",
        "pinpoint_sun_longest_dark_terrain_h", "pinpoint_earth_up_terrain_frac",
        "pinpoint_earth_up5_terrain_frac", "pinpoint_earth_up10_terrain_frac",
        "pinpoint_earth_longest_outage_terrain5_h",
        "relay_required", "terrain_model",
    ]
    write_csv(PROCESSED_DIR / "ephemeris_summary.csv", summary_rows, summary_fields)
    log(f"Wrote sites.csv ({len(site_rows)}) and ephemeris_summary.csv ({len(summary_rows)})")

    # Source registry and data-gap / placeholder bookkeeping.
    sources = read_json(ROOT / "config" / "sources.json")["sources"]
    write_csv(
        PROCESSED_DIR / "source_registry.csv",
        sources,
        ["source_id", "name", "type", "url", "status", "accessed", "credit", "notes"],
    )

    gaps = build_gaps(sites, terrain_rows)
    write_csv(
        PROCESSED_DIR / "data_gaps.csv",
        gaps,
        [
            "site_id", "gap_id", "dataset", "priority", "status", "aoi",
            "desired_resolution", "why", "request_spec", "request_from",
            "placeholder_file", "acceptance",
        ],
    )
    write_placeholders()
    write_json(
        PROCESSED_DIR / "build_manifest.json",
        {
            "built_at": utc_now(),
            "sites": len(site_rows),
            "ephemeris_summaries": len(summary_rows),
            "gaps": len(gaps),
            "criteria_count": len(load_criteria()),
        },
    )
    log(f"Wrote source registry, {len(gaps)} data-gap rows, and placeholder schemas")


if __name__ == "__main__":
    main()
