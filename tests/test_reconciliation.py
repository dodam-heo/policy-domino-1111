import tempfile
import unittest
from pathlib import Path
from unified.engine import store
from unified.publish import assemble

class PipelineReconciliationTest(unittest.TestCase):
    def test_archived_evidence_and_legacy_text_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before={"source":"admrul","stable_id":"x","serial":"1","title":"지원기준"}
            after={"source":"admrul","stable_id":"x","serial":"2","title":"지원기준"}
            store(root/"indexes"/"admrul"/"i.json.gz",{"records":[before,after]})
            store(root/"documents"/"admrul"/"x"/"old.json.gz",
                  {"record":before,"source_snapshot_provenance":{"generation":"v4"},
                   "body":{"status":"partial"}})
            store(root/"documents"/"admrul"/"x"/"new.json.gz",
                  {"record":after,"official_xml_base64":"official",
                   "body":{"status":"complete"}})
            store(root/"comparisons"/"c.json.gz",
                  {"changed_record":after,"status":"partial_unverified",
                   "changes":[{"clause":"제1조","before":"100원","after":"120원"}]})
            store(root/"impacts"/"i.json.gz",{"doc":after,"institutional_actions":[
                  {"agency":"공식기관","service":"공공지원",
                   "status":"review_of_verified_citation",
                   "evidence":{"reference_quote":"법 제1조","service_quote":"100원"}}]})
            report=assemble(root)["reconciliation"]
            self.assertEqual(report["saved_versions"],2)
            self.assertEqual(report["indexed_without_saved_original"],0)
            self.assertEqual(report["official_complete_originals"],1)
            self.assertEqual(report["legacy_extracted_versions_requiring_source_revalidation"],1)
            self.assertEqual(report["comparisons_by_status"]["partial_unverified"],1)
            self.assertEqual(report["verified_institutional_review_tasks"],0)
            self.assertEqual(report["review_leads_not_fully_verified"],1)

if __name__=="__main__":
    unittest.main()
