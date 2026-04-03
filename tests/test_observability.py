import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils import observability


class ObservabilityTest(unittest.TestCase):
    def test_update_job_status_preserves_existing_ops_fields(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            old_ops = observability.OPS_STATUS_FILE
            old_runtime = observability.RUNTIME_METRICS_FILE
            observability.OPS_STATUS_FILE = tmp_root / "ops_status.json"
            observability.RUNTIME_METRICS_FILE = tmp_root / "runtime_metrics.jsonl"
            try:
                observability.update_ops_status(status="running", scheduler="running")
                observability.update_job_status("lesson_reminder", "ok", sent=2, checked=3)

                payload = observability.load_ops_status()
                self.assertEqual(payload["status"], "running")
                self.assertEqual(payload["scheduler"], "running")
                self.assertEqual(payload["jobs"]["lesson_reminder"]["status"], "ok")
                self.assertEqual(payload["jobs"]["lesson_reminder"]["sent"], 2)
                self.assertEqual(payload["jobs"]["lesson_reminder"]["checked"], 3)
            finally:
                observability.OPS_STATUS_FILE = old_ops
                observability.RUNTIME_METRICS_FILE = old_runtime


if __name__ == "__main__":
    unittest.main()
