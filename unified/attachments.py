"""Retrieve and archive official PDF/DOCX annex contents safely.

HWP and scan-only files are archived as unresolved evidence, never treated as
verified numeric comparison. XML annex text is handled by the core parser.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import io
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

BASE = "https://www.law.go.kr/LSW/"
MAX_ATTACHMENT_BYTES = 12_000_000


def normalized_url(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    full = urljoin(BASE, raw)
    parsed = urlparse(full)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme not in ("http", "https") or host not in ("law.go.kr", "www.law.go.kr") or
        parsed.username or parsed.password):
        return ""
    return parsed._replace(scheme="https").geturl()


def fetch(url: str, transport=None):
    if transport:
        result = transport(url)
        if not isinstance(result, bytes):
            raise TypeError("Attachment transport must return bytes")
        return result
    with urlopen(Request(url, headers={
        "User-Agent": "PolicyDominoUnified/1.0",
        "Accept": "application/pdf,application/octet-stream,*/*"}), timeout=20) as response:
        if not normalized_url(response.geturl()):
            raise ValueError("Attachment redirected outside official law portal")
        return response.read(MAX_ATTACHMENT_BYTES+1)


def pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(raw), strict=False)
    return "\n".join((page.extract_text() or "") for page in pdf.pages[:80]).strip()


def docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as doc:
        if "word/document.xml" not in doc.namelist():
            return ""
        root = ET.fromstring(doc.read("word/document.xml"))
        paragraphs = []
        for node in root.iter():
            if node.tag.endswith("}p"):
                p = " ".join(t.text or "" for t in node.iter()
                             if t.tag.endswith("}t"))
                if p.strip():
                    paragraphs.append(p)
        return "\n".join(paragraphs)


def hwpx_extract(raw: bytes) -> tuple[str, dict]:
    """Preserve table coordinates; a flattened string cannot align amounts."""
    paragraphs, cells = [], {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        sections = sorted(f for f in archive.namelist()
                          if re.match(r"Contents/section\d+\.xml$", f))
        table_number = 0
        for section in sections:
            root = ET.fromstring(archive.read(section))
            paragraphs.extend(" ".join(t.text or "" for t in p.iter()
                              if t.tag.endswith("}t")) for p in root.iter()
                              if p.tag.endswith("}p"))
            for table in root.iter():
                if not table.tag.endswith("}tbl"):
                    continue
                table_number += 1
                rows = [[re.sub(r"\s+", " ", " ".join(t.text or "" for t in c.iter()
                         if t.tag.endswith("}t"))).strip()
                         for c in row if c.tag.endswith("}tc")]
                        for row in table if row.tag.endswith("}tr")]
                header_index = next((i for i, row in enumerate(rows)
                                     if len(row) > 1 and not any(re.fullmatch(
                                         r"[\d,]+", v) for v in row)), None)
                if header_index is None:
                    continue
                headers = rows[header_index]
                for row in rows[header_index+1:]:
                    if len(row) != len(headers) or not row[0]:
                        continue
                    for col, value in enumerate(row[1:], 1):
                        if not re.search(r"\d", value):
                            continue
                        label = f"표 {table_number} · {row[0]} · {headers[col]}"
                        cells[label] = value
    return "\n".join(p for p in paragraphs if p.strip()), cells


def _format(raw: bytes) -> str:
    if raw[:5] == b"%PDF-":
        return "pdf"
    if raw[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = archive.namelist()
            if "word/document.xml" in files:
                return "docx"
            if any(re.match(r"Contents/section\d+\.xml$", f) for f in files):
                return "hwpx"
        return "zip_other"
    if raw[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):
        return "hwp_ole"
    return "unknown"


def resolve_attachments(root: Path, original: dict,
                        transport=None, max_links: int=8) -> dict:
    links = original.get("attachment_links") or []
    if not links:
        return original
    clauses = dict(original.get("clauses") or {})
    records, unresolved = [], []
    for n, rawurl in enumerate(links):
        url = normalized_url(rawurl)
        row = {"index": n+1, "source_url": url or str(rawurl)[:120],
               "verified_text": False}
        if not url:
            row["reason"] = "non_official_or_invalid_attachment_url"
            unresolved.append(row)
            continue
        if n >= max_links:
            row["reason"] = "deferred_attachment_budget"
            unresolved.append(row)
            continue
        try:
            data = fetch(url, transport)
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise ValueError("official_attachment_too_large")
            fmt = _format(data)
            sha = hashlib.sha256(data).hexdigest()
            dest = root/"attachments"/sha[:2]/(sha+".gz")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                tmp = dest.with_suffix(".tmp")
                tmp.write_bytes(gzip.compress(data, mtime=0))
                tmp.replace(dest)
            row.update({"sha256": sha, "format": fmt, "size": len(data)})
            if fmt == "pdf":
                text = pdf_text(data)
            elif fmt == "docx":
                text = docx_text(data)
            elif fmt == "hwpx":
                text, table_cells = hwpx_extract(data)
                row["table_cells"] = table_cells
            else:
                text = ""
            text = re.sub(r"[ \t]+", " ", text)
            # Image-backed, unsupported HWP and unreadable tables stay partial.
            if len(text.strip()) < 100:
                row["reason"] = "insufficient_verified_extractable_text"
                unresolved.append(row)
                continue
            clauses["첨부 "+str(n+1)] = text[:15000]
            if len(text) > 15000:
                unresolved.append({"index": n+1, "reason": "attachment_text_truncated"})
            row.update({"verified_text": True, "text_sha256":
                hashlib.sha256(text.encode("utf8")).hexdigest()})
        except Exception as exc:
            row["reason"] = type(exc).__name__+": "+str(exc)[:100]
            unresolved.append(row)
        finally:
            records.append(row)
    incomplete = list(original.get("incomplete_keys", []))
    if records and all(x.get("verified_text") for x in records) and not unresolved:
        incomplete = [x for x in incomplete if x != "embedded_image_requires_full_attachment"]
    return {
        **original, "clauses": clauses, "incomplete_keys": incomplete,
        "attachments": records, "unresolved_attachments": unresolved,
        "body_sha256": hashlib.sha256(json.dumps(
            clauses, ensure_ascii=False, sort_keys=True).encode("utf8")).hexdigest(),
        "status": "complete" if clauses and not unresolved and
                    not incomplete else "partial",
    }
