"""Source-complete pagination and public-service evidence regressions."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from unified.engine import run, load
from unified.impact import impact_for


class OverflowSource:
    def search(self, source, start, end, edition, kind, query="", search_scope=1):
        if query:
            return [], {"reported": 0, "collected": 0, "pages": 1, "complete": True}
        days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1
        if days > 45:
            return [], {"reported": 2, "collected": 0, "pages": 20,
                        "complete": False, "error": "pagination_limit"}
        record = {"source": source, "stable_id": "test" + start,
                  "serial": "1", "title": "공식 고시", "published_at": start}
        return [record], {"reported": 1, "collected": 1,
                          "pages": 1, "complete": True}


class CoverageCompletionTests(unittest.TestCase):
    def test_overflow_shards_are_verified_before_backfill_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run(root, OverflowSource(), limit_streams=1, detail_budget=0,
                today=dt.date(2026, 11, 11))
            ledger = load(root / "collection-state.json")
            parent = [c for c in ledger["coverage"].values()
                      if c.get("stage") == "historical"]
            self.assertEqual(len(parent), 1)
            self.assertTrue(parent[0]["complete"])
            self.assertTrue(parent[0]["split_verified"])
            self.assertEqual(parent[0]["reported"], parent[0]["collected"])
            self.assertEqual(ledger["backfill"]["admrul|1|3"], "2026-08-06")

    def test_annual_named_standard_is_candidate_not_verified_citation(self):
        doc = {"source": "admrul",
               "title": "2027년도 생활지원 최저보장수준 및 생활급여 선정기준",
               "url": "https://www.law.go.kr"}
        comparison = {"status": "changed", "changes": [
            {"clause": "표 1", "before": "100,000원", "after": "120,000원"}]}
        program = {"id": "svc01", "agency": "공공기관",
                   "agency_type": "공공기관", "service_name": "공공서비스",
                   "url": "https://www.gov.kr",
                   "basis": {"법령": "별도의 법(제3조)"},
                   "criteria": {"선정기준": "생활지원 최저보장수준을 적용해 심사"}}
        linked = impact_for(doc, comparison, [program])
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["status"], "review_of_named_standard")
        self.assertFalse(linked[0]["evidence"]["numeric_value_in_operating_criteria"])
        program["criteria"]["선정기준"] = "일반 사업만 심사"
        self.assertEqual(impact_for(doc, comparison, [program]), [])


if __name__ == "__main__":
    unittest.main()
