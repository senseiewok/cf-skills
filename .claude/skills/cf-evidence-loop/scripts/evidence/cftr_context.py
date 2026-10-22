"""Deterministic CFTR RefSeq (NM_000492.4) exon & UniProt (P13569) structural domain context.

Provides a zero-network, standard-library structural lookup for canonical CFTR variants and codons
so `brief variant` can annotate protein domain boundaries, exon numbers, and mutation class context
with explicit primary source provenance (UniProt P13569, RefSeq NM_000492.4, CFTR2).
"""

from __future__ import annotations

import re
from typing import Any

UNIPROT_ACCESSION = "P13569"
REFSEQ_TRANSCRIPT = "NM_000492.4"

# UniProt P13569 / cryo-EM (PDB:5UAK, 6MSM) canonical domain boundaries (amino acid residues 1..1480)
CFTR_DOMAINS: tuple[tuple[int, int, str, str], ...] = (
    (1, 80, "N-terminal lasso motif", "Cytoplasmic lasso helix bundle anchoring TMD1/TMD2"),
    (81, 350, "TMD1 (Transmembrane Domain 1)", "Membrane-spanning helices TM1-TM6 forming the chloride pore"),
    (351, 388, "TMD1-NBD1 linker", "Cytoplasmic linker coupling TM6 to NBD1"),
    (389, 673, "NBD1 (Nucleotide-Binding Domain 1)", "ATP-binding domain containing the F508 interface with ICL4"),
    (674, 845, "R-domain (Regulatory Domain)", "Intrinsically disordered PKA-phosphorylation regulatory region"),
    (846, 1151, "TMD2 (Transmembrane Domain 2)", "Membrane-spanning helices TM7-TM12 and ICL4 (L1065-R1070) pocket"),
    (1152, 1206, "TMD2-NBD2 linker", "Cytoplasmic linker coupling TM12 to NBD2"),
    (1207, 1446, "NBD2 (Nucleotide-Binding Domain 2)", "Catalytic ATP-hydrolysis domain driving head-to-tail dimerization"),
    (1447, 1480, "C-terminal tail (PDZ-binding motif)", "Cytoplasmic tail ending in DTRL PDZ-interaction motif"),
)

# RefSeq NM_000492.4 27-exon coding amino acid spans (approximate codon boundaries 1..1480)
CFTR_EXON_SPANS: tuple[tuple[int, int, int], ...] = (
    (1, 1, 18),
    (2, 19, 55),
    (3, 56, 91),
    (4, 92, 163),
    (5, 164, 193),
    (6, 194, 248),
    (7, 249, 290),
    (8, 291, 372),
    (9, 373, 403),
    (10, 404, 464),
    (11, 465, 528),
    (12, 529, 557),
    (13, 558, 590),
    (14, 591, 831),
    (15, 832, 874),
    (16, 875, 917),
    (17, 918, 930),
    (18, 931, 1013),
    (19, 1014, 1040),
    (20, 1041, 1123),
    (21, 1124, 1175),
    (22, 1176, 1209),
    (23, 1210, 1292),
    (24, 1293, 1326),
    (25, 1327, 1384),
    (26, 1385, 1419),
    (27, 1420, 1480),
)

