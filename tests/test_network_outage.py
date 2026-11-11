"""Official-source outages must not silently consume all source queues."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from unified.engine import OfficialAPI, load, run


class NetworkOutageTests(unittest.TestCase):
    def test_failed_endpoint_opens_only_its_source_circuit(self):
        api = OfficialAPI("test")
        with patch("unified.engine.urlopen", side_effect=URLError("offline")) as request, \
             patch("unified.engine.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "official_api_network_error"):
                api.request("lawSearch.do", "law", page=1)
            self.assertEqual(request.call_count, 3)
            self.assertFalse(api.network_unavailable)
            with self.assertRaisesRegex(RuntimeError, "official_api_source_circuit_open"):
                api.request("lawSearch.do", "law", page=2)
            self.assertEqual(request.call_count, 3)
            with self.assertRaisesRegex(RuntimeError, "official_api_network_error"):
                api.request("lawSearch.do", "admrul", page=1)
            self.assertEqual(request.call_count, 6)
            self.assertFalse(api.network_unavailable)
            with self.assertRaisesRegex(RuntimeError, "official_api_network_error"):
                api.request("lawSearch.do", "ordin", page=1)
            self.assertTrue(api.network_unavailable)

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
            self.assertEqual(result["failed_windows"], 2)
            self.assertEqual(len(incomplete), 2)
            self.assertEqual({entry["source"] for entry in incomplete},
                             {"admrul", "law"})
            self.assertTrue(all("checked_at" in entry and "reported" not in entry
                                for entry in incomplete))


if __name__ == "__main__":
    unittest.main()
