import math
import unittest

import numpy as np

from scripts.refine_polar_regions import fine_horizon_for_observers


class PolarRegionRefinementTests(unittest.TestCase):
    def test_fine_horizon_preserves_a_nearby_ridge_before_region_summary(self):
        elevation = np.zeros((9, 9), dtype=np.float32)
        elevation[4, 5] = 100.0  # one 100 m pixel east of the observer

        horizon = fine_horizon_for_observers(
            elevation,
            np.asarray([4]),
            np.asarray([4]),
            pixel_size_m=100.0,
            bins=4,
            max_km=0.4,
        )

        self.assertGreater(math.degrees(horizon[0, 1]), 44.0)  # east
        self.assertLess(math.degrees(horizon[0, 3]), 1.0)  # west


if __name__ == "__main__":
    unittest.main()
