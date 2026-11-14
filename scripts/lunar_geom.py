"""Lunar geometry, DEM sampling, slope and horizon helpers.

All coordinates are planetocentric, east-longitude positive. Moon radius is
the IAU mean radius used by the NASA Moon Trek services (1,737.4 km).
"""

from __future__ import annotations

import math
from statistics import median

R_MOON_M = 1_737_400.0
DEG = math.pi / 180.0


# ---------------------------------------------------------------------------
# Projections used by the Moon Trek ImageServer layers
# ---------------------------------------------------------------------------

def project_point(projection: str, lat_deg: float, lon_deg: float) -> tuple[float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    if projection == "polar_stereographic":
        rho = 2.0 * R_MOON_M * math.tan(math.pi / 4.0 + lat / 2.0)
        return rho * math.sin(lon), rho * math.cos(lon)
    if projection == "geographic":
        return lon_deg, lat_deg
    if projection == "equirect_cm180_sp20":
        x = math.radians(lon_deg - 180.0) * R_MOON_M * math.cos(20.0 * DEG)
        y = lat * R_MOON_M
        return x, y
    raise ValueError(f"unknown projection: {projection}")


def unproject_point(projection: str, x: float, y: float) -> tuple[float, float]:
    if projection == "polar_stereographic":
        rho = math.hypot(x, y)
        lat = 2.0 * math.atan(rho / (2.0 * R_MOON_M)) - math.pi / 2.0
        lon = math.atan2(x, y)
        return math.degrees(lat), math.degrees(lon)
    if projection == "geographic":
        return y, x
    if projection == "equirect_cm180_sp20":
        lon = 180.0 + math.degrees(x / (R_MOON_M * math.cos(20.0 * DEG)))
        lat = math.degrees(y / R_MOON_M)
        return lat, lon
    raise ValueError(f"unknown projection: {projection}")


def bbox_native(
    projection: str, lat_deg: float, lon_deg: float, half_m: float
) -> tuple[float, float, float, float, str]:
    """Return a square-on-the-ground bbox in the layer's native units."""
    x0, y0 = project_point(projection, lat_deg, lon_deg)
    if projection == "polar_stereographic":
        return x0 - half_m, y0 - half_m, x0 + half_m, y0 + half_m, "m"
    if projection == "geographic":
        dlat = half_m / (R_MOON_M * DEG)
        dlon = half_m / (R_MOON_M * math.cos(math.radians(lat_deg)) * DEG)
        return lon_deg - dlon, lat_deg - dlat, lon_deg + dlon, lat_deg + dlat, "deg"
    if projection == "equirect_cm180_sp20":
        dx = half_m / math.cos(20.0 * DEG)
        return x0 - dx, y0 - half_m, x0 + dx, y0 + half_m, "m"
    raise ValueError(f"unknown projection: {projection}")


def sample_distance_native(projection: str, half_m: float) -> float:
    """Ask for roughly a 32x32 grid; the server caps at 1024 samples anyway."""
    spacing = 2.0 * half_m / 32.0
    if projection == "geographic":
        return spacing / (R_MOON_M * DEG)
    return spacing


def ground_offsets(
    projection: str,
    lat0_deg: float,
    x0: float,
    y0: float,
    x: float,
    y: float,
) -> tuple[float, float]:
    if projection == "polar_stereographic":
        return x - x0, y - y0
    if projection == "geographic":
        dx = (x - x0) * R_MOON_M * math.cos(math.radians(lat0_deg)) * DEG
        dy = (y - y0) * R_MOON_M * DEG
        return dx, dy
    if projection == "equirect_cm180_sp20":
        return (x - x0) * math.cos(20.0 * DEG), y - y0
    raise ValueError(f"unknown projection: {projection}")


def pixel_size_ground_m(
    projection: str, lat0_deg: float, x0: float, x1: float, y0: float, y1: float
) -> tuple[float, float]:
    dx, _ = ground_offsets(projection, lat0_deg, x0, y0, x1, y0)
    _, dy = ground_offsets(projection, lat0_deg, x0, y0, x0, y1)
    return abs(dx), abs(dy)


# ---------------------------------------------------------------------------
# DEM sample parsing and terrain statistics
# ---------------------------------------------------------------------------

def parse_dem_samples(payload: dict) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for sample in payload.get("samples") or []:
        value = sample.get("value")
        if value is None:
            continue
        try:
            z = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(z) or z < -1.0e30:
            continue
        location = sample.get("location") or {}
        x = location.get("x")
        y = location.get("y")
        if x is None or y is None:
            continue
        points.append((float(x), float(y), z))
    return points


def grid_from_samples(
    points: list[tuple[float, float, float]]
) -> tuple[list[float], list[float], dict[tuple[int, int], float]]:
    xs = sorted({round(x, 6) for x, _, _ in points})
    ys = sorted({round(y, 6) for _, y, _ in points})
    x_index = {x: i for i, x in enumerate(xs)}
    y_index = {y: i for i, y in enumerate(ys)}
    grid: dict[tuple[int, int], float] = {}
    for x, y, z in points:
        grid[(x_index[round(x, 6)], y_index[round(y, 6)])] = z
    return xs, ys, grid


def fit_plane_residual_std(points: list[tuple[float, float, float]]) -> float:
    """Least-squares plane fit z = ax + by + c; return residual std (m)."""
    if len(points) < 3:
        return 0.0
    n = float(len(points))
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sz = sum(p[2] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    syy = sum(p[1] * p[1] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    sxz = sum(p[0] * p[2] for p in points)
    syz = sum(p[1] * p[2] for p in points)

    # Normal equations for [a, b, c].
    matrix = [
        [sxx, sxy, sx],
        [sxy, syy, sy],
        [sx, sy, n],
    ]
    rhs = [sxz, syz, sz]
    det = _det3(matrix)
    if abs(det) < 1.0e-12:
        return 0.0
    a = _det3(_replace_col(matrix, 0, rhs)) / det
    b = _det3(_replace_col(matrix, 1, rhs)) / det
    c = _det3(_replace_col(matrix, 2, rhs)) / det
    residuals = [p[2] - (a * p[0] + b * p[1] + c) for p in points]
    if len(residuals) < 2:
        return 0.0
    avg = sum(residuals) / len(residuals)
    return (sum((r - avg) ** 2 for r in residuals) / (len(residuals) - 1)) ** 0.5


def _det3(m: list[list[float]]) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _replace_col(m: list[list[float]], col: int, rhs: list[float]) -> list[list[float]]:
    out = [row[:] for row in m]
    for i in range(3):
        out[i][col] = rhs[i]
    return out


def slope_grid(
    projection: str,
    lat0_deg: float,
    xs: list[float],
    ys: list[float],
    grid: dict[tuple[int, int], float],
) -> dict[tuple[int, int], float]:
    if len(xs) < 2 or len(ys) < 2:
        return {}
    dx, dy = pixel_size_ground_m(projection, lat0_deg, xs[0], xs[1], ys[0], ys[1])
    if dx <= 0 or dy <= 0:
        return {}
    slopes: dict[tuple[int, int], float] = {}
    for xi in range(len(xs)):
        for yi in range(len(ys)):
            z = grid.get((xi, yi))
            if z is None:
                continue
            if xi > 0:
                x_lo = grid.get((xi - 1, yi), z)
            else:
                x_lo = None
            if xi < len(xs) - 1:
                x_hi = grid.get((xi + 1, yi), z)
            else:
                x_hi = None
            if yi > 0:
                y_lo = grid.get((xi, yi - 1), z)
            else:
                y_lo = None
            if yi < len(ys) - 1:
                y_hi = grid.get((xi, yi + 1), z)
            else:
                y_hi = None
            if x_lo is not None and x_hi is not None:
                dzdx = (x_hi - x_lo) / (2.0 * dx)
            elif x_hi is not None:
                dzdx = (x_hi - z) / dx
            elif x_lo is not None:
                dzdx = (z - x_lo) / dx
            else:
                dzdx = 0.0
            if y_lo is not None and y_hi is not None:
                dzdy = (y_hi - y_lo) / (2.0 * dy)
            elif y_hi is not None:
                dzdy = (y_hi - z) / dy
            elif y_lo is not None:
                dzdy = (z - y_lo) / dy
            else:
                dzdy = 0.0
            slopes[(xi, yi)] = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    return slopes


def terrain_summary(
    projection: str,
    lat0_deg: float,
    points: list[tuple[float, float, float]],
) -> dict:
    xs, ys, grid = grid_from_samples(points)
    slopes = slope_grid(projection, lat0_deg, xs, ys, grid)
    zs = [p[2] for p in points]
    slope_values = list(slopes.values())
    dx, dy = (0.0, 0.0)
    if len(xs) > 1 and len(ys) > 1:
        dx, dy = pixel_size_ground_m(projection, lat0_deg, xs[0], xs[1], ys[0], ys[1])
    # Center the points before the plane fit for numerical stability.
    cx = sum(p[0] for p in points) / len(points) if points else 0.0
    cy = sum(p[1] for p in points) / len(points) if points else 0.0
    centered = [(p[0] - cx, p[1] - cy, p[2]) for p in points]
    return {
        "sample_count": len(points),
        "grid_nx": len(xs),
        "grid_ny": len(ys),
        "resolution_m": round((dx + dy) / 2.0, 2) if dx and dy else None,
        "elev_min_m": min(zs) if zs else None,
        "elev_max_m": max(zs) if zs else None,
        "elev_mean_m": sum(zs) / len(zs) if zs else None,
        "elev_std_m": _stdev(zs),
        "relief_p95_p5_m": _percentile(zs, 0.95) - _percentile(zs, 0.05) if zs else None,
        "slope_median_deg": median(slope_values) if slope_values else None,
        "slope_p90_deg": _percentile(slope_values, 0.90) if slope_values else None,
        "slope_max_deg": max(slope_values) if slope_values else None,
        "frac_slope_gt_15deg": (
            sum(1 for s in slope_values if s > 15.0) / len(slope_values)
            if slope_values
            else None
        ),
        "roughness_m": fit_plane_residual_std(centered),
    }


# ---------------------------------------------------------------------------
# Horizon profile
# ---------------------------------------------------------------------------

def horizon_profile(
    projection: str,
    lat0_deg: float,
    points: list[tuple[float, float, float]],
    center_x: float,
    center_y: float,
    site_elev_m: float,
    *,
    eye_height_m: float = 2.0,
    max_radius_m: float = 5000.0,
) -> list[float]:
    raw: list[float | None] = [None] * 360
    for x, y, z in points:
        dx, dy = ground_offsets(projection, lat0_deg, center_x, center_y, x, y)
        dist = math.hypot(dx, dy)
        if dist < 30.0 or dist > max_radius_m:
            continue
        azimuth = math.degrees(math.atan2(dx, dy)) % 360.0
        angle = math.degrees(
            math.atan2(z - (site_elev_m + eye_height_m), max(dist, 1.0))
        )
        idx = int(azimuth) % 360
        if raw[idx] is None or angle > raw[idx]:
            raw[idx] = angle
    profile = _fill_and_smooth(raw)
    return profile


def _fill_and_smooth(raw: list[float | None]) -> list[float]:
    if all(v is None for v in raw):
        return [0.0] * 360
    filled = [0.0] * 360
    for i in range(360):
        if raw[i] is not None:
            filled[i] = float(raw[i])
            continue
        # Nearest valid bin clockwise and counter-clockwise.
        prev_i = next_i = None
        for step in range(1, 360):
            if prev_i is None and raw[(i - step) % 360] is not None:
                prev_i = (i - step) % 360
            if next_i is None and raw[(i + step) % 360] is not None:
                next_i = (i + step) % 360
            if prev_i is not None and next_i is not None:
                break
        if prev_i is None or next_i is None:
            filled[i] = 0.0
        else:
            filled[i] = 0.5 * (float(raw[prev_i]) + float(raw[next_i]))
    # Circular 3-bin median to suppress single-pixel spikes.
    smoothed = []
    for i in range(360):
        window = [filled[(i - 1) % 360], filled[i], filled[(i + 1) % 360]]
        smoothed.append(sorted(window)[1])
    return smoothed


def horizon_stats(profile: list[float]) -> dict:
    return {
        "horizon_mean_deg": sum(profile) / len(profile),
        "horizon_p90_deg": _percentile(profile, 0.90),
        "horizon_max_deg": max(profile),
        "horizon_min_deg": min(profile),
        "open_sky_frac_2deg": sum(1 for h in profile if h < 2.0) / 360.0,
        "open_sky_frac_5deg": sum(1 for h in profile if h < 5.0) / 360.0,
        "open_sky_frac_10deg": sum(1 for h in profile if h < 10.0) / 360.0,
    }


def horizon_at(profile: list[float], azimuth_deg: float) -> float:
    index = azimuth_deg % 360.0
    i0 = int(index) % 360
    i1 = (i0 + 1) % 360
    frac = index - int(index)
    return profile[i0] * (1.0 - frac) + profile[i1] * frac


def best_pad(
    projection: str,
    lat0_deg: float,
    lon0_deg: float,
    xs: list[float],
    ys: list[float],
    grid: dict[tuple[int, int], float],
    site_elev_m: float,
    *,
    max_offset_m: float = 2000.0,
    min_elev_m: float | None = None,
) -> dict:
    """Flattest DEM cell within max_offset, excluding deep pits."""
    if min_elev_m is None:
        min_elev_m = site_elev_m - 50.0
    slopes = slope_grid(projection, lat0_deg, xs, ys, grid)
    cx, cy = project_point(projection, lat0_deg, lon0_deg)
    candidates = []
    for (xi, yi), slope in slopes.items():
        x, y = xs[xi], ys[yi]
        z = grid[(xi, yi)]
        dx, dy = ground_offsets(projection, lat0_deg, cx, cy, x, y)
        offset = math.hypot(dx, dy)
        if offset > max_offset_m or z < min_elev_m:
            continue
        candidates.append((slope, offset, x, y, z))
    if not candidates:
        return {
            "pinpoint_lat_deg": lat0_deg,
            "pinpoint_lon_deg": lon0_deg,
            "pinpoint_slope_deg": None,
            "pinpoint_offset_km": 0.0,
            "pinpoint_elev_m": site_elev_m,
            "pinpoint_score": None,
            "pinpoint_open_sky_frac_5deg": None,
        }
    slope, offset, x, y, z = min(candidates, key=lambda item: (item[0], item[1]))
    lat, lon = unproject_point(projection, x, y)
    return {
        "pinpoint_lat_deg": lat,
        "pinpoint_lon_deg": ((lon + 180.0) % 360.0) - 180.0,
        "pinpoint_slope_deg": slope,
        "pinpoint_offset_km": offset / 1000.0,
        "pinpoint_elev_m": z,
        "pinpoint_score": None,
        "pinpoint_open_sky_frac_5deg": None,
    }


def best_pad_open(
    projection: str,
    lat0_deg: float,
    lon0_deg: float,
    search_xs: list[float],
    search_ys: list[float],
    search_grid: dict[tuple[int, int], float],
    regional_points: list[tuple[float, float, float]],
    site_elev_m: float,
    *,
    max_offset_m: float = 1000.0,
    min_elev_m: float | None = None,
    max_slope_deg: float = 30.0,
) -> dict:
    """Pick a pad that trades local flatness against a 5 km open horizon.

    This is a screening objective, not a landing certification. The selected
    point is later re-checked on a 500 m / 16 m grid.
    """
    if min_elev_m is None:
        min_elev_m = site_elev_m - 50.0
    slopes = slope_grid(projection, lat0_deg, search_xs, search_ys, search_grid)
    cx, cy = project_point(projection, lat0_deg, lon0_deg)
    best = None
    for (xi, yi), slope in slopes.items():
        x, y = search_xs[xi], search_ys[yi]
        z = search_grid[(xi, yi)]
        dx, dy = ground_offsets(projection, lat0_deg, cx, cy, x, y)
        offset = math.hypot(dx, dy)
        if offset > max_offset_m or z < min_elev_m:
            continue
        lat, lon = unproject_point(projection, x, y)
        profile = horizon_profile(
            projection,
            lat,
            regional_points,
            x,
            y,
            z,
            max_radius_m=5000.0,
        )
        stats = horizon_stats(profile)
        flat_score = max(0.0, 1.0 - min(slope, max_slope_deg) / max_slope_deg)
        proximity = max(0.0, 1.0 - offset / max_offset_m)
        objective = (
            0.50 * stats["open_sky_frac_5deg"]
            + 0.35 * flat_score
            + 0.15 * proximity
        )
        candidate = (
            objective,
            -slope,
            -offset,
            lat,
            lon,
            z,
            slope,
            offset,
            stats,
        )
        if best is None or candidate[:3] > best[:3]:
            best = candidate
    if best is None:
        return best_pad(
            projection,
            lat0_deg,
            lon0_deg,
            search_xs,
            search_ys,
            search_grid,
            site_elev_m,
            max_offset_m=max_offset_m,
            min_elev_m=min_elev_m,
        )
    objective, _, _, lat, lon, z, slope, offset, stats = best
    return {
        "pinpoint_lat_deg": lat,
        "pinpoint_lon_deg": ((lon + 180.0) % 360.0) - 180.0,
        "pinpoint_slope_deg": slope,
        "pinpoint_offset_km": offset / 1000.0,
        "pinpoint_elev_m": z,
        "pinpoint_score": objective,
        "pinpoint_open_sky_frac_5deg": stats["open_sky_frac_5deg"],
    }


# ---------------------------------------------------------------------------
# Misc math
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * R_MOON_M * math.asin(min(1.0, math.sqrt(a))) / 1000.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    return (sum((v - avg) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight
