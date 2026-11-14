import unittest

from scripts.common import PROCESSED_DIR
from scripts.build_polar_dashboard import build_payload


class PolarDashboardTests(unittest.TestCase):
    def test_payload_exposes_fixed_regions_weights_and_date_status(self):
        payload = build_payload(PROCESSED_DIR)

        self.assertEqual(payload["recommendation"]["status"], "ranked")
        self.assertEqual(len(payload["regions"]), 6)
        self.assertEqual(len(payload["weights"]), 6)
        self.assertEqual(len(payload["timestamps"]), 2925)
        self.assertEqual(set(payload["timeline"]), {r["region_id"] for r in payload["regions"]})
        for region in payload["regions"]:
            self.assertEqual(len(region["dimensions"]), 6)
            self.assertEqual(len(payload["timeline"][region["region_id"]]), 2925)


if __name__ == "__main__":
    unittest.main()
