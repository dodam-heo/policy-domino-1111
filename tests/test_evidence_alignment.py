import unittest
from unified.engine import compare_bodies
from unified.impact import citation_quotes, delegated_proof, operating_value_proof

class EvidenceAlignmentTests(unittest.TestCase):
    def test_multiple_articles_belong_to_exact_law(self):
        self.assertTrue(citation_quotes('생활지원법(제6조, 제12조)||별개법(제7조)', '생활지원법', '제12조'))
        self.assertFalse(citation_quotes('생활지원법(제6조)||별개법(제12조)', '생활지원법', '제12조'))

    def test_delegation_in_intro_reaches_changed_annex(self):
        doc = {'source':'admrul', 'title':'2027년 생활지원급여 선정기준',
               'before_context':'「생활지원법」 제6조 및 제12조에 따른 생활지원급여',
               'after_context':'「생활지원법」 제6조 및 제12조에 따른 생활지원급여'}
        program = {'basis':{'법령':'생활지원법(제12조)'}, 'criteria':{'지원내용':'생활지원급여 지급'}}
        self.assertIsNotNone(delegated_proof(program, doc, {'before':'100,000', 'after':'120,000'}))
        program['basis']['법령'] = '생활지원법(제13조)'
        self.assertIsNone(delegated_proof(program, doc, {'before':'100,000', 'after':'120,000'}))

    def test_annex_file_order_does_not_change_table_alignment(self):
        def body(text, amount):
            return {'status':'complete','clauses':{'첨부 1':text}, 'attachments':[
                {'format':'hwpx','verified_text':True,'table_cells':{'표 1 · 금액 · 4인가구':amount}}]}
        result = compare_bodies(body('PDF old','100'),body('HWPX new','120'))
        self.assertEqual(len(result['changes']),1)
        self.assertEqual(result['changes'][0]['clause'],'표 1 · 금액 · 4인가구')

    def test_amount_alone_never_links_a_program(self):
        doc={'source':'admrul','title':'2027년 생활지원급여 선정기준',
             'before_context':'「생활지원법」 제5조','after_context':'「생활지원법」 제5조'}
        change={'clause':'표 1 · 금액 · 4인가구','before':'100,000','after':'120,000'}
        p={'basis':{'법령':'생활지원법(제1조)'},'service_name':'생활지원급여',
           'criteria':{'선정기준':'4인가구 100,000원'}}
        self.assertIsNotNone(operating_value_proof(p,doc,change))
        p['service_name']='무관한 사업'
        self.assertIsNone(operating_value_proof(p,doc,change))

    def test_added_clause_requires_complete_editions(self):
        old={'status':'complete','clauses':{'제1조':'기존'}}
        new={'status':'complete','clauses':{'제1조':'기존','제2조':'신설 의무'}}
        self.assertEqual(compare_bodies(old,new)['changes'][0]['change_type'],'added')
        old['status']='partial'
        self.assertFalse(compare_bodies(old,new)['changes'])

    def test_official_ordinance_jo_wrapper(self):
        from unified.engine import parse_body
        body=parse_body('<LawService><조문><조><조문번호>1</조문번호><조내용>제1조 목적</조내용></조></조문></LawService>'.encode())
        self.assertEqual(body['clauses']['제1조'],'제1조 목적')

    def test_annex_without_body_or_download_remains_partial(self):
        from unified.engine import parse_body
        body=parse_body('<LawService><조><조문번호>1</조문번호><조내용>본문</조내용></조><별표단위><별표번호>1</별표번호></별표단위></LawService>'.encode())
        self.assertEqual(body['status'],'partial')

    def test_table_amount_inherits_unit_from_header(self):
        from unified.ai import verify, UnverifiedAnalysis
        impact={'before':'100,000','after':'120,000','changed_clause':'표 1 금액 (원/월)',
                'evidence':{'service_quote':'기준 100,000원'}}
        reply={'old_quote':'100,000','new_quote':'120,000','program_quote':'100,000원',
               'explanation':'금액을 120,000원으로 검토'}
        self.assertTrue(verify(reply,impact)['verified'])
        reply['explanation']='금액을 900,000원으로 검토'
        with self.assertRaises(UnverifiedAnalysis):verify(reply,impact)
