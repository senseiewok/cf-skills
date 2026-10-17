"""Anti-hallucination and provenance guardrails for the evidence layer.

Stdlib-only module enforcing deterministic grounding, field integrity,
and non-blank query validation across the evidence pipeline.
"""

from __future__ import annotations

from typing import Any

from .record import Evidence, Status

GROUNDING_CONTRACT = (
    "GROUNDING CONTRACT: Write only from the evidence fields above; "
    "say 'not stated' where a field is absent; "
    "never invent an NCT ID, DOI, PMID, approval date, variant classification, or submission count."
)

PROHIBITED_NULL_STRINGS = frozenset({"none", "null", "undefined"})


def is_blank_query(q: object) -> bool:
    """Return True if q is None, not a string, or contains only whitespace."""
    if q is None or not isinstance(q, str):
        return True
    return len(q.strip()) == 0


def _check_no_stringified_nulls(fields: dict[str, Any], path: str = "") -> list[str]:
    """Recursively check for prohibited stringified null values inside fields."""
    errors: list[str] = []
    for k, v in fields.items():
        current_path = f"{path}.{k}" if path else str(k)
        if isinstance(v, str):
            if v.strip().lower() in PROHIBITED_NULL_STRINGS:
                errors.append(
                    f"prohibited stringified null value '{v}' in field '{current_path}': "
                    "absent values must be 'not stated', None, or omitted"
                )
        elif isinstance(v, dict):
            errors.extend(_check_no_stringified_nulls(v, current_path))
        elif isinstance(v, (list, tuple)):
            for i, item in enumerate(v):
                if isinstance(item, str) and item.strip().lower() in PROHIBITED_NULL_STRINGS:
                    errors.append(
                        f"prohibited stringified null value '{item}' in field '{current_path}[{i}]': "
                        "absent values must be 'not stated', None, or omitted"
                    )
                elif isinstance(item, dict):
                    errors.extend(_check_no_stringified_nulls(item, f"{current_path}[{i}]"))
    return errors


def validate_evidence_record(rec: Evidence) -> list[str]:
    """Check deterministic anti-hallucination and provenance invariants on an Evidence record.

    Invariants checked:
    1. rec.source (or source_id) and rec.question must be non-empty strings.
    2. When rec.status == Status.FOUND:
       - rec.limitations must be a non-empty string (at least 15 characters) naming
         the source or scope boundary.
       - rec.fields must be a non-empty dict.
       - No string value inside rec.fields may be literal 'None', 'null', or 'undefined'.

    Returns a list of violation messages; an empty list indicates compliance.
    """
    errors: list[str] = []

    if not isinstance(rec, Evidence):
        return [f"expected Evidence instance, got {type(rec).__name__}"]

    # 1. Source and question must be non-empty strings
    source = getattr(rec, "source_id", getattr(rec, "source", None))
    if not source or not isinstance(source, str) or not source.strip():
        errors.append("source/source_id must be a non-empty string")

    question = getattr(rec, "question", None)
    if not question or not isinstance(question, str) or not question.strip():
        errors.append("question must be a non-empty string")

    # 2. Invariants when status == Status.FOUND (or string value 'found')
    status_val = rec.status.value if isinstance(rec.status, Status) else str(rec.status)
    if status_val == Status.FOUND.value:
        limitations = getattr(rec, "limitations", "") or ""
        if not isinstance(limitations, str) or len(limitations.strip()) < 15:
            errors.append(
                f"FOUND record limitations must be a non-empty string with at least 15 characters, got {len(limitations.strip()) if isinstance(limitations, str) else 0}"
            )

        fields = getattr(rec, "fields", None)
        if not isinstance(fields, dict) or len(fields) == 0:
            errors.append("FOUND record fields must be a non-empty dict")
        else:
            errors.extend(_check_no_stringified_nulls(fields))

    return errors
