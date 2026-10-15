"""MyVariant.info provider. Variant annotations, CADD, SnpEff, ClinVar, and allele scores.

Never an interpretation for a person.
"""

from __future__ import annotations

from typing import Any

from ..http import Client
from ..record import Evidence, Status

PROVIDER = "myvariant/0.1"
SOURCE = "myvariant"
MAX_HITS = 5
NOT_STATED = "not stated"

LIMITATION = (
    "MyVariant.info aggregates variant annotations from external sources (CADD, ClinVar, SnpEff, dbSNP). "
    "In silico scores (CADD, PolyPhen, SIFT) are computational predictions, not proof of pathogenicity. "
    "It is not a clinical diagnosis, not eligibility for any therapy, and not an interpretation of any "
    "person's genotype."
)


def parse_myvariant_record(hit: dict[str, Any], question: str, url: str) -> Evidence:
    """Parse one MyVariant hit into an Evidence record."""
    record_id = hit.get("_id", NOT_STATED)
    cadd = hit.get("cadd", {}) if isinstance(hit.get("cadd"), dict) else {}
    clinvar_data = hit.get("clinvar", {}) if isinstance(hit.get("clinvar"), dict) else {}
    snpeff = hit.get("snpeff", {}) if isinstance(hit.get("snpeff"), dict) else {}
    raw_ann = snpeff.get("ann", {})
    snpeff_ann = raw_ann[0] if isinstance(raw_ann, list) and raw_ann else (raw_ann if isinstance(raw_ann, dict) else {})

    polyphen = cadd.get("polyphen", {}) if isinstance(cadd.get("polyphen"), dict) else {}
    sift = cadd.get("sift", {}) if isinstance(cadd.get("sift"), dict) else {}
    hg38 = clinvar_data.get("hg38", {}) if isinstance(clinvar_data.get("hg38"), dict) else {}

    fields = {
        "variant_id_genomic": record_id,
        "cadd_rawscore": cadd.get("rawscore", NOT_STATED),
        "cadd_phred": cadd.get("phred", NOT_STATED),
        "cadd_consequence": cadd.get("consequence", NOT_STATED),
        "polyphen_category": polyphen.get("cat", NOT_STATED),
        "polyphen_score": polyphen.get("val", NOT_STATED),
        "sift_category": sift.get("cat", NOT_STATED),
        "sift_score": sift.get("val", NOT_STATED),
        "clinvar_variant_id": clinvar_data.get("variant_id", NOT_STATED),
        "clinvar_rsid": clinvar_data.get("rsid", NOT_STATED),
        "hg38_start": hg38.get("start", NOT_STATED),
        "hg38_end": hg38.get("end", NOT_STATED),
        "snpeff_effect": snpeff_ann.get("effect", NOT_STATED),
        "snpeff_putative_impact": snpeff_ann.get("putative_impact", NOT_STATED),
        "snpeff_hgvs_c": snpeff_ann.get("hgvs_c", NOT_STATED),
        "snpeff_hgvs_p": snpeff_ann.get("hgvs_p", NOT_STATED),
    }

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=url,
        provider=PROVIDER,
        fields=fields,
        limitations=LIMITATION,
    )


def variants(client: Client, query: str, limit: int = MAX_HITS) -> list[Evidence]:
    """Query MyVariant.info for variant annotations."""
    q = f"Which MyVariant annotations match '{query}'?"
    f = client.get(SOURCE, "query", params={"q": query, "fields": "cadd,clinvar,snpeff", "size": min(limit, MAX_HITS)})
    if f.status is not Status.FOUND:
        return [
            Evidence(
                status=f.status,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"http_status": f.http_status},
                limitations="MyVariant request failed; establishes nothing.",
            )
        ]
    data = f.data if isinstance(f.data, dict) else {}
    hits = data.get("hits", [])
    if not isinstance(hits, list) or not hits:
        return [
            Evidence(
                status=Status.NOT_FOUND,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"query": query, "total": data.get("total", 0)},
                limitations="No MyVariant record matched; try genomic coordinates or standard HGVS protein notation.",
            )
        ]
    out: list[Evidence] = []
    for hit in hits[:limit]:
        if isinstance(hit, dict):
            out.append(parse_myvariant_record(hit, q, f.url))
    return out
