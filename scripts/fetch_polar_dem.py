#!/usr/bin/env python3
"""Download the NASA Moon Trek south-polar LOLA DEM as a local GeoTIFF."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.windows import Window

try:
    from .common import RAW_DIR, TREK_BASE, ensure_dirs, http_get, log, utc_now
except ImportError:
    from common import RAW_DIR, TREK_BASE, ensure_dirs, http_get, log, utc_now

SERVICE = "LRO_LOLA_DEM_SPole75_30mp_v04"
EXPORT_URL = f"{TREK_BASE}/{SERVICE}/ImageServer/exportImage"
DEFAULT_SIZE = 4096
DEFAULT_HALF_WIDTH_M = 304_000


def export_params(size: int, bbox: tuple[int, int, int, int]) -> dict[str, str]:
    if size <= 0:
        raise ValueError("size must be positive")
    xmin, ymin, xmax, ymax = bbox
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("bbox must have positive width and height")
    return {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "size": f"{size},{size}",
        "format": "tiff",
        "pixelType": "F32",
        "f": "image",
    }


def fetch_dem(
    output: Path,
    *,
    size: int,
    half_width_m: int,
    tile_size: int = 512,
    force: bool = False,
) -> Path:
    if output.exists() and not force:
        raise FileExistsError(f"{output} already exists; pass --force to replace it")
    if size <= 0 or tile_size <= 0 or size % tile_size:
        raise ValueError("size must be a positive multiple of tile_size")
    if half_width_m <= 0:
        raise ValueError("half_width_m must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"{partial} already exists; inspect it before removing")

    pixel_size = 2 * half_width_m / size
    profile = None
    try:
        with rasterio.open(partial, "w", driver="GTiff", width=size, height=size,
                           count=1, dtype="float32", tiled=True, compress="deflate",
                           predictor=3, blockxsize=256, blockysize=256,
                           transform=from_bounds(
                               -half_width_m, -half_width_m, half_width_m,
                               half_width_m, size, size
                           )) as target:
            for row in range(0, size, tile_size):
                for col in range(0, size, tile_size):
                    xmin = round(-half_width_m + col * pixel_size)
                    xmax = round(xmin + tile_size * pixel_size)
                    ymax = round(half_width_m - row * pixel_size)
                    ymin = round(ymax - tile_size * pixel_size)
                    bbox = (xmin, ymin, xmax, ymax)
                    payload = http_get(
                        EXPORT_URL,
                        export_params(tile_size, bbox),
                        timeout=120,
                    )
                    with MemoryFile(payload) as memory_file:
                        with memory_file.open() as tile:
                            if (
                                tile.count != 1
                                or tile.width != tile_size
                                or tile.height != tile_size
                            ):
                                raise RuntimeError(
                                    "NASA DEM export returned an unexpected raster shape "
                                    f"({tile.count} bands, {tile.width}x{tile.height})"
                                )
                            if tile.crs is None or tile.crs.is_geographic:
                                raise RuntimeError(
                                    "NASA DEM export lacks a projected lunar CRS"
                                )
                            if profile is None:
                                profile = tile.profile
                                target.crs = tile.crs
                            elif tile.crs != profile["crs"]:
                                raise RuntimeError("NASA DEM tiles use inconsistent CRSs")
                            target.write(
                                tile.read(1),
                                1,
                                window=Window(col, row, tile_size, tile_size),
                            )
                    log(
                        f"Fetched tile at row {row}, column {col} "
                        f"({size * size // tile_size // tile_size} tiles total)"
                    )
            target.set_band_description(1, "LOLA elevation (m)")
            target.update_tags(
                source=f"{TREK_BASE}/{SERVICE}/ImageServer",
                fetched_at=utc_now(),
                source_native_pixel_size_m="30",
                export_bbox_m=f"{-half_width_m},{-half_width_m},{half_width_m},{half_width_m}",
                export_resolution_m=f"{pixel_size:.3f}",
                caveat="Server-resampled export; not a native LOLA product at this resolution.",
            )
        if not force:
            os.link(partial, output)
            partial.unlink()
        else:
            os.replace(partial, output)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    log(f"Saved south-polar DEM to {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=RAW_DIR / "rasters" / "south_pole_lola_dem_4096.tif",
    )
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--half-width-m", type=int, default=DEFAULT_HALF_WIDTH_M)
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    ensure_dirs()
    fetch_dem(
        args.output,
        size=args.size,
        half_width_m=args.half_width_m,
        tile_size=args.tile_size,
        force=args.force,
    )


if __name__ == "__main__":
    main()
