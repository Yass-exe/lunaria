#!/usr/bin/env python3
"""Fetch LOLA/NAC terrain data and PSR context from NASA Moon Trek.

Uses the public ArcGIS ImageServer endpoints behind Moon Trek:
  * point elevation (identify)
  * 32x32 DEM samples over a local and regional box (getSamples)
  * hillshade renderings (exportImage)
  * the south-polar PSR catalogue (MapServer query)

The exact same data can be downloaded as GeoTIFFs later; this script keeps
the analysis reproducible without multi-gigabyte downloads.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from common import (
    ASSET_DIR,
    INTERIM_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    TREK_BASE,
    ensure_dirs,
    http_get,
    http_get_json,
    load_sites,
    log,
    read_json,
    utc_now,
    write_csv,
    write_json,
)
from lunar_geom import (
    best_pad_open,
    bbox_native,
    grid_from_samples,
    ground_offsets,
    haversine_km,
    horizon_profile,
    horizon_stats,
    parse_dem_samples,
    project_point,
    sample_distance_native,
    terrain_summary,
)

SERVICES_CATALOG = "https://trek.nasa.gov/moon/trekarcgis/rest/services?f=pjson"
STATIC_LAYERS = "https://trek.nasa.gov/moon/jpl/config/staticLayers.json"
PSR_QUERY = f"{TREK_BASE}/PSR_SP/MapServer/0/query"
WAC_GLOBAL = "LRO_WAC_Mosaic_Global_303ppd_v02"
WAC_SPOLE = "LRO_WAC_Mosaic_SPole60_100m_v02"


def fetch_json_cached(url: str, path: Path, params: dict | None = None, force: bool = False):
    if path.exists() and not force:
        return read_json(path)
    payload = http_get_json(url, params)
    write_json(path, payload)
    return payload


def service_metadata(service: str, force: bool = False) -> dict:
    path = RAW_DIR / "trek" / f"{service}_meta.json"
    return fetch_json_cached(f"{TREK_BASE}/{service}/ImageServer", path, {"f": "pjson"}, force)


def identify(service: str, site: dict, force: bool = False) -> dict:
    path = RAW_DIR / "trek" / f"{site['site_id']}_identify.json"
    if path.exists() and not force:
        return read_json(path)
    payload = http_get_json(
        f"{TREK_BASE}/{service}/ImageServer/identify",
        {
            "geometry": json.dumps(
                {
                    "x": site["lon_deg"],
                    "y": site["lat_deg"],
                    "spatialReference": {"wkid": 4326},
                }
            ),
            "geometryType": "esriGeometryPoint",
            "returnCatalogItems": "false",
            "returnGeometry": "true",
            "f": "json",
        },
    )
    write_json(path, payload)
    return payload


def get_samples(service: str, site: dict, label: str, half_m: float, force: bool = False) -> dict:
    path = RAW_DIR / "trek" / f"{site['site_id']}_samples_{label}.json"
    if path.exists() and not force:
        return read_json(path)
    projection = site["projection"]
    xmin, ymin, xmax, ymax, units = bbox_native(
        projection, site["lat_deg"], site["lon_deg"], half_m
    )
    payload = http_get_json(
        f"{TREK_BASE}/{service}/ImageServer/getSamples",
        {
            "geometry": json.dumps(
                {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}
            ),
            "geometryType": "esriGeometryEnvelope",
            "sampleDistance": sample_distance_native(projection, half_m),
            "f": "json",
        },
        timeout=120,
    )
    write_json(path, payload)
    log(
        f"{site['site_id']} {label}: {len(payload.get('samples') or []):,} samples, "
        f"bbox {units} [{xmin:.3f},{ymin:.3f},{xmax:.3f},{ymax:.3f}]"
    )
    return payload


def sample_elevation(identify_payload: dict, local_points: list[tuple[float, float, float]]) -> tuple[float, str]:
    value = identify_payload.get("value")
    if value not in (None, "NoData"):
        try:
            return float(value), "identify"
        except (TypeError, ValueError):
            pass
    if local_points:
        values = sorted(z for _, _, z in local_points)
        return values[len(values) // 2], "local_median"
    raise RuntimeError("No elevation available from identify() or getSamples()")


def fetch_psr(force: bool = False) -> dict:
    path = RAW_DIR / "trek" / "psr_sp.geojson"
    if path.exists() and not force:
        return read_json(path)
    payload = http_get_json(
        PSR_QUERY,
        {
            "where": "1=1",
            "outFields": "PSR_ID,Lunar_Feat,Area__km2_,Cent__Lat_,Cent__Long",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
        timeout=120,
    )
    write_json(path, payload)
    log(f"PSR catalogue: {len(payload.get('features') or [])} south-polar entries")
    return payload


def psr_proximity(site: dict, psr: dict) -> dict:
    best = None
    for feature in psr.get("features") or []:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        plon, plat = float(coords[0]), float(coords[1])
        props = feature.get("properties") or {}
        area = float(props.get("Area__km2_") or 0.0)
        radius = math.sqrt(area / math.pi) if area > 0 else 0.0
        center_distance = haversine_km(site["lat_deg"], site["lon_deg"], plat, plon)
        edge_distance = max(0.0, center_distance - radius)
        candidate = {
            "site_id": site["site_id"],
            "nearest_psr_id": props.get("PSR_ID", ""),
            "nearest_psr_feature": props.get("Lunar_Feat", ""),
            "psr_centroid_lat_deg": plat,
            "psr_centroid_lon_deg": plon,
            "psr_area_km2": round(area, 3),
            "psr_equivalent_radius_km": round(radius, 3),
            "centroid_distance_km": round(center_distance, 3),
            "psr_edge_km_approx": round(edge_distance, 3),
            "method": "centroid minus equivalent-area radius; approximate",
            "source_id": "SRC-PSR-01",
        }
        if best is None or candidate["psr_edge_km_approx"] < best["psr_edge_km_approx"]:
            best = candidate
    return best or {
        "site_id": site["site_id"],
        "nearest_psr_id": "",
        "nearest_psr_feature": "",
        "psr_edge_km_approx": "",
        "method": "PSR catalogue unavailable",
        "source_id": "SRC-PSR-01",
    }


def export_image(url: str, params: dict, path: Path, force: bool = False) -> bool:
    if path.exists() and not force:
        return True
    raw = http_get(url, params, timeout=120, accept="image/jpeg")
    if not raw.startswith(b"\xff\xd8"):
        log(f"WARNING: exportImage did not return JPEG for {path.name}: {raw[:120]!r}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    log(f"image saved: {path.name} ({len(raw):,} bytes)")
    return True


def render_hillshade(site: dict, service: str, half_m: float, force: bool = False) -> None:
    path = ASSET_DIR / f"hillshade_{site['site_id']}.jpg"
    if path.exists() and not force:
        return
    xmin, ymin, xmax, ymax, _ = bbox_native(
        site["projection"], site["lat_deg"], site["lon_deg"], half_m
    )
    rule = json.dumps(
        {
            "rasterFunction": "Hillshade",
            "rasterFunctionArguments": {
                "Azimuth": 315,
                "Altitude": 25,
                "ZFactor": 2,
            },
        }
    )
    ok = export_image(
        f"{TREK_BASE}/{service}/ImageServer/exportImage",
        {
            "bbox": f"{xmin},{ymin},{xmax},{ymax}",
            "size": "512,512",
            "format": "jpg",
            "renderingRule": rule,
            "f": "image",
        },
        path,
        force,
    )
    if not ok:
        export_image(
            f"{TREK_BASE}/{service}/ImageServer/exportImage",
            {"bbox": f"{xmin},{ymin},{xmax},{ymax}", "size": "512,512", "format": "jpg", "f": "image"},
            path,
            force=True,
        )


def render_basemaps(force: bool = False) -> None:
    export_image(
        f"{TREK_BASE}/{WAC_GLOBAL}/ImageServer/exportImage",
        {"bbox": "-180,-90,180,90", "size": "1024,512", "format": "jpg", "f": "image"},
        ASSET_DIR / "moon_wac_global.jpg",
        force,
    )
    export_image(
        f"{TREK_BASE}/{WAC_SPOLE}/ImageServer/exportImage",
        {"bbox": "-400000,-400000,400000,400000", "size": "1024,1024", "format": "jpg", "f": "image"},
        ASSET_DIR / "moon_wac_south.jpg",
        force,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sites", nargs="*", default=None)
    args = parser.parse_args()
    ensure_dirs()

    # Catalog the available Moon Trek services for provenance.
    fetch_json_cached(SERVICES_CATALOG, RAW_DIR / "trek" / "services.json", None, args.force)
    fetch_json_cached(STATIC_LAYERS, RAW_DIR / "trek" / "static_layers.json", None, args.force)
    psr = fetch_psr(args.force)

    sites = load_sites()
    elevations: dict[str, dict] = {}
    terrain_rows: list[dict] = []
    horizon_rows: list[dict] = []
    pinpoint_horizon_rows: list[dict] = []
    psr_rows: list[dict] = []
    details: dict[str, dict] = {}

    for site in sites:
        if args.sites and site["site_id"] not in args.sites:
            continue
        service = site["dem_service"]
        projection = site["projection"]
        log(f"--- {site['site_id']} using {service}")

        meta = service_metadata(service, args.force)
        identify_payload = identify(service, site, args.force)
        local_payload = get_samples(service, site, "local", 250.0, args.force)
        regional_payload = get_samples(service, site, "regional", 2500.0, args.force)
        search_payload = get_samples(service, site, "search", 1000.0, args.force)

        local_points = parse_dem_samples(local_payload)
        regional_points = parse_dem_samples(regional_payload)
        search_points = parse_dem_samples(search_payload)
        if not local_points or not regional_points or not search_points:
            raise RuntimeError(f"{site['site_id']}: DEM sample parsing returned no data")

        elevation_m, elevation_source = sample_elevation(identify_payload, local_points)
        site["elevation_m"] = elevation_m
        elevations[site["site_id"]] = {
            "elevation_m": round(elevation_m, 3),
            "elevation_source": elevation_source,
            "dem_service": service,
            "dem_label": site["dem_label"],
            "dem_res_m": site["dem_res_m"],
            "projection": projection,
        }

        local = terrain_summary(projection, site["lat_deg"], local_points)
        regional = terrain_summary(projection, site["lat_deg"], regional_points)
        cx, cy = project_point(projection, site["lat_deg"], site["lon_deg"])
        profile = horizon_profile(
            projection,
            site["lat_deg"],
            regional_points,
            cx,
            cy,
            elevation_m,
            max_radius_m=5000.0,
        )
        hstats = horizon_stats(profile)
        search_xs, search_ys, search_grid = grid_from_samples(search_points)
        search_terrain = terrain_summary(projection, site["lat_deg"], search_points)
        pad = best_pad_open(
            projection,
            site["lat_deg"],
            site["lon_deg"],
            search_xs,
            search_ys,
            search_grid,
            regional_points,
            elevation_m,
            max_offset_m=1000.0,
            min_elev_m=elevation_m - 50.0,
        )

        # Re-evaluate the horizon at the flattest pad candidate. Sun/Earth
        # azimuth-elevation barely changes over a 2 km offset, so the existing
        # ephemeris can be reused with this local horizon.
        pinpoint_site = dict(site)
        pinpoint_site["lat_deg"] = pad["pinpoint_lat_deg"]
        pinpoint_site["lon_deg"] = pad["pinpoint_lon_deg"]
        pinpoint_payload = get_samples(service, pinpoint_site, "pinpoint", 2500.0, args.force)
        pinpoint_local_payload = get_samples(
            service, pinpoint_site, "pinpoint_local", 250.0, args.force
        )
        pinpoint_points = parse_dem_samples(pinpoint_payload)
        pinpoint_local_points = parse_dem_samples(pinpoint_local_payload)
        pcx, pcy = project_point(projection, pad["pinpoint_lat_deg"], pad["pinpoint_lon_deg"])
        pprofile = horizon_profile(
            projection,
            pad["pinpoint_lat_deg"],
            pinpoint_points,
            pcx,
            pcy,
            pad["pinpoint_elev_m"],
            max_radius_m=5000.0,
        )
        pstats = horizon_stats(pprofile)
        pin_terrain = terrain_summary(
            projection, pad["pinpoint_lat_deg"], pinpoint_local_points
        )

        row = {
            "site_id": site["site_id"],
            "site_name": site["name"],
            "lat_deg": site["lat_deg"],
            "lon_deg": site["lon_deg"],
            "dem_service": service,
            "dem_label": site["dem_label"],
            "dem_res_nominal_m": site["dem_res_m"],
            "dem_res_effective_m": local.get("resolution_m"),
            "dem_pixel_size_meta": meta.get("pixelSizeX"),
            "elevation_site_m": round(elevation_m, 2),
            "elevation_source": elevation_source,
            "local_sample_count": local.get("sample_count"),
            "local_grid": f"{local.get('grid_nx')}x{local.get('grid_ny')}",
            "elev_min_m": _round(local.get("elev_min_m"), 2),
            "elev_max_m": _round(local.get("elev_max_m"), 2),
            "elev_mean_m": _round(local.get("elev_mean_m"), 2),
            "elev_std_m": _round(local.get("elev_std_m"), 2),
            "relief_p95_p5_m": _round(local.get("relief_p95_p5_m"), 2),
            "slope_median_deg": _round(local.get("slope_median_deg"), 3),
            "slope_p90_deg": _round(local.get("slope_p90_deg"), 3),
            "slope_max_deg": _round(local.get("slope_max_deg"), 3),
            "frac_slope_gt_15deg": _round(local.get("frac_slope_gt_15deg"), 4),
            "roughness_m": _round(local.get("roughness_m"), 3),
            "regional_resolution_m": regional.get("resolution_m"),
            "horizon_mean_deg": _round(hstats["horizon_mean_deg"], 3),
            "horizon_p90_deg": _round(hstats["horizon_p90_deg"], 3),
            "horizon_max_deg": _round(hstats["horizon_max_deg"], 3),
            "horizon_min_deg": _round(hstats["horizon_min_deg"], 3),
            "open_sky_frac_2deg": _round(hstats["open_sky_frac_2deg"], 4),
            "open_sky_frac_5deg": _round(hstats["open_sky_frac_5deg"], 4),
            "open_sky_frac_10deg": _round(hstats["open_sky_frac_10deg"], 4),
            "pinpoint_lat_deg": _round(pad["pinpoint_lat_deg"], 6),
            "pinpoint_lon_deg": _round(pad["pinpoint_lon_deg"], 6),
            "pinpoint_elev_m": _round(pad["pinpoint_elev_m"], 2),
            "pinpoint_slope_deg": _round(pad["pinpoint_slope_deg"], 3),
            "pinpoint_offset_km": _round(pad["pinpoint_offset_km"], 3),
            "pinpoint_search_score": _round(pad.get("pinpoint_score"), 4),
            "pinpoint_search_open_sky_frac_5deg": _round(pad.get("pinpoint_open_sky_frac_5deg"), 4),
            "pinpoint_search_res_m": _round(search_terrain.get("resolution_m"), 2),
            "pinpoint_slope_median_deg": _round(pin_terrain.get("slope_median_deg"), 3),
            "pinpoint_slope_p90_deg": _round(pin_terrain.get("slope_p90_deg"), 3),
            "pinpoint_slope_max_deg": _round(pin_terrain.get("slope_max_deg"), 3),
            "pinpoint_roughness_m": _round(pin_terrain.get("roughness_m"), 3),
            "pinpoint_relief_m": _round(pin_terrain.get("relief_p95_p5_m"), 3),
            "pinpoint_dem_res_m": _round(pin_terrain.get("resolution_m"), 2),
            "pinpoint_horizon_mean_deg": _round(pstats["horizon_mean_deg"], 3),
            "pinpoint_horizon_p90_deg": _round(pstats["horizon_p90_deg"], 3),
            "pinpoint_horizon_max_deg": _round(pstats["horizon_max_deg"], 3),
            "pinpoint_horizon_min_deg": _round(pstats["horizon_min_deg"], 3),
            "pinpoint_open_sky_frac_5deg": _round(pstats["open_sky_frac_5deg"], 4),
            "pinpoint_open_sky_frac_10deg": _round(pstats["open_sky_frac_10deg"], 4),
            "horizon_model_radius_km": 5.0,
            "horizon_eye_height_m": 2.0,
            "source_id": {
                "LRO_LOLA_DEM_SPole875_5mp_v04": "SRC-DEM-01",
                "LRO_LOLA_DEM_SPole75_30mp_v04": "SRC-DEM-02",
                "LRO_LOLA_DEM_Global_256ppd_v06": "SRC-DEM-03",
                "LRO_NAC_DEM_14N304E_2mp": "SRC-DEM-04",
                "NAC_DTM_APOLLO17": "SRC-DEM-05",
            }.get(service, "SRC-DEM-03"),
            "notes": "Slope/roughness from a 32x32 DEM sample grid; horizon model uses the 5 km regional grid.",
        }
        terrain_rows.append(row)

        for azimuth in range(360):
            horizon_rows.append(
                {
                    "site_id": site["site_id"],
                    "azimuth_deg": azimuth,
                    "horizon_deg": round(profile[azimuth], 4),
                }
            )
            pinpoint_horizon_rows.append(
                {
                    "site_id": site["site_id"],
                    "azimuth_deg": azimuth,
                    "horizon_deg": round(pprofile[azimuth], 4),
                }
            )

        psr_row = psr_proximity(site, psr)
        psr_rows.append(psr_row)

        render_hillshade(site, service, 2500.0, args.force)
        details[site["site_id"]] = {
            "terrain": row,
            "pinpoint": pad,
            "pinpoint_horizon_stats": pstats,
            "elevation": elevations[site["site_id"]],
            "psr": psr_row,
        }

    render_basemaps(args.force)

    elevations_path = INTERIM_DIR / "site_elevations.json"
    existing = read_json(elevations_path).get("sites", {}) if elevations_path.exists() else {}
    existing.update(elevations)
    write_json(
        elevations_path,
        {"generated_at": utc_now(), "sites": existing},
    )

    if terrain_rows:
        # Merge with any previously written rows when --sites is used.
        existing_rows = []
        terrain_path = PROCESSED_DIR / "terrain_summary.csv"
        if terrain_path.exists() and args.sites:
            existing_rows = [
                row for row in _read_rows(terrain_path) if row["site_id"] not in {r["site_id"] for r in terrain_rows}
            ]
        write_csv(terrain_path, existing_rows + terrain_rows)
        write_json(PROCESSED_DIR / "terrain_details.json", details)

        horizon_path = PROCESSED_DIR / "horizon_profiles.csv"
        horizon_existing = []
        if horizon_path.exists() and args.sites:
            selected = {row["site_id"] for row in terrain_rows}
            horizon_existing = [
                row for row in _read_rows(horizon_path) if row["site_id"] not in selected
            ]
        write_csv(horizon_path, horizon_existing + horizon_rows)

        pinpoint_path = PROCESSED_DIR / "pinpoint_horizon_profiles.csv"
        pinpoint_existing = []
        if pinpoint_path.exists() and args.sites:
            selected = {row["site_id"] for row in terrain_rows}
            pinpoint_existing = [
                row for row in _read_rows(pinpoint_path) if row["site_id"] not in selected
            ]
        write_csv(pinpoint_path, pinpoint_existing + pinpoint_horizon_rows)

        psr_path = PROCESSED_DIR / "psr_proximity.csv"
        psr_existing = []
        if psr_path.exists() and args.sites:
            selected = {row["site_id"] for row in terrain_rows}
            psr_existing = [row for row in _read_rows(psr_path) if row["site_id"] not in selected]
        write_csv(psr_path, psr_existing + psr_rows)

    log(f"Terrain rows: {len(terrain_rows)}; elevations: {len(elevations)}")


def _round(value, digits: int):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    return value


def _read_rows(path: Path) -> list[dict]:
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
