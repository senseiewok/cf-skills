"""Open Targets Platform v4 GraphQL API provider: target-disease associations, tractability, safety, and drugs.

Queries https://api.platform.opentargets.org/api/v4/graphql for target tractability (small molecule,
antibody, PROTAC, other modalities), curated target safety liabilities, disease-target association
scores, drug mechanisms of action, and FAERS post-marketing adverse event log-likelihood ratios.
Uses polite Client with source="open-targets" under CC0 1.0 Public Domain Dedication.

Per Open Targets third-party terms, ClinGen and gnomAD variant-level
datasources are excluded from queries; use NCBI ClinVar (variants) for variant pathogenicity.
"""

from __future__ import annotations

import re
from typing import Any

from ..http import Client, Fetch
from ..record import Evidence, Status
from ..shape import ShapeError, count, error_record, need

PROVIDER = "open_targets/0.1"
SOURCE = "open-targets"
DEFAULT_LIMIT = 5
MAX_LIMIT = 25
EXCERPT_CHARS = 700

ENSEMBL_ID_PATTERN = re.compile(r"^ENSG[0-9]{8,15}$", re.IGNORECASE)
DISEASE_ID_PATTERN = re.compile(r"^(?:EFO|MONDO|Orphanet|HP|OBA)_[0-9]+$", re.IGNORECASE)
CHEMBL_ID_PATTERN = re.compile(r"^CHEMBL[0-9]+$", re.IGNORECASE)

CC0_LICENSE = "CC0 1.0"
CC0_ATTRIBUTION = (
    "Open Targets Platform data is released under Creative Commons CC0 1.0 Universal "
    "(Public Domain Dedication); third-party source terms apply (ClinGen and gnomAD excluded because their third-party terms are not cleared for automated access)"
)

LIMITATION = (
    f"{CC0_ATTRIBUTION}. "
    "Open Targets association scores (0-1), tractability assessments, target safety liabilities, "
    "and FAERS pharmacovigilance log-likelihood ratios are aggregated computational and post-marketing "
    "research indicators. They do not establish clinical causality, comparative drug safety, "
    "or prescribing suitability for any individual patient."
)

TARGET_FIELDS_GQL = """
  id
  approvedSymbol
  approvedName
  biotype
  tractability {
    label
    modality
    value
  }
  safetyLiabilities {
    event
    eventId
    biosamples {
      tissueLabel
    }
    effects {
      direction
      dosing
    }
  }
  associatedDiseases(page: {index: 0, size: 5}) {
    count
    rows {
      score
      disease {
        id
        name
      }
    }
  }
"""

DISEASE_FIELDS_GQL = """
  id
  name
  description
  associatedTargets(page: {index: 0, size: 5}) {
    count
    rows {
      score
      target {
        id
        approvedSymbol
        approvedName
      }
    }
  }
"""

DRUG_FIELDS_GQL = """
  id
  name
  drugType
  maximumClinicalStage
  mechanismsOfAction {
    rows {
      mechanismOfAction
      actionType
      targetName
    }
  }
  adverseEvents(page: {index: 0, size: 5}) {
    count
    rows {
      name
      meddraCode
      count
      logLR
    }
  }
"""

TARGET_QUERY = f"query TargetById($id: String!) {{ target(ensemblId: $id) {{ {TARGET_FIELDS_GQL} }} }}"
DISEASE_QUERY = f"query DiseaseById($id: String!) {{ disease(efoId: $id) {{ {DISEASE_FIELDS_GQL} }} }}"
DRUG_QUERY = f"query DrugById($id: String!) {{ drug(chemblId: $id) {{ {DRUG_FIELDS_GQL} }} }}"

