"""Deterministic 100-point POLICY CHANGE review priority.

The three axes are separate. Missing institutional links are *unknown*, not
proof of zero downstream effects. AI text and counts of agency names never
contribute to the score. Preserve a concise source trail for every award.
"""
from __future__ import annotations

import re
from typing import Any

NUM = re.compile(r"(?<!\d)\d[\d,]*(?:\.\d+)?")
UNIT = re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(만원|만\s*원|원|%|개월|시간|가구|명|세|일|주|년)")
ANNOTATION = re.compile(r"<(?:개정|신설|삭제|본조신설|전문개정)[^>]*>|[〈<]\s*(?:개정|신설)[^〉>]*[〉>]")
PAYMENT = re.compile(r"급여|지원금|지원액|지급액|소득기준|소득인정액|중위소득|최저보장|보조금|장학금|보험료|부담금|수수료|요율|수가|단가|지급기준|금액")
ELIGIBILITY = re.compile(r"선정기준|지원대상|수급자격|자격기준|입주자격|지원요건|대상자|연령기준|소득구간|자격요건")
RIGHTS = re.compile(r"권리|의무|의무화|금지|제재|벌칙|과태료|처분기준")
PROCEDURE = re.compile(r"신청|접수|심사|인허가|인가|허가|승인|처리기한|제출기한|처리절차|행정서비스|집행절차")
ORGANIZATION = re.compile(r"직제|기구|정원|업무분장|사무분장|담당부서|소관업무|권한|조직|부서|전결|사무배분")
NATIONAL_STANDARD = re.compile(r"기준\s*중위소득|(?:생계|의료|주거|교육)급여.*(?:선정기준|최저보장수준)|(?:선정기준|최저보장수준).*(?:생계|의료|주거|교육)급여|전국|국민건강보험|요양급여비용")
LOCAL_INTERNAL = re.compile(r"행정기구|공무원\s*정원|직제|사무분장|업무분장|행정조직|지방공무원\s*인사|조직관리")
ONLY_DATE = re.compile(r"^[\s\.,;:/<>\[\]()\-년월일\d]+$")
ONLY_ARTICLE = re.compile(r"^(?:제\s*)?\d+\s*(?:조|항|호|목)(?:의\s*\d+)?$")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", ANNOTATION.sub("", str(value or ""))).strip()


def _evidence(doc, reason, article="", before="", after="", link=None):
    return {
        "reason": reason, "article": str(article or ""),
        "before": _clean(before)[:170], "after": _clean(after)[:170],
        "source_title": doc.get("title", ""), "source_url": link or doc.get("url", ""),
    }


def _local_edits(change):
    old, new = str(change.get("before") or ""), str(change.get("after") or "")
    windows = change.get("focus") or []
    if not windows and len(old) + len(new) < 450 and old != new:
        windows = [{"before": {"changed": old}, "after": {"changed": new}}]
    for pair in windows[:12]:
        left, right = pair.get("before") or {}, pair.get("after") or {}
        prev, curr = _clean(left.get("changed")), _clean(right.get("changed"))
        if prev == curr or not (prev or curr):
            continue
        if (ONLY_DATE.fullmatch(prev or "") and ONLY_DATE.fullmatch(curr or "")
                and ("개정" in (old + new) or "신설" in (old + new))):
            continue
        # A new revision-history date is not a changed benefit/entitlement.
        old_local = _clean(str(left.get("prefix") or "")[-65:] + " " + prev +
                           " " + str(left.get("suffix") or "")[:65])
        new_local = _clean(str(right.get("prefix") or "")[-65:] + " " + curr +
                           " " + str(right.get("suffix") or "")[:65])
        if not old_local.strip() and not new_local.strip():
            continue
        yield prev, curr, old_local, new_local


