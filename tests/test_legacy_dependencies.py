import tempfile
import unittest
from pathlib import Path
from unified.engine import store
from unified.dependencies import build_index, dependencies_for, program_actions

class LegacyDependencyCandidateTests(unittest.TestCase):
    def test_reused_archive_links_stay_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            doc={"source":"admrul","stable_id":"abc","serial":"123",
                 "title":"신청절차규정","published_at":"2026-01-01"}
            store(root/"documents"/"admrul"/"ab"/"old.json.gz",{
                "record":doc,
                "source_snapshot_provenance":{"generation":"v4"},
                "body":{"status":"partial","clauses":{
                    "제4조":"제4조 「지원법」 제3조에 따라 신청을 처리한다."}}})
            policy={"title":"지원법"}
            comparison={"changes":[{"clause":"제3조","before":"10일","after":"20일"}]}
            self.assertEqual(dependencies_for(policy,comparison,build_index(root)),[])
            leads=dependencies_for(policy,comparison,
                                   build_index(root,include_legacy=True))
            self.assertEqual(len(leads),1)
            self.assertEqual(leads[0]["status"],"historical_extracted_citation_candidate")
            service={"id":"p1","agency":"공공기관","agency_type":"공공기관",
                     "service_name":"신청업무","url":"https://www.gov.kr",
                     "basis":{"법령":"신청절차규정(제4조)"},
                     "criteria":{"신청기한":"10일"}}
            self.assertEqual(len(program_actions(policy,comparison,leads,[service])),1)

if __name__=="__main__":
    unittest.main()