SEARCH_QUERY = f"""
query SearchEntities($q: String!, $size: Int!) {{
  search(queryString: $q, entityNames: ["target", "disease", "drug"], page: {{index: 0, size: $size}}) {{
    total
    hits {{
      id
      entity
      name
      description
      object {{
        ... on Target {{ {TARGET_FIELDS_GQL} }}
        ... on Disease {{ {DISEASE_FIELDS_GQL} }}
        ... on Drug {{ {DRUG_FIELDS_GQL} }}
      }}
    }}
  }}
}}
"""


def _check_gql_envelope(data: Any, what: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ShapeError(f"{what} response is {type(data).__name__}, not an object")
    errors = data.get("errors")
    if isinstance(errors, list) and errors:
        first_msg = errors[0].get("message") if isinstance(errors[0], dict) else str(errors[0])
        raise ShapeError(f"{what} returned GraphQL error: {first_msg}")
    gql_data = need(data, "data", what)
    if not isinstance(gql_data, dict):
        raise ShapeError(f"{what} 'data' is {type(gql_data).__name__}, not an object")
    return gql_data


def _extract_target_fields(obj: dict[str, Any], search_total: int | None = None) -> dict[str, Any]:
    target_id = obj.get("id")
    tract_raw = obj.get("tractability")
    positive_tractability: list[str] = []
    if isinstance(tract_raw, list):
        for item in tract_raw:
            if isinstance(item, dict) and item.get("value") is True:
                mod = item.get("modality") or ""
                lbl = item.get("label") or ""
                entry = f"{mod}:{lbl}" if mod and lbl else (lbl or mod)
                if entry and entry not in positive_tractability:
                    positive_tractability.append(entry)

    safety_raw = obj.get("safetyLiabilities")
    safety_events: list[str] = []
    if isinstance(safety_raw, list):
        for item in safety_raw:
            if isinstance(item, dict) and item.get("event"):
                ev = str(item["event"]).strip()
                if ev and ev not in safety_events:
                    safety_events.append(ev)
                    if len(safety_events) >= 8:
                        break

    assoc_raw = obj.get("associatedDiseases") if isinstance(obj.get("associatedDiseases"), dict) else {}
    assoc_count = assoc_raw.get("count")
    top_diseases: list[dict[str, Any]] = []
    for row in assoc_raw.get("rows") or []:
        if isinstance(row, dict):
            dis = row.get("disease") if isinstance(row.get("disease"), dict) else {}
            score = row.get("score")
            top_diseases.append(
                {
                    "disease_id": dis.get("id"),
                    "disease_name": dis.get("name"),
                    "score": round(float(score), 4) if isinstance(score, (int, float)) else score,
                }
            )

    fields: dict[str, Any] = {
        "entity": "target",
        "id": target_id,
        "approved_symbol": obj.get("approvedSymbol"),
        "approved_name": obj.get("approvedName"),
        "biotype": obj.get("biotype"),
        "tractability_positive": positive_tractability,
        "safety_liabilities": safety_events,
        "associated_diseases_count": assoc_count,
        "top_associated_diseases": top_diseases[:5],
        "license": CC0_LICENSE,
        "license_attribution": CC0_ATTRIBUTION,
    }
    if search_total is not None:
        fields["search_total"] = search_total
    return fields


def _extract_disease_fields(obj: dict[str, Any], search_total: int | None = None) -> dict[str, Any]:
    disease_id = obj.get("id")
    assoc_raw = obj.get("associatedTargets") if isinstance(obj.get("associatedTargets"), dict) else {}
    assoc_count = assoc_raw.get("count")
    top_targets: list[dict[str, Any]] = []
    for row in assoc_raw.get("rows") or []:
        if isinstance(row, dict):
            tgt = row.get("target") if isinstance(row.get("target"), dict) else {}
            score = row.get("score")
            top_targets.append(
                {
                    "target_id": tgt.get("id"),
                    "approved_symbol": tgt.get("approvedSymbol"),
                    "approved_name": tgt.get("approvedName"),
                    "score": round(float(score), 4) if isinstance(score, (int, float)) else score,
                }
            )

    fields: dict[str, Any] = {
        "entity": "disease",
        "id": disease_id,
        "name": obj.get("name"),
        "associated_targets_count": assoc_count,
        "top_associated_targets": top_targets[:5],
        "license": CC0_LICENSE,
        "license_attribution": CC0_ATTRIBUTION,
    }
    if search_total is not None:
        fields["search_total"] = search_total
    return fields


def _extract_drug_fields(obj: dict[str, Any], search_total: int | None = None) -> dict[str, Any]:
    drug_id = obj.get("id")
    moa_raw = obj.get("mechanismsOfAction") if isinstance(obj.get("mechanismsOfAction"), dict) else {}
    mechanisms: list[dict[str, Any]] = []
    for row in moa_raw.get("rows") or []:
        if isinstance(row, dict):
            mechanisms.append(
                {
                    "mechanism_of_action": row.get("mechanismOfAction"),
                    "action_type": row.get("actionType"),
                    "target_name": row.get("targetName"),
                }
            )

    ae_raw = obj.get("adverseEvents") if isinstance(obj.get("adverseEvents"), dict) else {}
    ae_count = ae_raw.get("count")
    top_ae: list[dict[str, Any]] = []
    for row in ae_raw.get("rows") or []:
        if isinstance(row, dict):
            log_lr = row.get("logLR")
            top_ae.append(
                {
                    "name": row.get("name"),
                    "meddra_code": row.get("meddraCode"),
                    "count": row.get("count"),
                    "log_lr": round(float(log_lr), 2) if isinstance(log_lr, (int, float)) else log_lr,
                }
            )

    fields: dict[str, Any] = {
        "entity": "drug",
        "id": drug_id,
        "name": obj.get("name"),
        "drug_type": obj.get("drugType"),
        "maximum_clinical_stage": obj.get("maximumClinicalStage"),
        "mechanisms_of_action": mechanisms[:5],
        "adverse_events_count": ae_count,
        "top_adverse_events": top_ae[:5],
        "license": CC0_LICENSE,
        "license_attribution": CC0_ATTRIBUTION,
    }
    if search_total is not None:
        fields["search_total"] = search_total
    return fields


def _entity_url(entity: str, entity_id: str | None, fallback: str) -> str:
    if not entity_id:
        return fallback
    kind = entity.lower()
    if kind in ("target", "disease", "drug"):
        return f"https://platform.opentargets.org/{kind}/{entity_id}"
    return fallback


def parse_target(data: Any, question: str, url: str, target_id: str = "") -> Evidence:
    """Parse a direct Open Targets target(ensemblId) GraphQL response."""
    try:
        gql_data = _check_gql_envelope(data, "Open Targets target")
        if "target" not in gql_data:
            raise ShapeError("Open Targets target data has no 'target'")
        tgt = gql_data["target"]
        if tgt is None:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"id": target_id, "entity": "target", "license": CC0_LICENSE},
                limitations=LIMITATION,
            )
        if not isinstance(tgt, dict):
            raise ShapeError(f"Open Targets 'target' is {type(tgt).__name__}, not an object")
        tid = need(tgt, "id", "Open Targets target")
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    fields = _extract_target_fields(tgt)
    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=_entity_url("target", tid, url),
        provider=PROVIDER,
        fields=fields,
        limitations=LIMITATION,
    )