def change_substance(doc, change):
    """Highest evidenced substantive tier for this change; never AI inferred."""
    old, new = str(change.get("before") or ""), str(change.get("after") or "")
    if not old or not new or _clean(old) == _clean(new):
        return None
    is_table = str(change.get("clause") or "").startswith("표 ")
    title = str(doc.get("title") or "")
    best = None
    for before_frag, after_frag, before_local, after_local in _local_edits(change):
        context = str(change.get("clause") or "") + " " + before_local + " " + after_local
        if is_table:
            context += " " + title
        amounts_left = {(v.replace(",", ""), u.replace(" ", "")) for v, u in UNIT.findall(before_local)}
        amounts_right = {(v.replace(",", ""), u.replace(" ", "")) for v, u in UNIT.findall(after_local)}
        units_left = {u for _, u in amounts_left}
        units_right = {u for _, u in amounts_right}
        numeric_delta = any(
            {v for v, unit in amounts_left if unit == u} !=
            {v for v, unit in amounts_right if unit == u}
            for u in units_left & units_right
        )
        if is_table and len(old) + len(new) < 350 and NUM.search(old) and NUM.search(new):
            # Official matched table cell; label states the relevant unit.
            numeric_delta = numeric_delta or (
                set(NUM.findall(old)) != set(NUM.findall(new))
                and bool(PAYMENT.search(context) or ELIGIBILITY.search(context))
            )
        nontrivial = bool(re.search(r"[가-힣]{2,}", before_frag + after_frag))
        if numeric_delta and (PAYMENT.search(context) or ELIGIBILITY.search(context) or RIGHTS.search(context)):
            score, reason = 40, "급여·금액·자격·권리 등 실질 기준의 변경"
        elif nontrivial and not ONLY_ARTICLE.fullmatch(before_frag) and (
            ELIGIBILITY.search(context) or RIGHTS.search(context)
        ):
            # An actual changed entitlement/qualifying clause, not merely a title.
            score, reason = 40, "자격·권리·의무의 실질 문구 변경"
        elif numeric_delta and PROCEDURE.search(context):
            score, reason = 30, "신청·심사·처리 기한 또는 절차 변경"
        elif nontrivial and PROCEDURE.search(context):
            score, reason = 30, "신청·심사·집행 절차의 실질 문구 변경"
        elif nontrivial and ORGANIZATION.search(context):
            score, reason = 20, "기관 기능·권한·업무분장 변경"
        elif nontrivial or numeric_delta:
            score, reason = 10, "경미하거나 적용 범위가 제한적인 본문 정비"
        else:
            continue
        if best is None or score > best[0]:
            best = (score, _evidence(doc, reason, change.get("clause"),
                                     before_local, after_local))
    return best


def _scope(doc):
    title = str(doc.get("title") or "")
    source = doc.get("source")
    if not source or not title:
        return None
    if source == "ordin":
        if LOCAL_INTERNAL.search(title):
            return 5, "단일 지방기관 내부 운영 범위"
        return 15, "특정 지방자치단체·지역·사업에 적용"
    if source in ("law", "admrul"):
        if LOCAL_INTERNAL.search(title):
            return 5, "소관 기관 내부 조직·인사·사무 범위"
        if NATIONAL_STANDARD.search(title):
            return 35, "전국 공통 법정 급여·보장·보험 기준"
        if source == "law":
            return 35, "국가 법률에 따른 전국 단위 규율 범위"
        return 25, "중앙행정규칙이 관할하는 전국 특정 분야"
    return None


def _ripple(actions, rules):
    verified_programs = set()
    for a in actions or []:
        evidence = a.get("evidence") or {}
        if (a.get("status") == "review_of_verified_citation"
                and evidence.get("reference_quote") and evidence.get("service_quote")):
            ident = a.get("service_id") or (
                a.get("agency", ""), a.get("service", ""), a.get("changed_clause", ""))
            verified_programs.add(str(ident))
    verified_rules = {
        (r.get("source"), r.get("stable_id"), r.get("serial"), r.get("article"))
        for r in rules or []
        if r.get("status") == "citation_dependency_review"
        and r.get("reference_quote")
    }
    verified_rules.discard((None, None, None, None))
    count = len(verified_programs) + len(verified_rules)
    if count >= 2:
        return 25, "별개로 확인된 복수 하위 규정·공공사업 연결 경로"
    if verified_programs:
        return 15, "공식 공공사업 운영기준과 변경 조문 직접 연결"
    if verified_rules:
        return 8, "하위 규정의 명시적 조문 인용 확인, 운영 영향은 대조 중"
    # Absence of a discovered link is not an official determination of zero.
    return None


