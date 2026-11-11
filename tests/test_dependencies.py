import tempfile
import unittest
from pathlib import Path
from unified.engine import store
from unified.dependencies import build_index, dependencies_for, program_actions


class DependencyTests(unittest.TestCase):
    def test_archived_citation_path_requires_each_exact_article(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = dict(source='admrul', stable_id='10', serial='20', title='처리규정', published_at='2026-01-01', url='https://www.law.go.kr')
            store(root/'documents/admrul/10/20.json.gz', dict(record=record, official_xml_base64='archived', body={'clauses': {'제4조': '제4조 「지원법」 제3조에 따라 신청을 처리한다.'}}))
            doc = dict(title='지원법', url='https://www.law.go.kr')
            comparison = {'changes': [dict(clause='제3조', before='10일', after='20일')]}
            edges = dependencies_for(doc, comparison, build_index(root))
            self.assertEqual(len(edges), 1)
            p = dict(id='1', agency='기관', agency_type='공공기관', service_name='신청업무', url='https://www.gov.kr', basis={'법령':'처리규정(제4조)'}, criteria={'신청기한':'10일'})
            self.assertEqual(len(program_actions(doc, comparison, edges, [p])), 1)
            p['basis']['법령'] = '처리규정(제5조)'
            self.assertEqual(program_actions(doc, comparison, edges, [p]), [])
            comparison['changes'][0]['clause'] = '제2조'
            self.assertEqual(dependencies_for(doc, comparison, build_index(root)), [])

    def test_imported_unarchived_rule_and_old_edition_are_not_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for serial, date, archived, text in [('1','2025-01-01',True,'제4조 「지원법」 제3조'), ('2','2026-01-01',True,'제4조 별도 절차'), ('3','2026-01-02',False,'제4조 「지원법」 제3조')]:
                store(root/f'documents/admrul/10/{serial}.json.gz', {'record':dict(source='admrul',stable_id='10',serial=serial,title='처리규정',published_at=date), 'official_xml_base64':'archive' if archived else '', 'body':{'clauses':{'제4조':text}}})
            self.assertEqual(dict(build_index(root)), {})
