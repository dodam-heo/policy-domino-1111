"""NEXT-derived direct statutory actor discovery, separate from verified tasks.

Never infer a public-service operation from an actor name. A subject must
occur in BOTH old and new text close to the changed words, not somewhere else
in a multi-page administrative order.
"""
from __future__ import annotations

import re

ACTOR = re.compile(
    r"(?<![가-힣])([가-힣]{2,35}(?:장관|청장|원장|시장|군수|구청장|위원회|공사|공단|기관장))"
    r"(?:은|는|이|가)\s+"
)


def _local_sides(change):
    old, new = str(change.get("before") or ""), str(change.get("after") or "")
    windows = change.get("focus") or []
    if not windows and len(old) + len(new) < 700 and old != new:
        return [(old, new)]
    results = []
    for window in windows[:12]:
        previous = window.get("before") or {}
        current = window.get("after") or {}
        old_window = (str(previous.get("prefix") or "")[-160:] +
                      str(previous.get("changed") or "") +
                      str(previous.get("suffix") or "")[:125])
        new_window = (str(current.get("prefix") or "")[-160:] +
                      str(current.get("changed") or "") +
                      str(current.get("suffix") or "")[:125])
        if old_window and new_window:
            results.append((old_window, new_window))
    return results


def direct_actor_leads(doc, comparison):
    if comparison.get("status") not in ("changed", "partial_unverified"):
        return []
    results = {}
    for change in comparison.get("changes", []):
        clause = str(change.get("clause") or "")
        if not clause.startswith("제"):
            continue
        for before, after in _local_sides(change):
            old_actors = set(ACTOR.findall(before))
            new_actors = set(ACTOR.findall(after))
            for actor in sorted(old_actors & new_actors):
                if len(actor) < 4:
                    continue
                key = (actor, clause)
                if key in results:
                    continue
                results[key] = {
                    "actor": actor,
                    "article": clause,
                    "before": before[:260],
                    "after": after[:260],
                    "source_url": str(doc.get("url") or ""),
                    "verification": "explicit_actor_near_changed_words_in_both_versions",
                    "operational_program_verified": False,
                    "required_action_verified": False,
                }
    return list(results.values())
