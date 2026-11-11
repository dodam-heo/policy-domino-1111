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



    def test_priority_ignores_unrelated_fee_word_in_long_organization_rule(self):
        from unified.publish import review_priority
        doc = {"title": "금천구 행정기구 설치 조례 시행규칙"}
        old = "수수료 담당부서 지정. " * 30 + "직원 정원 12명"
        new = "수수료 담당부서 지정. " * 30 + "직원 정원 13명"
        comparison = {"status": "changed", "changes": [{
            "clause": "제3조", "before": old, "after": new,
            "focus": [{"before": {"prefix": "직원 정원 ", "changed": "12", "suffix": "명"},
                       "after": {"prefix": "직원 정원 ", "changed": "13", "suffix": "명"}}]}]}
        self.assertEqual(review_priority(doc, comparison, []), [])

    def test_priority_detects_fee_change_near_changed_number(self):
        from unified.publish import review_priority
        doc = {"title": "재정 운영 규정"}
        comparison = {"status": "changed", "changes": [{
            "clause": "제3조", "before": "접수 수수료 100원", "after": "접수 수수료 120원",
            "focus": [{"before": {"prefix": "접수 수수료 ", "changed": "100원"},
                       "after": {"prefix": "접수 수수료 ", "changed": "120원"}}]}]}
        self.assertEqual(review_priority(doc, comparison, []),
                         ["요율·수수료·부담금 변경"])


    def test_no_false_priority_from_revision_dates_or_article_renumbering(self):
        from unified.publish import review_priority
        old = "예방접종 지원대상자는 다음과 같다. <개정 2025. 12. 26.>"
        new = "예방접종 지원대상자는 다음과 같다. <개정 2025. 12. 26., 2026. 11. 6.>"
        comparison = {"status": "changed", "changes": [{
            "clause": "제4조", "before": old, "after": new,
            "focus": [{"before":{"changed":"26."}, "after":{"changed":"26., 2026. 11. 6."},
                       "before_context":"지원대상"}]}]}
        self.assertEqual(review_priority({"title":"예방접종 지원 조례"},comparison,[]),[])
        doc = {"title":"행정기구 설치 시행규칙"}
        comparison = {"status":"changed","changes":[{
            "clause":"제11조","before":"제2호 민원여권과","after":"제3호 민원여권과",
            "focus":[{"before":{"prefix":"제", "changed":"2","suffix":"호 민원여권과"},
                      "after":{"prefix":"제", "changed":"3","suffix":"호 민원여권과"}}]}]}
        self.assertEqual(review_priority(doc,comparison,[]),[])

    def test_support_amount_near_numeric_change_is_high_priority(self):
        from unified.publish import review_priority
        old = "지원액 : 월 10만원"
        new = "지원액 : 월 20만원"
        changes = [{"clause":"제6조", "before":old, "after":new,
                    "focus":[{"before":{"prefix":"지원액 : 월 ","changed":"10","suffix":"만원"},
                              "after":{"prefix":"지원액 : 월 ","changed":"20","suffix":"만원"}}]}]
        result = review_priority({"title":"보훈 지원 조례"},
                                 {"status":"changed","changes":changes},[])
        self.assertEqual(result,["급여·지원금·소득 기준 변경"])


if __name__ == "__main__":
    unittest.main()
