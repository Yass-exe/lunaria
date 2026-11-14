#!/usr/bin/env python3
"""Derive measured south-polar illumination, Earth visibility and dark periods.

Method
------
1. Block-aggregate the ~148 m LOLA south-polar DEM to the 1 km study grid,
   keeping a maximum-elevation grid so shadow-casting ridge crests survive.
2. Cast horizon rays on that grid for every cell and azimuth bin.
3. Convert JPL Horizons sub-solar and sub-Earth selenographic lon/lat to unit
   vectors, then compute elevation/azimuth at every cell and sample time and
   compare against the terrain horizon.

Outputs per 1 km cell: solar illumination fraction, longest dark period,
6.5-day sunlight continuity, Earth visibility fraction, data coverage. These are
screening values from a 1 km DEM, not landing-pad certification.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

try:
    from .common import CONFIG_DIR, INTERIM_DIR, PROCESSED_DIR, read_json, write_json
except ImportError:
    from common import CONFIG_DIR, INTERIM_DIR, PROCESSED_DIR, read_json, write_json

LUNAR_RADIUS_M = 1_737_400.0
LUNAR_RADIUS_KM = LUNAR_RADIUS_M / 1000.0
NODATA = -9999.0
FILL = -1.0e9

DEFAULT_DEM = Path("data/raw/rasters/south_pole_lola_dem_4096.tif")
DEFAULT_TERRAIN = Path("data/processed/polar_terrain_1km.tif")
DEFAULT_EPHEMERIS = INTERIM_DIR / "polar_ephemeris.csv"
DEFAULT_OUTPUT = PROCESSED_DIR / "polar_cell_metrics.csv"
DEFAULT_RASTER = PROCESSED_DIR / "polar_illumination_1km.tif"


def lat_lon_from_xy(x_m: np.ndarray, y_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    radius = np.hypot(x_m, y_m)
    latitude = -(90.0 - np.degrees(2.0 * np.arctan(radius / (2.0 * LUNAR_RADIUS_M))))
    longitude = np.degrees(np.arctan2(x_m, y_m))
    return latitude, longitude


def xy_from_lat_lon(latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
    radius = 2.0 * LUNAR_RADIUS_KM * math.tan(
        math.radians(90.0 + latitude_deg) / 2.0
    )
    return (
        radius * math.sin(math.radians(longitude_deg)),
        radius * math.cos(math.radians(longitude_deg)),
    )


def shifted_into(dst: np.ndarray, src: np.ndarray, dr: int, dc: int, fill: float) -> None:
    """dst[r, c] = src[r + dr, c + dc], out-of-range filled with ``fill``."""
    dst.fill(fill)
    rows, cols = src.shape
    src_r0 = max(0, dr)
    src_r1 = min(rows, rows + dr)
    dst_r0 = max(0, -dr)
    dst_r1 = dst_r0 + (src_r1 - src_r0)
    src_c0 = max(0, dc)
    src_c1 = min(cols, cols + dc)
    dst_c0 = max(0, -dc)
    dst_c1 = dst_c0 + (src_c1 - src_c0)
    if src_r1 > src_r0 and src_c1 > src_c0:
        dst[dst_r0:dst_r1, dst_c0:dst_c1] = src[src_r0:src_r1, src_c0:src_c1]


def horizon_angle_grid(
    z0: np.ndarray,
    z_max: np.ndarray,
    cell_size_m: float,
    *,
    bins: int,
    max_km: float,
) -> np.ndarray:
    """Return (rows, cols, bins) terrain-horizon elevation angle in radians.

    Includes lunar curvature. A point at height h above the reference sphere
    has a geometric horizon depressed by arccos(R/(R+h)); without this term a
    high polar ridge is wrongly treated as losing the Sun whenever the Sun is
    below the local horizontal plane, which matters where the Sun stays within
    about 1.6 deg of the horizon.
    """
    rows, cols = z0.shape
    horizon = np.full((rows, cols, bins), FILL, dtype=np.float32)
    rings = list(range(1, 31)) + list(range(35, int(max_km) + 1, 5))
    valid = z0 != NODATA
    z0f = np.where(valid, z0, 0.0).astype(np.float32)
    height = np.maximum(z0f, 0.0)
    dip = -np.arccos(
        LUNAR_RADIUS_M / (LUNAR_RADIUS_M + height.astype(np.float64))
    ).astype(np.float32)
    shifted = np.empty_like(z_max)
    for bi in range(bins):
        azimuth = math.radians(bi * 360.0 / bins)
        h = dip.copy()
        for distance_km in rings:
            distance_m = distance_km * 1000.0
            dr = int(round(-distance_km * math.cos(azimuth) * 1000.0 / cell_size_m))
            dc = int(round(distance_km * math.sin(azimuth) * 1000.0 / cell_size_m))
            shifted_into(shifted, z_max, dr, dc, FILL)
            angle = np.arctan2(shifted - z0f, distance_m) - distance_m / (2.0 * LUNAR_RADIUS_M)
            np.maximum(h, angle, out=h)
        h[~valid] = FILL
        horizon[:, :, bi] = h
    return horizon


def aggregate_dem(
    dem_path: Path,
    *,
    cell_size_m: float = 1000.0,
    latitude_min_deg: float = -90.0,
    latitude_max_deg: float = -80.0,
) -> dict:
    """Block-aggregate the fine DEM into centre elevation, max elevation and coverage."""
    with rasterio.open(dem_path) as src:
        elevation = src.read(1, masked=False).astype(np.float32)
        transform = src.transform
        crs = src.crs
        res_x = abs(transform.a)
        res_y = abs(transform.e)
        xmin, ymax = transform.c, transform.f
        height, width = elevation.shape
        nodata = src.nodata

    valid = np.isfinite(elevation) & (elevation != NODATA)
    if nodata is not None:
        valid &= elevation != nodata

    cols = int(round(width * res_x / cell_size_m))
    rows = int(round(height * res_y / cell_size_m))
    x_centers = xmin + (np.arange(cols) + 0.5) * cell_size_m
    y_centers = ymax - (np.arange(rows) + 0.5) * cell_size_m
    x_grid, y_grid = np.meshgrid(x_centers, y_centers)
    latitude = lat_lon_from_xy(x_grid, y_grid)[0]
    polar = (latitude >= latitude_min_deg) & (latitude <= latitude_max_deg)

    fine_x = xmin + (np.arange(width) + 0.5) * res_x
    fine_y = ymax - (np.arange(height) + 0.5) * res_y
    cell_col = np.clip(np.floor((fine_x - xmin) / cell_size_m).astype(int), 0, cols - 1)
    cell_row = np.clip(np.floor((ymax - fine_y) / cell_size_m).astype(int), 0, rows - 1)
    labels = (cell_row[:, None] * cols + cell_col[None, :]).astype(np.int32)
    counts = np.bincount(labels.ravel(), minlength=rows * cols).astype(np.float64)

    filled = np.where(valid, elevation, np.float32(FILL))
    z_max_flat = np.full(rows * cols, np.float32(FILL), dtype=np.float32)
    np.maximum.at(z_max_flat, labels.ravel(), filled.ravel())
    z_max = z_max_flat.reshape(rows, cols)
    z_max = np.where(counts.reshape(rows, cols) > 0, z_max, FILL).astype(np.float32)

    valid_sum = np.bincount(
        labels.ravel(), weights=valid.astype(np.float64).ravel(), minlength=rows * cols
    )
    coverage = np.where(counts > 0, valid_sum / np.maximum(counts, 1.0), 0.0).reshape(
        rows, cols
    )
    elevation_sum = np.bincount(
        labels.ravel(),
        weights=np.where(valid, elevation, 0.0).astype(np.float64).ravel(),
        minlength=rows * cols,
    )
    center = np.full((rows, cols), NODATA, dtype=np.float32)
    z_center = (
        np.where(valid_sum > 0, elevation_sum / np.maximum(valid_sum, 1.0), NODATA)
        .reshape(rows, cols)
        .astype(np.float32)
    )
    has = valid_sum.reshape(rows, cols) > 0
    center[has] = z_center[has]
    return {
        "rows": rows,
        "cols": cols,
        "cell_size_m": cell_size_m,
        "xmin": xmin,
        "ymax": ymax,
        "crs": crs,
        "center": center,
        "z_max": z_max,
        "coverage": coverage.astype(np.float32),
        "polar": polar,
        "source_resolution_m": res_x,
    }


def load_ephemeris(path: Path) -> dict[str, np.ndarray]:
    """Return unit vectors from selenographic sub-point lon/lat.

    ``lon_deg``/``lat_deg`` are the Moon body-fixed sub-solar and sub-Earth
    points (Horizons QUANTITIES 15 and 14). Converting them to unit vectors
    keeps the per-cell elevation/azimuth math identical for both bodies.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} is empty; run fetch_polar_ephemeris.py first")
    if any(key not in rows[0] for key in ("lon_deg", "lat_deg", "range_km")):
        raise ValueError(
            "ephemeris lacks body-fixed sub-points or center range; re-run "
            "fetch_polar_ephemeris.py --force"
        )
    bodies: dict[str, list[tuple[str, list[float], float]]] = {}
    for row in rows:
        lon = math.radians(float(row["lon_deg"]))
        lat = math.radians(float(row["lat_deg"]))
        bodies.setdefault(row["body"], []).append(
            (
                row["utc"],
                [
                    math.cos(lat) * math.cos(lon),
                    math.cos(lat) * math.sin(lon),
                    math.sin(lat),
                ],
                float(row["range_km"]),
            )
        )
    if "sun" not in bodies or "earth" not in bodies:
        raise ValueError("ephemeris must contain both sun and earth rows")
    ordered = {body: sorted(values, key=lambda item: item[0]) for body, values in bodies.items()}
    sun_times = [item[0] for item in ordered["sun"]]
    earth_times = [item[0] for item in ordered["earth"]]
    if len(set(sun_times)) != len(sun_times) or len(set(earth_times)) != len(earth_times):
        raise ValueError("ephemeris timestamps must be unique for each body")
    if sun_times != earth_times:
        raise ValueError("sun and earth ephemeris timestamps must match exactly")
    result = {
        "utc": np.asarray(sun_times),
        "sun": np.asarray([item[1] for item in ordered["sun"]], dtype=np.float64),
        "earth": np.asarray([item[1] for item in ordered["earth"]], dtype=np.float64),
        "sun_range_km": np.asarray(
            [item[2] for item in ordered["sun"]], dtype=np.float64
        ),
        "earth_range_km": np.asarray(
            [item[2] for item in ordered["earth"]], dtype=np.float64
        ),
    }
    return result


