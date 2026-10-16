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

    # Extract ClinVar clinical significance / classification
    clinvar_sig = NOT_STATED
    if isinstance(clinvar_data, dict):
        if "clinical_significance" in clinvar_data:
            clinvar_sig = clinvar_data["clinical_significance"]
        elif "rcv" in clinvar_data:
            rcv = clinvar_data["rcv"]
            if isinstance(rcv, list) and rcv:
                sigs = [r.get("clinical_significance") for r in rcv if isinstance(r, dict) and r.get("clinical_significance")]
                if sigs:
                    clinvar_sig = "; ".join(dict.fromkeys(sigs))
            elif isinstance(rcv, dict):
                clinvar_sig = rcv.get("clinical_significance", NOT_STATED)

    # Extract gnomAD population aggregate allele frequencies (from dbsnp or direct gnomad fields)
    dbsnp_data = hit.get("dbsnp", {}) if isinstance(hit.get("dbsnp"), dict) else {}
    gnomad_exome_data = hit.get("gnomad_exome", {}) if isinstance(hit.get("gnomad_exome"), dict) else {}
    gnomad_genome_data = hit.get("gnomad_genome", {}) if isinstance(hit.get("gnomad_genome"), dict) else {}

    gnomad_freq = NOT_STATED
    dbsnp_alleles = dbsnp_data.get("alleles")
    if isinstance(dbsnp_alleles, list):
        alt_allele = dbsnp_data.get("alt")
        freqs: list[tuple[str, Any]] = []
        for a in dbsnp_alleles:
            if isinstance(a, dict) and "freq" in a and isinstance(a["freq"], dict):
                al_name = a.get("allele", "")
                f = a["freq"].get("gnomad") or a["freq"].get("gnomad_exomes")
                if f is not None:
                    freqs.append((al_name, f))
        if freqs:
            alt_match = [f for al, f in freqs if al == alt_allele]
            if alt_match:
                gnomad_freq = alt_match[0]
            else:
                gnomad_freq = freqs[-1][1] if len(freqs) > 1 else freqs[0][1]

    gnomad_exome_af = NOT_STATED
    if isinstance(gnomad_exome_data.get("af"), dict):
        gnomad_exome_af = gnomad_exome_data["af"].get("af", NOT_STATED)
    elif gnomad_exome_data.get("af") is not None:
        gnomad_exome_af = gnomad_exome_data.get("af")

    gnomad_genome_af = NOT_STATED
    if isinstance(gnomad_genome_data.get("af"), dict):
        gnomad_genome_af = gnomad_genome_data["af"].get("af", NOT_STATED)
    elif gnomad_genome_data.get("af") is not None:
        gnomad_genome_af = gnomad_genome_data.get("af")

    if gnomad_freq == NOT_STATED:
        if gnomad_genome_af != NOT_STATED:
            gnomad_freq = gnomad_genome_af
        elif gnomad_exome_af != NOT_STATED:
            gnomad_freq = gnomad_exome_af

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
        "clinvar_clinical_significance": clinvar_sig,
        "gnomad_allele_freq": gnomad_freq,
        "gnomad_exome_af": gnomad_exome_af,
        "gnomad_genome_af": gnomad_genome_af,
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
    f = client.get(
        SOURCE,
        "query",
        params={
            "q": query,
            "fields": "cadd,clinvar,snpeff,dbsnp,gnomad_exome,gnomad_genome",
            "size": min(limit, MAX_HITS),
        },
    )
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
