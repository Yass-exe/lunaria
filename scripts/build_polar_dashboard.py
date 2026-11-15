#!/usr/bin/env python3
"""Build compact static data and map layers for the polar-first dashboard."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

try:
    from .common import CONFIG_DIR, PROCESSED_DIR, WEB_DIR, read_csv, read_json, utc_now
    from .polar_model import SCORE_DIMENSIONS
except ImportError:
    from common import CONFIG_DIR, PROCESSED_DIR, WEB_DIR, read_csv, read_json, utc_now
    from polar_model import SCORE_DIMENSIONS


ARTIFACT_LABELS = {
    "data/interim/polar_ephemeris.csv": "JPL Horizons Sun/Earth ephemeris",
    "data/processed/polar_cell_metrics.csv.gz": "All screened cell measurements",
    "data/processed/polar_terrain_1km.tif": "1 km terrain aggregate",
    "data/processed/polar_illumination_1km.tif": "Solar and Earth visibility rasters",
    "data/processed/polar_region_ranking.csv": "Stage-one region ranking",
    "data/processed/polar_candidate_regions.geojson": "Candidate region polygons",
    "data/processed/polar_refined_region_ranking.csv": "Final refined region ranking",
    "data/processed/polar_refined_cells.csv": "Refined source-cell measurements",
    "data/processed/polar_candidate_timeseries.csv": "Six-hour Sun/Earth status",
    "data/processed/polar_data_gaps.csv": "Missing-data request ledger",
    "data/processed/polar_sensitivity.csv": "Dirichlet top-1 probabilities",
    "data/processed/polar_recommendation.json": "Machine-readable recommendation",
    "data/processed/polar_benchmark.json": "Geometry and validation benchmark",
    "data/processed/polar_terrain_manifest.json": "Terrain manifest",
    "data/processed/polar_illumination_manifest.json": "Illumination manifest",
}


def _float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _summary(values) -> dict:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not array.size:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "median": None,
            "p90": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": int(array.size),
        "min": round(float(array.min()), 6),
        "p10": round(float(np.percentile(array, 10)), 6),
        "median": round(float(np.median(array)), 6),
        "p90": round(float(np.percentile(array, 90)), 6),
        "max": round(float(array.max()), 6),
        "mean": round(float(array.mean()), 6),
    }


def _distribution(values, *, bins: int = 24, low: float, high: float) -> dict:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not array.size or high <= low:
        return {**_summary(array), "low": low, "high": high, "clipped": 0, "bins": [], "edges": []}
    clipped = int(np.count_nonzero((array < low) | (array > high)))
    counts, edges = np.histogram(np.clip(array, low, high), bins=bins, range=(low, high))
    return {
        **_summary(array),
        "low": low,
        "high": high,
        "clipped": clipped,
        "bins": counts.astype(int).tolist(),
        "edges": [round(float(value), 6) for value in edges],
    }


def _read_cell_arrays(processed_dir: Path) -> dict[str, list[float]]:
    arrays: dict[str, list[float]] = {
        "solar": [],
        "earth": [],
        "slope": [],
        "dark": [],
        "psr": [],
    }
    with (processed_dir / "polar_cell_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            arrays["solar"].append(_float(row["solar_illumination_fraction"], 0.0))
            arrays["earth"].append(_float(row["earth_visibility_fraction"], 0.0))
            arrays["slope"].append(_float(row["regional_slope_p90_deg"], 0.0))
            arrays["dark"].append(_float(row["longest_dark_days"], 0.0))
            arrays["psr"].append(_float(row["psr_edge_km"], 0.0))
    return arrays


def _read_score_array(processed_dir: Path) -> list[float]:
    values: list[float] = []
    with (processed_dir / "polar_cell_scores.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            values.append(_float(row["weighted_geometric_mean"], 0.0))
    return values


def _row_count(path: Path) -> int | None:
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    return None


def _artifact_rows(manifest: dict) -> list[dict]:
    rows = []
    for item in manifest.get("files", []):
        path = item["path"]
        suffix = Path(path).suffix.lower()
        rows.append(
            {
                "path": path,
                "label": ARTIFACT_LABELS.get(path, Path(path).name),
                "href": f"../{path}",
                "kind": {
                    ".csv": "CSV",
                    ".gz": "CSV.GZ",
                    ".tif": "GeoTIFF",
                    ".json": "JSON",
                    ".geojson": "GeoJSON",
                }.get(suffix, suffix.lstrip(".").upper() or "File"),
                "bytes": _int(item.get("bytes")),
                "sha256": item.get("sha256", ""),
                "rows": _row_count(Path(path)) if suffix in {".csv", ".gz"} else None,
            }
        )
    return rows


def _pipeline(meta: dict, regions: int, refined: int, artifacts: int) -> list[dict]:
    return [
        {
            "label": "Source terrain",
            "value": 4096 * 4096,
            "display": "4096²",
            "unit": "pixels",
            "detail": f"NASA LOLA south-polar DEM at {meta['source_resolution_m']:.2f} m/px",
        },
        {
            "label": "Full-cap screen",
            "value": meta["cell_count"],
            "display": f"{meta['cell_count']:,}",
            "unit": "cells",
            "detail": "1 km observer cells, horizons to 60 km, 2,925 six-hour samples",
        },
        {
            "label": "Candidate clusters",
            "value": regions,
            "display": str(regions),
            "unit": "regions",
            "detail": "Eight-way connected components at the operational 0.60 threshold",
        },
        {
            "label": "Source refinement",
            "value": refined,
            "display": f"{refined:,}",
            "unit": "pixels",
            "detail": "Fresh ~148 m horizons inside each shortlisted cluster",
        },
        {
            "label": "Sun/Earth states",
            "value": meta["timeline_rows"],
            "display": f"{meta['timeline_rows']:,}",
            "unit": "samples",
            "detail": "Six regions × 2,925 aligned timestamps",
        },
        {
            "label": "Packaged evidence",
            "value": artifacts,
            "display": str(artifacts),
            "unit": "files",
            "detail": "Rankings, geometry, timeline, benchmark, and checksums",
        },
    ]


def build_payload(processed_dir: Path = PROCESSED_DIR) -> dict:
    recommendation = read_json(processed_dir / "polar_recommendation.json")
    ranking = read_csv(processed_dir / "polar_refined_region_ranking.csv")
    stage1_ranking = {
        row["region_id"]: row
        for row in read_csv(processed_dir / "polar_region_ranking.csv")
    }
    refined = read_csv(processed_dir / "polar_refined_cells.csv")
    sensitivity = {
        row["candidate_id"]: row
        for row in read_csv(processed_dir / "polar_sensitivity.csv")
    }
    seed_rows = {row["candidate_id"]: row for row in refined}

    timeline_rows = read_csv(processed_dir / "polar_candidate_timeseries.csv")
    by_region: dict[str, list[dict]] = defaultdict(list)
    for row in timeline_rows:
        by_region[row["region_id"]].append(row)
    for rows in by_region.values():
        rows.sort(key=lambda row: row["utc"])
    if not by_region:
        raise ValueError("candidate timeline is empty")
    first_region = ranking[0]["region_id"]
    timestamps = [row["utc"] for row in by_region[first_region]]
    for region_id, rows in by_region.items():
        if [row["utc"] for row in rows] != timestamps:
            raise ValueError(f"timeline timestamps do not align for {region_id}")

    regions = []
    for row in ranking:
        region_id = row["region_id"]
        seed = seed_rows[row["provisional_seed_id"]]
        stage1_cells = []
        for candidate_id in stage1_ranking[region_id]["member_cell_ids"].split(";"):
            _, raster_row, raster_col = candidate_id.split("-")
            stage1_cells.append([int(raster_row), int(raster_col)])
        regions.append(
            {
                "rank": _int(row["rank"]),
                "region_id": region_id,
                "label": f"Candidate Region {_int(row['rank'])}",
                "stage1_rank": _int(row["stage1_rank"]),
                "cell_count": _int(row["refined_cell_count"]),
                "eligible_cell_count": _int(row["eligible_refined_cell_count"]),
                "weighted_sum": _float(row["weighted_sum"]),
                "weighted_geometric_mean": _float(row["weighted_geometric_mean"]),
                "top1_probability": _float(
                    sensitivity.get(region_id, {}).get("top1_probability"), 0.0
                ),
                "dimensions": {
                    key: _float(row[key], 0.0) for key in SCORE_DIMENSIONS
                },
                "indicators": {
                    "solar_power": _float(row["solar_power"], 0.0),
                    "earth_visibility": _float(row["earth_visibility"], 0.0),
                    "terrain_safety": _float(row["terrain_safety"], 0.0),
                    "isru_access_proxy": _float(row["isru_access"], 0.0),
                    "science_proxy": _float(row["science_value"], 0.0),
                    "thermal_proxy": _float(row["thermal_stability"], 0.0),
                    "crew_safety": _float(row["terrain_safety"], 0.0),
                    "data_maturity": _float(row["data_maturity"], 0.0),
                },
                "stage1_cells": stage1_cells,
                "seed": {
                    "id": row["provisional_seed_id"],
                    "lat_deg": _float(row["provisional_seed_lat_deg"]),
                    "lon_deg": _float(row["provisional_seed_lon_deg"]),
                    "elevation_m": _float(row["provisional_seed_elevation_m"]),
                    "resolution_m": _float(
                        row["provisional_seed_source_resolution_m"]
                    ),
                    "score": _float(row["provisional_seed_score"]),
                    "fine_row": _int(seed["fine_row"]),
                    "fine_col": _int(seed["fine_col"]),
                    "solar_fraction": _float(seed["solar_illumination_fraction"]),
                    "longest_dark_days": _float(seed["longest_dark_days"]),
                    "continuity_fraction": _float(seed["sunlight_continuity_fraction"]),
                    "earth_fraction": _float(seed["earth_visibility_fraction"]),
                    "slope_p90_deg": _float(seed["regional_slope_p90_deg"]),
                    "psr_edge_km": _float(seed["psr_edge_km"]),
                },
            }
        )

    compact_timeline = {}
    for region_id, rows in by_region.items():
        compact_timeline[region_id] = [
            [
                round(_float(row["sun_elevation_deg"], 0.0), 3),
                round(_float(row["sun_horizon_deg"], 0.0), 3),
                row["sun_visible"] == "True",
                round(_float(row["earth_elevation_deg"], 0.0), 3),
                round(_float(row["earth_horizon_deg"], 0.0), 3),
                row["earth_visible"] == "True",
            ]
            for row in rows
        ]

    benchmark = read_json(processed_dir / "polar_benchmark.json")
    illumination_manifest = read_json(
        processed_dir / "polar_illumination_manifest.json"
    )
    terrain_manifest = read_json(processed_dir / "polar_terrain_manifest.json")
    config = read_json(CONFIG_DIR / "polar_scoring.json")
    artemis = read_json(CONFIG_DIR / "artemis_regions.json")
    data_manifest = read_json(processed_dir / "polar_data_manifest.json")
    data_gaps = read_csv(processed_dir / "polar_data_gaps.csv")
    artifacts = _artifact_rows(data_manifest)

    cell_arrays = _read_cell_arrays(processed_dir)
    cell_arrays["score"] = _read_score_array(processed_dir)
    cell_stats = {
        "count": len(cell_arrays["solar"]),
        "solar": _distribution(cell_arrays["solar"], low=0.0, high=1.0),
        "earth": _distribution(cell_arrays["earth"], low=0.0, high=1.0),
        "slope": _distribution(cell_arrays["slope"], low=0.0, high=45.0),
        "dark": _distribution(cell_arrays["dark"], low=0.0, high=60.0),
        "psr": _distribution(cell_arrays["psr"], low=0.0, high=70.0),
        "score": _distribution(cell_arrays["score"], low=0.0, high=1.0),
    }

    refined_by_region: dict[str, list[dict]] = defaultdict(list)
    for row in refined:
        refined_by_region[row["region_id"]].append(row)
    region_stats = {}
    for region in regions:
        rows = refined_by_region[region["region_id"]]
        region_stats[region["region_id"]] = {
            "solar": _summary([row["solar_illumination_fraction"] for row in rows]),
            "earth": _summary([row["earth_visibility_fraction"] for row in rows]),
            "slope": _summary([row["regional_slope_p90_deg"] for row in rows]),
            "dark": _summary([row["longest_dark_days"] for row in rows]),
            "psr": _summary([row["psr_edge_km"] for row in rows]),
            "score": _summary([row["weighted_geometric_mean"] for row in rows]),
        }

    region_index = {region["region_id"]: index for index, region in enumerate(regions)}
    refined_cloud = [
        [
            region_index[row["region_id"]],
            round(_float(row["solar_illumination_fraction"], 0.0), 6),
            round(_float(row["earth_visibility_fraction"], 0.0), 6),
            round(_float(row["regional_slope_p90_deg"], 0.0), 4),
            round(_float(row["weighted_geometric_mean"], 0.0), 6),
            round(_float(row["psr_edge_km"], 0.0), 4),
            round(_float(row["lat_deg"], 0.0), 6),
            round(_float(row["lon_deg"], 0.0), 6),
        ]
        for row in refined
    ]

    meta = {
        "generated_at": utc_now(),
        "scope": "Lunar south pole, 80–90°S",
        "window_start": timestamps[0],
        "window_end": timestamps[-1],
        "step_hours": 6,
        "cell_count": illumination_manifest["cells"],
        "stage1_cell_m": 1000,
        "stage2_resolution_m": recommendation["refinement"][
            "stage2_source_resolution_m"
        ],
        "observer_elevation": illumination_manifest.get("observer_elevation", "max"),
        "source_resolution_m": terrain_manifest["source_resolution_m"],
        "refined_cell_count": len(refined),
        "timeline_rows": len(timeline_rows),
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(item["bytes"] for item in artifacts),
    }

    return {
        "meta": meta,
        "recommendation": recommendation,
        "weights": config["weights"],
        "policy": config,
        "scoring": {
            "headline": config["scoring"]["headline"],
            "geometric_floor": config["scoring"]["geometric_floor"],
            "continuity_weighted": False,
        },
        "dimensions": list(SCORE_DIMENSIONS),
        "regions": regions,
        "region_stats": region_stats,
        "refined_cells": {
            "fields": [
                "region_index",
                "solar",
                "earth",
                "slope",
                "score",
                "psr_edge_km",
                "lat_deg",
                "lon_deg",
            ],
            "rows": refined_cloud,
        },
        "cell_stats": cell_stats,
        "pipeline": _pipeline(meta, len(regions), len(refined), len(artifacts)),
        "timestamps": timestamps,
        "timeline": compact_timeline,
        "benchmark": benchmark,
        "artemis_regions": artemis,
        "data_gaps": data_gaps,
        "artifacts": artifacts,
        "layers": {
            "score": {
                "src": "assets/polar_score.png",
                "label": "Suitability score",
                "low": "Lower score",
                "high": "Higher score",
                "description": "Weighted geometric mean of all eight normalized indicators for every 1 km cell.",
            },
            "solar": {
                "src": "assets/polar_solar.png",
                "label": "Solar illumination",
                "low": "Less illuminated",
                "high": "More illuminated",
                "description": "Fraction of 2,925 six-hour samples with the Sun above the local terrain horizon.",
            },
            "earth": {
                "src": "assets/polar_earth.png",
                "label": "Earth visibility",
                "low": "Less visible",
                "high": "More visible",
                "description": "Direct-to-Earth visibility above the terrain horizon; relay availability is unknown.",
            },
            "slope": {
                "src": "assets/polar_slope.png",
                "label": "Terrain roughness",
                "low": "Flatter",
                "high": "Steeper",
                "description": "1 km regional slope p90 derived from the ~148 m LOLA source. Not landing-pad slope.",
            },
        },
    }


def _rgba(values: np.ndarray, valid: np.ndarray, palette: str) -> np.ndarray:
    normalized = np.clip(values, 0.0, 1.0)
    if palette == "solar":
        red = 34 + 221 * normalized
        green = 20 + 177 * normalized
        blue = 72 - 42 * normalized
    elif palette == "earth":
        red = 20 + 90 * normalized
        green = 28 + 180 * normalized
        blue = 60 + 195 * normalized
    elif palette == "slope":
        red = 45 + 210 * normalized
        green = 190 - 140 * normalized
        blue = 95 - 55 * normalized
    else:
        red = 24 + 230 * normalized
        green = 26 + 180 * normalized
        blue = 58 + 92 * normalized
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    rgba[..., 0] = red.astype(np.uint8)
    rgba[..., 1] = green.astype(np.uint8)
    rgba[..., 2] = blue.astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba


def build_map_assets(processed_dir: Path, asset_dir: Path) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    with rasterio.open(processed_dir / "polar_illumination_1km.tif") as source:
        solar = source.read(1, masked=False)
        earth = source.read(2, masked=False)
        nodata = source.nodata
    with rasterio.open(processed_dir / "polar_terrain_1km.tif") as source:
        slope = source.read(2, masked=False)
        terrain_nodata = source.nodata
    valid = np.isfinite(solar) & (solar != nodata)
    terrain_valid = np.isfinite(slope) & (slope != terrain_nodata)

    score = np.full(solar.shape, np.nan, dtype=np.float32)
    with (processed_dir / "polar_cell_scores.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            score[int(row["row"]), int(row["col"])] = float(
                row["weighted_geometric_mean"]
            )
    layers = {
        "solar": (solar, valid, "solar"),
        "earth": (earth, valid, "earth"),
        "slope": (np.clip(slope / 25.0, 0.0, 1.0), terrain_valid, "slope"),
        "score": (score, np.isfinite(score), "score"),
    }
    for name, (values, mask, palette) in layers.items():
        image = Image.fromarray(_rgba(np.nan_to_num(values), mask, palette), "RGBA")
        image.save(asset_dir / f"polar_{name}.png", optimize=True)


def main() -> None:
    payload = build_payload(PROCESSED_DIR)
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    build_map_assets(PROCESSED_DIR, WEB_DIR / "assets")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    (WEB_DIR / "data.js").write_text(
        "/* Generated by scripts/build_polar_dashboard.py. */\n"
        f"window.LUNARIA_POLAR_DATA = {serialized};\n",
        encoding="utf-8",
    )
    print(
        f"Wrote polar dashboard: {len(payload['regions'])} regions, "
        f"{len(payload['timestamps'])} timestamps, "
        f"{payload['meta']['refined_cell_count']} refined cells, "
        f"{len(payload['artifacts'])} artifacts"
    )


if __name__ == "__main__":
    main()
