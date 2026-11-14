import unittest

import numpy as np
from rasterio.transform import from_origin

from scripts.derive_polar_terrain import compute_terrain_grid


class PolarTerrainTests(unittest.TestCase):
    def test_slope_is_derived_before_aggregation(self):
        pixel_m = 1.0
        x = np.arange(20, dtype=float) * pixel_m
        elevation = np.tile(x * 0.1, (20, 1))
        center, slope_p90, polar_mask = compute_terrain_grid(
            elevation,
            from_origin(-10, 10, pixel_m, pixel_m),
            cell_size_m=10.0,
        )
        self.assertEqual(center.shape, (2, 2))
        self.assertTrue(polar_mask.all())
        np.testing.assert_allclose(slope_p90, np.degrees(np.arctan(0.1)), atol=1e-4)

    def test_cells_outside_south_polar_extent_remain_masked(self):
        elevation = np.zeros((20, 20), dtype=float)
        _, _, polar_mask = compute_terrain_grid(
            elevation,
            from_origin(-10, 10, 1, 1),
            cell_size_m=10.0,
            latitude_min_deg=-90.0,
            latitude_max_deg=-89.99999,
        )
        self.assertFalse(polar_mask.any())


if __name__ == "__main__":
    unittest.main()
