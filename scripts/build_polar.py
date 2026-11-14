#!/usr/bin/env python3
"""Run the complete cached south-polar pipeline and package reusable outputs."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .common import INTERIM_DIR, PROCESSED_DIR, utc_now, write_json
except ImportError:
    from common import INTERIM_DIR, PROCESSED_DIR, utc_now, write_json

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_metrics(source: Path, target: Path) -> dict:
    """Write a deterministic gzip copy of measured cell metrics."""
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    with source.open("rb") as source_handle, partial.open("wb") as raw_target:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_target, compresslevel=9, mtime=0
        ) as compressed:
            shutil.copyfileobj(source_handle, compressed, length=1024 * 1024)
    os.replace(partial, target)
    with source.open("rb") as handle:
        rows = max(0, sum(1 for _ in handle) - 1)
    return {
        "path": str(target),
        "rows": rows,
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "compression": "gzip-9; mtime=0; no embedded filename",
    }


def _run(script: str, *arguments: str) -> None:
    command = [sys.executable, "-B", str(ROOT / "scripts" / script), *arguments]
    print("+", " ".join(command), flush=True)
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def write_data_manifest(packaged_metrics: dict) -> dict:
    paths = [
        INTERIM_DIR / "polar_ephemeris.csv",
        PROCESSED_DIR / "polar_cell_metrics.csv.gz",
        PROCESSED_DIR / "polar_terrain_1km.tif",
        PROCESSED_DIR / "polar_illumination_1km.tif",
        PROCESSED_DIR / "polar_region_ranking.csv",
        PROCESSED_DIR / "polar_candidate_regions.geojson",
        PROCESSED_DIR / "polar_refined_region_ranking.csv",
        PROCESSED_DIR / "polar_refined_cells.csv",
        PROCESSED_DIR / "polar_candidate_timeseries.csv",
        PROCESSED_DIR / "polar_data_gaps.csv",
        PROCESSED_DIR / "polar_sensitivity.csv",
        PROCESSED_DIR / "polar_recommendation.json",
        PROCESSED_DIR / "polar_benchmark.json",
        PROCESSED_DIR / "polar_terrain_manifest.json",
        PROCESSED_DIR / "polar_illumination_manifest.json",
    ]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing packaged outputs: " + ", ".join(missing))
    manifest = {
        "generated_at": utc_now(),
        "pipeline": "two-stage south-polar screen",
        "metrics_package": {
            **packaged_metrics,
            "path": str(Path(packaged_metrics["path"]).relative_to(ROOT)),
        },
        "files": [
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in paths
        ],
    }
    write_json(PROCESSED_DIR / "polar_data_manifest.json", manifest)
    return manifest


def run(*, skip_illumination: bool = False, skip_benchmark: bool = False) -> dict:
    required = [
        ROOT / "data/raw/rasters/south_pole_lola_dem_4096.tif",
        INTERIM_DIR / "polar_ephemeris.csv",
        PROCESSED_DIR / "polar_terrain_1km.tif",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "cached inputs are missing; run fetch_polar_dem.py, "
            "derive_polar_terrain.py, and fetch_polar_ephemeris.py first: "
            + ", ".join(missing)
        )
    if not skip_illumination:
        _run("polar_illumination.py", "--observer", "max", "--force")
    _run("score_polar_grid.py")
    _run("refine_polar_regions.py")
    if not skip_benchmark:
        _run("benchmark_polar.py")
    _run("build_polar_dashboard.py")
    packaged = package_metrics(
        PROCESSED_DIR / "polar_cell_metrics.csv",
        PROCESSED_DIR / "polar_cell_metrics.csv.gz",
    )
    manifest = write_data_manifest(packaged)
    recommendation = json.loads(
        (PROCESSED_DIR / "polar_recommendation.json").read_text(encoding="utf-8")
    )
    result = {
        "status": recommendation["status"],
        "winner": recommendation["winner"],
        "winner_score": recommendation["winner_score"],
        "provisional_seed": recommendation["provisional_seed"],
        "region_count": recommendation["region_count"],
        "manifest_files": len(manifest["files"]),
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-illumination",
        action="store_true",
        help="reuse the existing corrected polar_cell_metrics.csv",
    )
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="skip the live Horizons geometry cross-check",
    )
    args = parser.parse_args()
    run(
        skip_illumination=args.skip_illumination,
        skip_benchmark=args.skip_benchmark,
    )


if __name__ == "__main__":
    main()
