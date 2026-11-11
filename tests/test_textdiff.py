import unittest
from unified.engine import compare_bodies
from unified.textdiff import difference_windows

class TextDiffTests(unittest.TestCase):
    def body(self,text):return {'status':'complete','clauses':{'제1조':text}}
    def test_layout_is_not_amendment(self):
        result=compare_bodies(self.body('┌─┐지원 금액 100,000원\n신청 기한 30일'),self.body('지원금액 100,000원 신청기한 30일'))
        self.assertEqual(result['status'],'no_text_change')
        self.assertEqual(result['counts']['presentation_only'],1)
    def test_amount_and_deadline_are_separate_edits(self):
        middle=' 안내문은 동일하며 변경하지 않습니다. '*100
        a='지원금액 100,000원'+middle+'신청기한 30일'
        b='지원금액 120,000원'+middle+'신청기한 60일'
        result=compare_bodies(self.body(a),self.body(b))
        focus=result['changes'][0]['focus']
        self.assertEqual(len(focus),2)
        self.assertEqual(focus[0]['before']['changed'],'100,000')
        self.assertEqual(focus[1]['after']['changed'],'60')
        self.assertLess(sum(len(x['before']['changed']) for x in focus),30)
    def test_large_replacement_is_bounded(self):
        focus,count=difference_windows('가나다 '*5000,'다라마 '*5000)
        self.assertTrue(focus[0]['before']['truncated'])
        self.assertLessEqual(len(focus[0]['before']['changed']),401)
        self.assertEqual(count,1)