def compute_cell_metrics(
    aggregate: dict,
    ephemeris: dict[str, np.ndarray],
    *,
    bins: int,
    horizon_km: float,
    terrain_path: Path = DEFAULT_TERRAIN,
    observer: str = "max",
    continuity_days: float = 6.5,
) -> dict:
    rows, cols = aggregate["rows"], aggregate["cols"]
    center = aggregate["center"]
    if observer == "max":
        center = np.where(aggregate["z_max"] > FILL / 2, aggregate["z_max"], center)
    elif observer != "center":
        raise ValueError("observer must be 'center' or 'max'")
    valid_cells = aggregate["polar"] & (center != NODATA)
    flat_idx = np.flatnonzero(valid_cells)
    n_cells = len(flat_idx)
    if n_cells == 0:
        raise ValueError("no valid polar cells in aggregated DEM")
    observer_radius_km = (
        LUNAR_RADIUS_M + center.ravel()[flat_idx].astype(np.float64)
    ) / 1000.0

    x = aggregate["xmin"] + (np.arange(cols) + 0.5) * aggregate["cell_size_m"]
    y = aggregate["ymax"] - (np.arange(rows) + 0.5) * aggregate["cell_size_m"]
    x_grid, y_grid = np.meshgrid(x, y)
    lat_all, lon_all = lat_lon_from_xy(x_grid, y_grid)
    lat = lat_all.ravel()[flat_idx].astype(np.float64)
    lon = lon_all.ravel()[flat_idx].astype(np.float64)

    horizon = horizon_angle_grid(
        center,
        aggregate["z_max"],
        aggregate["cell_size_m"],
        bins=bins,
        max_km=horizon_km,
    )
    horizon_flat = horizon.reshape(-1, bins)[flat_idx].astype(np.float32)
    del horizon
    sin_horizon = np.sin(horizon_flat).astype(np.float32).ravel()

    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    cos_lat, sin_lat = np.cos(lat_rad), np.sin(lat_rad)
    cos_lon, sin_lon = np.cos(lon_rad), np.sin(lon_rad)
    ax = (cos_lat * cos_lon).astype(np.float32)
    ay = (cos_lat * sin_lon).astype(np.float32)
    az_up = sin_lat.astype(np.float32)
    e_dot = (-sin_lon).astype(np.float32)  # east unit-vector components
    e_dot2 = cos_lon.astype(np.float32)
    n_sin_lat = (-sin_lat).astype(np.float32)
    n_cos_lat = cos_lat.astype(np.float32)
    cell_index = np.arange(n_cells, dtype=np.int64) * bins

    times = len(ephemeris["sun"])
    sun_lit = 0
    earth_lit = 0
    max_dark = np.zeros(n_cells, dtype=np.int32)
    dark_run = np.zeros(n_cells, dtype=np.int32)
    window_len = continuity_window_samples(continuity_days, step_hours=6.0)
    history = np.zeros((window_len, n_cells), dtype=bool)
    window_count = np.zeros(n_cells, dtype=np.int16)
    lit_windows = np.zeros(n_cells, dtype=np.int32)
    pos = 0

    sun_vecs = ephemeris["sun"].astype(np.float32)
    earth_vecs = ephemeris["earth"].astype(np.float32)
    for t in range(times):
        sx, sy, sz = sun_vecs[t]
        su_center = sx * ax + sy * ay + sz * az_up
        se_center = sx * e_dot + sy * e_dot2
        sn_center = n_sin_lat * (sx * cos_lon + sy * sin_lon) + sz * n_cos_lat
        su, se, sn = topocentric_direction_components(
            su_center,
            se_center,
            sn_center,
            range_km=float(ephemeris["sun_range_km"][t]),
            observer_radius_km=observer_radius_km,
        )
        sun_bin = (
            (np.degrees(np.arctan2(se, sn)) + 360.0) % 360.0 * (bins / 360.0)
        ).astype(np.int64) % bins
        lit = su > sin_horizon[cell_index + sun_bin]
        sun_lit += lit

        ex, ey, ez = earth_vecs[t]
        eu_center = ex * ax + ey * ay + ez * az_up
        ee_center = ex * e_dot + ey * e_dot2
        en_center = n_sin_lat * (ex * cos_lon + ey * sin_lon) + ez * n_cos_lat
        eu, ee, en = topocentric_direction_components(
            eu_center,
            ee_center,
            en_center,
            range_km=float(ephemeris["earth_range_km"][t]),
            observer_radius_km=observer_radius_km,
        )
        earth_bin = (
            (np.degrees(np.arctan2(ee, en)) + 360.0) % 360.0 * (bins / 360.0)
        ).astype(np.int64) % bins
        earth_lit += eu > sin_horizon[cell_index + earth_bin]

        dark_run = np.where(lit, 0, dark_run + 1)
        np.maximum(max_dark, dark_run, out=max_dark)

        old = history[pos]
        window_count += lit.astype(np.int16) - old.astype(np.int16)
        history[pos] = lit
        if t >= window_len - 1:
            lit_windows += window_count == window_len
        pos = (pos + 1) % window_len
        if t % 500 == 0:
            print(f"  ephemeris sample {t:,}/{times:,}", file=sys.stderr, flush=True)

    windows_total = max(1, times - window_len + 1)
    illum = sun_lit.astype(np.float64) / times
    earth = earth_lit.astype(np.float64) / times
    dark_days = sampled_run_duration_days(max_dark, sample_count=times, step_hours=6.0)
    continuity = lit_windows.astype(np.float64) / windows_total

    with rasterio.open(terrain_path) as terrain_src:
        slope_band = terrain_src.read(2, masked=False)
    slope = slope_band.ravel()[flat_idx].astype(np.float64)
    slope = np.where(slope == NODATA, np.nan, slope)

    psr_distance = psr_edge_distance(x_grid, y_grid, flat_idx)
    science = science_value_proxy(slope)
    thermal = thermal_stability_proxy(lat)
    coverage = aggregate["coverage"].ravel()[flat_idx].astype(np.float64)

    return {
        "row": (flat_idx // cols).astype(int),
        "col": (flat_idx % cols).astype(int),
        "lat_deg": lat,
        "lon_deg": lon,
        "solar_illumination_fraction": illum,
        "longest_dark_days": dark_days,
        "sunlight_continuity_fraction": continuity,
        "earth_visibility_fraction": earth,
        "regional_slope_p90_deg": slope,
        "psr_edge_km": psr_distance,
        "science_proxy": science,
        "thermal_proxy": thermal,
        "data_coverage_fraction": coverage,
        "bins": bins,
        "times": times,
        "window_len": window_len,
    }


def psr_edge_distance(
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    flat_idx: np.ndarray,
) -> np.ndarray:
    psr_path = Path("data/raw/trek/psr_sp.geojson")
    fallback = np.full(len(flat_idx), 100.0)
    if not psr_path.exists():
        return fallback
    payload = json.loads(psr_path.read_text(encoding="utf-8"))
    points = []
    areas = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        lat = props.get("Cent__Lat_")
        lon = props.get("Cent__Long")
        area = props.get("Area__km2_")
        if lat is None or lon is None or area is None:
            continue
        points.append(xy_from_lat_lon(float(lat), float(lon)))
        areas.append(float(area))
    if not points:
        return fallback
    cells_xy = np.column_stack(
        [x_grid.ravel()[flat_idx] / 1000.0, y_grid.ravel()[flat_idx] / 1000.0]
    )
    return equivalent_circle_edge_distance(
        cells_xy, np.asarray(points, dtype=float), np.asarray(areas, dtype=float)
    )


def equivalent_circle_edge_distance(
    cells_xy_km: np.ndarray,
    psr_centers_xy_km: np.ndarray,
    psr_areas_km2: np.ndarray,
    *,
    chunk_size: int = 8192,
) -> np.ndarray:
    """Return exact nearest equivalent-circle PSR edge distance in kilometres.

    The source catalogue supplies centroids and areas, not polygons. Treating
    each area as a circle is an explicit approximation, but unlike centroid
    distance it uses all of the information actually present in the source.
    """
    cells = np.asarray(cells_xy_km, dtype=float)
    centers = np.asarray(psr_centers_xy_km, dtype=float)
    areas = np.asarray(psr_areas_km2, dtype=float)
    if cells.ndim != 2 or cells.shape[1] != 2:
        raise ValueError("cells_xy_km must have shape (n, 2)")
    if centers.ndim != 2 or centers.shape[1] != 2 or len(centers) != len(areas):
        raise ValueError("PSR centers and areas must have matching rows")
    if not len(centers) or np.any(~np.isfinite(areas)) or np.any(areas < 0):
        raise ValueError("PSR areas must be finite, non-negative, and non-empty")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    radii = np.sqrt(areas / math.pi)
    result = np.empty(len(cells), dtype=float)
    for start in range(0, len(cells), chunk_size):
        block = cells[start : start + chunk_size]
        center_distance = np.sqrt(
            np.sum((block[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        )
        result[start : start + len(block)] = np.maximum(
            0.0, np.min(center_distance - radii[None, :], axis=1)
        )
    return result


def thermal_stability_proxy(latitude_deg: np.ndarray | float) -> np.ndarray:
    """Tier-C latitude proxy: 0 at 80 S, increasing linearly to 1 at 90 S."""
    latitude = np.asarray(latitude_deg, dtype=float)
    return np.clip(-(latitude + 80.0) / 10.0, 0.0, 1.0)


def science_value_proxy(reference_values: np.ndarray | float) -> np.ndarray:
    """Neutral placeholder until independent geology/spectral data is ingested."""
    values = np.asarray(reference_values, dtype=float)
    return np.full(values.shape, 0.5, dtype=float)


def sampled_run_duration_days(
    run_samples: np.ndarray | int,
    *,
    sample_count: int,
    step_hours: float,
) -> np.ndarray:
    """Convert sampled run lengths to duration without exceeding the window."""
    if sample_count <= 0 or not math.isfinite(step_hours) or step_hours <= 0:
        raise ValueError("sample_count and step_hours must be positive")
    runs = np.asarray(run_samples, dtype=float)
    if np.any(~np.isfinite(runs)) or np.any(runs < 0):
        raise ValueError("run lengths must be finite and non-negative")
    capped = np.minimum(runs, max(0, sample_count - 1))
    return capped * step_hours / 24.0


def continuity_window_samples(days: float, *, step_hours: float) -> int:
    """Number of point samples spanning a duration, including both endpoints."""
    if not math.isfinite(days) or days <= 0:
        raise ValueError("continuity duration must be finite and positive")
    if not math.isfinite(step_hours) or step_hours <= 0:
        raise ValueError("step_hours must be finite and positive")
    intervals = int(round(days * 24.0 / step_hours))
    return max(2, intervals + 1)


def topocentric_direction_components(
    center_up: np.ndarray | float,
    center_east: np.ndarray | float,
    center_north: np.ndarray | float,
    *,
    range_km: float,
    observer_radius_km: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Translate a Moon-centred body direction to a lunar-surface observer."""
    if not math.isfinite(range_km) or range_km <= 0:
        raise ValueError("body range must be finite and positive")
    up = np.asarray(center_up, dtype=float)
    east = np.asarray(center_east, dtype=float)
    north = np.asarray(center_north, dtype=float)
    radius = np.asarray(observer_radius_km, dtype=float)
    topocentric_up = range_km * up - radius
    topocentric_east = range_km * east
    topocentric_north = range_km * north
    norm = np.sqrt(
        topocentric_up**2 + topocentric_east**2 + topocentric_north**2
    )
    if np.any(~np.isfinite(norm)) or np.any(norm <= 0):
        raise ValueError("topocentric direction has invalid norm")
    return (
        topocentric_up / norm,
        topocentric_east / norm,
        topocentric_north / norm,
    )


def write_metrics(path: Path, metrics: dict) -> int:
    fields = [
        "candidate_id",
        "row",
        "col",
        "lat_deg",
        "lon_deg",
        "solar_illumination_fraction",
        "longest_dark_days",
        "sunlight_continuity_fraction",
        "earth_visibility_fraction",
        "regional_slope_p90_deg",
        "pinpoint_slope_p90_deg",
        "psr_edge_km",
        "science_proxy",
        "thermal_proxy",
        "data_coverage_fraction",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    count = len(metrics["row"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for i in range(count):
            writer.writerow(
                {
                    "candidate_id": f"polar-{metrics['row'][i]:03d}-{metrics['col'][i]:03d}",
                    "row": int(metrics["row"][i]),
                    "col": int(metrics["col"][i]),
                    "lat_deg": f"{metrics['lat_deg'][i]:.6f}",
                    "lon_deg": f"{metrics['lon_deg'][i]:.6f}",
                    "solar_illumination_fraction": f"{metrics['solar_illumination_fraction'][i]:.6f}",
                    "longest_dark_days": f"{metrics['longest_dark_days'][i]:.4f}",
                    "sunlight_continuity_fraction": f"{metrics['sunlight_continuity_fraction'][i]:.6f}",
                    "earth_visibility_fraction": f"{metrics['earth_visibility_fraction'][i]:.6f}",
                    "regional_slope_p90_deg": (
                        "" if math.isnan(metrics["regional_slope_p90_deg"][i]) else f"{metrics['regional_slope_p90_deg'][i]:.4f}"
                    ),
                    "pinpoint_slope_p90_deg": "",
                    "psr_edge_km": f"{metrics['psr_edge_km'][i]:.4f}",
                    "science_proxy": f"{metrics['science_proxy'][i]:.6f}",
                    "thermal_proxy": f"{metrics['thermal_proxy'][i]:.6f}",
                    "data_coverage_fraction": f"{metrics['data_coverage_fraction'][i]:.6f}",
                }
            )
    return count


def write_rasters(path: Path, aggregate: dict, metrics: dict) -> None:
    rows, cols = aggregate["rows"], aggregate["cols"]
    bands = np.full((4, rows, cols), NODATA, dtype=np.float32)
    flat = metrics["row"] * cols + metrics["col"]
    bands[0].ravel()[flat] = metrics["solar_illumination_fraction"].astype(np.float32)
    bands[1].ravel()[flat] = metrics["earth_visibility_fraction"].astype(np.float32)
    bands[2].ravel()[flat] = metrics["longest_dark_days"].astype(np.float32)
    bands[3].ravel()[flat] = metrics["sunlight_continuity_fraction"].astype(np.float32)
    transform = from_origin(
        aggregate["xmin"], aggregate["ymax"], aggregate["cell_size_m"], aggregate["cell_size_m"]
    )
    profile = {
        "driver": "GTiff",
        "width": cols,
        "height": rows,
        "count": 4,
        "dtype": "float32",
        "crs": aggregate["crs"],
        "transform": transform,
        "nodata": NODATA,
        "compress": "deflate",
        "predictor": 3,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(bands)
        dst.set_band_description(1, "Solar illumination fraction")
        dst.set_band_description(2, "Earth visibility fraction (>0 deg)")
        dst.set_band_description(3, "Longest dark period (days, 6 h sampling)")
        dst.set_band_description(4, "6.5-day sunlight continuity fraction")


def validate_benchmarks(metrics: dict) -> dict:
    sites = read_json(CONFIG_DIR / "sites.json")
    lookup = {site["site_id"]: site for site in sites}
    results = []
    for site_id in ("nobile_connecting_ridge", "shackleton_rim"):
        site = lookup.get(site_id)
        if not site:
            continue
        lat, lon = float(site["lat_deg"]), float(site["lon_deg"])
        distance = np.hypot(
            (metrics["lat_deg"] - lat) * 111.0,
            (metrics["lon_deg"] - lon) * 111.0 * np.cos(np.radians(lat)),
        )
        nearest = int(np.argmin(distance))
        results.append(
            {
                "site_id": site_id,
                "lat_deg": lat,
                "lon_deg": lon,
                "nearest_cell_offset_km": float(distance[nearest]),
                "solar_illumination_fraction": float(
                    metrics["solar_illumination_fraction"][nearest]
                ),
            }
        )
    by_id = {row["site_id"]: row for row in results}
    check = {
        "reference": "Barker et al. 2021, DOI 10.1016/j.pss.2020.105119",
        "expected_ranking": "Site01 highest average illumination among Sites 01, 04, 07, 11",
        "pass": False,
        "status": "blocked",
        "reason": (
            "FAIL/BLOCKED: Barker Site 01/04/07/11 ROI coordinates, 5 m LDEMs and solar-disk "
            "method are not in the repository. The legacy Nobile (-84.2 S) point is "
            "not Barker Site 01 (Connecting Ridge, near the pole), so it cannot be "
            "used as a substitute."
        ),
        "legacy_points": by_id,
    }
    return {"benchmarks": results, "validation": check}


def run(
    *,
    dem_path: Path = DEFAULT_DEM,
    ephemeris_path: Path = DEFAULT_EPHEMERIS,
    output_path: Path = DEFAULT_OUTPUT,
    raster_path: Path = DEFAULT_RASTER,
    terrain_path: Path = DEFAULT_TERRAIN,
    bins: int = 96,
    horizon_km: float = 60.0,
    observer: str = "center",
    max_times: int | None = None,
    force: bool = False,
) -> dict:
    if output_path.exists() and not force:
        raise FileExistsError(f"{output_path} exists; pass --force to replace")
    aggregate = aggregate_dem(dem_path)
    print(
        f"aggregated DEM: {aggregate['rows']}x{aggregate['cols']} cells, "
        f"source {aggregate['source_resolution_m']:.2f} m",
        file=sys.stderr,
    )
    ephemeris = load_ephemeris(ephemeris_path)
    if max_times is not None:
        ephemeris = {key: value[:max_times] for key, value in ephemeris.items()}
    metrics = compute_cell_metrics(
        aggregate,
        ephemeris,
        bins=bins,
        horizon_km=horizon_km,
        terrain_path=terrain_path,
        observer=observer,
    )
    count = write_metrics(output_path, metrics)
    write_rasters(raster_path, aggregate, metrics)
    validation = validate_benchmarks(metrics)
    finite = np.isfinite(metrics["solar_illumination_fraction"])
    summary = {
        "cells": count,
        "azimuth_bins": bins,
        "horizon_km": horizon_km,
        "observer_elevation": observer,
        "ephemeris_samples": metrics["times"],
        "ephemeris_step_hours": 6,
        "continuity_window_samples": metrics["window_len"],
        "illumination_median": float(np.median(metrics["solar_illumination_fraction"][finite])),
        "illumination_p90": float(np.percentile(metrics["solar_illumination_fraction"][finite], 90)),
        "earth_visibility_median": float(np.median(metrics["earth_visibility_fraction"][finite])),
        "data_coverage_median": float(np.median(metrics["data_coverage_fraction"][finite])),
        "caveats": [
            "1 km screening values; not landing-pad slope or hazard certification.",
            "Horizon rays use the highest ~148 m source pixel in each 1 km cell as an optimistic screening observer and maximum-elevation obstacles out to 60 km.",
            "Solar/Earth geometry uses Horizons sub-solar/sub-Earth selenographic points at 6 h sampling, 2024-01-01..2026-01-01.",
            "Earth visibility assumes no relay; it is graded, never a hard failure.",
        ],
        **validation,
    }
    write_json(PROCESSED_DIR / "polar_illumination_manifest.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--ephemeris", type=Path, default=DEFAULT_EPHEMERIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--terrain", type=Path, default=DEFAULT_TERRAIN)
    parser.add_argument("--bins", type=int, default=96)
    parser.add_argument("--horizon-km", type=float, default=60.0)
    parser.add_argument("--observer", choices=("center", "max"), default="max")
    parser.add_argument("--max-times", type=int, help="debug: truncate ephemeris samples")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run(
        dem_path=args.dem,
        ephemeris_path=args.ephemeris,
        output_path=args.output,
        raster_path=args.raster,
        terrain_path=args.terrain,
        bins=args.bins,
        horizon_km=args.horizon_km,
        observer=args.observer,
        max_times=args.max_times,
        force=args.force,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
