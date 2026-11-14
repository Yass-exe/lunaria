import unittest

from scripts.fetch_polar_ephemeris import parse_subpoints


class PolarEphemerisFetchTests(unittest.TestCase):
    def test_parse_subpoints_includes_center_range_for_surface_parallax(self):
        text = """header
$$SOE
 2024-Jan-01 00:00, , ,   0.037465,  -4.685011,  0.00270481348636,  0.0084978,
$$EOE
footer
"""

        rows = parse_subpoints(text)

        self.assertEqual(rows[0]["utc"], "2024-01-01T00:00:00Z")
        self.assertAlmostEqual(rows[0]["range_km"], 404634.3, delta=1.0)


if __name__ == "__main__":
    unittest.main()
