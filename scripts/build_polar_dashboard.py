#!/usr/bin/env python3
"""Build compact static data and map layers for the polar-first dashboard."""

from __future__ import annotations

import csv
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
    return {
        "meta": {
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
            "observer_elevation": illumination_manifest.get(
                "observer_elevation", "max"
            ),
            "source_resolution_m": terrain_manifest["source_resolution_m"],
        },
        "recommendation": recommendation,
        "weights": config["weights"],
        "dimensions": list(SCORE_DIMENSIONS),
        "regions": regions,
        "timestamps": timestamps,
        "timeline": compact_timeline,
        "benchmark": benchmark,
        "artemis_regions": artemis,
        "layers": {
            "score": "assets/polar_score.png",
            "solar": "assets/polar_solar.png",
            "earth": "assets/polar_earth.png",
            "slope": "assets/polar_slope.png",
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
        f"{len(payload['timestamps'])} timestamps"
    )


if __name__ == "__main__":
    main()