def evaluate(doc, comparison, actions=None, rules=None):
    """Returns lower bound, full scoring trail and deterministic category.

    Incomplete comparators can still produce a decisive high *lower bound*
    when one exact official numeric table criterion changed. The remaining
    items stay explicitly pending, never silently scored zero.
    """
    status = comparison.get("status", "")
    changes = comparison.get("changes") or []
    axes = {}
    if status == "no_text_change":
        axes["substance"] = {"score": 0, "status": "confirmed",
                             "evidence": [_evidence(doc, "조문 문구 변경 없음")]}
    elif status in ("changed", "partial_unverified") and changes:
        ranked = [(score, ev, i) for i, c in enumerate(changes)
                  if (item := change_substance(doc, c)) is not None
                  for score, ev in [item]]
        if ranked:
            ranked.sort(key=lambda p: (-p[0], p[2]))
            score, ev, _ = ranked[0]
            # A partial or incomplete original can establish a positive lower
            # bound only for a real paired numeric standard, not for vague text.
            if status == "changed" or (
                score == 40 and "실질 기준" in ev["reason"]
                and (str(ev["article"]).startswith("표 ") or
                     bool(re.search(r"\d", ev["before"]) and re.search(r"\d", ev["after"])))
            ):
                axes["substance"] = {"score": score, "status": "confirmed",
                                     "evidence": [ev]}
            else:
                axes["substance"] = {"score": None, "status": "pending",
                                     "evidence": [_evidence(doc, "부분 대조의 근거 추가 확인 필요")]}
        elif status == "changed":
            # Known editorial/metadata-only edits are not substantive.
            meaningful = any(_clean(c.get("before")) != _clean(c.get("after"))
                             and change_substance(doc, c) for c in changes)
            axes["substance"] = {"score": 10 if meaningful else 0,
                                 "status": "confirmed",
                                 "evidence": [_evidence(doc, "실질 기준 변경 근거 미확인 · 문구 정비")]}
        else:
            axes["substance"] = {"score": None, "status": "pending",
                                 "evidence": [_evidence(doc, "원문 일부만 확보되어 변경 실질성 판정 보류")]}
    else:
        axes["substance"] = {"score": None, "status": "pending",
                             "evidence": [_evidence(doc, "종전·현행 원문 비교 대기")]}
    scope = _scope(doc)
    axes["scope"] = ({"score": scope[0], "status": "confirmed",
                      "evidence": [_evidence(doc, scope[1])]} if scope
                     else {"score": None, "status": "pending",
                           "evidence": [_evidence(doc, "적용 대상·지역 확인 필요")]})
    ripple = _ripple(actions, rules)
    axes["ripple"] = ({"score": ripple[0], "status": "confirmed",
                       "evidence": [_evidence(doc, ripple[1],
                                              link=(next((r.get("url") for r in rules or []
                                                          if r.get("url")), None)))]}
                      if ripple else {"score": None, "status": "pending",
                                      "evidence": [_evidence(doc, "하위 규정·사업 파급 경로 조사 중")]})
    lower = sum(a["score"] for a in axes.values() if a["score"] is not None)
    maxscore = lower + sum(maxpoint for name, maxpoint in (
        ("substance", 40), ("scope", 35), ("ripple", 25))
        if axes[name]["score"] is None)
    sub = axes["substance"]["score"]
    is_high = sub is not None and sub >= 30 and lower >= 65
    completed = all(a["score"] is not None for a in axes.values())
    potential_high = (sub is None or sub >= 30) and maxscore >= 65
    if is_high:
        classification = "high"
    elif completed or not potential_high:
        classification = "normal"
    else:
        classification = "pending"
    ranked_changes = sorted(
        ((i, change_substance(doc, c)) for i, c in enumerate(changes)),
        key=lambda pair: -(pair[1][0] if pair[1] else 0))
    return {
        "classification": classification, "score": lower,
        "score_min": lower, "score_max": maxscore, "score_complete": completed,
        "threshold": 65, "minimum_substance": 30,
        "possible_high": potential_high and not is_high,
        "axes": axes,
        "featured_change_indices": [i for i, pair in ranked_changes
                                    if pair and pair[0] >= 20][:3],
        "scoring_version": "substance40-scope35-ripple25-v1",
    }
