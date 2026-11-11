import tempfile
import unittest
from pathlib import Path
from unified.attachments import normalized_url, resolve_attachments


class AnnexTest(unittest.TestCase):
    def test_block_non_law_portal_hosts(self):
        self.assertEqual(normalized_url("https://attacker.invalid/file.pdf"), "")
        self.assertTrue(normalized_url("/LSW/test.pdf").startswith("https://www.law.go.kr/"))
    def test_upgrade_official_http_link(self):
        self.assertEqual(normalized_url('http://law.go.kr/flDownload.do?flSeq=123'),
                         'https://law.go.kr/flDownload.do?flSeq=123')
        self.assertEqual(normalized_url('http://law.go.kr.attacker.invalid/a'), '')

    def test_official_text_after_15000_chars_is_retained(self):
        from unittest.mock import patch
        long_text = "선정기준 100원 " * 1800
        with tempfile.TemporaryDirectory() as temp, \
             patch("unified.attachments.pdf_extract",
                   return_value=(long_text, False)):
            doc = {"status": "partial", "clauses": {"제1조": "본문"},
                   "attachment_links": ["https://www.law.go.kr/LSW/a.pdf"]}
            result = resolve_attachments(Path(temp), doc,
                                         transport=lambda url: b"%PDF-test")
            self.assertEqual(result["status"], "complete")
            self.assertGreater(len(result["clauses"]["첨부 1"]), 15000)

    def test_short_structured_hwpx_table_is_verified(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp, \
             patch("unified.attachments._format", return_value="hwpx"), \
             patch("unified.attachments.hwpx_extract",
                   return_value=("공식 선정금액표", {"표 1 · 4인가구 · 금액": "120원"})):
            doc = {"status": "partial", "clauses": {"제1조": "본문"},
                   "attachment_links": ["https://www.law.go.kr/LSW/a.hwpx"]}
            result = resolve_attachments(Path(temp), doc,
                                         transport=lambda url: b"archived")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["attachments"][0]["table_cells"]["표 1 · 4인가구 · 금액"],
                             "120원")

    def test_truncated_pdf_pages_remain_unverified(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp, \
             patch("unified.attachments.pdf_extract",
                   return_value=("본문 " * 100, True)):
            doc = {"status": "partial", "clauses": {"제1조": "본문"},
                   "attachment_links": ["https://www.law.go.kr/LSW/a.pdf"]}
            result = resolve_attachments(Path(temp), doc,
                                         transport=lambda url: b"%PDF-test")
            self.assertEqual(result["status"], "partial")
            self.assertTrue(any(x["reason"] == "attachment_pages_truncated"
                                for x in result["unresolved_attachments"]))

    def test_never_certify_unreadable_annex(self):
        with tempfile.TemporaryDirectory() as temp:
            doc={"status":"partial","clauses":{"제1조":"본문"},
                 "attachment_links":["https://www.law.go.kr/LSW/annex.pdf"]}
            row=resolve_attachments(Path(temp),doc,transport=lambda url:b"not a valid pdf")
            self.assertEqual(row["status"],"partial")
            self.assertEqual(len(row["unresolved_attachments"]),1)
            self.assertFalse(row["attachments"][0]["verified_text"])


if __name__=="__main__":
    unittest.main()