def parse_disease(data: Any, question: str, url: str, disease_id: str = "") -> Evidence:
    """Parse a direct Open Targets disease(efoId) GraphQL response."""
    try:
        gql_data = _check_gql_envelope(data, "Open Targets disease")
        if "disease" not in gql_data:
            raise ShapeError("Open Targets disease data has no 'disease'")
        dis = gql_data["disease"]
        if dis is None:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"id": disease_id, "entity": "disease", "license": CC0_LICENSE},
                limitations=LIMITATION,
            )
        if not isinstance(dis, dict):
            raise ShapeError(f"Open Targets 'disease' is {type(dis).__name__}, not an object")
        did = need(dis, "id", "Open Targets disease")
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    desc = (dis.get("description") or "").strip()
    excerpt = (desc[:EXCERPT_CHARS] + ("…" if len(desc) > EXCERPT_CHARS else "")) if desc else None
    fields = _extract_disease_fields(dis)
    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=_entity_url("disease", did, url),
        provider=PROVIDER,
        fields=fields,
        excerpt=excerpt,
        limitations=LIMITATION,
    )


def parse_drug(data: Any, question: str, url: str, drug_id: str = "") -> Evidence:
    """Parse a direct Open Targets drug(chemblId) GraphQL response."""
    try:
        gql_data = _check_gql_envelope(data, "Open Targets drug")
        if "drug" not in gql_data:
            raise ShapeError("Open Targets drug data has no 'drug'")
        drg = gql_data["drug"]
        if drg is None:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={"id": drug_id, "entity": "drug", "license": CC0_LICENSE},
                limitations=LIMITATION,
            )
        if not isinstance(drg, dict):
            raise ShapeError(f"Open Targets 'drug' is {type(drg).__name__}, not an object")
        cid = need(drg, "id", "Open Targets drug")
    except ShapeError as exc:
        return error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)

    fields = _extract_drug_fields(drg)
    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=_entity_url("drug", cid, url),
        provider=PROVIDER,
        fields=fields,
        limitations=LIMITATION,
    )


