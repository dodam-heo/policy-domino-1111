"""Official-source outages must not silently consume all source queues."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from unified.engine import OfficialAPI, load, run


class NetworkOutageTests(unittest.TestCase):
    def test_failed_endpoint_opens_circuit_for_this_run(self):
        api = OfficialAPI("test")
        with patch("unified.engine.urlopen", side_effect=URLError("offline")) as request, \
             patch("unified.engine.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "official_api_network_error"):
                api.request("lawSearch.do", "law", page=1)
            self.assertEqual(request.call_count, 3)
            with self.assertRaisesRegex(RuntimeError, "official_api_network_circuit_open"):
                api.request("lawSearch.do", "law", page=2)
            self.assertEqual(request.call_count, 3)

    def test_outage_leaves_pending_windows_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("unified.engine.urlopen", side_effect=URLError("offline")), \
                 patch("unified.engine.time.sleep"):
                result = run(root, OfficialAPI("test"), limit_streams=6,
                             detail_budget=60, today=dt.date(2026, 11, 11))
            ledger = load(root / "collection-state.json", {})
            incomplete = [c for c in ledger["coverage"].values()
                          if c.get("complete") is False]
            self.assertEqual(result["failed_windows"], 1)
            self.assertEqual(len(incomplete), 1)
            self.assertIn("checked_at", incomplete[0])
            self.assertNotIn("reported", incomplete[0])


if __name__ == "__main__":
    unittest.main()
