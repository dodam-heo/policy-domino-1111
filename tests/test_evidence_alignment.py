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
