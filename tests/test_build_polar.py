import gzip
import tempfile
import unittest
from pathlib import Path

from scripts.build_polar import package_metrics


class PolarBuildTests(unittest.TestCase):
    def test_package_metrics_is_reusable_and_records_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "metrics.csv"
            target = root / "metrics.csv.gz"
            source.write_text("candidate_id,score\na,0.5\n", encoding="utf-8")

            packaged = package_metrics(source, target)

            with gzip.open(target, "rt", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), source.read_text(encoding="utf-8"))
            self.assertEqual(packaged["rows"], 1)
            self.assertEqual(len(packaged["sha256"]), 64)
            self.assertEqual(packaged["path"], str(target))


if __name__ == "__main__":
    unittest.main()
