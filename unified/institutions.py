"""Official institution directory; registration is never policy-impact proof."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
from .engine import load, store, save_json, hash256, clean

ORIGIN = 'https://www.alioplus.go.kr'
LIST_URL = ORIGIN + '/organization/organByTypeList.do?schApbaGb=APBA&pageNo=1'
DATA_URL = ORIGIN + '/comm/searchApbaList.do'


def parse_registry(payload: dict, reported: int | None) -> list[dict]:
    rows = payload.get('apbaList')
    if not isinstance(rows, list) or not rows:
        raise ValueError('official_institution_rows_missing')
    found = {}
    for row in rows:
        code, name = clean(row.get('apbaId')), clean(row.get('apbaNa'))
        if not re.fullmatch(r'C\d+', code) or not name:
            raise ValueError('official_institution_identity_missing')
        if code in found:
            raise ValueError('duplicate_official_institution_code')
        found[code] = {'id':code,'name':name,'type_code':clean(row.get('apbaType')),
                       'source':'alioplus','source_url':DATA_URL,
                       'url':ORIGIN+'/organization/organHeadDetail.do?apbaId='+code}
    if reported is None or len(found) != reported:
        raise ValueError('official_institution_count_mismatch')
    return sorted(found.values(),key=lambda x:x['id'])


def collect(root: Path, transport=None) -> dict:
    def fetch(url, post=False):
        if transport:
            return transport(url,post)
        req=Request(url,data=b'' if post else None,headers={
            'User-Agent':'PolicyDomino/1.0', 'Referer':LIST_URL,
            'Content-Type':'application/x-www-form-urlencoded'})
        with urlopen(req,timeout=18) as response:
            if not response.geturl().startswith(ORIGIN+'/'):
                raise ValueError('untrusted_directory_redirect')
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise ValueError('official_directory_too_large')
        return raw
    try:
        html=fetch(LIST_URL).decode('utf-8','replace')
        match=re.search(r'<div\s+class="total">\s*총\s*<strong>([\d,]+)',html)
        reported=int(match.group(1).replace(',','')) if match else None
        raw=fetch(DATA_URL,True)
        records=parse_registry(json.loads(raw),reported)
        snapshot={'source':'alioplus','source_url':DATA_URL,'listing_url':LIST_URL,
                  'fetched_at':datetime.now(timezone.utc).isoformat(),
                  'reported_headquarters':reported,'records':records,
                  'raw_sha256':hash256(raw),'official_payload':json.loads(raw)}
        store(root/'institutions'/'alioplus.json.gz',snapshot)
        state={'configured':True,'status':'collected','registered_public_institutions':len(records),
               'reported_public_institutions':reported,'alio_directory_complete':True,
               'scope':'ALIOPLUS headquarters; excludes government and local-public-enterprise registers',
               'source_url':LIST_URL,'updated_at':snapshot['fetched_at']}
    except Exception as exc:
        cached=load(root/'institutions'/'alioplus.json.gz',{})
        state={'status':'refresh_failed','registered_public_institutions':len(cached.get('records',[])),
               'alio_directory_complete':False,'error':type(exc).__name__+':'+str(exc)[:120],
               'source_url':LIST_URL}
    save_json(root/'institutions-status.json',state)
    return state


def coverage(root: Path) -> dict:
    directory=load(root/'institutions'/'alioplus.json.gz',{})
    agencies={}
    programs=0
    for path in (root/'programs').glob('*.json.gz'):
        for row in load(path,{}).get('records',[]):
            programs+=1
            if row.get('agency'):
                agencies[row['agency']]=row.get('agency_type','')
    status=load(root/'gov24-status.json',{})
    return {'alio_public_institutions':len(directory.get('records',[])),
            'alio_reported':directory.get('reported_headquarters'),
            'alio_source_url':LIST_URL,'alio_updated_at':directory.get('fetched_at',''),
            'gov24_programs':programs,'gov24_agencies':len(agencies),
            'gov24_agency_types':dict(Counter(agencies.values())),
            'gov24_refresh':status.get('last_run',{}),
            'directory_is_impact_evidence':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('data'))
    args=p.parse_args();print(json.dumps(collect(args.root),ensure_ascii=False))

if __name__=='__main__':main()
