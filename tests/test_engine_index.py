import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unified.engine import run, _pending_index_records, relative_path, load


class OfficialStub:
    def __init__(self):
        self.queries = []
    def search(self, source, start, end, edition, kind, query="", search_scope=1):
        self.queries.append((source, edition, kind, query, search_scope))
        # A notice discovered outside the small detail budget cannot disappear.
        doc = {"source": "admrul", "stable_id": "402", "serial": "999",
               "title": "2027년도 시험 정책기준", "published_at": "2026-09-01",
               "effective_date": "2027-01-01"}
        return [doc], {"reported": 1, "collected": 1, "pages": 1, "complete": True}
    def detail(self, rec):
        return ("<법령><조문단위><조문번호>1</조문번호>"
                "<조문내용>공식 변경 본문</조문내용></조문단위></법령>").encode()
    def predecessor(self, rec):
        return None, False


class IncrementalLedgerTest(unittest.TestCase):
    def test_official_version_history_handles_renamed_title(self):
        """Official stable IDs outrank a changed legal notice title."""
        from unified.engine import hash256, ident

        previous = {"source": "admrul", "stable_id": "402", "serial": "998",
                    "title": "이전 명칭 공공기준", "published_at": "2025-08-01",
                    "effective_date": "2026-01-01"}
        latest = {"source": "admrul", "stable_id": "402", "serial": "999",
                  "title": "변경된 명칭 공공기준", "published_at": "2026-09-01",
                  "effective_date": "2027-01-01"}

        class RenamedNoticeStub(OfficialStub):
            def search(self, source, start, end, edition, kind, query="",
                       search_scope=1):
                return [previous, latest], {
                    "reported": 2, "collected": 2, "pages": 1, "complete": True}

            def detail(self, rec):
                value = "120원" if rec["serial"] == "999" else "100원"
                return (("<법령><조문단위><조문번호>1</조문번호>"
                         "<조문내용>지원기준 " + value +
                         "</조문내용></조문단위></법령>").encode())

            def predecessor(self, rec):
                raise AssertionError("Official-ID history should be reused")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run(root, RenamedNoticeStub(), limit_streams=1, detail_budget=2,
                today=dt.date(2026, 11, 11))
            comparison = load(root / "comparisons" /
                              (hash256(ident(latest))[:24] + ".json.gz"), {})
            self.assertEqual(comparison.get("status"), "changed")
            self.assertEqual(comparison.get("relationship"),
                             "same_official_id_revision")
            self.assertEqual(comparison["changes"][0]["before"], "지원기준 100원")
            self.assertEqual(comparison["changes"][0]["after"], "지원기준 120원")

    def test_yearless_annual_notice_uses_exact_issuer_and_effective_year(self):
        """New IDs are comparable only with a unique official annual predecessor."""
        from unified.engine import hash256, ident
        earlier = {"source": "admrul", "stable_id": "old-id", "serial": "301",
                   "title": "생활지원금 기준표", "kind": "고시",
                   "ministry": "공식 부처", "published_at": "2025-10-10",
                   "effective_date": "2026-01-01"}
        later = {"source": "admrul", "stable_id": "new-id", "serial": "302",
                 "title": "생활지원금 기준표", "kind": "고시",
                 "ministry": "공식 부처", "published_at": "2026-10-10",
                 "effective_date": "2027-01-01"}

        class AnnualStub(OfficialStub):
            def search(self, source, start, end, edition, kind, query="",
                       search_scope=1):
                return [earlier, later], {"reported": 2, "collected": 2,
                                         "pages": 1, "complete": True}

            def detail(self, rec):
                amt = "120원" if rec["stable_id"] == "new-id" else "100원"
                return (("<법령><조문단위><조문번호>1</조문번호>"
                         "<조문내용>선정 기준 " + amt +
                         "</조문내용></조문단위></법령>").encode())

            def predecessor(self, rec):
                raise AssertionError("Already indexed annual history must be used")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run(root, AnnualStub(), limit_streams=1, detail_budget=1,
                today=dt.date(2026, 11, 11))
            compared = load(root / "comparisons" /
                            (hash256(ident(later))[:24] + ".json.gz"), {})
            self.assertEqual(compared.get("status"), "changed")
            self.assertEqual(compared.get("relationship"), "annual_successor")
            self.assertEqual(compared["prior_record"]["stable_id"], "old-id")

    def test_discovered_versions_survive_zero_detail_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api = OfficialStub()
            run(root, api, limit_streams=1, detail_budget=0,
                today=dt.date(2026, 11, 11))
            pending = _pending_index_records(root)
            self.assertEqual(len(pending), 1)
            self.assertTrue(any(item[3] == "2027" for item in api.queries))
            self.assertTrue(any(item[3] == "2027" and item[4] == 2
                                and item[2] == "" for item in api.queries))
            self.assertFalse((root / relative_path(pending[0])).exists())
            run(root, api, limit_streams=1, detail_budget=1,
                today=dt.date(2026, 11, 11))
            self.assertEqual(load(root / relative_path(pending[0]))["body"]["status"],
                             "complete")
            self.assertEqual(len(_pending_index_records(root)), 1)


if __name__ == "__main__":
    unittest.main()
