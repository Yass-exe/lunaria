import unittest

from scripts.fetch_polar_dem import export_params


class PolarDemExportTests(unittest.TestCase):
    def test_export_requests_float_tiff_in_square_moon2000_extent(self):
        self.assertEqual(
            export_params(size=4096, bbox=(-304_000, -304_000, 304_000, 304_000)),
            {
                "bbox": "-304000,-304000,304000,304000",
                "size": "4096,4096",
                "format": "tiff",
                "pixelType": "F32",
                "f": "image",
            },
        )

    def test_export_rejects_nonpositive_dimensions(self):
        with self.assertRaises(ValueError):
            export_params(size=0, bbox=(-1, -1, 1, 1))


if __name__ == "__main__":
    unittest.main()
