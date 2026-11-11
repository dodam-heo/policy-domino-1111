import unittest

from unified.impact_scoring import evaluate, change_substance


def table_change(old="1,282,119", new="1,368,021"):
    return {"clause": "표 1 · 금액 (원/월) · 1인가구",
            "before": old, "after": new,
            "focus": [{"before": {"changed": old}, "after": {"changed": new}}]}


def action(id="p1", agency="공공기관"):
    return {"agency": agency, "service": "공공급여",
            "service_id": id, "status": "review_of_verified_citation",
            "evidence": {"reference_quote": "「국민기초법」 제6조",
                         "service_quote": "선정기준 지급액"}}


class ImpactScoreTests(unittest.TestCase):
    def test_national_income_table_75_even_when_downstream_unknown(self):
        doc = {"source": "admrul",
               "title": "2027년 기준 중위소득 및 생계·의료급여의 선정기준",
               "url": "https://www.law.go.kr/"}
        scored = evaluate(doc, {"status": "partial_unverified",
                                "changes": [table_change()]}, [], [])
        self.assertEqual(scored["classification"], "high")
        self.assertEqual(scored["score_min"], 75)
        self.assertEqual(scored["axes"]["substance"]["score"], 40)
        self.assertEqual(scored["axes"]["scope"]["score"], 35)
        self.assertIsNone(scored["axes"]["ripple"]["score"])
        self.assertEqual(scored["score_max"], 100)
        self.assertFalse(scored["score_complete"])
        self.assertEqual(scored["featured_change_indices"], [0])

    def test_national_procedure_with_one_official_link_is_70(self):
        change = {"clause": "제5조", "before": "신청기한은 10일",
                  "after": "신청기한은 20일",
                  "focus": [{"before": {"prefix": "신청기한은 ", "changed": "10", "suffix": "일"},
                             "after": {"prefix": "신청기한은 ", "changed": "20", "suffix": "일"}}]}
        doc = {"source": "admrul", "title": "민원신청 절차 규정"}
        result = evaluate(doc, {"status": "changed", "changes": [change]}, [action()], [])
        self.assertEqual(result["classification"], "high")
        self.assertEqual(result["score"], 70)
        self.assertEqual(result["axes"]["substance"]["score"], 30)
        self.assertEqual(result["axes"]["scope"]["score"], 25)
        self.assertEqual(result["axes"]["ripple"]["score"], 15)

    def test_organizational_change_never_high_even_with_three_agencies(self):
        change = {"clause": "제3조",
                  "before": "총무과의 소관업무를 행정지원부에서 담당한다.",
                  "after": "총무과의 소관업무를 운영지원과에서 담당한다.",
                  "focus": [{"before": {"prefix": "소관업무를 ", "changed": "행정지원부"},
                             "after": {"prefix": "소관업무를 ", "changed": "운영지원과"}}]}
        doc = {"source": "admrul", "title": "공공기관 사무분장 규정"}
        result = evaluate(doc, {"status": "changed", "changes": [change]},
                          [action("a", "기관가"), action("b", "기관나"),
                           action("c", "기관다")], [])
        self.assertEqual(result["classification"], "normal")
        self.assertEqual(result["axes"]["substance"]["score"], 20)
        self.assertEqual(result["axes"]["ripple"]["score"], 25)

    def test_partial_unspecified_change_remains_pending(self):
        result = evaluate({"source": "admrul", "title": "공공지원 규정"},
                          {"status": "partial_unverified",
                           "changes": [{"clause": "제1조",
                                        "before": "신청을 허용한다.",
                                        "after": "신청을 제한한다."}]}, [], [])
        self.assertEqual(result["classification"], "pending")
        self.assertIsNone(result["axes"]["substance"]["score"])
        self.assertIsNone(result["axes"]["ripple"]["score"])

    def test_dates_and_law_name_corrections_do_not_promote_money(self):
        doc = {"source": "ordin", "title": "서울특별시 복지급여 지원 조례"}
        change = {"clause": "제2조",
                  "before": "「대한민국재향경우회법」에 따른 지원 2025. 2. 11.",
                  "after": "「대한민국재향경찰회법」에 따른 지원 2026. 2. 11.",
                  "focus": [{"before": {"changed": "대한민국재향경우회법"},
                             "after": {"changed": "대한민국재향경찰회법"}}]}
        result = evaluate(doc, {"status": "changed", "changes": [change]}, [], [])
        self.assertNotEqual(result["classification"], "high")
        self.assertNotEqual(result["axes"]["substance"]["score"], 40)

    def test_two_verified_distinct_paths_are_25_not_agency_count(self):
        doc = {"source": "admrul", "title": "2027년 주거급여 선정기준 및 최저보장수준"}
        result = evaluate(doc, {"status": "changed", "changes": [table_change()]},
                          [action("svc1"), action("svc2")], [])
        self.assertEqual(result["axes"]["ripple"]["score"], 25)
        self.assertEqual(result["score"], 100)

    def test_unverified_agencies_do_not_increase_ripple(self):
        doc = {"source": "admrul", "title": "2027년 교육급여 선정기준 및 최저보장수준"}
        result = evaluate(doc, {"status": "changed", "changes": [table_change()]},
                          [{**action(), "status": "review_of_named_standard"}] * 4, [])
        self.assertIsNone(result["axes"]["ripple"]["score"])

    def test_explicit_rule_citation_only_8_and_missing_is_unknown(self):
        doc = {"source": "law", "title": "국민서비스법"}
        comparison = {"status": "changed", "changes": [{
            "clause": "제4조", "before": "심사 절차는 서면으로 한다.",
            "after": "심사 절차는 전자문서로 한다.",
            "focus": [{"before": {"prefix": "심사 절차는 ", "changed": "서면으로"},
                        "after": {"prefix": "심사 절차는 ", "changed": "전자문서로"}}]}]}
        rule = {"source": "admrul", "stable_id": "r1", "serial": "1",
                "article": "제3조", "status": "citation_dependency_review",
                "reference_quote": "국민서비스법 제4조 인용"}
        result = evaluate(doc, comparison, [], [rule])
        self.assertEqual(result["axes"]["ripple"]["score"], 8)
        self.assertEqual(result["axes"]["substance"]["score"], 30)

    def test_missing_raw_comparison_is_pending_not_zero(self):
        result = evaluate({"source": "admrul", "title": "2027년 교육급여 선정기준 및 최저보장수준"},
                          {}, [], [])
        self.assertEqual(result["classification"], "pending")
        self.assertIsNone(result["axes"]["substance"]["score"])
        self.assertIsNone(result["axes"]["ripple"]["score"])

    def test_confirmed_no_change_is_not_high(self):
        result = evaluate({"source": "law", "title": "국민서비스법"},
                          {"status": "no_text_change"}, [], [])
        self.assertEqual(result["classification"], "normal")
        self.assertEqual(result["axes"]["substance"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
