"""Exact article citation paths, using archived official originals only.

A citation is a review dependency, not proof that a rule must be amended or
that its issuing authority operates a particular public service.
"""
from collections import defaultdict
from .engine import load
from .impact import ARTICLE, cited_articles, citation_quotes, plain


def build_index(root):
    latest = {}
    for path in (root / 'documents').glob('*/*/*.json.gz'):
        item = load(path, {})
        doc = item.get('record', {})
        if not doc.get('title'):
            continue
        key = (doc.get('source'), doc.get('stable_id'))
        rank = (doc.get('published_at', ''), doc.get('serial', ''))
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, item)
    index = defaultdict(list)
    for _, item in latest.values():
        if not item.get('official_xml_base64'):
            continue
        doc = item['record']
        for key, text in item.get('body', {}).get('clauses', {}).items():
            # Only numbered operative clauses; annexes and amendment histories
            # must not be represented as current statutory dependencies.
            if not key.startswith('제'):
                continue
            heading = ARTICLE.match(text)
            clause = plain(heading.group()) if heading else key
            for title, article, quote in cited_articles(text):
                if plain(title) == plain(doc['title']):
                    continue
                index[(plain(title), plain(article))].append({
                    'title': doc['title'], 'article': clause,
                    'source': doc.get('source'), 'stable_id': doc.get('stable_id'),
                    'serial': doc.get('serial'), 'url': doc.get('url', ''),
                    'published_at': doc.get('published_at', ''),
                    'effective_date': doc.get('effective_date', ''),
                    'reference_quote': quote, 'rule_quote': text,
                    'status': 'citation_dependency_review',
                })
    return index


def dependencies_for(doc, comparison, index):
    found = {}
    for change in comparison.get('changes', []):
        article = change.get('clause', '')
        for edge in index.get((plain(doc['title']), plain(article)), []):
            key = (edge['source'], edge['stable_id'], edge['serial'], edge['article'], article)
            found[key] = dict(edge, changed_article=article)
    return list(found.values())


def program_actions(doc, comparison, dependencies, programs):
    changes = {c['clause']: c for c in comparison.get('changes', [])}
    results = {}
    for edge in dependencies:
        change = changes[edge['changed_article']]
        for program in programs:
            quotes = [q for basis in program.get('basis', {}).values()
                      for q in citation_quotes(basis, edge['title'], edge['article'])]
            criteria = [(k, v) for k, v in program.get('criteria', {}).items() if v]
            if not quotes or not criteria:
                continue
            field, text = criteria[0]
            key = (program['id'], edge['title'], edge['article'], edge['changed_article'])
            results[key] = {
                'agency': program['agency'], 'agency_type': program['agency_type'],
                'service': program['service_name'], 'service_id': program['id'],
                'service_url': program['url'], 'policy_url': doc.get('url', ''),
                'policy': doc['title'], 'changed_clause': edge['changed_article'],
                'required_change': f"{edge['title']} {edge['article']}가 인용하는 상위 조문이 변경되었습니다. {program['service_name']}의 {field}와 해당 규정의 적용 관계를 대조해 안내·처리기준 수정 여부를 검토하세요.",
                'before': change['before'], 'after': change['after'],
                'linked_changes': [dict(article=change['clause'], before=change['before'], after=change['after'])],
                'evidence': {'proof_type': 'official_article_dependency_path',
                    'reference_quote': quotes[0], 'service_field': field,
                    'service_quote': text, 'dependency_path': [edge],
                    'numeric_value_in_operating_criteria': False},
                'status': 'review_of_verified_citation',
            }
    return list(results.values())