# Curated high-frequency CFTR alleles with exact HGVS, exon, domain, and mechanistic class
CANONICAL_ALLELES: dict[str, dict[str, Any]] = {
    "F508DEL": {
        "allele": "F508del",
        "hgvs_c": "c.1521_1523delCTT",
        "hgvs_p": "p.Phe508del",
        "codon": 508,
        "exon": 11,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class II (misfolding/trafficking defect at NBD1-ICL4 interface)",
    },
    "G551D": {
        "allele": "G551D",
        "hgvs_c": "c.1652G>A",
        "hgvs_p": "p.Gly551Asp",
        "codon": 551,
        "exon": 12,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class III (ATP signature motif LSGGQ gating arrest)",
    },
    "G542X": {
        "allele": "G542X",
        "hgvs_c": "c.1624G>T",
        "hgvs_p": "p.Gly542Ter",
        "codon": 542,
        "exon": 12,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class I (premature termination codon / NMD substrate)",
    },
    "W1282X": {
        "allele": "W1282X",
        "hgvs_c": "c.3846G>A",
        "hgvs_p": "p.Trp1282Ter",
        "codon": 1282,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class I (premature termination codon in NBD2)",
    },
    "N1303K": {
        "allele": "N1303K",
        "hgvs_c": "c.3909C>G",
        "hgvs_p": "p.Asn1303Lys",
        "codon": 1303,
        "exon": 24,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class II (late NBD2 folding and gating defect)",
    },
    "R117H": {
        "allele": "R117H",
        "hgvs_c": "c.350G>A",
        "hgvs_p": "p.Arg117His",
        "codon": 117,
        "exon": 4,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class IV (external pore loop ECL1 conductance defect)",
    },
    "R553X": {
        "allele": "R553X",
        "hgvs_c": "c.1657C>T",
        "hgvs_p": "p.Arg553Ter",
        "codon": 553,
        "exon": 12,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class I (premature termination codon in NBD1)",
    },
    "3849+10KBC>T": {
        "allele": "3849+10kbC>T",
        "hgvs_c": "c.3718-2477C>T",
        "hgvs_p": "intronic cryptic splice donor",
        "codon": None,
        "exon": 22,
        "domain": "Intron 22 (84-bp pseudoexon inclusion between exons 22 and 23)",
        "cftr_class": "Class V (cryptic splice site reducing canonical transcript)",
    },
}

_CODON_RE = re.compile(
    r"\b(?:p\.[A-Z][a-z]{2}|[ACDEFGHIKLMNPQRSTVWY])(\d{1,4})(?:del|dup|ins|fs|Ter|X|[A-Z][a-z]{2}|[ACDEFGHIKLMNPQRSTVWY*])\b"
)


def domain_for_codon(codon: int) -> str:
    """Return the UniProt P13569 structural domain name for a 1-based CFTR amino acid residue."""
    for start, end, name, _desc in CFTR_DOMAINS:
        if start <= codon <= end:
            return name
    return "outside canonical 1480-aa CFTR sequence"


def exon_for_codon(codon: int) -> int | None:
    """Return the RefSeq NM_000492.4 exon number (1..27) for a 1-based CFTR codon."""
    for exon_num, start, end in CFTR_EXON_SPANS:
        if start <= codon <= end:
            return exon_num
    return None


def lookup_cftr_context(term: str) -> dict[str, Any] | None:
    """Resolve a query term (e.g. 'CFTR[gene] AND F508del', 'G551D', 'p.Arg117His') to CFTR structural metadata."""
    if not isinstance(term, str) or not term.strip():
        return None
    upper = term.upper()
    for key, info in CANONICAL_ALLELES.items():
        if key in upper:
            return {
                **info,
                "transcript": REFSEQ_TRANSCRIPT,
                "uniprot": UNIPROT_ACCESSION,
            }

    # Check protein HGVS aliases for canonical alleles
    for info in CANONICAL_ALLELES.values():
        if info["hgvs_p"].upper() in upper or info["hgvs_c"].upper() in upper:
            return {
                **info,
                "transcript": REFSEQ_TRANSCRIPT,
                "uniprot": UNIPROT_ACCESSION,
            }

    # Generic codon extraction when query mentions CFTR or HGVS protein notation
    if "CFTR" in upper or "P." in upper:
        m = _CODON_RE.search(term)
        if m:
            codon = int(m.group(1))
            if 1 <= codon <= 1480:
                return {
                    "allele": m.group(0),
                    "hgvs_c": "not stated",
                    "hgvs_p": m.group(0) if m.group(0).startswith("p.") else f"codon {codon}",
                    "codon": codon,
                    "exon": exon_for_codon(codon),
                    "domain": domain_for_codon(codon),
                    "cftr_class": "not stated",
                    "transcript": REFSEQ_TRANSCRIPT,
                    "uniprot": UNIPROT_ACCESSION,
                }
    return None
