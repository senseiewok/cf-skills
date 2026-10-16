"""gnomAD (Genome Aggregation Database) provider.

Population-level aggregate allele frequencies across exomes and genomes.
Automated direct live queries are subject to gnomAD/Broad Institute robots.txt
and catalog access policies. Aggregates are also served via MyVariant.info.

Never an interpretation for a person.
"""

from __future__ import annotations

from typing import Any

from ..http import Client
from ..record import Evidence, Status

PROVIDER = "gnomad/0.1"
SOURCE = "gnomad"
NOT_STATED = "not stated"

LIMITATION = (
    "gnomAD aggregate allele frequencies are population-level observations across exomes and genomes. "
    "They reflect reference dataset cohort distributions and do not constitute clinical diagnoses, "
    "individual carrier interpretations, or therapeutic eligibility determinations."
)


def parse_gnomad_record(hit: dict[str, Any], question: str, url: str) -> Evidence:
    """Parse one gnomAD variant record into an Evidence record."""
    variant_id = hit.get("variant_id") or hit.get("_id") or NOT_STATED
    chrom = hit.get("chrom", NOT_STATED)
    pos = hit.get("pos", NOT_STATED)
    ref = hit.get("ref", NOT_STATED)
    alt = hit.get("alt", NOT_STATED)

    exome = hit.get("exome", {}) if isinstance(hit.get("exome"), dict) else {}
    genome = hit.get("genome", {}) if isinstance(hit.get("genome"), dict) else {}
    joint = hit.get("joint", {}) if isinstance(hit.get("joint"), dict) else {}

    fields = {
        "variant_id": variant_id,
        "chrom": chrom,
        "pos": pos,
        "ref": ref,
        "alt": alt,
        "exome_allele_count": exome.get("ac", NOT_STATED),
        "exome_allele_number": exome.get("an", NOT_STATED),
        "exome_allele_freq": exome.get("af", NOT_STATED),
        "genome_allele_count": genome.get("ac", NOT_STATED),
        "genome_allele_number": genome.get("an", NOT_STATED),
        "genome_allele_freq": genome.get("af", NOT_STATED),
        "joint_allele_count": joint.get("ac", NOT_STATED),
        "joint_allele_number": joint.get("an", NOT_STATED),
        "joint_allele_freq": joint.get("af", NOT_STATED),
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


def variant(client: Client, variant_id: str) -> Evidence:
    """Query gnomAD for aggregate variant frequencies under catalog access rules."""
    q = f"What are the gnomAD aggregate allele frequencies for '{variant_id}'?"
    try:
        f = client.get(SOURCE, f"variant/{variant_id}")
        if f.status is not Status.FOUND:
            return Evidence(
                status=f.status,
                question=q,
                source_id=SOURCE,
                url=f.url,
                provider=PROVIDER,
                fields={"variant_id": variant_id, "http_status": f.http_status},
                limitations=LIMITATION,
            )
        data = f.data if isinstance(f.data, dict) else {}
        return parse_gnomad_record(data, q, f.url)
    except Exception as exc:
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=SOURCE,
            url=f"https://gnomad.broadinstitute.org/variant/{variant_id}",
            provider=PROVIDER,
            fields={"variant_id": variant_id, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
            limitations=(
                "gnomAD automated direct query blocked under catalog policy (access: manual, robots: disallow). "
                "Use MyVariant.info aggregate frequencies or manual browser download."
            ),
        )
