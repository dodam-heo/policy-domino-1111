import hashlib
import tempfile
import unittest
from pathlib import Path

from unified.import_next import merge_state, verified_clauses, _compare_verified
from unified.engine import load, relative_path


def rec(id_, serial, date):
    return {"id": id_, "source": "admrul", "stable_id": "policy-test",
            "serial": serial, "title": "공공 지원기준 고시",
            "published_at": date, "law_type": "고시",
            "url": "https://www.law.go.kr/"}


def clause(text):
    return {"text": text, "complete": True,
            "sha256": hashlib.sha256(text.encode()).hexdigest()}


class ReadOnlyNextImporterTests(unittest.TestCase):
    def state(self):
        old = "선정기준은 100만원으로 한다."
        new = "선정기준은 120만원으로 한다."
        return {"schema": "policy-domino-next-v1",
                "documents": {"a": rec("a", "1", "2025-01-02"),
                              "b": rec("b", "2", "2026-01-02")},
                "versions": {
                    "a": {"status": "extracted", "clauses": {"제1조": clause(old)}},
                    "b": {"status": "extracted", "clauses": {"제1조": clause(new)}},
                },
                "findings": {"b": {
                    "status": "compared", "baseline": {"id": "a"},
                    "changes": [{"article": "제1조", "before": old,
                                 "after": new}]}}}

    def test_merges_without_claiming_full_official_originals(self):
        state = self.state()
        # Real archive is large; this test bypasses the minimum safety size.
        for i in range(60):
            state["documents"][f"extra-{i}"] = rec(
                f"extra-{i}", str(i+100), "2026-01-02")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha = "a" * 40
            first = merge_state(state, root, sha)
            self.assertEqual(first["counts"]["versions_imported"], 2)
            self.assertEqual(first["counts"]["comparisons_imported"], 1)
            record = state["documents"]["b"]
            path = root/relative_path(record)
            saved = load(path)
            self.assertEqual(saved["body"]["status"], "partial")
            self.assertFalse(saved["source_snapshot_provenance"]["has_raw_official_xml"])
            comparison = load(root/"comparisons"/(
                hashlib.sha256("admrul|policy-test|2".encode()).hexdigest()[:24]+".json.gz"))
            self.assertEqual(comparison["status"], "partial_unverified")
            self.assertEqual(comparison["changes"][0]["clause"], "제1조")
            second = merge_state(state, root, sha)
            self.assertEqual(second["counts"].get("versions_imported",0), 0)
            self.assertEqual(second["counts"].get("comparisons_imported",0), 0)

    def test_rejects_unverified_clause_digest_and_mismatched_source(self):
        self.assertEqual(verified_clauses({"status": "extracted",
             "clauses": {"제1조": {"text": "가짜", "complete": True,
                                  "sha256": "a"*64}}}), {})
        old = {"body": {"clauses": {"제1조": "100원"}}}
        new = {"body": {"clauses": {"제1조": "120원"}}}
        self.assertIsNone(_compare_verified({
            "changes": [{"article":"제1조","before":"99원","after":"120원"}]},old,new))


if __name__ == "__main__":
    unittest.main()
