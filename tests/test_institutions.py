import json,tempfile,unittest
from pathlib import Path
from unified.institutions import parse_registry,collect
from unified.engine import load,store

class InstitutionDirectoryTests(unittest.TestCase):
    def test_exact_identity_and_reported_total(self):
        payload={'apbaList':[{'apbaId':'C0001','apbaNa':'시험공공기관','apbaType':'A2005'}]}
        self.assertEqual(parse_registry(payload,1)[0]['name'],'시험공공기관')
        with self.assertRaises(ValueError):parse_registry(payload,2)
        with self.assertRaises(ValueError):parse_registry({'apbaList':payload['apbaList']*2},2)

    def test_failed_refresh_preserves_official_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'institutions'/'alioplus.json.gz'
            store(path,{'records':[{'id':'C0001','name':'시험공공기관'}]})
            def transport(url,post):return b'<html>unavailable</html>' if not post else b'{}'
            report=collect(root,transport)
            self.assertEqual(report['status'],'refresh_failed')
            self.assertEqual(load(path)['records'][0]['id'],'C0001')
