#!/usr/bin/env python3
"""Derive 1 km south-polar elevation and local fine-DEM slope summaries."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

try:
    from .common import PROCESSED_DIR, write_json
except ImportError:
    from common import PROCESSED_DIR, write_json

LUNAR_RADIUS_M = 1_737_400.0
NODATA = -9999.0


def compute_terrain_grid(
    elevation: np.ndarray,
    transform,
    *,
    cell_size_m: float = 1000.0,
    latitude_min_deg: float = -90.0,
    latitude_max_deg: float = -80.0,
    nodata: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return 1 km center elevations, local fine-slope p90, and the polar mask."""
    if elevation.ndim != 2 or cell_size_m <= 0:
        raise ValueError("elevation must be 2D and cell_size_m must be positive")
    if not math.isclose(transform.b, 0.0) or not math.isclose(transform.d, 0.0):
        raise ValueError("rotated DEM transforms are not supported")
    pixel_x, pixel_y = transform.a, abs(transform.e)
    if pixel_x <= 0 or pixel_y <= 0 or not math.isclose(pixel_x, pixel_y, rel_tol=1e-6):
        raise ValueError("source DEM must have square, north-up pixels")

    height, width = elevation.shape
    xmin, ymax = transform.c, transform.f
    xmax = xmin + width * pixel_x
    ymin = ymax - height * pixel_y
    cols = int(math.floor((xmax - xmin) / cell_size_m))
    rows = int(math.floor((ymax - ymin) / cell_size_m))
    if cols <= 0 or rows <= 0:
        raise ValueError("source DEM is smaller than the target cell size")
    x_centers = xmin + (np.arange(cols) + 0.5) * cell_size_m
    y_centers = ymax - (np.arange(rows) + 0.5) * cell_size_m
    x_grid, y_grid = np.meshgrid(x_centers, y_centers)
    radius = np.hypot(x_grid, y_grid)
    latitude = -(90.0 - np.degrees(2.0 * np.arctan(radius / (2.0 * LUNAR_RADIUS_M))))
    polar_mask = (latitude >= latitude_min_deg) & (latitude <= latitude_max_deg)

    source_cols = np.floor((x_grid - xmin) / pixel_x).astype(int)
    source_rows = np.floor((ymax - y_grid) / pixel_y).astype(int)
    valid_source = np.isfinite(elevation)
    if nodata is not None:
        valid_source &= elevation != nodata
    source_elevation = np.where(valid_source, elevation, np.nan)
    dy, dx = np.gradient(source_elevation, pixel_y, pixel_x)
    fine_slope = np.degrees(np.arctan(np.hypot(dx, dy)))

    center_elevation = np.full((rows, cols), NODATA, dtype=np.float32)
    slope_p90 = np.full((rows, cols), NODATA, dtype=np.float32)
    valid_positions = np.argwhere(polar_mask)
    window_size = max(3, int(round(cell_size_m / pixel_x)))
    if window_size % 2 == 0:
        window_size += 1
    radius_px = window_size // 2
    padded_elevation = np.pad(source_elevation, radius_px, constant_values=np.nan)
    padded_slope = np.pad(fine_slope, radius_px, constant_values=np.nan)
    source_rows = source_rows + radius_px
    source_cols = source_cols + radius_px

    batch_size = 4096
    for start in range(0, len(valid_positions), batch_size):
        positions = valid_positions[start : start + batch_size]
        out_rows, out_cols = positions[:, 0], positions[:, 1]
        src_rows = source_rows[out_rows, out_cols]
        src_cols = source_cols[out_rows, out_cols]
        center = padded_elevation[src_rows, src_cols]
        samples = np.stack(
            [
                padded_slope[src_rows + dr, src_cols + dc]
                for dr in range(-radius_px, radius_px + 1)
                for dc in range(-radius_px, radius_px + 1)
            ],
            axis=0,
        )
        center_elevation[out_rows, out_cols] = np.where(
            np.isfinite(center), center, NODATA
        )
        with np.errstate(invalid="ignore"):
            values = np.nanpercentile(samples, 90, axis=0)
        slope_p90[out_rows, out_cols] = np.where(np.isfinite(values), values, NODATA)
    return center_elevation, slope_p90, polar_mask


def derive(
    input_path: Path,
    output_path: Path,
    *,
    cell_size_m: float = 1000.0,
    force: bool = False,
) -> dict:
    manifest_path = PROCESSED_DIR / "polar_terrain_manifest.json"
    if not force and (output_path.exists() or manifest_path.exists()):
        raise FileExistsError(
            "polar terrain output or manifest already exists; pass --force to replace"
        )
    partial_path = output_path.with_name(output_path.name + ".partial")
    if partial_path.exists():
        raise FileExistsError(f"{partial_path} already exists; inspect it before removing")
    with rasterio.open(input_path) as source:
        elevation = source.read(1, masked=False)
        source_resolution_m = source.res[0]
        center, slope, polar_mask = compute_terrain_grid(
            elevation,
            source.transform,
            cell_size_m=cell_size_m,
            nodata=source.nodata,
        )
        x_origin, y_origin = source.transform.c, source.transform.f
        target_transform = from_origin(x_origin, y_origin, cell_size_m, cell_size_m)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        profile = {
            "driver": "GTiff",
            "width": center.shape[1],
            "height": center.shape[0],
            "count": 2,
            "dtype": "float32",
            "crs": source.crs,
            "transform": target_transform,
            "nodata": NODATA,
            "compress": "deflate",
            "predictor": 3,
        }
        try:
            with rasterio.open(partial_path, "w", **profile) as output:
                output.write(center, 1)
                output.write(slope, 2)
                output.set_band_description(1, "Cell-center elevation (m)")
                output.set_band_description(2, "Fine-DEM local slope p90 (degrees)")
                output.update_tags(
                    source=str(input_path),
                    source_resolution_m=f"{source_resolution_m:.3f}",
                    target_cell_size_m=str(cell_size_m),
                    slope_note=(
                        "p90 of slope computed on the source DEM within a local "
                        "approximately 1 km window; not a 5 m landing-pad slope."
                    ),
                )
            if force:
                os.replace(partial_path, output_path)
            else:
                os.link(partial_path, output_path)
                partial_path.unlink()
        except Exception:
            if partial_path.exists():
                partial_path.unlink()
            raise
    valid = slope[polar_mask & (slope != NODATA)]
    manifest = {
        "source_dem": str(input_path),
        "output_raster": str(output_path),
        "source_resolution_m": source_resolution_m,
        "target_cell_size_m": cell_size_m,
        "latitude_min_deg": -90.0,
        "latitude_max_deg": -80.0,
        "valid_polar_cells": int(len(valid)),
        "slope_p90_median_deg": float(np.median(valid)) if len(valid) else None,
        "slope_p90_max_deg": float(np.max(valid)) if len(valid) else None,
        "pinpoint_slope_status": "not available from this regional DEM",
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/raw/rasters/south_pole_lola_dem_4096.tif")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/polar_terrain_1km.tif"),
    )
    parser.add_argument("--cell-size-m", type=float, default=1000.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = derive(
        args.input, args.output, cell_size_m=args.cell_size_m, force=args.force
    )
    print(result)


if __name__ == "__main__":
    main()
