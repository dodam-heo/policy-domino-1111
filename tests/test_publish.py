import json
import tempfile
import unittest
from pathlib import Path
from unified.engine import relative_path, store
from unified.publish import assemble


class PublishTest(unittest.TestCase):
    def test_unverified_agency_not_invented(self):
        doc = {"source": "admrul", "stable_id": "X", "serial": "123",
               "title": "행정규칙", "published_at": "2026-11-01"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store(path / relative_path(doc), {"record": doc, "body": {
                "status": "complete", "clauses": {"제1조": "본문"}}})
            result = assemble(path)
            self.assertEqual(result["total_source_versions_saved"], 1)
            self.assertEqual(result["summary"]["agency_action_count"], 0)
            self.assertEqual(len(result["events"]), 1)


    def test_priority_requires_real_numeric_change_and_verified_comparison(self):
        from unified.publish import review_priority, primary_change_summary
        doc = {"title": "정부 지원금액 및 선정기준"}
        changed = {"status": "changed", "changes": [
            {"clause": "표 1", "before": "지원액 100,000원",
             "after": "지원액 120,000원",
             "focus": [{"before": {"changed": "100,000원"},
                        "after": {"changed": "120,000원"}}]}]}
        reasons = review_priority(doc, changed, [])
        self.assertIn("급여·지원금·소득 기준 변경", reasons)
        self.assertIn("100,000원 → 120,000원",
                      primary_change_summary(changed["changes"]))
        self.assertEqual(review_priority(doc, {
            **changed, "status": "partial_unverified"}, []), [])
        self.assertEqual(review_priority(doc, {
            "status": "changed", "changes": [{
                "clause": "제1조", "before": "지원액 100원",
                "after": "지원액 100원입니다."}]}, []), [])

    def test_priority_does_not_promote_unverified_agency_candidates(self):
        from unified.publish import review_priority
        doc = {"title": "기본 운영 규정"}
        changed = {"status": "changed", "changes": [{
            "clause": "제1조", "before": "종전 문장",
            "after": "새로운 문장"}]}
        candidate = {"status": "review_of_named_standard",
                     "evidence": {"reference_quote": "기준 명칭",
                                  "service_quote": "공식 기준"}}
        self.assertEqual(review_priority(doc, changed, [candidate]), [])
        verified = {**candidate, "status": "review_of_verified_citation"}
        self.assertEqual(review_priority(doc, changed, [verified]),
                         ["공식 사업·기관 업무의 변경 조문 인용 확인"])



if __name__ == "__main__":
    unittest.main()
