"""Generate the single static UI catalog from independent version files.

The UI never calls unofficial data sources and displays only linked official
agency actions actually supported by the rule's changed article evidence.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from .engine import ident, load, save_json
from .institutions import coverage
from .impact_scoring import evaluate as score_impact, change_substance

TOPICS = (
    ("급여·지원기준", re.compile(r"급여|지원대상|선정기준|기준 중위소득|소득인정액|보조금|복지")),
    ("행정절차·인허가", re.compile(r"허가|승인|신고|등록|제출|심사|접수|증빙|서식")),
    ("공공재정·요율", re.compile(r"예산|수수료|요율|부담금|세율|재정|공공요금")),
    ("조직·인력", re.compile(r"직제|조직|정원|직급|사무분장|정원규정")),
)


def classify(doc, changes) -> str:
    context = " ".join([doc.get("title", "")] + [
        (x.get("before", "") + " " + x.get("after", ""))[:300]
        for x in changes[:3]])
    for label, pattern in TOPICS:
        if pattern.search(context):
            return label
    return "기타 제·개정"



AMOUNT_OR_PERIOD = re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(만원|만\s*원|개월|시간|가구|원|%|일|명|년|세|주)")
IMPACT_CRITERIA = (
    ("급여·지원금·소득 기준 변경", re.compile(r"급여|지원금|중위소득|소득기준|소득인정액|생계비|주거비|장학금|보조금|지원액")),
    ("지원대상·자격·선정 기준 변경", re.compile(r"선정기준|지원대상|입주자격|수급자격|자격기준|심사기준|지원요건")),
    ("요율·수수료·부담금 변경", re.compile(r"요율|세율|수수료|부담금|보험료|과태료|과징금")),
    ("신청·처리 기한 변경", re.compile(r"신청기한|신청기간|처리기한|처리기간|접수기간|제출기한")),
    ("법정 의무·제재 기준 변경", re.compile(r"법정의무|의무기준|제재기준|처분기준|벌칙|위반기준")),
)
MONEY_UNITS = {"원", "만원", "%", "표 수치"}
ELIGIBILITY_UNITS = MONEY_UNITS | {"명", "세", "가구", "개월"}
DEADLINE_UNITS = {"일", "개월", "년", "주", "시간"}


def _quantities(text: str) -> dict[str, set[str]]:
    """Numbers and their real units, excluding article numbers and dates."""
    text = re.sub(r"<[^>]{0,140}>", "", text)
    text = re.sub(r"제\s*\d+\s*조(?:의\s*\d+)?", "", text)
    found = {}
    for value, unit in AMOUNT_OR_PERIOD.findall(text):
        unit = unit.replace(" ", "")
        found.setdefault(unit, set()).add(value.replace(",", ""))
    return found


def review_priority(doc: dict, comparison: dict, actions: list[dict]) -> list[str]:
    """An auditably local numeric criterion change or verified program link.

    An article renumbering, revision date, agency reshuffle or unrelated keyword
    must never be categorized as an income, fee or eligibility change.
    """
    if comparison.get("status") != "changed" or not comparison.get("changes"):
        return []
    reasons = []
    if any(a.get("status") == "review_of_verified_citation" and
           a.get("evidence", {}).get("reference_quote") and
           a.get("evidence", {}).get("service_quote") for a in actions):
        reasons.append("공식 사업·기관 업무의 변경 조문 인용 확인")
    for change in comparison["changes"]:
        old, new = str(change.get("before") or ""), str(change.get("after") or "")
        if not old or not new or old == new:
            continue
        windows = change.get("focus") or []
        if not windows and len(old) + len(new) <= 350:
            windows = [{"before": {"changed": old}, "after": {"changed": new}}]
        for window in windows:
            left, right = window.get("before") or {}, window.get("after") or {}
            old_edit = str(left.get("changed") or "")
            new_edit = str(right.get("changed") or "")
            # One-sided insertion and amendment-history dates are not proof
            # that an operating amount or deadline was replaced.
            if not re.search(r"\d", old_edit) or not re.search(r"\d", new_edit):
                continue
            old_local = (str(left.get("prefix") or "")[-70:] +
                         old_edit + str(left.get("suffix") or "")[:70])
            new_local = (str(right.get("prefix") or "")[-70:] +
                         new_edit + str(right.get("suffix") or "")[:70])
            prior, current = _quantities(old_local), _quantities(new_local)
            changed_units = {unit for unit in prior.keys() & current.keys()
                             if prior[unit] != current[unit]}
            is_table = str(change.get("clause") or "").startswith("표 ")
            if is_table and len(old) + len(new) <= 250:
                numeric_old = set(re.findall(r"(?<!\d)\d[\d,]*(?:\.\d+)?", old))
                numeric_new = set(re.findall(r"(?<!\d)\d[\d,]*(?:\.\d+)?", new))
                if numeric_old and numeric_new and numeric_old != numeric_new:
                    changed_units.add("표 수치")
            if not changed_units:
                continue
            local_context = (" ".join((str(change.get("clause") or ""),
                                     old_local, new_local)))
            if is_table and len(old) + len(new) <= 250:
                local_context += " " + str(doc.get("title") or "")
            for index, (label, pattern) in enumerate(IMPACT_CRITERIA):
                if label in reasons or not pattern.search(local_context):
                    continue
                allowed = (MONEY_UNITS if index in (0, 2) else
                           ELIGIBILITY_UNITS if index == 1 else
                           DEADLINE_UNITS if index == 3 else
                           MONEY_UNITS | DEADLINE_UNITS)
                if changed_units & allowed:
                    reasons.append(label)
    return reasons


def primary_change_summary(changes: list[dict]) -> str:
    """Small, factual list preview derived from real changed spans."""
    for change in changes:
        focus = change.get("focus") or []
        if not focus:
            continue
        first = focus[0]
        prior = (first.get("before") or {}).get("changed", "").strip()
        new = (first.get("after") or {}).get("changed", "").strip()
        if prior or new:
            prior = re.sub(r"\s+", " ", prior)[:76] or "신설"
            new = re.sub(r"\s+", " ", new)[:76] or "삭제"
            return str(change.get("clause") or "본문") + " · " + prior + " → " + new
    return ""

def assemble(root: Path, limit: int | None = None) -> dict:
    sources = []
    official_originals = legacy_texts = 0
    for path in (root / "documents").glob("*/*/*.json.gz"):
        value = load(path, {})
        doc = value.get("record", {})
        if not all(doc.get(k) for k in ("source", "stable_id", "serial", "title")):
            continue
        sources.append(doc)
        official_originals += bool(value.get("official_xml_base64") and
                                   value.get("body", {}).get("status") == "complete")
        legacy_texts += bool(value.get("source_snapshot_provenance") and
                             not value.get("official_xml_base64"))
    sources.sort(key=lambda v: (v.get("published_at", ""), v.get("serial", "")), reverse=True)
    comparisons = {}
    for path in (root / "comparisons").glob("*.json.gz"):
        c = load(path, {})
        row = c.get("changed_record") or {}
        if all(row.get(k) for k in ("source", "stable_id", "serial")):
            comparisons[ident(row)] = c
    impacts = {}
    analyses = {}
    dependencies = {}
    for path in (root / "impacts").glob("*.json.gz"):
        payload = load(path, {})
        row = payload.get("doc") or {}
        if all(row.get(k) for k in ("source", "stable_id", "serial")):
            impacts[ident(row)] = payload.get("institutional_actions", [])
            analyses[ident(row)] = payload.get("policy_analysis")
            dependencies[ident(row)] = payload.get("dependent_rules", [])
    events = []
    for doc in sources[:limit]:
        key = ident(doc)
        comp = comparisons.get(key, {})
        changes = comp.get("changes", [])
        before_after = [{
            "article": c.get("clause", ""), "before": c.get("before", ""),
            "after": c.get("after", ""),
            "focus": c.get("focus", []), "diff_window_count": c.get("diff_window_count", 0),
        } for c in changes]
        candidates = impacts.get(key, [])
        assessment = score_impact(doc, comp, candidates, dependencies.get(key, []))
        priority = [
            axis["evidence"][0]["reason"]
            for axis in assessment["axes"].values()
            if axis["score"] is not None and axis["score"] > 0
            and axis["evidence"]
        ]
        featured = assessment["featured_change_indices"]
        focus_change = next((changes[i] for i in featured if i < len(changes)), None)
        actual_summary = primary_change_summary([focus_change]) if focus_change else ""
        if not actual_summary and assessment["axes"]["substance"]["score"] is not None:
            if assessment["axes"]["substance"]["score"] < 20:
                actual_summary = "표현·인용·경미한 규정 정비 — 세부 변경은 신구대비에서 확인"
        before_after = [
            dict(row, substance_score=(change_substance(doc, changes[i]) or (0, None))[0])
            for i, row in enumerate(before_after)
        ]
        events.append({
            "id": key, "title": doc.get("title", ""),
            "source": doc["source"], "kind": doc.get("kind", ""),
            "ministry": doc.get("ministry", ""), "published_at": doc.get("published_at", ""),
            "effective_date": doc.get("effective_date", ""),
            "revision": doc.get("revision", ""), "url": doc.get("url", ""),
            "category": classify(doc, changes),
            "primary_change_summary": actual_summary,
            "priority_reasons": priority,
            "impact_assessment": assessment,
            "comparison_status": comp.get("status", "original_saved_comparison_pending"),
            "relationship": comp.get("relationship", ""),
            "changes": before_after,
            "unresolved": comp.get("unresolved", []),
            "institutions": candidates,
            "dependent_rules": dependencies.get(key, []),
            "policy_analysis": analyses.get(key),
            "impact_level": assessment["classification"],
            "prior_url": (comp.get("prior_record") or {}).get("url", ""),
        })
    report = {
        "schema": "policy-domino-unified-ui-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "source-backed version catalog; institutional actions only for exact citation evidence",
        "total_source_versions_saved": len(sources),
        "events": events,
        "summary": {
            "displayed_events": len(events),
            "with_verified_changes": sum(bool(e["changes"]) and e["comparison_status"] == "changed" for e in events),
            "with_text_differences": sum(bool(e["changes"]) for e in events),
            "with_institutional_actions": sum(bool(e["institutions"]) for e in events),
            "agency_action_count": sum(len(e["institutions"]) for e in events),
            "by_category": dict(Counter(e["category"] for e in events)),
        },
    }
    report["collection"] = load(root / "collection-state.json", {}).get("last_run_stats", {})
    report["analysis"] = load(root / "impact-status.json", {})
    report["coverage"] = coverage(root)
    # These measures are stage-specific: indexed metadata is not an archived
    # original; a partial extracted comparison is not a verified amendment.
    indexed = set()
    for path in (root / "indexes").glob("*/*.json.gz"):
        for row in load(path, {}).get("records", []):
            if all(row.get(k) for k in ("source", "stable_id", "serial")):
                indexed.add(ident(row))
    compared = Counter(c.get("status", "unknown") for c in comparisons.values())
    known = {ident(s) for s in sources}
    verified_tasks = review_leads = 0
    for key, actions in impacts.items():
        for action in actions:
            if not action.get("agency") or not action.get("service"):
                continue
            proof = action.get("evidence") or {}
            if (comparisons.get(key, {}).get("status") == "changed" and
                    action.get("status") == "review_of_verified_citation" and
                    proof.get("reference_quote") and proof.get("service_quote")):
                verified_tasks += 1
            else:
                review_leads += 1
    report["reconciliation"] = {
        "indexed_unique_versions": len(indexed),
        "saved_versions": len(sources),
        "indexed_without_saved_original": len(indexed - known),
        "official_complete_originals": official_originals,
        "legacy_extracted_versions_requiring_source_revalidation": legacy_texts,
        "comparisons": len(comparisons),
        "comparisons_by_status": dict(compared),
        "comparisons_without_impact_assessment": len(set(comparisons) - set(impacts)),
        "verified_institutional_review_tasks": verified_tasks,
        "review_leads_not_fully_verified": review_leads,
        "source": "incremental_cumulative_official_evidence",
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("site/data.json"))
    args = parser.parse_args()
    payload = assemble(args.root)
    save_json(args.root / "reconciliation-status.json", payload["reconciliation"])
    # Fetch summaries once; fetch only the selected event's comparison/impact.
    detail_dir = args.output.parent / "events"
    detail_dir.mkdir(parents=True, exist_ok=True)
    for event in payload["events"]:
        filename = __import__("hashlib").sha256(event["id"].encode()).hexdigest()[:24] + ".json"
        save_json(detail_dir / filename, event)
        event["detail_url"] = "events/" + filename
        event["change_count"] = len(event["changes"])
        event["agency_names"] = sorted({a["agency"] for a in event["institutions"]})
        event["action_count"] = len(event["institutions"])
        event["dependency_count"] = len(event.get("dependent_rules", []))
        event.pop("dependent_rules", None)
        event.pop("changes")
        event.pop("institutions")
        event.pop("unresolved")
    registry = load(args.root / "institutions" / "alioplus.json.gz", {})
    save_json(args.output.parent / "institutions.json", {"source": "alioplus",
              "updated_at": registry.get("fetched_at", ""), "records": registry.get("records", [])})
    save_json(args.output, payload)
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
