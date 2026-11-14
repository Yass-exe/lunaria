#!/usr/bin/env python3
"""Refine shortlisted 1 km south-polar regions on the ~148 m source DEM.

The full-cap pass is intentionally a fast 1 km screen. This module evaluates
only its shortlisted cells on the source raster before producing a provisional
pinpoint seed. The seed is not a 5 m landing pad and is never labelled as
hazard-certified.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
import rasterio

try:
    from .common import CONFIG_DIR, INTERIM_DIR, PROCESSED_DIR, read_csv, write_csv, write_json
    from .polar_illumination import (
        equivalent_circle_edge_distance,
        continuity_window_samples,
        lat_lon_from_xy,
        load_ephemeris,
        sampled_run_duration_days,
        science_value_proxy,
        thermal_stability_proxy,
        topocentric_direction_components,
        xy_from_lat_lon,
    )
    from .polar_model import (
        SCORE_DIMENSIONS,
        combine_scores,
        dirichlet_sensitivity,
        load_scoring_policy,
        rank_agreement,
        score_candidate,
    )
except ImportError:
    from common import CONFIG_DIR, INTERIM_DIR, PROCESSED_DIR, read_csv, write_csv, write_json
    from polar_illumination import (
        equivalent_circle_edge_distance,
        continuity_window_samples,
        lat_lon_from_xy,
        load_ephemeris,
        sampled_run_duration_days,
        science_value_proxy,
        thermal_stability_proxy,
        topocentric_direction_components,
        xy_from_lat_lon,
    )
    from polar_model import (
        SCORE_DIMENSIONS,
        combine_scores,
        dirichlet_sensitivity,
        load_scoring_policy,
        rank_agreement,
        score_candidate,
    )

LUNAR_RADIUS_M = 1_737_400.0
FILL = -1.0e9
NODATA = -9999.0

DEFAULT_DEM = Path("data/raw/rasters/south_pole_lola_dem_4096.tif")
DEFAULT_METRICS = PROCESSED_DIR / "polar_cell_metrics.csv"
DEFAULT_REGIONS = PROCESSED_DIR / "polar_region_ranking.csv"
DEFAULT_EPHEMERIS = INTERIM_DIR / "polar_ephemeris.csv"


def fine_horizon_for_observers(
    elevation: np.ndarray,
    observer_rows: np.ndarray,
    observer_cols: np.ndarray,
    *,
    pixel_size_m: float,
    bins: int = 96,
    max_km: float = 60.0,
) -> np.ndarray:
    """Return terrain horizon radians for selected fine-raster observers."""
    surface = np.asarray(elevation, dtype=np.float32)
    rows = np.asarray(observer_rows, dtype=int)
    cols = np.asarray(observer_cols, dtype=int)
    if surface.ndim != 2 or rows.shape != cols.shape:
        raise ValueError("elevation must be 2D and observer coordinates must match")
    if pixel_size_m <= 0 or bins <= 0 or max_km <= 0:
        raise ValueError("pixel size, bins, and horizon distance must be positive")
    if np.any(rows < 0) or np.any(rows >= surface.shape[0]):
        raise ValueError("observer row lies outside the elevation raster")
    if np.any(cols < 0) or np.any(cols >= surface.shape[1]):
        raise ValueError("observer column lies outside the elevation raster")

    z0 = surface[rows, cols].astype(np.float64)
    valid_observer = np.isfinite(z0) & (z0 > FILL / 2)
    if not np.all(valid_observer):
        raise ValueError("all observer elevations must be valid")
    dip = -np.arccos(
        LUNAR_RADIUS_M / (LUNAR_RADIUS_M + np.maximum(z0, 0.0))
    )
    horizon = np.repeat(dip[:, None], bins, axis=1)

    max_pixels = max(1, int(math.ceil(max_km * 1000.0 / pixel_size_m)))
    near_end = min(max_pixels, max(1, int(math.ceil(6_000.0 / pixel_size_m))))
    medium_end = min(max_pixels, max(near_end, int(math.ceil(20_000.0 / pixel_size_m))))
    distances = list(range(1, near_end + 1))
    distances.extend(range(near_end + 4, medium_end + 1, 4))
    distances.extend(range(medium_end + 10, max_pixels + 1, 10))
    if max_pixels not in distances:
        distances.append(max_pixels)
    distances = sorted(set(distances))

    height, width = surface.shape
    for bin_index in range(bins):
        azimuth = 2.0 * math.pi * bin_index / bins
        for distance_pixels in distances:
            target_rows = rows + int(round(-distance_pixels * math.cos(azimuth)))
            target_cols = cols + int(round(distance_pixels * math.sin(azimuth)))
            valid = (
                (target_rows >= 0)
                & (target_rows < height)
                & (target_cols >= 0)
                & (target_cols < width)
            )
            if not np.any(valid):
                continue
            target = np.full(len(rows), FILL, dtype=np.float64)
            target[valid] = surface[target_rows[valid], target_cols[valid]]
            distance_m = distance_pixels * pixel_size_m
            angle = (
                np.arctan2(target - z0, distance_m)
                - distance_m / (2.0 * LUNAR_RADIUS_M)
            )
            horizon[:, bin_index] = np.maximum(horizon[:, bin_index], angle)
    return horizon.astype(np.float32)


def _observer_geometry(
    latitude_deg: np.ndarray,
    longitude_deg: np.ndarray,
) -> tuple[np.ndarray, ...]:
    lat = np.radians(latitude_deg)
    lon = np.radians(longitude_deg)
    cos_lat, sin_lat = np.cos(lat), np.sin(lat)
    cos_lon, sin_lon = np.cos(lon), np.sin(lon)
    return (
        cos_lat * cos_lon,
        cos_lat * sin_lon,
        sin_lat,
        -sin_lon,
        cos_lon,
        -sin_lat,
        cos_lat,
        cos_lon,
        sin_lon,
    )


def evaluate_observers(
    latitude_deg: np.ndarray,
    longitude_deg: np.ndarray,
    horizons_rad: np.ndarray,
    ephemeris: dict[str, np.ndarray],
    *,
    continuity_days: float = 6.5,
    observer_elevation_m: np.ndarray | None = None,
    return_timeline: bool = False,
) -> dict[str, np.ndarray | list[dict]]:
    """Evaluate Sun/Earth terrain clearance for selected observers."""
    lat = np.asarray(latitude_deg, dtype=float)
    lon = np.asarray(longitude_deg, dtype=float)
    horizons = np.asarray(horizons_rad, dtype=float)
    if lat.shape != lon.shape or horizons.shape[0] != len(lat):
        raise ValueError("observer coordinates and horizons must have matching rows")
    if horizons.ndim != 2 or horizons.shape[1] <= 0:
        raise ValueError("horizons must have shape (observers, azimuth bins)")
    elevation = (
        np.zeros(len(lat), dtype=float)
        if observer_elevation_m is None
        else np.asarray(observer_elevation_m, dtype=float)
    )
    if elevation.shape != lat.shape or np.any(~np.isfinite(elevation)):
        raise ValueError("observer elevations must be finite and match coordinates")
    observer_radius_km = (LUNAR_RADIUS_M + elevation) / 1000.0
    bins = horizons.shape[1]
    times = len(ephemeris["sun"])
    if times != len(ephemeris["earth"]) or times != len(ephemeris["utc"]):
        raise ValueError("ephemeris bodies and timestamps must be aligned")

    ax, ay, up_z, east_x, east_y, north_xy, north_z, cos_lon, sin_lon = _observer_geometry(lat, lon)
    cell_index = np.arange(len(lat), dtype=np.int64) * bins
    sin_horizon = np.sin(horizons).ravel()
    sun_count = np.zeros(len(lat), dtype=np.int32)
    earth_count = np.zeros(len(lat), dtype=np.int32)
    dark_run = np.zeros(len(lat), dtype=np.int32)
    max_dark = np.zeros(len(lat), dtype=np.int32)
    window_len = continuity_window_samples(continuity_days, step_hours=6.0)
    history = np.zeros((window_len, len(lat)), dtype=bool)
    window_count = np.zeros(len(lat), dtype=np.int16)
    lit_windows = np.zeros(len(lat), dtype=np.int32)
    timeline: list[dict] = []

    for time_index in range(times):
        states: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for body in ("sun", "earth"):
            x, y, z = ephemeris[body][time_index]
            center_up = x * ax + y * ay + z * up_z
            center_east = x * east_x + y * east_y
            center_north = north_xy * (x * cos_lon + y * sin_lon) + z * north_z
            upward, eastward, northward = topocentric_direction_components(
                center_up,
                center_east,
                center_north,
                range_km=float(ephemeris[f"{body}_range_km"][time_index]),
                observer_radius_km=observer_radius_km,
            )
            azimuth = (np.degrees(np.arctan2(eastward, northward)) + 360.0) % 360.0
            bin_index = (azimuth * bins / 360.0).astype(np.int64) % bins
            visible = upward > sin_horizon[cell_index + bin_index]
            elevation = np.degrees(np.arcsin(np.clip(upward, -1.0, 1.0)))
            terrain = np.degrees(horizons[np.arange(len(lat)), bin_index])
            states[body] = (visible, elevation, terrain)

        sun_visible = states["sun"][0]
        earth_visible = states["earth"][0]
        sun_count += sun_visible
        earth_count += earth_visible
        dark_run = np.where(sun_visible, 0, dark_run + 1)
        np.maximum(max_dark, dark_run, out=max_dark)

        pos = time_index % window_len
        old = history[pos].copy()
        window_count += sun_visible.astype(np.int16) - old.astype(np.int16)
        history[pos] = sun_visible
        if time_index >= window_len - 1:
            lit_windows += window_count == window_len

        if return_timeline:
            if len(lat) != 1:
                raise ValueError("timeline output requires exactly one observer")
            timeline.append(
                {
                    "utc": str(ephemeris["utc"][time_index]),
                    "sun_elevation_deg": float(states["sun"][1][0]),
                    "sun_horizon_deg": float(states["sun"][2][0]),
                    "sun_visible": bool(sun_visible[0]),
                    "earth_elevation_deg": float(states["earth"][1][0]),
                    "earth_horizon_deg": float(states["earth"][2][0]),
                    "earth_visible": bool(earth_visible[0]),
                }
            )

    return {
        "solar_illumination_fraction": sun_count / times,
        "earth_visibility_fraction": earth_count / times,
        "longest_dark_days": sampled_run_duration_days(
            max_dark, sample_count=times, step_hours=6.0
        ),
        "sunlight_continuity_fraction": lit_windows
        / max(1, times - window_len + 1),
        "timeline": timeline,
    }


def _local_slope_p90(
    slope: np.ndarray, rows: np.ndarray, cols: np.ndarray, radius_pixels: int
) -> np.ndarray:
    values = np.empty(len(rows), dtype=float)
    for index, (row, col) in enumerate(zip(rows, cols)):
        window = slope[
            max(0, row - radius_pixels) : row + radius_pixels + 1,
            max(0, col - radius_pixels) : col + radius_pixels + 1,
        ]
        finite = window[np.isfinite(window)]
        values[index] = float(np.percentile(finite, 90)) if len(finite) else math.nan
    return values


def _load_psr_catalog(path: Path) -> tuple[np.ndarray, np.ndarray]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    centers, areas = [], []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        if any(props.get(key) is None for key in ("Cent__Lat_", "Cent__Long", "Area__km2_")):
            continue
        centers.append(
            xy_from_lat_lon(float(props["Cent__Lat_"]), float(props["Cent__Long"]))
        )
        areas.append(float(props["Area__km2_"]))
    if not centers:
        raise ValueError("PSR catalogue contains no centroid/area records")
    return np.asarray(centers, dtype=float), np.asarray(areas, dtype=float)


def _fine_pixels_for_members(
    transform,
    shape: tuple[int, int],
    member_positions: set[tuple[int, int]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    height, width = shape
    x = transform.c + (np.arange(width) + 0.5) * transform.a
    y = transform.f + (np.arange(height) + 0.5) * transform.e
    coarse_cols = np.floor((x + 304_000.0) / 1000.0).astype(int)
    coarse_rows = np.floor((304_000.0 - y) / 1000.0).astype(int)
    pairs = []
    for coarse_row, coarse_col in member_positions:
        fine_rows = np.flatnonzero(coarse_rows == coarse_row)
        fine_cols = np.flatnonzero(coarse_cols == coarse_col)
        if len(fine_rows) and len(fine_cols):
            rr, cc = np.meshgrid(fine_rows, fine_cols, indexing="ij")
            pairs.extend(zip(rr.ravel().tolist(), cc.ravel().tolist()))
    if not pairs:
        raise ValueError("shortlisted region does not intersect the source DEM")
    unique = sorted(set(pairs))
    rows = np.asarray([pair[0] for pair in unique], dtype=int)
    cols = np.asarray([pair[1] for pair in unique], dtype=int)
    return rows, cols, x[cols], y[rows]


def select_provisional_seed(candidates: list[dict]) -> dict:
    """Select the best non-disqualified fine cell and label it honestly."""
    eligible = [candidate for candidate in candidates if not candidate["disqualified"]]
    if not eligible:
        raise ValueError("refined region contains no eligible provisional seed")
    winner = max(
        eligible,
        key=lambda row: (
            float(row["weighted_geometric_mean"]),
            float(row["weighted_sum"]),
            str(row["candidate_id"]),
        ),
    )
    return {
        **winner,
        "status": "provisional_148m_seed",
        "hazard_certified": False,
        "required_data": "5 m Barker/LOLA LDEM or 1-2 m LROC NAC stereo DTM with error layer",
    }


def _four_km_aoi(latitude_deg: float, longitude_deg: float) -> str:
    km_per_degree = math.pi * (LUNAR_RADIUS_M / 1000.0) / 180.0
    latitude_delta = 2.0 / km_per_degree
    longitude_delta = 2.0 / (km_per_degree * math.cos(math.radians(latitude_deg)))
    return (
        f"lat {latitude_deg-latitude_delta:.6f}..{latitude_deg+latitude_delta:.6f}; "
        f"lon {longitude_deg-longitude_delta:.6f}..{longitude_deg+longitude_delta:.6f} "
        "(approximately 4 x 4 km)"
    )


def write_polar_data_gaps(path: Path, seed: dict) -> None:
    aoi = _four_km_aoi(float(seed["lat_deg"]), float(seed["lon_deg"]))
    rows = [
        {
            "priority": "P0",
            "gap_id": "winner_barker_ldem",
            "dataset": "Barker/LOLA 5 m LDEM with error and valid-pixel mask",
            "aoi": aoi,
            "desired_resolution": "5 m/px native",
            "why": "Validate illumination and meaningful local slope without treating interpolated pixels as observations.",
            "request_spec": "Exact Barker site product ID, controlled GeoTIFF, vertical error, LOLA shot count, and valid/interpolated-pixel mask.",
            "request_from": "NASA GSFC LOLA / PDS Geosciences",
            "placeholder_file": "placeholders/barker_ldem_inventory.csv",
            "acceptance": "Product provenance and CRS verified; valid fraction reported; error layer aligned pixel-for-pixel.",
            "status": "missing",
        },
        {
            "priority": "P0",
            "gap_id": "winner_lroc_nac_dtm",
            "dataset": "LROC NAC stereo DTM",
            "aoi": aoi,
            "desired_resolution": "1-2 m/px",
            "why": "Resolve slopes, scarps, craters, and boulder-scale context hidden by the 148 m screening source.",
            "request_spec": "Controlled NAC stereo pair, DTM GeoTIFF, control report, vertical-error map, and source image IDs.",
            "request_from": "LROC Science Operations Center / PDS Imaging",
            "placeholder_file": "placeholders/lroc_nac_dtm.csv",
            "acceptance": "Vertical error <1 m (1 sigma), slope error <2 degrees at 5 m baseline, geolocation <5 m.",
            "status": "missing",
        },
        {
            "priority": "P0",
            "gap_id": "winner_lroc_nac_ortho",
            "dataset": "LROC NAC controlled orthophoto",
            "aoi": aoi,
            "desired_resolution": "0.5-1 m/px",
            "why": "Screen metre-scale rocks and verify the provisional seed against the stereo terrain.",
            "request_spec": "Radiometrically calibrated orthophoto tied to the requested DTM, with incidence and emission metadata.",
            "request_from": "LROC Science Operations Center / PDS Imaging",
            "placeholder_file": "placeholders/lroc_nac_ortho.csv",
            "acceptance": "Orthorectified to DTM, geolocation <5 m, no unexplained holes larger than 2 pixels.",
            "status": "missing",
        },
        {
            "priority": "P0",
            "gap_id": "artemis_region_geometry",
            "dataset": "Official Artemis III candidate-region polygons",
            "aoi": "80-90 S",
            "desired_resolution": "authoritative vector geometry",
            "why": "Associate ranked raster clusters with NASA's named regions without inventing boundaries.",
            "request_spec": "Versioned polygon layer for all 13 regions, source CRS, release date, and provenance URL.",
            "request_from": "NASA Artemis / Moon Trek geospatial team",
            "placeholder_file": "placeholders/artemis_iii_region_geometry.csv",
            "acceptance": "All 13 official names present; valid non-empty polygons; CRS and version documented.",
            "status": "missing",
        },
        {
            "priority": "P1",
            "gap_id": "winner_diviner",
            "dataset": "Diviner thermal time series",
            "aoi": aoi,
            "desired_resolution": "best available, full lunar day and seasonal pair",
            "why": "Replace the Tier C poleward thermal proxy with temperatures and uncertainty.",
            "request_spec": "Calibrated surface temperature/H-parameter time series with local time, season, resolution, and uncertainty.",
            "request_from": "Diviner / PDS Geosciences",
            "placeholder_file": "placeholders/diviner_thermal.csv",
            "acceptance": "At least 8 local-time bins and summer/winter coverage with uncertainty.",
            "status": "missing",
        },
        {
            "priority": "P1",
            "gap_id": "winner_volatile_evidence",
            "dataset": "LEND WEH and Mini-RF CPR",
            "aoi": aoi,
            "desired_resolution": "native products with uncertainty/incidence layers",
            "why": "Replace PSR proximity with actual volatile-evidence measurements.",
            "request_spec": "LEND water-equivalent hydrogen plus Mini-RF CPR/S1 with footprint, incidence, epoch, and uncertainty.",
            "request_from": "LEND and Mini-RF teams / PDS",
            "placeholder_file": "placeholders/lend_weh.csv;placeholders/mini_rf_cpr.csv",
            "acceptance": "Registered to the AOI with uncertainty and native footprint/resolution reported.",
            "status": "missing",
        },
        {
            "priority": "P1",
            "gap_id": "winner_relay_link_budget",
            "dataset": "Relay availability and link budget",
            "aoi": aoi,
            "desired_resolution": "mission architecture",
            "why": "Turn graded direct-to-Earth visibility into an operational communications result.",
            "request_spec": "Relay ephemeris, antenna assumptions, data rate, margin, latency, coverage, and worst outage.",
            "request_from": "Mission communications team",
            "placeholder_file": "placeholders/relay_link_budget.csv",
            "acceptance": "Coverage and worst outage reproduced for the provisional seed and mission dates.",
            "status": "missing",
        },
    ]
    fields = list(rows[0])
    write_csv(path, rows, fields)


def run(
    *,
    dem_path: Path = DEFAULT_DEM,
    metrics_path: Path = DEFAULT_METRICS,
    regions_path: Path = DEFAULT_REGIONS,
    ephemeris_path: Path = DEFAULT_EPHEMERIS,
    output_dir: Path = PROCESSED_DIR,
    bins: int = 96,
    horizon_km: float = 60.0,
) -> dict:
    stage1_metrics = {row["candidate_id"]: row for row in read_csv(metrics_path)}
    stage1_regions = read_csv(regions_path)
    if not stage1_regions:
        raise ValueError("stage-one ranking has no regions to refine")
    ephemeris = load_ephemeris(ephemeris_path)
    policy = load_scoring_policy(CONFIG_DIR / "polar_scoring.json")
    psr_centers, psr_areas = _load_psr_catalog(Path("data/raw/trek/psr_sp.geojson"))

    with rasterio.open(dem_path) as source:
        elevation = source.read(1, masked=False).astype(np.float32)
        transform = source.transform
        pixel_size_m = abs(transform.a)
        source_nodata = source.nodata
    valid = np.isfinite(elevation)
    if source_nodata is not None:
        valid &= elevation != source_nodata
    surface = np.where(valid, elevation, np.nan)
    dy, dx = np.gradient(surface, pixel_size_m, pixel_size_m)
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))

    refined_cells = []
    region_summaries = []
    seed_horizons: dict[str, tuple[dict, np.ndarray]] = {}
    for region_number, region in enumerate(stage1_regions, start=1):
        member_ids = [value for value in region["member_cell_ids"].split(";") if value]
        members = [stage1_metrics[candidate_id] for candidate_id in member_ids]
        positions = {(int(row["row"]), int(row["col"])) for row in members}
        fine_rows, fine_cols, x_m, y_m = _fine_pixels_for_members(
            transform, elevation.shape, positions
        )
        observer_valid = valid[fine_rows, fine_cols]
        fine_rows, fine_cols = fine_rows[observer_valid], fine_cols[observer_valid]
        x_m, y_m = x_m[observer_valid], y_m[observer_valid]
        print(
            f"refining {region['region_id']}: {len(fine_rows):,} source pixels",
            file=sys.stderr,
        )
        horizons = fine_horizon_for_observers(
            elevation,
            fine_rows,
            fine_cols,
            pixel_size_m=pixel_size_m,
            bins=bins,
            max_km=horizon_km,
        )
        latitude, longitude = lat_lon_from_xy(x_m, y_m)
        observer_elevation = elevation[fine_rows, fine_cols].astype(float)
        visibility = evaluate_observers(
            latitude,
            longitude,
            horizons,
            ephemeris,
            observer_elevation_m=observer_elevation,
        )
        local_slope = _local_slope_p90(
            slope,
            fine_rows,
            fine_cols,
            max(1, int(round(500.0 / pixel_size_m))),
        )
        psr_distance = equivalent_circle_edge_distance(
            np.column_stack([x_m / 1000.0, y_m / 1000.0]),
            psr_centers,
            psr_areas,
        )
        candidates = []
        for index in range(len(fine_rows)):
            metrics = {
                "solar_illumination_fraction": float(visibility["solar_illumination_fraction"][index]),
                "longest_dark_days": float(visibility["longest_dark_days"][index]),
                "sunlight_continuity_fraction": float(visibility["sunlight_continuity_fraction"][index]),
                "earth_visibility_fraction": float(visibility["earth_visibility_fraction"][index]),
                "regional_slope_p90_deg": float(local_slope[index]),
                "pinpoint_slope_p90_deg": None,
                "psr_edge_km": float(psr_distance[index]),
                "science_proxy": float(science_value_proxy(local_slope[index])),
                "thermal_proxy": float(thermal_stability_proxy(latitude[index])),
                "data_coverage_fraction": 1.0,
            }
            scored = score_candidate(metrics, policy=policy)
            candidate = {
                "candidate_id": f"{region['region_id']}-fine-r{fine_rows[index]:04d}-c{fine_cols[index]:04d}",
                "region_id": region["region_id"],
                "fine_row": int(fine_rows[index]),
                "fine_col": int(fine_cols[index]),
                "lat_deg": float(latitude[index]),
                "lon_deg": float(longitude[index]),
                "elevation_m": float(elevation[fine_rows[index], fine_cols[index]]),
                "source_resolution_m": pixel_size_m,
                **metrics,
                **scored["indicators"],
                "weighted_sum": scored["weighted_sum"],
                "weighted_geometric_mean": scored["weighted_geometric_mean"],
                "hard_failures": ";".join(scored["hard_failures"]),
                "disqualified": scored["disqualified"],
                "dimensions": {
                    "solar_power": float(scored["indicators"]["solar_power"]),
                    "earth_visibility": float(scored["indicators"]["earth_visibility"]),
                    "terrain_safety": float(scored["indicators"]["terrain_safety"]),
                    "isru_access": float(scored["indicators"]["isru_access_proxy"]),
                    "science_value": float(scored["indicators"]["science_proxy"]),
                    "thermal_stability": float(scored["indicators"]["thermal_proxy"]),
                },
                "_horizon": horizons[index],
            }
            candidates.append(candidate)
        seed = select_provisional_seed(candidates)
        eligible = [candidate for candidate in candidates if not candidate["disqualified"]]
        dimensions = {
            key: statistics.median(candidate["dimensions"][key] for candidate in eligible)
            for key in SCORE_DIMENSIONS
        }
        combined = combine_scores(
            dimensions, policy.weights, geometric_floor=policy.geometric_floor
        )
        summary = {
            "region_id": region["region_id"],
            "stage1_rank": int(region["rank"]),
            "refined_cell_count": len(candidates),
            "eligible_refined_cell_count": len(eligible),
            "provisional_seed_id": seed["candidate_id"],
            "provisional_seed_lat_deg": seed["lat_deg"],
            "provisional_seed_lon_deg": seed["lon_deg"],
            "provisional_seed_elevation_m": seed["elevation_m"],
            "provisional_seed_source_resolution_m": pixel_size_m,
            "provisional_seed_score": seed["weighted_geometric_mean"],
            "weighted_sum": combined["weighted_sum"],
            "weighted_geometric_mean": combined["weighted_geometric_mean"],
            "data_maturity": 1.0,
            "dimensions": dimensions,
            "candidate_id": region["region_id"],
            "disqualified": False,
        }
        summary.update(dimensions)
        region_summaries.append(summary)
        seed_horizons[region["region_id"]] = (seed, seed["_horizon"])
        for candidate in candidates:
            candidate.pop("_horizon", None)
            candidate.pop("dimensions", None)
            refined_cells.append(candidate)

    region_summaries.sort(
        key=lambda row: (
            -row["weighted_geometric_mean"],
            -row["weighted_sum"],
            row["region_id"],
        )
    )
    for rank, summary in enumerate(region_summaries, start=1):
        summary["rank"] = rank
    sum_order = sorted(
        region_summaries, key=lambda row: (-row["weighted_sum"], row["region_id"])
    )
    agreement = rank_agreement(
        [row["region_id"] for row in sum_order],
        [row["region_id"] for row in region_summaries],
    )
    sensitivity = dirichlet_sensitivity(
        region_summaries,
        draws=1000,
        seed=42,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    refined_fields = [
        key for key in refined_cells[0] if key not in {"dimensions", "_horizon"}
    ]
    write_csv(output_dir / "polar_refined_cells.csv", refined_cells, refined_fields)
    ranking_fields = [
        "rank",
        "region_id",
        "stage1_rank",
        "refined_cell_count",
        "eligible_refined_cell_count",
        "provisional_seed_id",
        "provisional_seed_lat_deg",
        "provisional_seed_lon_deg",
        "provisional_seed_elevation_m",
        "provisional_seed_source_resolution_m",
        "provisional_seed_score",
        "weighted_sum",
        "weighted_geometric_mean",
        *SCORE_DIMENSIONS,
        "data_maturity",
    ]
    write_csv(
        output_dir / "polar_refined_region_ranking.csv",
        [{key: row.get(key) for key in ranking_fields} for row in region_summaries],
        ranking_fields,
    )
    write_csv(
        output_dir / "polar_sensitivity.csv",
        sensitivity,
        ["candidate_id", "top1_probability", "draws", "method", "seed"],
    )

    timeline_rows = []
    for summary in region_summaries:
        seed, horizon = seed_horizons[summary["region_id"]]
        timeline = evaluate_observers(
            np.asarray([seed["lat_deg"]]),
            np.asarray([seed["lon_deg"]]),
            horizon[None, :],
            ephemeris,
            observer_elevation_m=np.asarray([seed["elevation_m"]]),
            return_timeline=True,
        )["timeline"]
        for row in timeline:
            timeline_rows.append(
                {
                    "region_id": summary["region_id"],
                    "seed_id": seed["candidate_id"],
                    **row,
                }
            )
    timeline_fields = [
        "region_id",
        "seed_id",
        "utc",
        "sun_elevation_deg",
        "sun_horizon_deg",
        "sun_visible",
        "earth_elevation_deg",
        "earth_horizon_deg",
        "earth_visible",
    ]
    write_csv(
        output_dir / "polar_candidate_timeseries.csv",
        timeline_rows,
        timeline_fields,
    )

    winner = region_summaries[0]
    winner_seed, _ = seed_horizons[winner["region_id"]]
    recommendation = {
        "status": "ranked",
        "winner": winner["region_id"],
        "winner_score": winner["weighted_geometric_mean"],
        "region_count": len(region_summaries),
        "rank_agreement": agreement,
        "weights": policy.weights,
        "provisional_seed": {
            key: value
            for key, value in winner_seed.items()
            if key not in {"_horizon", "dimensions", "indicators"}
        },
        "refinement": {
            "stage1_cell_size_m": 1000,
            "stage2_source_resolution_m": pixel_size_m,
            "horizon_km": horizon_km,
            "azimuth_bins": bins,
            "pinpoint_status": "provisional_148m_seed_not_hazard_certified",
        },
        "barker_validation": {
            "pass": False,
            "status": "blocked",
            "reason": "FAIL/BLOCKED: exact Barker ROI LDEMs, error layers, and valid-pixel masks are absent.",
        },
        "caveats": [
            "Screening result, not a flight-certified landing site or hazard map.",
            "The provisional seed uses a server-resampled ~148 m LOLA product; 5 m Barker/LOLA or 1-2 m LROC NAC terrain is required.",
            "PSR edge distance uses an equivalent-circle approximation from catalogue centroid and area; it is not an ice detection.",
            "Science is a neutral placeholder and thermal is a visibly labelled proxy; neither is a measurement.",
            "Earth visibility is graded because relay availability is unknown; it is not a hard filter.",
        ],
    }
    write_json(output_dir / "polar_recommendation.json", recommendation)
    write_polar_data_gaps(output_dir / "polar_data_gaps.csv", winner_seed)
    return recommendation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--regions", type=Path, default=DEFAULT_REGIONS)
    parser.add_argument("--ephemeris", type=Path, default=DEFAULT_EPHEMERIS)
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--bins", type=int, default=96)
    parser.add_argument("--horizon-km", type=float, default=60.0)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                dem_path=args.dem,
                metrics_path=args.metrics,
                regions_path=args.regions,
                ephemeris_path=args.ephemeris,
                output_dir=args.output_dir,
                bins=args.bins,
                horizon_km=args.horizon_km,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
