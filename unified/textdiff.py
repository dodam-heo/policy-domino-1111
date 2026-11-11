"""Source-preserving differences; layout noise is never a policy change."""
import re
import unicodedata
from difflib import SequenceMatcher


def substantive_text(value):
    return re.sub(r'[\s\u2500-\u257f]+', '', unicodedata.normalize('NFC', str(value or '')))


def difference_windows(before, after, context=4, limit=8):
    """Bounded, disjoint token edits. Source strings remain available separately."""
    def tokens(text):
        return list(re.finditer(r'\d[\d,.]*|[가-힣A-Za-z]+|[^\s\u2500-\u257f]', text))
    a, b = str(before or ''), str(after or '')
    ta, tb = tokens(a), tokens(b)
    matcher=SequenceMatcher(None,[x.group() for x in ta],[x.group() for x in tb],autojunk=max(len(ta),len(tb))>5000)
    windows=[]
    def part(text,tokens,start,end):
        left=tokens[start].start() if start<len(tokens) else len(text)
        right=tokens[end-1].end() if end>start else left
        prefix=text[max(0,left-45):left]
        suffix=text[right:right+45]
        changed=text[left:right]
        return {'prefix':('…' if left>45 else '')+prefix,'changed':changed[:400]+('…' if len(changed)>400 else ''),'suffix':suffix+('…' if right+45<len(text) else ''),'truncated':len(changed)>400}
    for tag,i,j,k,l in matcher.get_opcodes():
        if tag=='equal':continue
        windows.append({'before':part(a,ta,i,j),'after':part(b,tb,k,l)})
    return windows[:limit],len(windows)
