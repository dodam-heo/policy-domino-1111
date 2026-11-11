"""Evidence-gated impact identification from public-program operating records.

Only official provider names, operating criteria and exact legal evidence form
an institutional action; literal policy title overlap alone is never enough.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time

from .engine import hash256, clean, load, store, save_json, relative_path, YEAR

REFERENCES = re.compile(r"[「｢]([^」｣]{2,180})[」｣]\s*(제\s*\d+\s*조(?:의\s*\d+)?)?")
ARTICLE = re.compile(r"제\s*\d+\s*조(?:의\s*\d+)?")
NUMBERS = re.compile(r"(?<![\d,])\d[\d,]*(?:\.\d+)?\s*(?:만\s*원|원|%|명|개월)")
CRITERIA_FIELDS = ("선정기준", "지원대상", "지원내용", "신청기한", "구비서류")
BASIS_FIELDS = ("법령", "행정규칙", "자치법규")


def collect_programs(catalog: dict) -> list[dict]:
    raw = catalog.get("services") or {}
    entries = raw.values() if isinstance(raw, dict) else raw
    found = {}
    for r in entries:
        if not isinstance(r, dict):
            continue
        sid = clean(r.get("id") or r.get("서비스ID"))
        agency = clean(r.get("agency") or r.get("소관기관명"))
        name = clean(r.get("title") or r.get("서비스명"))
        agency_type = clean(r.get("agency_type") or r.get("소관기관유형"))
        if not sid or not agency or not name or "민간" in agency_type:
            continue
        detail = r.get("detail") or {}
        criteria = {k: clean(detail.get({
            "선정기준": "criteria", "지원대상": "eligible"}.get(k, "")) or
                              r.get({"선정기준": "criteria",
                                     "지원대상": "eligible",
                                     "지원내용": "benefits"}.get(k, "")) or
                              detail.get(k) or r.get(k))[:5000]
                    for k in CRITERIA_FIELDS}
        basis = {k: clean(detail.get({"법령": "laws", "행정규칙": "rules",
                                      "자치법규": "ordinances"}[k]) or r.get(k))[:5000]
                 for k in BASIS_FIELDS}
        if not any(criteria.values()) or not any(basis.values()):
            continue
        url = clean(r.get("detail_url") or r.get("상세조회URL"))
        if not url.startswith("https://"):
            url = "https://www.data.go.kr/data/15113968/openapi.do"
        found[sid] = {
            "id": sid, "agency": agency, "agency_type": agency_type,
            "service_name": name, "url": url,
            "criteria": criteria, "basis": basis,
            "origin": "official_gov24_public_service_catalog",
        }
    return list(found.values())


def import_catalog(root: Path, source: Path) -> dict:
    raw = json.loads(source.read_text("utf8"))
    if not isinstance(raw, dict):
        raise ValueError("Official public-service source must be an object")
    programs = collect_programs(raw)
    shards = {}
    for row in programs:
        key = hash256(row["id"])[:2]
        shards.setdefault(key, []).append(row)
    updated = 0
    for shard, records in shards.items():
        records.sort(key=lambda r: r["id"])
        updated += int(store(root / "programs" / (shard+".json.gz"),
                             {"source": "gov24", "records": records}))
    summary = {"official_services_indexed": len(programs),
               "shards": len(shards), "shards_changed": updated,
               "source": "gov24", "source_snapshot_hash": hash256(source.read_bytes())}
    save_json(root / "program-import.json", summary)
    return summary


def read_programs(root: Path):
    for source in sorted((root / "programs").glob("*.json.gz")):
        for row in load(source, {}).get("records", []):
            yield row


def plain(text):
    return clean(text).replace(" ", "")


def cited_articles(text: str) -> list[tuple[str, str, str]]:
    citations = []
    for match in re.finditer(r"[「｢]([^」｣]{2,180})[」｣]", text):
        tail = text[match.end():match.end()+220]
        block = re.match(r"[\s\d제조의항호목및과,·ㆍ]+", tail)
        if block:
            for article in ARTICLE.finditer(block.group()):
                citations.append((match.group(1), article.group(),
                                  match.group()+block.group()))
    return citations


def citation_quotes(basis: str, title: str, article: str) -> list[str]:
    """Read every article in each exact-title citation, including comma lists."""
    found = []
    for entry in re.split(r"[|;\n]", basis):
        normalized = plain(entry)
        wanted = plain(title).strip("「」｢｣")
        starts = normalized.startswith(wanted+"(") or normalized.startswith(wanted+"（")
        bracket = re.search(r"[「｢]"+re.escape(wanted)+r"[」｣]", normalized)
        if not (starts or bracket):
            continue
        # Bound the citation to this named law, never a later law's article.
        tail = normalized[len(wanted):] if starts else normalized[bracket.end():]
        if starts:
            tail = re.split(r"[)）]", tail, maxsplit=1)[0]
        else:
            tail = re.split(r"[「｢]", tail, maxsplit=1)[0]
        if plain(article) in [plain(m.group()) for m in ARTICLE.finditer(tail)]:
            found.append(entry)
    return found


def proof(program: dict, doc: dict, change: dict) -> dict | None:
    """Exact law+changed article in official program legal basis is required."""
    title, clause = doc.get("title", ""), change.get("clause", "")
    if not title or not clause:
        return None
    expected_title, expected_article = plain(title), plain(clause)
    basis = " ".join(program["basis"].values())
    # An explicit reference to the changed article, not just the legal title.
    citations = [(plain(m.group(1)), plain(m.group(2)), m.group(0))
                 for m in REFERENCES.finditer(basis)]
    exact = [quote for ref_title, ref_article, quote in citations
             if ref_title == expected_title and ref_article == expected_article]
    # Old/new must be complete, different and retained from official bodies.
    old, new = change.get("before", ""), change.get("after", "")
    # Gov24 supplies both 「법명」 제N조 and 법명(제N조, 제M항).
    # Match a complete title at a citation boundary, never substring similarity.
    exact.extend(citation_quotes(basis, title, clause))
    if not exact:
        for value in program["basis"].values():
            for entry in re.split(r"[\n;|]", value):
                normalized = plain(entry)
                normalized_title = expected_title.strip("「」")
                pattern = (r"(?:^|[,])" + re.escape(normalized_title) +
                           r"[（(]" + re.escape(expected_article) + r"(?=[,，)）]|$)")
                if re.search(pattern, normalized):
                    exact.append(entry)
    if not exact or not old or not new or old == new:
        return None
    relevant = [(k, v) for k, v in program["criteria"].items() if v]
    if not relevant:
        return None
    field, source_text = relevant[0]
    old_figures = set(NUMBERS.findall(old))
    new_figures = set(NUMBERS.findall(new))
    removed = sorted(old_figures-new_figures)
    added = sorted(new_figures-old_figures)
    # No number-only join. Numerical suggestions require the exact citation
    # above AND the actual old value in the service operating criteria.
    numeric = (len(removed) == 1 and len(added) == 1 and
               any(removed[0] in val for _, val in relevant))
    matched = next(((k, val) for k, val in relevant if numeric and removed[0] in val),
                   (field, source_text))
    return {
        "proof_type": "exact_changed_article_cited_by_official_program",
        "reference_quote": exact[0],
        "service_field": matched[0],
        "service_quote": matched[1][:1200],
        "old_value": removed[0] if numeric else "",
        "new_value": added[0] if numeric else "",
        "numeric_value_in_operating_criteria": numeric,
    }



def delegated_proof(program: dict, doc: dict, change: dict) -> dict | None:
    """Notice → explicitly cited parent article → official program criterion.

    This yields a review candidate, never a claim of a completed update.
    A shared parent title alone or an unchanged notice cannot create an edge.
    """
    if doc.get("source") != "admrul":
        return None
    old, new = change.get("before", ""), change.get("after", "")
    if not old or not new or old == new:
        return None
    if not (set(re.findall(r"\d[\d,]*(?:\.\d+)?", old)) ^ set(re.findall(r"\d[\d,]*(?:\.\d+)?", new))):
        return None
    previous = {(plain(t), plain(a)) for t, a, _ in
                cited_articles(doc.get("before_context", old))}
    current = [(t, a, q) for t, a, q in
               cited_articles(doc.get("after_context", new))
               if (plain(t), plain(a)) in previous]
    stop = {"선정기준", "최저보장수준", "적용", "시행", "기준", "고시", "운영규정",
            "지급기준", "지원기준", "운영", "관한", "규정", "계획", "관리", "사업"}
    terms = [word.removesuffix("의") for word in re.findall(r"[가-힣]{4,}", doc.get("title", ""))]
    terms = [t for t in terms if t not in stop and
             t in doc.get("before_context", old) and t in doc.get("after_context", new)]
    if not terms:
        return None
    for ref_title, ref_article, ref_quote in current:
        for basis in program["basis"].values():
            title, article = plain(ref_title), plain(ref_article)
            bracket = any(plain(m.group(1)) == title and plain(m.group(2)) == article
                          for m in REFERENCES.finditer(basis))
            pattern = r"(?:^|[|;,])" + re.escape(title) + r"[（(]" + re.escape(article) + r"(?=[,，)）]|$)"
            if not bracket and not re.search(pattern, plain(basis)) and not citation_quotes(basis, ref_title, ref_article):
                continue
            for field, value in program["criteria"].items():
                shared = next((t for t in terms if t in value), None)
                if shared:
                    return {"proof_type": "delegated_rule_and_operating_criterion",
                            "reference_quote": basis, "delegation_quote": ref_quote,
                            "criterion_term": shared, "service_field": field,
                            "service_quote": value, "old_value": "", "new_value": "",
                            "numeric_value_in_operating_criteria": False}
    return None


def operating_value_proof(program: dict, doc: dict, change: dict) -> dict | None:
    """Exact old table value + policy subject + shared official parent law.

    This is a second evidence path when Gov24 cites the law's purpose article
    rather than the delegated article. Numbers alone cannot link a program.
    """
    if doc.get("source") != "admrul" or not change.get("clause", "").startswith("표 "):
        return None
    old, new = change.get("before", ""), change.get("after", "")
    if not re.fullmatch(r"[\d,]+(?:\.\d+)?(?:원|만원|%)?", old) or old == new:
        return None
    parents = cited_articles(doc.get("after_context", ""))
    prior_parents = {plain(t) for t, _, _ in cited_articles(doc.get("before_context", ""))}
    basis = " ".join(program["basis"].values())
    parent = next(((t, q) for t, _, q in parents if plain(t) in prior_parents and
                   any(plain(entry).startswith(plain(t)+"(") or
                       ("「"+plain(t)+"」") in plain(entry)
                       for entry in re.split(r"[|;\n]", basis))), None)
    if not parent:
        return None
    terms = [t.removesuffix("의") for t in re.findall(r"[가-힣]{4,}", doc.get("title", ""))]
    subject = next((t for t in terms if t not in {"선정기준", "최저보장수준", "운영규정", "지급기준"}
                    and t in program["service_name"]), None)
    if not subject:
        return None
    match = next(((k, v) for k, v in program["criteria"].items()
                  if re.search(r"(?<![\d,])"+re.escape(old)+r"(?![\d,])", v)), None)
    if not match:
        return None
    return {"proof_type": "official_parent_subject_and_operating_value",
            "reference_quote": basis, "delegation_quote": parent[1],
            "criterion_term": subject, "service_field": match[0],
            "service_quote": match[1], "old_value": old, "new_value": new,
            "numeric_value_in_operating_criteria": True}



def named_standards(title: str) -> list[str]:
    """Find distinctive standards explicitly named in an official notice.

    Annual year changes are ignored; similar policy subjects alone are
    never sufficient evidence for a program linkage.
    """
    title = YEAR.sub("", clean(title))
    parts = re.split(r"\s+및\s+|[,·]|(?<=[가-힣])과\s+(?=[가-힣])|(?<=[가-힣])와\s+(?=[가-힣])", title)
    excluded = {"선정기준", "지원기준", "운영기준", "고시내용",
                "업무처리", "세부기준", "일부개정", "행정규칙"}
    terms = []
    for part in parts:
        part = re.sub(r"(?:에\s*관한|에\s*따른|의\s*개정).*?$", "", part).strip(" ()[]")
        if len(re.findall(r"[가-힣]", part)) < 6 or plain(part) in excluded:
            continue
        if part not in terms:
            terms.append(part)
    return terms


def named_standard_proof(program: dict, doc: dict, change: dict) -> dict | None:
    """An official program explicitly using a changed named standard is
    a review candidate, NOT a verified direct legal citation or update.
    """
    if doc.get("source") != "admrul":
        return None
    old, new = change.get("before", ""), change.get("after", "")
    if not old or not new or old == new:
        return None
    old_values = set(re.findall(r"\d[\d,]*(?:\.\d+)?", old))
    new_values = set(re.findall(r"\d[\d,]*(?:\.\d+)?", new))
    if not old_values.symmetric_difference(new_values):
        return None
    for phrase in named_standards(doc.get("title", "")):
        for field, value in program.get("criteria", {}).items():
            if not value or plain(phrase) not in plain(value):
                continue
            removed, added = sorted(old_values-new_values), sorted(new_values-old_values)
            numeric = (len(removed) == len(added) == 1 and
                       bool(re.search(r"(?<![\d,])" + re.escape(removed[0]) +
                                      r"(?![\d,])", value)))
            return {
                "proof_type": "explicit_named_standard_in_official_criteria",
                "reference_quote": doc["title"] + " · " + change.get("clause", ""),
                "standard_quote": phrase, "service_field": field,
                "service_quote": value[:1200],
                "old_value": removed[0] if numeric else "",
                "new_value": added[0] if numeric else "",
                "numeric_value_in_operating_criteria": numeric,
            }
    return None


def impact_for(doc: dict, comparison: dict, programs: list[dict]) -> list[dict]:
    if comparison.get("status") not in ("changed", "partial_unverified"):
        return []
    if not comparison.get("changes"):
        return []
    results = []
    reference_titles = {plain(doc.get("title", ""))}
    reference_titles.update(plain(m.group(1)) for m in REFERENCES.finditer(doc.get("after_context", "")))
    for change in comparison["changes"]:
        reference_titles.update(plain(m.group(1)) for m in REFERENCES.finditer(change.get("after", "")))
    # Exact legal citations and explicitly named operating standards are
    # separate paths. Do not treat a standard-name match as legal proof.
    standards = [plain(x) for x in named_standards(doc.get("title", ""))]
    programs = [p for p in programs if (
        any(title and title in (p.get("_basis_search") or plain(" ".join(p["basis"].values())))
            for title in reference_titles)
        or (doc.get("source") == "admrul" and standards and
            any(term in (p.get("_criteria_search") or plain(" ".join(p["criteria"].values())))
                for term in standards)))]
    for change in comparison["changes"]:
        for p in programs:
            evidence = (proof(p, doc, change) or operating_value_proof(p, doc, change)
                        or delegated_proof(p, doc, change)
                        or named_standard_proof(p, doc, change))
            if evidence is None:
                continue
            field = evidence["service_field"]
            if evidence["numeric_value_in_operating_criteria"]:
                action = (field + "에 기재된 종전 " + evidence["old_value"] +
                          "을 새 공식 기준 " + evidence["new_value"] +
                          "과 대조하고, 관련 안내·심사 산식을 변경된 기준에 맞게 검토")
            elif evidence["proof_type"] == "delegated_rule_and_operating_criterion":
                action = (field + "의 '" + evidence["criterion_term"] + "' 적용 기준을 " +
                          doc["title"] + "의 개정 기준과 대조하고, 지원 안내·대상 심사·지급 산식의 수정 항목 확인")
            elif evidence["proof_type"] == "explicit_named_standard_in_official_criteria":
                action = (field + "에서 명시적으로 사용 중인 '" +
                          evidence["standard_quote"] + "'을 " + doc["title"] +
                          "의 변경 전후 기준과 대조하고, 적용 대상·안내·심사 기준의 수정 필요 여부 검토")
            else:
                action = (field + "에서 인용한 " + change["clause"] +
                          "의 개정 문구를 확인하고 사업의 해당 처리기준·안내·심사 절차에 반영할 항목 검토")
            results.append({
                "agency": p["agency"], "agency_type": p["agency_type"],
                "service": p["service_name"], "service_id": p["id"],
                "service_url": p["url"], "policy_url": doc.get("url", ""),
                "policy": doc["title"], "changed_clause": change["clause"],
                "required_change": action,
                "before": change["before"], "after": change["after"],
                "evidence": evidence,
                "status": ("review_of_named_standard"
                           if evidence["proof_type"] == "explicit_named_standard_in_official_criteria"
                           else "review_of_verified_citation"),
                # This IS NOT a claim that the institution has/has not acted.
            })
    # Multiple file formats of the same official notice are one program task.
    unique = {}
    for result in results:
        key = (result["service_id"], result["evidence"]["reference_quote"], result["evidence"]["service_field"])
        if key not in unique:
            result["linked_changes"] = []
            unique[key] = result
        unique[key]["linked_changes"].append({"article": result["changed_clause"],
            "before": result["before"], "after": result["after"]})
    return list(unique.values())


def run(root: Path, limit_events: int = 300) -> dict:
    from .engine import refresh_cached
    refresh_cached(root)
    from .dependencies import build_index, dependencies_for, program_actions
    dependency_index = build_index(root)
    dependency_count = 0
    programs = list(read_programs(root))
    # Each policy previously normalized all 9k+ lengthy official program
    # records anew. Cache only in-memory search strings; never modify the
    # archived official source records.
    for program in programs:
        program["_basis_search"] = plain(" ".join(program["basis"].values()))
        program["_criteria_search"] = plain(" ".join(program["criteria"].values()))
    generated = []
    policy_ai_count = 0
    statuses = Counter()
    ai_failure_reasons = Counter()
    ai_attempts, ai_verified, ai_errors = 0, 0, 0
    key_available = bool(os.getenv("PD_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"))
    model_available = True
    ai_budget = max(0, int(os.getenv("PD_LLM_MAX_REQUESTS", "12")))
    ai_deadline = time.monotonic() + max(0, int(os.getenv("PD_LLM_TOTAL_SECONDS", "240")))
    files = sorted((root / "comparisons").glob("*.json.gz"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for source in files:
        comparison = load(source, {})
        doc = comparison.get("changed_record") or {}
        if not doc:
            continue
        # Delegation citations often live in the introduction, while changed
        # amounts live in the annex. Both editions must contain the citation.
        context_doc = dict(doc)
        for field, record in (("before_context", comparison.get("prior_record") or {}),
                              ("after_context", doc)):
            if all(record.get(k) for k in ("source", "stable_id", "serial")):
                original = load(root / relative_path(record), {})
                if original.get("official_xml_base64"):
                    context_doc[field] = " ".join(original.get("body", {}).get("clauses", {}).values())
        dependencies = dependencies_for(context_doc, comparison, dependency_index)
        dependency_count += len(dependencies)
        impacted = impact_for(context_doc, comparison, programs)
        direct_services = {a["service_id"] for a in impacted}
        impacted.extend(a for a in program_actions(context_doc, comparison, dependencies, programs)
                        if a["service_id"] not in direct_services)
        # AI is an optional explanatory layer AFTER deterministic official
        # linkage; model text cannot create a new agency or evidence edge.
        if key_available and model_available:
            from .ai import analyze
            for action in impacted:
                fingerprint = hash256(json.dumps(action, ensure_ascii=False, sort_keys=True))
                output = root / "ai" / (fingerprint[:24] + ".json.gz")
                verified = load(output)
                if (not verified and model_available and ai_attempts < ai_budget
                        and time.monotonic() < ai_deadline):
                    ai_attempts += 1
                    try:
                        verified = analyze(action)
                        if verified:
                            store(output, verified)
                    except Exception as exc:
                        ai_errors += 1
                        reason = str(exc) if str(exc).startswith("AI_HTTP_") else (
                            type(exc).__name__+":"+str(exc)
                            if type(exc).__name__ == "UnverifiedAnalysis"
                            else type(exc).__name__)
                        ai_failure_reasons[reason] += 1
                        if reason.startswith(("AI_HTTP_429:", "AI_HTTP_502:",
                                              "AI_HTTP_503:", "AI_HTTP_504:")):
                            model_available = False
                if verified and verified.get("verified"):
                    action["ai_analysis"] = verified
                    ai_verified += 1
        policy_analysis = None
        if comparison.get("changes"):
            changes = comparison["changes"]
            policy_context = {"analysis_scope": "policy", "policy": doc["title"],
                              "changed_clause": "; ".join(c["clause"] for c in changes[:20]),
                              "before": "\n".join(c["clause"]+": "+c["before"] for c in changes[:20]),
                              "after": "\n".join(c["clause"]+": "+c["after"] for c in changes[:20])}
            if max(len(policy_context["before"]), len(policy_context["after"])) > 10000:
                # Long annexes must not be explained from their opening lines
                # alone. Supply disjoint edits from every compared clause.
                policy_context["change_windows"] = [
                    {"clause": c["clause"], "total_locations": c.get("diff_window_count", 0),
                     "samples": c.get("focus", [])}
                    for c in changes if c.get("focus")]
            policy_context["evidence"] = {"service_quote": policy_context["after"]}
            fingerprint = hash256(json.dumps(policy_context, ensure_ascii=False, sort_keys=True))
            output = root / "ai" / ("policy-" + fingerprint[:24]+".json.gz")
            policy_analysis = load(output)
            if (not policy_analysis and key_available and model_available
                    and ai_attempts < ai_budget and time.monotonic() < ai_deadline):
                from .ai import analyze
                ai_attempts += 1
                try:
                    policy_analysis = analyze(policy_context)
                    if policy_analysis:
                        store(output, policy_analysis)
                except Exception as exc:
                    ai_errors += 1
                    reason = str(exc) if str(exc).startswith("AI_HTTP_") else (
                        type(exc).__name__+":"+str(exc)
                        if type(exc).__name__ == "UnverifiedAnalysis"
                        else type(exc).__name__)
                    ai_failure_reasons[reason] += 1
                    if reason.startswith(("AI_HTTP_429:", "AI_HTTP_502:",
                                          "AI_HTTP_503:", "AI_HTTP_504:")):
                        model_available = False
            if policy_analysis and policy_analysis.get("verified"):
                policy_ai_count += 1
        payload = {"doc": doc, "comparison_status": comparison.get("status"),
                   "changes_count": len(comparison.get("changes", [])),
                   "institutional_actions": impacted, "dependent_rules": dependencies, "policy_analysis": policy_analysis}
        target = root / "impacts" / (hash256("|".join((
            doc.get("source", ""), doc.get("stable_id", ""),
            doc.get("serial", ""))))[:24] + ".json.gz")
        store(target, payload)
        statuses[comparison.get("status", "")] += 1
        generated.extend(impacted)
    verified_tasks = sum(a.get("status") == "review_of_verified_citation"
                         for a in generated)
    named_standard_leads = sum(a.get("status") == "review_of_named_standard"
                               for a in generated)
    stats = {"official_programs": len(programs), "comparisons_considered": sum(statuses.values()),
             "verified_institutional_tasks": verified_tasks,
             "named_standard_review_candidates": named_standard_leads,
             "official_rule_dependencies": dependency_count,
             "comparison_statuses": dict(statuses),
             "ai_explanation_attempts": ai_attempts,
             "ai_verified_explanations": ai_verified,
             "ai_failures": ai_errors, "ai_failure_reasons": dict(ai_failure_reasons), "policy_ai_summaries": policy_ai_count,
             "ai_configured": key_available,
             "policy_summaries_pending": max(0, sum(1 for p in files if load(p, {}).get("changes")) - policy_ai_count)}
    save_json(root / "impact-status.json", stats)
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("data"))
    p.add_argument("--catalog", type=Path)
    args = p.parse_args()
    if args.catalog:
        print("IMPORT", json.dumps(import_catalog(args.root, args.catalog), ensure_ascii=False))
    print("IMPACT", json.dumps(run(args.root), ensure_ascii=False))


if __name__ == "__main__":
    main()