def parse_search(data: Any, question: str, url: str, limit: int | None = None) -> list[Evidence]:
    """Parse an Open Targets search(queryString) GraphQL response."""
    try:
        gql_data = _check_gql_envelope(data, "Open Targets search")
        search_obj = need(gql_data, "search", "Open Targets search data")
        if not isinstance(search_obj, dict):
            raise ShapeError(f"Open Targets 'search' is {type(search_obj).__name__}, not an object")
        total = count(need(search_obj, "total", "Open Targets search"), "Open Targets search total")
        hits = need(search_obj, "hits", "Open Targets search")
        if not isinstance(hits, list):
            raise ShapeError(f"Open Targets search 'hits' is {type(hits).__name__}, not a list")
    except ShapeError as exc:
        return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

    if total == 0 or len(hits) == 0:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={
                    "search_total": total,
                    "license": CC0_LICENSE,
                    "license_attribution": CC0_ATTRIBUTION,
                },
                limitations=LIMITATION,
            )
        ]

    if limit is not None and limit > 0:
        hits = hits[:limit]

    out: list[Evidence] = []
    for idx, hit in enumerate(hits):
        if not isinstance(hit, dict):
            exc = ShapeError(f"Open Targets search hit {idx} is {type(hit).__name__}, not an object")
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]
        try:
            hit_id = need(hit, "id", f"Open Targets search hit {idx}")
            entity = str(need(hit, "entity", f"Open Targets search hit {idx}")).lower()
        except ShapeError as exc:
            return [error_record(exc, question=question, source_id=SOURCE, url=url, provider=PROVIDER)]

        obj = hit.get("object") if isinstance(hit.get("object"), dict) else {}
        desc = (hit.get("description") or obj.get("description") or "").strip()
        excerpt = (desc[:EXCERPT_CHARS] + ("…" if len(desc) > EXCERPT_CHARS else "")) if desc else None

        if entity == "target" and obj:
            fields = _extract_target_fields(obj, search_total=total)
        elif entity == "disease" and obj:
            fields = _extract_disease_fields(obj, search_total=total)
        elif entity == "drug" and obj:
            fields = _extract_drug_fields(obj, search_total=total)
        else:
            fields = {
                "entity": entity,
                "id": hit_id,
                "name": hit.get("name"),
                "search_total": total,
                "license": CC0_LICENSE,
                "license_attribution": CC0_ATTRIBUTION,
            }

        out.append(
            Evidence(
                status=Status.FOUND,
                question=question,
                source_id=SOURCE,
                url=_entity_url(entity, hit_id, url),
                provider=PROVIDER,
                fields=fields,
                excerpt=excerpt,
                limitations=LIMITATION,
            )
        )

    return out


