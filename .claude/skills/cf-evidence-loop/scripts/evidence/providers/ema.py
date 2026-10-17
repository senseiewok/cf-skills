"""EMA medicines provider: reads the downloaded EMA JSON report as evidence records.

Pure offline file-reading provider (source="ema-medicines-json").
Opens NO network connection (does not import http.py, urllib, requests, or socket).
Reads the JSON report placed under sources/downloads by the fetcher.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import catalog
from ..record import Evidence, Status

PROVIDER = "ema/0.1"
SOURCE = "ema-medicines-json"
DEFAULT_CATALOG_URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
EXCERPT_CHARS = 700


def _str_field(item: dict, key: str) -> str:
    """Safely extract and strip a string field, returning empty string if missing or non-string."""
    val = item.get(key)
    return val.strip() if isinstance(val, str) else ""


def _fmt_ema_date(s: Any) -> str | None:
    """Convert EMA date format DD/MM/YYYY to ISO format YYYY-MM-DD."""
    if not s or not isinstance(s, (str, int)):
        return None
    cleaned = str(s).strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", cleaned)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return cleaned


def resolve_report_path(file_path: str | Path | None = None) -> Path:
    """Deterministically resolve the EMA JSON report file path:
    1. Explicit file_path argument.
    2. EMA_MEDICINES_JSON environment variable.
    3. <catalog_dir>/downloads/EMA_medicines_json_report_en.json (next to EVIDENCE_CATALOG if set).
    4. <CATALOG_PATH>/../downloads/EMA_medicines_json_report_en.json.
    5. Sibling checkout cf-research/sources/downloads/EMA_medicines_json_report_en.json.
    """
    if file_path:
        return Path(file_path)

    env_path = os.environ.get("EMA_MEDICINES_JSON")
    if env_path:
        return Path(env_path)

    ev_cat = os.environ.get("EVIDENCE_CATALOG")
    if ev_cat:
        p = Path(ev_cat).parent / "downloads" / "EMA_medicines_json_report_en.json"
        if p.is_file():
            return p

    p_cat = catalog.CATALOG_PATH.parent / "downloads" / "EMA_medicines_json_report_en.json"
    if p_cat.is_file():
        return p_cat

    # Check all ancestor directories for sibling cf-research
    for ancestor in Path(__file__).resolve().parents:
        cand = ancestor / "cf-research" / "sources" / "downloads" / "EMA_medicines_json_report_en.json"
        if cand.is_file():
            return cand
        cand_parent = ancestor.parent / "cf-research" / "sources" / "downloads" / "EMA_medicines_json_report_en.json"
        if cand_parent.is_file():
            return cand_parent

    # Fallback to catalog downloads path
    return p_cat


def _get_file_timestamp(data: dict, file_path: Path | None = None) -> str:
    """Extract report timestamp from meta or file modification time."""
    meta = data.get("meta")
    if isinstance(meta, dict) and meta.get("timestamp"):
        return str(meta["timestamp"])
    if file_path and file_path.exists():
        try:
            mtime = file_path.stat().st_mtime
            return datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except OSError:
            pass
    return "unknown"


def parse(
    data: dict,
    drug: str,
    question: str,
    url: str = DEFAULT_CATALOG_URL,
    file_timestamp: str | None = None,
) -> Evidence:
    """Pure in-memory parsing of an EMA JSON report dict."""
    if not isinstance(data, dict):
        return Evidence(
            status=Status.ERROR,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"drug": drug, "error": f"Invalid report shape: expected dict, got {type(data).__name__}"},
            limitations="Source: European Medicines Agency (EMA). EMA medicines report file format error.",
        )

    ts = file_timestamp or _get_file_timestamp(data)

    # Finding 1.1: Guard against empty or whitespace-only drug query
    if not drug or not str(drug).strip():
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"drug": drug, "report_timestamp": ts},
            limitations=(
                f"Source: European Medicines Agency (EMA) medicines report (report timestamp {ts}). "
                "No medicine name provided; query cannot be empty."
            ),
        )

    items = data.get("data")
    if not isinstance(items, list):
        return Evidence(
            status=Status.ERROR,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"drug": drug, "error": f"Invalid report shape: 'data' is {type(items).__name__}, not a list"},
            limitations=f"Source: European Medicines Agency (EMA) medicines report (report timestamp {ts}). Invalid data structure.",
        )

    target = drug.strip().lower()

    # Finding 1.4: Strict match ranking tiers (exact > token > substring > INN/substance)
    exact_matches: list[tuple[bool, dict]] = []
    token_matches: list[tuple[bool, dict]] = []
    substr_matches: list[tuple[bool, dict]] = []
    inn_matches: list[tuple[bool, dict]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        # Finding 1.2: Safely extract string fields
        name = _str_field(item, "name_of_medicine")
        inn = _str_field(item, "international_non_proprietary_name_common_name")
        substance = _str_field(item, "active_substance")
        category = _str_field(item, "category")

        # Prioritise Human medicine category
        is_human = category.lower() == "human"

        name_lower = name.lower()
        inn_lower = inn.lower()
        substance_lower = substance.lower()

        if name_lower == target:
            exact_matches.append((is_human, item))
        elif target in name_lower.split():
            token_matches.append((is_human, item))
        elif target in name_lower:
            substr_matches.append((is_human, item))
        elif target in inn_lower or target in substance_lower:
            inn_matches.append((is_human, item))

    picked = None
    for bucket in (exact_matches, token_matches, substr_matches, inn_matches):
        if bucket:
            # Sort so human medicine comes first (not is_human places True before False)
            bucket.sort(key=lambda x: not x[0])
            picked = bucket[0][1]
            break

    if not picked:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"drug": drug, "report_timestamp": ts},
            limitations=(
                f"Source: European Medicines Agency (EMA) medicines report (report timestamp {ts}). "
                f"No medicine matching '{drug}' found in the report."
            ),
        )

    item_url = _str_field(picked, "medicine_url") or url
    auth_date_raw = _str_field(picked, "marketing_authorisation_date")
    auth_date_iso = _fmt_ema_date(auth_date_raw)
    decision_date_raw = _str_field(picked, "european_commission_decision_date")
    decision_date_iso = _fmt_ema_date(decision_date_raw)
    indication = _str_field(picked, "therapeutic_indication")
    excerpt = None
    if indication:
        excerpt = indication[:EXCERPT_CHARS] + ("…" if len(indication) > EXCERPT_CHARS else "")

    fields: dict[str, Any] = {
        "name_of_medicine": picked.get("name_of_medicine"),
        "medicine_status": picked.get("medicine_status"),
        "marketing_authorisation_date": auth_date_iso,
        "marketing_authorisation_date_raw": auth_date_raw,
        "european_commission_decision_date": decision_date_iso,
        "revision_number": picked.get("revision_number"),
        "active_substance": picked.get("active_substance"),
        "inn": picked.get("international_non_proprietary_name_common_name"),
        "ema_product_number": picked.get("ema_product_number"),
        "category": picked.get("category"),
        "therapeutic_area": picked.get("therapeutic_area_mesh"),
        "last_updated_date": _fmt_ema_date(picked.get("last_updated_date")),
        "report_timestamp": ts,
    }

    limitations = (
        f"Source: European Medicines Agency (EMA) medicines report (report timestamp {ts}). "
        "European Union marketing authorisation status and dates as indexed by EMA; "
        "does not establish US FDA or other national regulatory approvals, or any individual's clinical eligibility or access."
    )

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=item_url,
        provider=PROVIDER,
        publisher_date=auth_date_iso,
        fields=fields,
        excerpt=excerpt,
        limitations=limitations,
    )


def lookup(drug: str, file_path: str | Path | None = None) -> Evidence:
    """Read the downloaded EMA medicines JSON report and return an Evidence record for the specified drug."""
    q = f"What is the EU marketing authorisation status and date for medicine '{drug}'?"

    # Finding 1.1: Guard against empty or whitespace drug in lookup
    if not drug or not str(drug).strip():
        return Evidence(
            status=Status.NOT_FOUND,
            question=q,
            source_id=SOURCE,
            url=DEFAULT_CATALOG_URL,
            provider=PROVIDER,
            fields={"drug": drug, "error": "empty drug query"},
            limitations="Source: European Medicines Agency (EMA). No medicine name provided; query cannot be empty.",
        )

    path = resolve_report_path(file_path)

    if not path.is_file():
        return Evidence(
            status=Status.ERROR,
            question=q,
            source_id=SOURCE,
            url=DEFAULT_CATALOG_URL,
            provider=PROVIDER,
            fields={"drug": drug, "path": str(path), "error": "file not found"},
            limitations=(
                f"Source: European Medicines Agency (EMA). Report file not found at {path}; "
                "the fetcher must place the report under sources/downloads before this offline provider can read it."
            ),
        )

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Evidence(
            status=Status.ERROR,
            question=q,
            source_id=SOURCE,
            url=DEFAULT_CATALOG_URL,
            provider=PROVIDER,
            fields={"drug": drug, "path": str(path), "error": str(exc)},
            limitations=f"Source: European Medicines Agency (EMA). Failed to read or parse {path}: {exc}",
        )

    ts = _get_file_timestamp(data, path)
    return parse(data, drug, q, DEFAULT_CATALOG_URL, file_timestamp=ts)
