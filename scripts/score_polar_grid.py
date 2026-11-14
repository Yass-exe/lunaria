#!/usr/bin/env python3
"""Score measured south-polar cells and rank contiguous high-suitability regions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

try:
    from .common import CONFIG_DIR, PROCESSED_DIR, read_csv, read_json, write_csv, write_json
    from .polar_model import (
        DEFAULT_WEIGHTS,
        SCORE_DIMENSIONS,
        ScoringPolicy,
        cluster_cells,
        combine_scores,
        dirichlet_sensitivity,
        load_scoring_policy,
        rank_agreement,
        score_candidate,
    )
except ImportError:
    from common import CONFIG_DIR, PROCESSED_DIR, read_csv, read_json, write_csv, write_json
    from polar_model import (
        DEFAULT_WEIGHTS,
        SCORE_DIMENSIONS,
        ScoringPolicy,
        cluster_cells,
        combine_scores,
        dirichlet_sensitivity,
        load_scoring_policy,
        rank_agreement,
        score_candidate,
    )

INPUT_FIELDS = {
    "candidate_id",
    "row",
    "col",
    "solar_illumination_fraction",
    "earth_visibility_fraction",
    "regional_slope_p90_deg",
    "psr_edge_km",
    "science_proxy",
    "thermal_proxy",
}
OPTIONAL_FLOAT_FIELDS = {
    "lat_deg",
    "lon_deg",
    "longest_dark_days",
    "sunlight_continuity_fraction",
    "pinpoint_slope_p90_deg",
    "data_coverage_fraction",
}
INDICATOR_DIMENSIONS = {
    "solar_power": "solar_power",
    "earth_visibility": "earth_visibility",
    "terrain_safety": "terrain_safety",
    "isru_access": "isru_access_proxy",
    "science_value": "science_proxy",
    "thermal_stability": "thermal_proxy",
}
LUNAR_RADIUS_M = 1_737_400.0
GRID_XMIN_M = -304_000.0
GRID_YMAX_M = 304_000.0
GRID_CELL_M = 1_000.0
SCORE_FIELDS = [
    "candidate_id",
    "row",
    "col",
    "lat_deg",
    "lon_deg",
    "solar_power",
    "earth_visibility",
    "terrain_safety",
    "isru_access_proxy",
    "science_proxy",
    "thermal_proxy",
    "crew_safety",
    "data_maturity",
    "weighted_sum",
    "weighted_geometric_mean",
    "hard_failures",
    "disqualified",
]
REGION_FIELDS = [
    "rank",
    "region_id",
    "cell_count",
    "best_cell_id",
    "best_cell_lat_deg",
    "best_cell_lon_deg",
    "best_cell_weighted_geometric_mean",
    "weighted_sum",
    "weighted_geometric_mean",
    *SCORE_DIMENSIONS,
    "data_maturity",
    "member_cell_ids",
]


def _number(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def _read_metrics(path: Path) -> list[dict]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(
            f"{path} has headers but no measured rows; no polar ranking can be computed"
        )
    missing = INPUT_FIELDS - set(rows[0])
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")

    parsed = []
    seen = set()
    for line_number, row in enumerate(rows, start=2):
        candidate_id = row["candidate_id"].strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError(f"{path}:{line_number} has a missing or duplicate candidate_id")
        seen.add(candidate_id)
        candidate = {key: value for key, value in row.items()}
        candidate["candidate_id"] = candidate_id
        try:
            candidate["row"] = int(row["row"])
            candidate["col"] = int(row["col"])
            for key in OPTIONAL_FLOAT_FIELDS | (INPUT_FIELDS - {"candidate_id", "row", "col"}):
                candidate[key] = _number(row.get(key))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{path}:{line_number} contains an invalid numeric value") from error
        parsed.append(candidate)
    return parsed


def _score_rows(
    rows: list[dict],
    *,
    weights: dict[str, float],
    policy: ScoringPolicy,
    slope_limit: float,
    solar_cutoff: float,
) -> list[dict]:
    scored = []
    for candidate in rows:
        result = score_candidate(
            candidate,
            weights,
            policy=policy,
            slope_limit=slope_limit,
            solar_cutoff=solar_cutoff,
        )
        dimensions = {
            key: float(result["indicators"][indicator])
            for key, indicator in INDICATOR_DIMENSIONS.items()
        }
        scored.append(
            {
                **candidate,
                **result["indicators"],
                "weighted_sum": result["weighted_sum"],
                "weighted_geometric_mean": result["weighted_geometric_mean"],
                "hard_failures": ";".join(result["hard_failures"]),
                "disqualified": result["disqualified"],
                "dimensions": dimensions,
            }
        )
    return scored


def _rank_regions(
    scored: list[dict],
    *,
    weights: dict[str, float],
    connectivity: int,
    min_cell_score: float,
    min_cells: int,
    geometric_floor: float,
) -> tuple[list[dict], list[dict], dict]:
    eligible = [
        {**row, "score": row["weighted_geometric_mean"]}
        for row in scored
        if not row["disqualified"]
        and row["weighted_geometric_mean"] >= min_cell_score
    ]
    clusters = cluster_cells(eligible, connectivity=connectivity)
    regions = []
    for cluster in clusters:
        if len(cluster) < min_cells:
            continue
        dimensions = {
            key: statistics.median(cell["dimensions"][key] for cell in cluster)
            for key in SCORE_DIMENSIONS
        }
        combined = combine_scores(
            dimensions, weights, geometric_floor=geometric_floor
        )
        best_cell = max(
            cluster,
            key=lambda cell: (
                cell["weighted_geometric_mean"],
                cell["weighted_sum"],
                cell["candidate_id"],
            ),
        )
        regions.append(
            {
                "cell_count": len(cluster),
                "best_cell_id": best_cell["candidate_id"],
                "best_cell_lat_deg": best_cell.get("lat_deg"),
                "best_cell_lon_deg": best_cell.get("lon_deg"),
                "best_cell_weighted_geometric_mean": best_cell[
                    "weighted_geometric_mean"
                ],
                "weighted_sum": combined["weighted_sum"],
                "weighted_geometric_mean": combined["weighted_geometric_mean"],
                "data_maturity": statistics.median(
                    cell["data_maturity"]
                    for cell in cluster
                    if cell["data_maturity"] is not None
                )
                if any(cell["data_maturity"] is not None for cell in cluster)
                else None,
                "member_cell_ids": ";".join(
                    sorted(cell["candidate_id"] for cell in cluster)
                ),
                "anchor_row": min(int(cell["row"]) for cell in cluster),
                "anchor_col": min(int(cell["col"]) for cell in cluster),
                "dimensions": dimensions,
                "disqualified": False,
            }
        )
    regions.sort(
        key=lambda region: (
            -region["weighted_geometric_mean"],
            -region["weighted_sum"],
            region["best_cell_id"],
        )
    )
    for rank, region in enumerate(regions, start=1):
        region["rank"] = rank
        region["region_id"] = (
            f"polar-region-r{region['anchor_row']:03d}-c{region['anchor_col']:03d}"
        )
        region["candidate_id"] = region["region_id"]
        region.update(region["dimensions"])
    sum_ranking = sorted(
        regions, key=lambda region: (-region["weighted_sum"], region["region_id"])
    )
    geometric_ranking = sorted(
        regions,
        key=lambda region: (
            -region["weighted_geometric_mean"],
            region["region_id"],
        ),
    )
    agreement = (
        rank_agreement(
            [region["region_id"] for region in sum_ranking],
            [region["region_id"] for region in geometric_ranking],
        )
        if regions
        else None
    )
    return regions, sum_ranking, agreement


def _lon_lat(x_m: float, y_m: float) -> list[float]:
    radius = math.hypot(x_m, y_m)
    latitude = -(90.0 - math.degrees(2.0 * math.atan(radius / (2.0 * LUNAR_RADIUS_M))))
    longitude = math.degrees(math.atan2(x_m, y_m))
    return [longitude, latitude]


def _cell_polygon(row: int, col: int) -> list[list[float]]:
    x0 = GRID_XMIN_M + col * GRID_CELL_M
    x1 = x0 + GRID_CELL_M
    y1 = GRID_YMAX_M - row * GRID_CELL_M
    y0 = y1 - GRID_CELL_M
    return [
        _lon_lat(x0, y1),
        _lon_lat(x1, y1),
        _lon_lat(x1, y0),
        _lon_lat(x0, y0),
        _lon_lat(x0, y1),
    ]


def _write_regions_geojson(path: Path, regions: list[dict], scored: list[dict]) -> None:
    by_id = {row["candidate_id"]: row for row in scored}
    features = []
    for region in regions:
        members = [
            by_id[candidate_id]
            for candidate_id in region["member_cell_ids"].split(";")
        ]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "region_id": region["region_id"],
                    "rank": region["rank"],
                    "cell_count": region["cell_count"],
                    "best_cell_id": region["best_cell_id"],
                    "weighted_sum": region["weighted_sum"],
                    "weighted_geometric_mean": region["weighted_geometric_mean"],
                    **region["dimensions"],
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[_point for _point in _cell_polygon(int(cell["row"]), int(cell["col"]))]]
                        for cell in members
                    ],
                },
            }
        )
    write_json(path, {"type": "FeatureCollection", "features": features})


def run(
    input_path: Path,
    output_dir: Path,
    *,
    weights: dict[str, float] | None = None,
    draws: int | None = None,
) -> dict:
    config = read_json(CONFIG_DIR / "polar_scoring.json")
    policy_path = CONFIG_DIR / "polar_scoring.json"
    policy = load_scoring_policy(policy_path)
    scoring = config["scoring"]
    weights = (
        policy.weights if weights is None else weights
    )
    rows = _read_metrics(input_path)
    scored = _score_rows(
        rows,
        weights=weights,
        policy=policy,
        slope_limit=policy.slope_limit,
        solar_cutoff=policy.solar_cutoff,
    )
    regions, _, agreement = _rank_regions(
        scored,
        weights=weights,
        connectivity=scoring["cluster_connectivity"],
        min_cell_score=scoring["cluster_cell_score_min"],
        min_cells=scoring["cluster_min_cells"],
        geometric_floor=policy.geometric_floor,
    )
    sensitivity = dirichlet_sensitivity(
        regions,
        draws=scoring["sensitivity_draws"] if draws is None else draws,
        seed=scoring["random_seed"],
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "polar_cell_scores.csv",
        [{key: row.get(key) for key in SCORE_FIELDS} for row in scored],
        SCORE_FIELDS,
    )
    write_csv(
        output_dir / "polar_region_ranking.csv",
        [{key: region.get(key) for key in REGION_FIELDS} for region in regions],
        REGION_FIELDS,
    )
    write_csv(
        output_dir / "polar_sensitivity.csv",
        sensitivity,
        ["candidate_id", "top1_probability", "draws", "method", "seed"],
    )
    _write_regions_geojson(
        output_dir / "polar_candidate_regions.geojson", regions, scored
    )
    recommendation = {
        "status": "ranked" if regions else "no_eligible_regions",
        "winner": regions[0]["region_id"] if regions else None,
        "candidate_cell_id": regions[0]["best_cell_id"] if regions else None,
        "weights": weights,
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "rank_agreement": agreement,
        "region_count": len(regions),
        "input_cell_count": len(scored),
        "sensitivity_draws": scoring["sensitivity_draws"] if draws is None else draws,
        "caveat": (
            "Screening only; region polygons, pinpoint hazard certification, and "
            "source-data coverage must be verified before mission decisions."
        ),
    }
    write_json(output_dir / "polar_recommendation.json", recommendation)
    return recommendation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=PROCESSED_DIR / "polar_cell_metrics.csv"
    )
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--weights", type=Path, help="JSON file containing six criterion weights")
    parser.add_argument("--draws", type=int)
    args = parser.parse_args()
    weights = read_json(args.weights) if args.weights else None
    try:
        result = run(args.input, args.output_dir, weights=weights, draws=args.draws)
    except (ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