def _fail(f: Fetch, question: str) -> Evidence:
    return Evidence(
        status=f.status,
        question=question,
        source_id=SOURCE,
        url=f.url,
        provider=PROVIDER,
        fields={"http_status": f.http_status, "license": CC0_LICENSE},
        limitations=LIMITATION,
    )


def lookup(client: Client, query: str, limit: int = DEFAULT_LIMIT) -> list[Evidence]:
    """Query Open Targets Platform by Ensembl ID, EFO/MONDO ID, ChEMBL ID, or free-text search."""
    stripped = query.strip()
    max_items = max(1, min(limit, MAX_LIMIT))

    if ENSEMBL_ID_PATTERN.match(stripped):
        ens_id = stripped.upper()
        q = f"What is the Open Targets target profile for '{ens_id}'?"
        f = client.post(SOURCE, "graphql", json={"query": TARGET_QUERY, "variables": {"id": ens_id}})
        if f.dry_run:
            return [
                Evidence(
                    status=Status.OUT_OF_SCOPE,
                    question=q,
                    source_id=SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={"id": ens_id, "entity": "target", "license": CC0_LICENSE},
                    limitations=LIMITATION,
                )
            ]
        if f.status is not Status.FOUND:
            return [_fail(f, q)]
        return [parse_target(f.data, q, f.url, target_id=ens_id)]

    if DISEASE_ID_PATTERN.match(stripped):
        parts = stripped.split("_", 1)
        prefix = "Orphanet" if parts[0].lower() == "orphanet" else parts[0].upper()
        dis_id = f"{prefix}_{parts[1]}"
        q = f"What is the Open Targets disease profile for '{dis_id}'?"
        f = client.post(SOURCE, "graphql", json={"query": DISEASE_QUERY, "variables": {"id": dis_id}})
        if f.dry_run:
            return [
                Evidence(
                    status=Status.OUT_OF_SCOPE,
                    question=q,
                    source_id=SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={"id": dis_id, "entity": "disease", "license": CC0_LICENSE},
                    limitations=LIMITATION,
                )
            ]
        if f.status is not Status.FOUND:
            return [_fail(f, q)]
        return [parse_disease(f.data, q, f.url, disease_id=dis_id)]

    if CHEMBL_ID_PATTERN.match(stripped):
        chembl_id = stripped.upper()
        q = f"What is the Open Targets drug profile for '{chembl_id}'?"
        f = client.post(SOURCE, "graphql", json={"query": DRUG_QUERY, "variables": {"id": chembl_id}})
        if f.dry_run:
            return [
                Evidence(
                    status=Status.OUT_OF_SCOPE,
                    question=q,
                    source_id=SOURCE,
                    url=f.url,
                    provider=PROVIDER,
                    fields={"id": chembl_id, "entity": "drug", "license": CC0_LICENSE},
                    limitations=LIMITATION,
                )
            ]
        if f.status is not Status.FOUND:
            return [_fail(f, q)]
        return [parse_drug(f.data, q, f.url, drug_id=chembl_id)]

    q = f"Which Open Targets entities match '{stripped}'?"
    f = client.post(
        SOURCE,
        "graphql",
        json={"query": SEARCH_QUERY, "variables": {"q": stripped, "size": max_items}},
    )
    if f.dry_run:
        return [
            Evidence(
                status=Status.OUT_OF_SCOPE,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"planned_query": stripped, "license": CC0_LICENSE},
                limitations=LIMITATION,
            )
        ]
    if f.status is not Status.FOUND:
        return [_fail(f, q)]
    return parse_search(f.data, q, f.url, limit=max_items)
