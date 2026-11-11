"""One-time, read-only NEXT v2 ledger import into Policy Domino Unified.

Do not clone NEXT into this repository or mutate NEXT. NEXT's immutable,
fingerprint-checked clause packs are read with its own versioned loader.
Keep original XML in Unified as the canonical source. Reused extracted clauses
remain *partial* and may never substitute for a fully verified XML original.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .engine import (
    hash256, ident, load, store, relative_path, save_json,
)
from .textdiff import substantive_text, difference_windows

SOURCES = {"law", "admrul", "ordin"}
NEXT_SCHEMA = "policy-domino-next-v1"


def fingerprint(clauses):
    return hash256(json.dumps(clauses, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")))


def normalize(raw):
    if not isinstance(raw, dict):
        return None
    rec = {
        "source": str(raw.get("source") or "").strip(),
        "stable_id": str(raw.get("stable_id") or "").strip(),
        "serial": str(raw.get("serial") or "").strip(),
        "title": str(raw.get("title") or "").strip(),
        "published_at": str(raw.get("published_at") or "").strip(),
        "effective_date": str(raw.get("effective_date") or "").strip(),
        "revision": str(raw.get("revision") or ""),
        "kind": str(raw.get("law_type") or raw.get("kind") or ""),
        "ministry": str(raw.get("ministry") or ""),
        "url": str(raw.get("url") or ""),
    }
    if (rec["source"] not in SOURCES or
            not all(rec.get(k) for k in ("stable_id", "serial", "title")) or
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rec["published_at"])):
        return None
    if not rec["url"].startswith("https://"):
        rec["url"] = "https://www.law.go.kr/"
    return rec


def verified_clauses(version):
    """Only extract individually hashed, complete official clause text."""
    if not isinstance(version, dict):
        return {}
    if version.get("status") not in ("extracted", "partial"):
        return {}
    source = version.get("clauses") or {}
    if not isinstance(source, dict):
        return {}
    result = {}
    for key, body in source.items():
        if not isinstance(key, str) or not isinstance(body, dict):
            continue
        value = body.get("text")
        if not body.get("complete") or not isinstance(value, str) or not value.strip():
            continue
        digest = body.get("sha256")
        if not isinstance(digest, str) or hashlib.sha256(value.encode("utf8")).hexdigest() != digest:
            continue
        result[key] = value
    return result


def _compare_verified(findings, original_before, original_after):
    """Recheck NEXT changes against imported exact source text, not AI prose."""
    before = original_before.get("body", {}).get("clauses", {})
    after = original_after.get("body", {}).get("clauses", {})
    changes = []
    for change in findings.get("changes", []):
        article = change.get("article")
        old = change.get("before")
        new = change.get("after")
        if not article or not isinstance(old, str) or not isinstance(new, str):
            continue
        if old == new or article not in before or article not in after:
            continue
        if before[article] != old or after[article] != new:
            continue
        if substantive_text(old) == substantive_text(new):
            continue
        focused, count = difference_windows(old, new)
        changes.append({
            "clause": article, "before": old, "after": new,
            "focus": focused, "diff_window_count": count,
            "before_hash": hash256(old), "after_hash": hash256(new),
            "next_change_evidence": change.get("evidence", {}),
        })
    if not changes:
        return None
    official_xml = all(x.get("official_xml_base64") and
                       x.get("body", {}).get("status") == "complete"
                       for x in (original_before, original_after))
    return {
        "status": "changed" if official_xml else "partial_unverified",
        "relationship": "reused_official_version_comparison",
        "changes": changes,
        "unresolved": [] if official_xml else [
            {"reason": "imported_exact_clauses_pending_official_xml_confirmation"}],
        "counts": {"changed": len(changes), "unresolved": 0 if official_xml else 1,
                   "presentation_only": 0},
        "source_of_comparison": "NEXT_official_clause_fingerprints_and_pairs",
    }


def merge_state(state, root, next_sha, *, max_versions=1800, max_comparisons=900):
    root = Path(root)
    if state.get("schema") != NEXT_SCHEMA:
        raise ValueError("NEXT state has unexpected schema")
    documents = state.get("documents") or {}
    versions = state.get("versions") or {}
    findings = state.get("findings") or {}
    if not documents or not isinstance(documents, dict):
        raise ValueError("NEXT state has no documents")
    rec_by_id = {}
    index = {"law": [], "admrul": [], "ordin": []}
    for id_, doc in documents.items():
        rec = normalize(doc)
        if rec is None:
            continue
        rec_by_id[id_] = rec
        index[rec["source"]].append(rec)
    if len(rec_by_id) < 50:
        raise ValueError("NEXT official identifier catalog unexpectedly small")
    tally = Counter()
    for source, rows in index.items():
        rows.sort(key=lambda r: ident(r))
        destination = (root/"indexes"/source/
                       ("read-only-next-"+next_sha[:16]+".json.gz"))
        if store(destination, {
            "source": source, "records": rows,
            "origin": "NEXT_immutable_ledger_index",
            "snapshot_sha": next_sha,
            "official_xml_claimed": False,
        }):
            tally["indexed_shards_written"] += 1
    tally["indexed_eligible_records"] = len(rec_by_id)

    # Prefer versions that are part of a confirmed NEXT comparison and then
    # recent editions. Never overwrite a 1111 source file.
    findings_ids = set(findings)
    prior_ids = set()
    for finding in findings.values():
        if isinstance(finding, dict) and isinstance(finding.get("baseline"), dict):
            prior = finding["baseline"].get("id")
            if prior:
                prior_ids.add(prior)
    priority = sorted(
        versions.items(),
        key=lambda pair: (
            int(pair[0] in findings_ids or pair[0] in prior_ids),
            rec_by_id.get(pair[0], {}).get("published_at", ""),
            pair[0],
        ),
        reverse=True,
    )
    for id_, version in priority:
        if tally["versions_considered"] >= max_versions:
            break
        rec = rec_by_id.get(id_)
        if rec is None:
            continue
        tally["versions_considered"] += 1
        path = root / relative_path(rec)
        if path.exists():
            tally["versions_preexisting"] += 1
            continue
        clauses = verified_clauses(version)
        if not clauses:
            tally["versions_skipped_without_verified_text"] += 1
            continue
        obj = {
            "identity": ident(rec), "record": rec,
            "body": {
                "status": "partial", "clauses": clauses,
                "attachment_links": [],
                "incomplete_keys": [
                    "archived_NEXT_clause_extraction_requires_original_xml_validation"],
                "original_xml_available": False,
                "body_sha256": fingerprint(clauses),
            },
            "source_snapshot_provenance": {
                "repository": "dodam-heo/policy-domino-next",
                "commit": next_sha, "schema": NEXT_SCHEMA,
                "status": "verified_extracted_clauses_not_full_original",
                "has_raw_official_xml": False,
                "clause_count": len(clauses),
            },
        }
        if store(path, obj):
            tally["versions_imported"] += 1

    for id_, finding in sorted(findings.items()):
        if tally["comparison_cases_considered"] >= max_comparisons:
            break
        if not isinstance(finding, dict) or finding.get("status") not in (
                "compared", "partial_compared"):
            continue
        doc = rec_by_id.get(id_)
        baseline = finding.get("baseline") or {}
        previous = rec_by_id.get(baseline.get("id"))
        if not doc or not previous:
            tally["findings_skipped_no_baseline"] += 1
            continue
        tally["comparison_cases_considered"] += 1
        destination = (root / "comparisons" /
                       (hash256(ident(doc))[:24] + ".json.gz"))
        if destination.exists():
            tally["comparisons_preexisting"] += 1
            continue
        after = load(root / relative_path(doc), {})
        before = load(root / relative_path(previous), {})
        if not after or not before:
            tally["findings_skipped_missing_source"] += 1
            continue
        compared = _compare_verified(finding, before, after)
        if not compared:
            tally["findings_skipped_mismatched_clauses"] += 1
            continue
        compared["prior_record"] = previous
        compared["changed_record"] = doc
        compared["next_snapshot_sha"] = next_sha
        if store(destination, compared):
            tally["comparisons_imported"] += 1

    result = {
        "next_read_only_snapshot_sha": next_sha,
        "source_schema": NEXT_SCHEMA,
        "integrated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "origin_claim": "extracted_clauses_paired_from_NEXT_not_official_XML",
        "original_unified_sources_overwritten": 0,
        "next_source_repo_modified": False,
        "counts": dict(tally),
    }
    save_json(root / "next-import-status.json", result)
    return result


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--next", type=Path, required=True)
    cli.add_argument("--root", type=Path, default=Path("data"))
    cli.add_argument("--max-versions", type=int, default=1800)
    cli.add_argument("--max-comparisons", type=int, default=900)
    cli.add_argument("--expected-ref", required=True)
    opts = cli.parse_args()
    folder = opts.next.resolve()
    actual = subprocess.check_output(
        ["git", "-C", str(folder), "rev-parse", "HEAD"], text=True).strip()
    if actual != opts.expected_ref or not re.fullmatch("[0-9a-f]{40}", actual):
        raise ValueError("NEXT checkout must equal the pinned read-only commit")
    loader = folder/"policy_domino"/"state_store.py"
    if not loader.is_file():
        raise ValueError("Missing NEXT immutable source loader")
    spec = importlib.util.spec_from_file_location("_pinned_next_state_store", loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = module.load_shards(folder/"data"/"state.json", NEXT_SCHEMA)
    print("NEXT_IMPORT", json.dumps(merge_state(
        state, opts.root, actual,
        max_versions=opts.max_versions,
        max_comparisons=opts.max_comparisons), ensure_ascii=False))


if __name__ == "__main__":
    main()
