import unittest
from unified.actors import direct_actor_leads


class DirectActorEvidenceTests(unittest.TestCase):
    doc = {"title": "공공지원법", "url": "https://www.law.go.kr"}

    def test_exact_actor_in_both_changed_local_contexts(self):
        comparison = {
            "status": "changed",
            "changes": [{"clause": "제12조",
                         "before": "국토교통부장관은 신청기간을 10일로 정한다.",
                         "after": "국토교통부장관은 신청기간을 20일로 정한다.",
                         "focus": [{"before": {"prefix": "국토교통부장관은 신청기간을 ",
                                               "changed": "10",
                                               "suffix": "일로 정한다."},
                                    "after": {"prefix": "국토교통부장관은 신청기간을 ",
                                              "changed": "20",
                                              "suffix": "일로 정한다."}}]}],
        }
        a = direct_actor_leads(self.doc, comparison)
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["actor"], "국토교통부장관")
        self.assertFalse(a[0]["required_action_verified"])
        self.assertFalse(a[0]["operational_program_verified"])

    def test_does_not_infer_actor_from_unrelated_unchanged_section(self):
        old = "국토교통부장관은 다음을 정한다. " + ("기존 업무 내용. " * 60) + "행정절차는 10일이다."
        new = "국토교통부장관은 다음을 정한다. " + ("기존 업무 내용. " * 60) + "행정절차는 20일이다."
        comparison = {
            "status": "partial_unverified",
            "changes": [{"clause": "제12조", "before": old, "after": new,
                         "focus": [{"before": {"prefix": "행정절차는 ", "changed": "10", "suffix": "일이다."},
                                    "after": {"prefix": "행정절차는 ", "changed": "20", "suffix": "일이다."}}]}],
        }
        self.assertEqual(direct_actor_leads(self.doc, comparison), [])

    def test_actor_name_only_changed_and_no_shared_actor_is_excluded(self):
        comparison = {
            "status": "changed",
            "changes": [{"clause": "제3조",
                         "before": "국토교통부장관은 신청한다.",
                         "after": "환경부장관은 신청한다.",
                         "focus": [{"before": {"changed": "국토교통부장관은 신청한다."},
                                    "after": {"changed": "환경부장관은 신청한다."}}]}],
        }
        self.assertEqual(direct_actor_leads(self.doc, comparison), [])


if __name__ == "__main__":
    unittest.main()
