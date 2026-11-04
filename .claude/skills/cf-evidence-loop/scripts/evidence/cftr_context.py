"""Deterministic CFTR RefSeq (NM_000492.4) exon, UniProt (P13569) domain, modulator & Cryo-EM context.

Provides a zero-network, standard-library structural lookup for canonical CFTR variants and codons
so `brief variant` and the `cftr-context` command can annotate protein domain boundaries, exon numbers,
and mutation class context with explicit primary source provenance (UniProt P13569, RefSeq NM_000492.4, CFTR2).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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

# Curated high-frequency CFTR alleles with exact HGVS, exon, domain, and mechanistic class (CFTR2 / CFFPR)
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
    "621+1G>T": {
        "allele": "621+1G>T",
        "hgvs_c": "c.489+1G>T",
        "hgvs_p": "canonical splice donor disruption (exon 4 skipping)",
        "codon": None,
        "exon": 4,
        "domain": "Intron 4 (canonical 5' donor splice site)",
        "cftr_class": "Class I (splice donor site disruption / loss of full-length protein)",
    },
    "1717-1G>A": {
        "allele": "1717-1G>A",
        "hgvs_c": "c.1585-1G>A",
        "hgvs_p": "canonical splice acceptor disruption (exon 12 skipping)",
        "codon": None,
        "exon": 12,
        "domain": "Intron 11 (canonical 3' acceptor splice site)",
        "cftr_class": "Class I (splice acceptor site disruption / out-of-frame exon 12 skip)",
    },
    "2789+5G>A": {
        "allele": "2789+5G>A",
        "hgvs_c": "c.2657+5G>A",
        "hgvs_p": "alternative splice donor efficiency reduction",
        "codon": None,
        "exon": 15,
        "domain": "Intron 15 (5' donor splice region)",
        "cftr_class": "Class V (reduced normal splicing efficiency / partial WT CFTR)",
    },
    "3120+1G>A": {
        "allele": "3120+1G>A",
        "hgvs_c": "c.2988+1G>A",
        "hgvs_p": "canonical splice donor disruption (exon 18 skipping)",
        "codon": None,
        "exon": 18,
        "domain": "Intron 18 (canonical 5' donor splice site)",
        "cftr_class": "Class I (splice donor site disruption)",
    },
    "I507DEL": {
        "allele": "I507del",
        "hgvs_c": "c.1519_1521delATC",
        "hgvs_p": "p.Ile507del",
        "codon": 507,
        "exon": 11,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class II (NBD1 folding and processing defect)",
    },
    "A455E": {
        "allele": "A455E",
        "hgvs_c": "c.1364C>A",
        "hgvs_p": "p.Ala455Glu",
        "codon": 455,
        "exon": 10,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class V (reduced mature protein synthesis / partial processing)",
    },
    "S549N": {
        "allele": "S549N",
        "hgvs_c": "c.1646G>A",
        "hgvs_p": "p.Ser549Asn",
        "codon": 549,
        "exon": 12,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class III (ATP signature motif gating defect)",
    },
    "V520F": {
        "allele": "V520F",
        "hgvs_c": "c.1558G>T",
        "hgvs_p": "p.Val520Phe",
        "codon": 520,
        "exon": 11,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class II (NBD1-ICL4 interface trafficking defect)",
    },
    "R334W": {
        "allele": "R334W",
        "hgvs_c": "c.1000C>T",
        "hgvs_p": "p.Arg334Trp",
        "codon": 334,
        "exon": 8,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class IV (pore architecture / reduced single-channel conductance)",
    },
    "R347P": {
        "allele": "R347P",
        "hgvs_c": "c.1040G>C",
        "hgvs_p": "p.Arg347Pro",
        "codon": 347,
        "exon": 8,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class IV (TM6 pore helix selectivity / reduced conductance)",
    },
    "R1162X": {
        "allele": "R1162X",
        "hgvs_c": "c.3484C>T",
        "hgvs_p": "p.Arg1162Ter",
        "codon": 1162,
        "exon": 21,
        "domain": "TMD2-NBD2 linker",
        "cftr_class": "Class I (premature termination codon in cytoplasmic linker)",
    },
    "2184DELA": {
        "allele": "2184delA",
        "hgvs_c": "c.2052delA",
        "hgvs_p": "p.Lys684fs",
        "codon": 684,
        "exon": 14,
        "domain": "R-domain (Regulatory Domain)",
        "cftr_class": "Class I (frameshift leading to premature stop)",
    },
    "3659DELC": {
        "allele": "3659delC",
        "hgvs_c": "c.3527delC",
        "hgvs_p": "p.Thr1176fs",
        "codon": 1176,
        "exon": 22,
        "domain": "TMD2-NBD2 linker",
        "cftr_class": "Class I (frameshift truncating NBD2 catalytic domain)",
    },
    "G85E": {
        "allele": "G85E",
        "hgvs_c": "c.254G>A",
        "hgvs_p": "p.Gly85Glu",
        "codon": 85,
        "exon": 3,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class II (severe TM1 misfolding and trafficking defect)",
    },
    "D1152H": {
        "allele": "D1152H",
        "hgvs_c": "c.3454G>C",
        "hgvs_p": "p.Asp1152His",
        "codon": 1152,
        "exon": 21,
        "domain": "TMD2-NBD2 linker",
        "cftr_class": "Class IV (reduced channel conductance and altered gating)",
    },
    "Y1092X": {
        "allele": "Y1092X",
        "hgvs_c": "c.3276C>A",
        "hgvs_p": "p.Tyr1092Ter",
        "codon": 1092,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class I (premature termination codon in TM12)",
    },
    "M1101K": {
        "allele": "M1101K",
        "hgvs_c": "c.3302T>A",
        "hgvs_p": "p.Met1101Lys",
        "codon": 1101,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class II (misfolding defect in TMD2)",
    },
    "R560T": {
        "allele": "R560T",
        "hgvs_c": "c.1679G>C",
        "hgvs_p": "p.Arg560Thr",
        "codon": 560,
        "exon": 13,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class II (severe NBD1 thermal destabilization and trafficking arrest)",
    },
    "L206W": {
        "allele": "L206W",
        "hgvs_c": "c.617T>G",
        "hgvs_p": "p.Leu206Trp",
        "codon": 206,
        "exon": 6,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class II (TM3 membrane insertion and folding defect)",
    },
    "1898+1G>A": {
        "allele": "1898+1G>A",
        "hgvs_c": "c.1766+1G>A",
        "hgvs_p": "canonical splice donor disruption (exon 13 skipping)",
        "codon": None,
        "exon": 13,
        "domain": "Intron 13 (canonical 5' donor splice site)",
        "cftr_class": "Class I (splice donor site disruption / loss of full-length transcript)",
    },
    "S1251N": {
        "allele": "S1251N",
        "hgvs_c": "c.3752G>A",
        "hgvs_p": "p.Ser1251Asn",
        "codon": 1251,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 ATP-dependent channel gating defect; potentiator-responsive)",
    },
    "G1244E": {
        "allele": "G1244E",
        "hgvs_c": "c.3731G>A",
        "hgvs_p": "p.Gly1244Glu",
        "codon": 1244,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 Walker A signature gating defect; potentiator-responsive)",
    },
    "G178R": {
        "allele": "G178R",
        "hgvs_c": "c.532G>A",
        "hgvs_p": "p.Gly178Arg",
        "codon": 178,
        "exon": 5,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class III (TM3 pore coupling gating defect; potentiator-responsive)",
    },
    "S549R": {
        "allele": "S549R",
        "hgvs_c": "c.1645A>C",
        "hgvs_p": "p.Ser549Arg",
        "codon": 549,
        "exon": 12,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class III (NBD1 ATP signature motif gating defect; potentiator-responsive)",
    },
    "Q1412X": {
        "allele": "Q1412X",
        "hgvs_c": "c.4234C>T",
        "hgvs_p": "p.Gln1412Ter",
        "codon": 1412,
        "exon": 26,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class VI (accelerated cell-surface turnover / C-terminal truncation)",
    },
    "G1349D": {
        "allele": "G1349D",
        "hgvs_c": "c.4046G>A",
        "hgvs_p": "p.Gly1349Asp",
        "codon": 1349,
        "exon": 25,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 ATP signature motif LSGGQ gating defect; potentiator-responsive)",
    },
    "P67L": {
        "allele": "P67L",
        "hgvs_c": "c.200C>T",
        "hgvs_p": "p.Pro67Leu",
        "codon": 67,
        "exon": 3,
        "domain": "N-terminal lasso motif",
        "cftr_class": "Class IV (N-terminal / TM1 misprocessing & reduced conductance; modulator-responsive)",
    },
    "R1066C": {
        "allele": "R1066C",
        "hgvs_c": "c.3196C>T",
        "hgvs_p": "p.Arg1066Cys",
        "codon": 1066,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class II (severe ICL4 pocket destabilization and trafficking arrest)",
    },
    "R75X": {
        "allele": "R75X",
        "hgvs_c": "c.223C>T",
        "hgvs_p": "p.Arg75Ter",
        "codon": 75,
        "exon": 3,
        "domain": "N-terminal lasso motif",
        "cftr_class": "Class I (premature termination codon in N-terminal lasso)",
    },
    "711+1G>T": {
        "allele": "711+1G>T",
        "hgvs_c": "c.579+1G>T",
        "hgvs_p": "canonical splice donor disruption (exon 5 skipping)",
        "codon": None,
        "exon": 5,
        "domain": "Intron 5 (canonical 5' donor splice site)",
        "cftr_class": "Class I (splice donor site disruption / loss of full-length protein)",
    },
    "2183AA>G": {
        "allele": "2183AA>G",
        "hgvs_c": "c.2051_2052delAAinsG",
        "hgvs_p": "p.Lys684fs",
        "codon": 684,
        "exon": 14,
        "domain": "R-domain (Regulatory Domain)",
        "cftr_class": "Class I (frameshift leading to premature stop / NMD substrate)",
    },
    "394DELTT": {
        "allele": "394delTT",
        "hgvs_c": "c.262_263delTT",
        "hgvs_p": "p.Leu88fs",
        "codon": 88,
        "exon": 3,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class I (N-terminal frameshift / loss of functional protein)",
    },
    "1078DELT": {
        "allele": "1078delT",
        "hgvs_c": "c.948delT",
        "hgvs_p": "p.Phe316fs",
        "codon": 316,
        "exon": 8,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class I (TM5 frameshift / premature truncation)",
    },
    "R117C": {
        "allele": "R117C",
        "hgvs_c": "c.349C>T",
        "hgvs_p": "p.Arg117Cys",
        "codon": 117,
        "exon": 4,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class IV (external pore loop ECL1 / reduced chloride conductance)",
    },
    "S1255P": {
        "allele": "S1255P",
        "hgvs_c": "c.3763T>C",
        "hgvs_p": "p.Ser1255Pro",
        "codon": 1255,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 ATP-binding cassette gating defect; potentiator-responsive)",
    },
    "Y122X": {
        "allele": "Y122X",
        "hgvs_c": "c.366T>A",
        "hgvs_p": "p.Tyr122Ter",
        "codon": 122,
        "exon": 4,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class I (premature termination codon in ECL1/TM2)",
    },
    "Q493X": {
        "allele": "Q493X",
        "hgvs_c": "c.1477C>T",
        "hgvs_p": "p.Gln493Ter",
        "codon": 493,
        "exon": 11,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class I (premature termination codon in NBD1 / NMD substrate)",
    },
    "E60X": {
        "allele": "E60X",
        "hgvs_c": "c.178G>T",
        "hgvs_p": "p.Glu60Ter",
        "codon": 60,
        "exon": 3,
        "domain": "N-terminal lasso motif",
        "cftr_class": "Class I (N-terminal premature termination codon / NMD substrate)",
    },
    "R1158X": {
        "allele": "R1158X",
        "hgvs_c": "c.3472C>T",
        "hgvs_p": "p.Arg1158Ter",
        "codon": 1158,
        "exon": 21,
        "domain": "TMD2-NBD2 linker",
        "cftr_class": "Class I (premature termination codon in cytoplasmic linker)",
    },
    "R347H": {
        "allele": "R347H",
        "hgvs_c": "c.1040G>A",
        "hgvs_p": "p.Arg347His",
        "codon": 347,
        "exon": 8,
        "domain": "TMD1 (Transmembrane Domain 1 / TM6 pore)",
        "cftr_class": "Class IV (reduced channel conductance in TM6 pore; Kalydeco-responsive)",
    },
    "CFTRDELE2,3": {
        "allele": "CFTRdele2,3",
        "hgvs_c": "c.54-5940_273+10250del21kb",
        "hgvs_p": "p.Met1_Lys95del",
        "codon": None,
        "exon": 2,
        "domain": "N-terminal lasso motif / TMD1 (exons 2-3 deletion)",
        "cftr_class": "Class I (21kb founder deletion / loss of initiation codon and lasso)",
        "aliases": ["dele2,3", "dele2,3(21kb)", "CFTRdele2,3(21kb)", "del2,3"],
    },
    "R1070W": {
        "allele": "R1070W",
        "hgvs_c": "c.3208C>T",
        "hgvs_p": "p.Arg1070Trp",
        "codon": 1070,
        "exon": 20,
        "domain": "TMD2 (ICL4 coupling loop)",
        "cftr_class": "Class II (ICL4-NBD1 interface allele; classic F508del structural suppressor)",
    },
    "W1089X": {
        "allele": "W1089X",
        "hgvs_c": "c.3267G>A",
        "hgvs_p": "p.Trp1089Ter",
        "codon": 1089,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2 / TM11)",
        "cftr_class": "Class I (premature termination codon in TM11 / NMD substrate)",
    },
    "E92K": {
        "allele": "E92K",
        "hgvs_c": "c.274G>A",
        "hgvs_p": "p.Glu92Lys",
        "codon": 92,
        "exon": 4,
        "domain": "TMD1 (Transmembrane Domain 1 / TM1)",
        "cftr_class": "Class II (misfolding/processing defect in TM1; prevalent Slavic founder variant)",
    },
    "S492F": {
        "allele": "S492F",
        "hgvs_c": "c.1475C>T",
        "hgvs_p": "p.Ser492Phe",
        "codon": 492,
        "exon": 11,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class II (NBD1 core folding destabilization and processing arrest)",
    },
    "G1249R": {
        "allele": "G1249R",
        "hgvs_c": "c.3745G>A",
        "hgvs_p": "p.Gly1249Arg",
        "codon": 1249,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 Walker A signature gating defect; ivacaftor-responsive)",
    },
    "C524X": {
        "allele": "C524X",
        "hgvs_c": "c.1572C>A",
        "hgvs_p": "p.Cys524Ter",
        "codon": 524,
        "exon": 11,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class I (premature termination codon in NBD1 / NMD substrate)",
    },
    "W846X": {
        "allele": "W846X",
        "hgvs_c": "c.2538G>A",
        "hgvs_p": "p.Trp846Ter",
        "codon": 846,
        "exon": 15,
        "domain": "TMD2 (Transmembrane Domain 2 / TM7)",
        "cftr_class": "Class I (premature termination codon in TM7 / NMD substrate)",
    },
    "R1066H": {
        "allele": "R1066H",
        "hgvs_c": "c.3197G>A",
        "hgvs_p": "p.Arg1066His",
        "codon": 1066,
        "exon": 20,
        "domain": "TMD2 (ICL4 coupling loop)",
        "cftr_class": "Class II (severe ICL4 coupling loop destabilization and trafficking arrest)",
    },
    "S1255X": {
        "allele": "S1255X",
        "hgvs_c": "c.3764C>A",
        "hgvs_p": "p.Ser1255Ter",
        "codon": 1255,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class I (premature termination codon in NBD2 / NMD substrate)",
        "aliases": ["S1255X", "p.Ser1255Ter", "p.Ser1255*", "c.3764C>A"],
    },
    "3905INST": {
        "allele": "3905insT",
        "hgvs_c": "c.3773dupT",
        "hgvs_p": "p.Leu1258PhefsTer7",
        "codon": 1258,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class I (1-bp frameshift duplication in NBD2 introducing premature termination)",
        "aliases": ["3905insT", "3905INST", "c.3773dupT", "c.3773dup", "p.Leu1258PhefsTer7"],
    },
    "1811+1.6KBA>G": {
        "allele": "1811+1.6kbA>G",
        "hgvs_c": "c.1680-883A>G",
        "hgvs_p": "p.(=) (cryptic pseudoexon insertion with premature termination)",
        "codon": None,
        "exon": 13,
        "domain": "Intron 12 (deep intronic cryptic splice site creating 49-bp pseudoexon)",
        "cftr_class": "Class V (cryptic splice site activation; low residual normal transcript)",
        "aliases": ["1811+1.6kbA->G", "1811+1.6kbA>G", "c.1680-883A>G", "1811+1.6kbA-G"],
    },
    "S945L": {
        "allele": "S945L",
        "hgvs_c": "c.2834C>T",
        "hgvs_p": "p.Ser945Leu",
        "codon": 945,
        "exon": 18,
        "domain": "TMD2 (Transmembrane Domain 2 / TM8)",
        "cftr_class": "Class V / Class II (TM8 misprocessing and reduced trafficking; ivacaftor and ETI responsive)",
        "aliases": ["S945L", "p.Ser945Leu", "c.2834C>T"],
    },
    "G970R": {
        "allele": "G970R",
        "hgvs_c": "c.2908G>A",
        "hgvs_p": "p.Gly970Arg",
        "codon": 970,
        "exon": 18,
        "domain": "TMD2 (Transmembrane Domain 2 / TM8)",
        "cftr_class": "Class III (TM8 gating/conduction defect; potentiator-responsive)",
        "aliases": ["G970R", "p.Gly970Arg", "c.2908G>A"],
    },
    "F1052V": {
        "allele": "F1052V",
        "hgvs_c": "c.3154T>G",
        "hgvs_p": "p.Phe1052Val",
        "codon": 1052,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2 / TM10)",
        "cftr_class": "Class IV (reduced conductance / residual function; modulator-responsive)",
        "aliases": ["F1052V", "p.Phe1052Val", "c.3154T>G"],
    },
    "3272-26A>G": {
        "allele": "3272-26A>G",
        "hgvs_c": "c.3140-26A>G",
        "hgvs_p": "p.(=) (cryptic splice acceptor creating alternative transcript with PTC)",
        "codon": None,
        "exon": 20,
        "domain": "Intron 19 (cryptic splice acceptor 26-bp upstream of exon 20)",
        "cftr_class": "Class V (cryptic splice acceptor generating alternative transcript; residual normal transcript; modulator-responsive)",
        "aliases": ["3272-26A->G", "3272-26A>G", "c.3140-26A>G", "3272-26"],
    },
    "L927P": {
        "allele": "L927P",
        "hgvs_c": "c.2780T>C",
        "hgvs_p": "p.Leu927Pro",
        "codon": 927,
        "exon": 17,
        "domain": "TMD2 (Transmembrane Domain 2 / TM8)",
        "cftr_class": "Class II (TM8 proline insertion causing helix kink and trafficking arrest)",
        "aliases": ["L927P", "p.Leu927Pro", "c.2780T>C"],
    },
    "D579G": {
        "allele": "D579G",
        "hgvs_c": "c.1736A>G",
        "hgvs_p": "p.Asp579Gly",
        "codon": 579,
        "exon": 13,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class IV / Class II (NBD1 surface charge disruption causing reduced conductance and processing defect)",
        "aliases": ["D579G", "p.Asp579Gly", "c.1736A>G"],
    },
    "H1085R": {
        "allele": "H1085R",
        "hgvs_c": "c.3254A>G",
        "hgvs_p": "p.His1085Arg",
        "codon": 1085,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2 / TM11)",
        "cftr_class": "Class II (TM11 helical distortion causing severe misprocessing and trafficking defect)",
        "aliases": ["H1085R", "p.His1085Arg", "c.3254A>G"],
    },
    "K1060T": {
        "allele": "K1060T",
        "hgvs_c": "c.3179A>C",
        "hgvs_p": "p.Lys1060Thr",
        "codon": 1060,
        "exon": 20,
        "domain": "TMD2 (ICL4 coupling loop)",
        "cftr_class": "Class II / Class V (ICL4 coupling loop processing defect; responsive to modulators)",
        "aliases": ["K1060T", "p.Lys1060Thr", "c.3179A>C"],
    },
    "G314E": {
        "allele": "G314E",
        "hgvs_c": "c.941G>A",
        "hgvs_p": "p.Gly314Glu",
        "codon": 314,
        "exon": 8,
        "domain": "TMD1 (Transmembrane Domain 1 / TM5)",
        "cftr_class": "Class II / Class IV (TM5 pore helix charge insertion leading to misfolding and reduced conductance)",
        "aliases": ["G314E", "p.Gly314Glu", "c.941G>A"],
    },
    "P5L": {
        "allele": "P5L",
        "hgvs_c": "c.14C>T",
        "hgvs_p": "p.Pro5Leu",
        "codon": 5,
        "exon": 1,
        "domain": "N-terminal lasso motif",
        "cftr_class": "Class IV (N-terminal lasso flexibility alteration; mild phenotype with residual conductance)",
        "aliases": ["P5L", "p.Pro5Leu", "c.14C>T"],
    },
    "W57G": {
        "allele": "W57G",
        "hgvs_c": "c.169T>G",
        "hgvs_p": "p.Trp57Gly",
        "codon": 57,
        "exon": 3,
        "domain": "N-terminal lasso motif",
        "cftr_class": "Class II (N-terminal lasso hydrophobic core disruption and membrane insertion defect)",
        "aliases": ["W57G", "p.Trp57Gly", "c.169T>G"],
    },
    "R1070Q": {
        "allele": "R1070Q",
        "hgvs_c": "c.3209G>A",
        "hgvs_p": "p.Arg1070Gln",
        "codon": 1070,
        "exon": 20,
        "domain": "TMD2 (ICL4 coupling loop)",
        "cftr_class": "Class II (ICL4-NBD1 coupling interface alteration; defective folding and maturation)",
        "aliases": ["R1070Q", "p.Arg1070Gln", "c.3209G>A"],
    },
    "E1371Q": {
        "allele": "E1371Q",
        "hgvs_c": "c.4111G>C",
        "hgvs_p": "p.Glu1371Gln",
        "codon": 1371,
        "exon": 25,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (catalytic Walker B glutamate substitution eliminating ATP hydrolysis; traps CFTR in active dimerized open state; used in Cryo-EM structures 9DW8, 9DW9)",
        "aliases": ["E1371Q", "p.Glu1371Gln", "c.4111G>C"],
    },
    "K464N": {
        "allele": "K464N",
        "hgvs_c": "c.1392G>T",
        "hgvs_p": "p.Lys464Asn",
        "codon": 464,
        "exon": 10,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class III (NBD1 Walker A motif substitution impairing ATP binding and catalytic dimerization)",
        "aliases": ["K464N", "p.Lys464Asn", "c.1392G>T"],
    },
    "D1370N": {
        "allele": "D1370N",
        "hgvs_c": "c.4108G>A",
        "hgvs_p": "p.Asp1370Asn",
        "codon": 1370,
        "exon": 25,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 Walker B catalytic site Mg2+ coordination defect)",
        "aliases": ["D1370N", "p.Asp1370Asn", "c.4108G>A"],
    },
    "G673X": {
        "allele": "G673X",
        "hgvs_c": "c.2017G>T",
        "hgvs_p": "p.Gly673Ter",
        "codon": 673,
        "exon": 14,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class I (premature termination codon in NBD1 / NMD substrate)",
        "aliases": ["G673X", "p.Gly673Ter", "c.2017G>T"],
    },
    "E1104X": {
        "allele": "E1104X",
        "hgvs_c": "c.3310G>T",
        "hgvs_p": "p.Glu1104Ter",
        "codon": 1104,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class I (premature termination codon in TM12 / NMD substrate)",
        "aliases": ["E1104X", "p.Glu1104Ter", "c.3310G>T"],
    },
    "R792X": {
        "allele": "R792X",
        "hgvs_c": "c.2374C>T",
        "hgvs_p": "p.Arg792Ter",
        "codon": 792,
        "exon": 14,
        "domain": "R-domain (Regulatory Domain)",
        "cftr_class": "Class I (premature termination codon in R-domain / NMD substrate)",
        "aliases": ["R792X", "p.Arg792Ter", "c.2374C>T"],
    },
    "Q890X": {
        "allele": "Q890X",
        "hgvs_c": "c.2668C>T",
        "hgvs_p": "p.Gln890Ter",
        "codon": 890,
        "exon": 16,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class I (premature termination codon in TM7 / NMD substrate)",
        "aliases": ["Q890X", "p.Gln890Ter", "c.2668C>T"],
    },
    "R352Q": {
        "allele": "R352Q",
        "hgvs_c": "c.1055G>A",
        "hgvs_p": "p.Arg352Gln",
        "codon": 352,
        "exon": 8,
        "domain": "TMD1-NBD1 linker / TM6 cytoplasmic boundary",
        "cftr_class": "Class IV (pore architecture alteration; eliminates essential R352-D993 electrostatic salt bridge governing anion permeation and open-pore stability)",
        "aliases": ["R352Q", "p.Arg352Gln", "c.1055G>A"],
    },
    "D993Y": {
        "allele": "D993Y",
        "hgvs_c": "c.2977G>T",
        "hgvs_p": "p.Asp993Tyr",
        "codon": 993,
        "exon": 18,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class IV (pore architecture alteration; disrupts canonical R352-D993 intra-pore salt bridge required for normal chloride permeation)",
        "aliases": ["D993Y", "p.Asp993Tyr", "c.2977G>T"],
    },
    "V232D": {
        "allele": "V232D",
        "hgvs_c": "c.695T>A",
        "hgvs_p": "p.Val232Asp",
        "codon": 232,
        "exon": 6,
        "domain": "TMD1 (Transmembrane Domain 1)",
        "cftr_class": "Class II (misfolding due to charged aspartate insertion into hydrophobic TM4 core disrupting TM2-TM4 packing interface)",
        "aliases": ["V232D", "p.Val232Asp", "c.695T>A"],
    },
    "Q39X": {
        "allele": "Q39X",
        "hgvs_c": "c.115C>T",
        "hgvs_p": "p.Gln39Ter",
        "codon": 39,
        "exon": 2,
        "domain": "N-terminal lasso motif",
        "cftr_class": "Class I (premature termination codon in exon 2 / NMD substrate; severe Mediterranean nonsense allele)",
        "aliases": ["Q39X", "p.Gln39Ter", "c.115C>T"],
    },
    "W401X": {
        "allele": "W401X",
        "hgvs_c": "c.1203G>A",
        "hgvs_p": "p.Trp401Ter",
        "codon": 401,
        "exon": 9,
        "domain": "NBD1 (Nucleotide-Binding Domain 1)",
        "cftr_class": "Class I (premature termination codon in NBD1 / NMD substrate)",
        "aliases": ["W401X", "p.Trp401Ter", "c.1203G>A"],
    },
    "R1102X": {
        "allele": "R1102X",
        "hgvs_c": "c.3304C>T",
        "hgvs_p": "p.Arg1102Ter",
        "codon": 1102,
        "exon": 20,
        "domain": "TMD2 (Transmembrane Domain 2)",
        "cftr_class": "Class I (premature termination codon in TM12 / NMD substrate)",
        "aliases": ["R1102X", "p.Arg1102Ter", "c.3304C>T"],
    },
    "E831X": {
        "allele": "E831X",
        "hgvs_c": "c.2491G>T",
        "hgvs_p": "p.Glu831Ter",
        "codon": 831,
        "exon": 14,
        "domain": "R-domain (Regulatory Domain)",
        "cftr_class": "Class I (premature termination codon in R-domain / NMD substrate)",
        "aliases": ["E831X", "p.Glu831Ter", "c.2491G>T"],
    },
    "K1250A": {
        "allele": "K1250A",
        "hgvs_c": "c.3748A>G",
        "hgvs_p": "p.Lys1250Ala",
        "codon": 1250,
        "exon": 23,
        "domain": "NBD2 (Nucleotide-Binding Domain 2)",
        "cftr_class": "Class III (NBD2 Walker A catalytic lysine substitution; abolishes ATP hydrolysis and locks dimer in closed or open conformation)",
        "aliases": ["K1250A", "p.Lys1250Ala", "c.3748A>G"],
    },
}

# Curated approved & investigational CFTR modulators with active ingredients, NDAs, and AH-4 boxed warning boundaries
CANONICAL_MODULATORS: dict[str, dict[str, Any]] = {
    "KALYDECO": {
        "brand": "Kalydeco",
        "active_ingredients": ["ivacaftor"],
        "molecular_codes": ["VX-770"],
        "mechanistic_class": "CFTR Potentiator (increases channel open probability Po at cell surface)",
        "fda_nda": "NDA 203188",
        "sponsor": "Vertex Pharmaceuticals",
        "approval_year": 2012,
        "spl_boxed_warning": "not stated (transaminase monitoring in Section 5 Warnings and Precautions)",
        "primary_pdb": "6MSM",
        "target_mechanism": "Binds transmembrane helices TM8/TM9/TM10/TM11 to stabilize open channel pore",
        "aliases": ["KALYDECO", "IVACAFTOR", "VX-770", "VX770", "IVA"],
    },
    "ORKAMBI": {
        "brand": "Orkambi",
        "active_ingredients": ["lumacaftor", "ivacaftor"],
        "molecular_codes": ["VX-809", "VX-770"],
        "mechanistic_class": "Type I CFTR Corrector + Potentiator (MSD1/NBD1 chaperone + gating)",
        "fda_nda": "NDA 206038",
        "sponsor": "Vertex Pharmaceuticals",
        "approval_year": 2015,
        "spl_boxed_warning": "not stated (respiratory events and transaminase monitoring in Section 5)",
        "primary_pdb": "5UAK",
        "target_mechanism": "Stabilizes MSD1 and ICL1 pocket to rescue F508del trafficking; potentiated by ivacaftor",
        "aliases": ["ORKAMBI", "LUMACAFTOR", "VX-809", "VX809", "LUMACAFTOR/IVACAFTOR", "LUM/IVA"],
    },
    "SYMDEKO": {
        "brand": "Symdeko",
        "active_ingredients": ["tezacaftor", "ivacaftor"],
        "molecular_codes": ["VX-661", "VX-770"],
        "mechanistic_class": "Type I CFTR Corrector + Potentiator (second-generation NBD1-MSD chaperone + gating)",
        "fda_nda": "NDA 210491",
        "sponsor": "Vertex Pharmaceuticals",
        "approval_year": 2018,
        "spl_boxed_warning": "not stated (transaminase monitoring in Section 5 Warnings and Precautions)",
        "primary_pdb": "8EIQ",
        "target_mechanism": "Binds TMD1 pocket stabilizing NBD1-ICL1/ICL4 interface without CYP3A induction",
        "aliases": ["SYMDEKO", "SYMKEVI", "TEZACAFTOR", "VX-661", "VX661", "TEZACAFTOR/IVACAFTOR", "TEZ/IVA"],
    },
    "TRIKAFTA": {
        "brand": "Trikafta",
        "active_ingredients": ["elexacaftor", "tezacaftor", "ivacaftor"],
        "molecular_codes": ["VX-445", "VX-661", "VX-770"],
        "mechanistic_class": "Next-Generation Type II Corrector + Type I Corrector + Potentiator (cooperative dual-corrector chaperone + gating)",
        "fda_nda": "NDA 212273",
        "sponsor": "Vertex Pharmaceuticals",
        "approval_year": 2019,
        "spl_boxed_warning": "drug-induced liver injury (DILI) and acute hepatic failure (baseline and periodic ALT/AST and bilirubin monitoring required)",
        "primary_pdb": "8EIQ",
        "target_mechanism": "Elexacaftor binds TM2/TM3/TM4/TM10/TM11 while tezacaftor binds TM1/TM2/TM3/TM6, providing cooperative allosteric rescue of F508del",
        "aliases": ["TRIKAFTA", "KAFTRIO", "ELEXACAFTOR", "VX-445", "VX445", "ETI", "ELEXACAFTOR/TEZACAFTOR/IVACAFTOR", "ELX/TEZ/IVA"],
    },
    "ALYFTREK": {
        "brand": "Alyftrek",
        "active_ingredients": ["vanzacaftor", "tezacaftor", "deutivacaftor"],
        "molecular_codes": ["VX-121", "VX-661", "VX-561"],
        "mechanistic_class": "Once-Daily Next-Generation Corrector + Type I Corrector + Deuterated Potentiator",
        "fda_nda": "NDA 218730",
        "sponsor": "Vertex Pharmaceuticals",
        "approval_year": 2025,
        "spl_boxed_warning": "drug-induced liver injury (DILI) and acute hepatic failure",
        "primary_pdb": "8EIQ",
        "target_mechanism": "High-potency next-generation corrector vanzacaftor with deuterated potentiator deutivacaftor for once-daily dosing",
        "aliases": ["ALYFTREK", "VANZACAFTOR", "VX-121", "VX121", "DEUTIVACAFTOR", "VX-561", "VX561", "VTD", "VANZACAFTOR/TEZACAFTOR/DEUTIVACAFTOR", "VNZ/TEZ/D-IVA"],
    },
}

# Curated benchmark Cryo-EM coordinate structures for human CFTR
CANONICAL_PDB_STRUCTURES: dict[str, dict[str, Any]] = {
    "6MSM": {
        "pdb_id": "6MSM",
        "title": "Structure of human CFTR phosphorylated and ATP-bound with potentiator VX-770 (ivacaftor)",
        "conformation": "Phosphorylated, ATP-bound active channel open state",
        "ligands": ["VX-770 (ivacaftor)", "ATP", "Mg2+"],
        "resolution_angstrom": 3.2,
        "method": "Cryo-EM",
        "reference": "Liu et al., Science 2019 (DOI: 10.1126/science.aaw7611)",
    },
    "5UAK": {
        "pdb_id": "5UAK",
        "title": "Cryo-EM structure of human dephosphorylated, ATP-free CFTR",
        "conformation": "Dephosphorylated, ATP-free inward-facing quiescent/inactive state",
        "ligands": [],
        "resolution_angstrom": 3.9,
        "method": "Cryo-EM",
        "reference": "Liu et al., Cell 2017 (DOI: 10.1016/j.cell.2017.02.024)",
    },
    "6O2P": {
        "pdb_id": "6O2P",
        "title": "Cryo-EM structure of human CFTR in ATP-bound conformation",
        "conformation": "Phosphorylated, ATP-bound active channel state",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 3.3,
        "method": "Cryo-EM",
        "reference": "Zhang et al., Cell 2018 (DOI: 10.1016/j.cell.2018.02.049)",
    },
    "7SVD": {
        "pdb_id": "7SVD",
        "title": "Cryo-EM structure of human CFTR G551D mutant channel in complex with ATP",
        "conformation": "G551D gating-defective catalytic site uncoupled conformation",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Zhang & Chen, Cell 2021 (DOI: 10.1016/j.cell.2021.11.014)",
    },
    "7SV7": {
        "pdb_id": "7SV7",
        "title": "Cryo-EM structure of human CFTR phosphorylated and ATP-bound channel open state",
        "conformation": "Phosphorylated, ATP-bound active channel open state",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 3.2,
        "method": "Cryo-EM",
        "reference": "Zhang & Chen, Cell 2021 (DOI: 10.1016/j.cell.2021.11.014)",
    },
    "8EIQ": {
        "pdb_id": "8EIQ",
        "title": "Human CFTR complex with elexacaftor (VX-445), tezacaftor (VX-661), and ivacaftor (VX-770)",
        "conformation": "Trikafta (ETI)-bound ternary cooperative conformation",
        "ligands": ["VX-445 (elexacaftor)", "VX-661 (tezacaftor)", "VX-770 (ivacaftor)", "ATP"],
        "resolution_angstrom": 2.9,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.abq7985)",
    },
    "8EJ1": {
        "pdb_id": "8EJ1",
        "title": "Structure of uncorrected human F508del CFTR showing NBD1-ICL4 interface collapse",
        "conformation": "Uncorrected F508del apo conformation",
        "ligands": [],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.abq7985)",
    },
    "8EIZ": {
        "pdb_id": "8EIZ",
        "title": "Cryo-EM structure of human CFTR in complex with elexacaftor (VX-445) and tezacaftor (VX-661)",
        "conformation": "Dual corrector-bound ternary pre-open conformation",
        "ligands": ["VX-445 (elexacaftor)", "VX-661 (tezacaftor)", "ATP"],
        "resolution_angstrom": 3.0,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.abq7985)",
    },
    "7SVR": {
        "pdb_id": "7SVR",
        "title": "Cryo-EM structure of human CFTR G551D mutant channel in dephosphorylated, ATP-free state",
        "conformation": "G551D dephosphorylated inward-facing quiescent/inactive state",
        "ligands": [],
        "resolution_angstrom": 3.6,
        "method": "Cryo-EM",
        "reference": "Zhang & Chen, Cell 2021 (DOI: 10.1016/j.cell.2021.11.014)",
    },
    "8EIA": {
        "pdb_id": "8EIA",
        "title": "Cryo-EM structure of human CFTR in complex with tezacaftor (VX-661)",
        "conformation": "Tezacaftor (Type I corrector)-bound pre-open conformation",
        "ligands": ["VX-661 (tezacaftor)", "ATP"],
        "resolution_angstrom": 3.2,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "8EIB": {
        "pdb_id": "8EIB",
        "title": "Cryo-EM structure of human CFTR in complex with elexacaftor (VX-445)",
        "conformation": "Elexacaftor (Type II corrector)-bound pre-open conformation",
        "ligands": ["VX-445 (elexacaftor)", "ATP"],
        "resolution_angstrom": 3.1,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "8EIU": {
        "pdb_id": "8EIU",
        "title": "Cryo-EM structure of human CFTR in complex with lumacaftor (VX-809)",
        "conformation": "Lumacaftor (first-generation Type I corrector)-bound pre-open conformation",
        "ligands": ["VX-809 (lumacaftor)", "ATP"],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "8EIO": {
        "pdb_id": "8EIO",
        "title": "Cryo-EM structure of human F508del CFTR in complex with elexacaftor (VX-445), lumacaftor (VX-809), and ATP",
        "conformation": "Phosphorylated F508del dual-corrected active/pre-open conformation",
        "ligands": ["VX-445 (elexacaftor)", "VX-809 (lumacaftor)", "ATP", "Mg2+"],
        "resolution_angstrom": 2.8,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "9MXL": {
        "pdb_id": "9MXL",
        "title": "Cryo-EM structure of phosphorylated human CFTR in complex with (R)-BPO-27 and ATP",
        "conformation": "Phosphorylated, ATP-bound active state with pore-blocker (R)-BPO-27",
        "ligands": ["(R)-BPO-27", "ATP", "Mg2+"],
        "resolution_angstrom": 2.1,
        "method": "Cryo-EM",
        "reference": "Young et al., Nat Commun 2025 (DOI: 10.1038/s41467-025-62199-7)",
    },
    "6O1V": {
        "pdb_id": "6O1V",
        "title": "Cryo-EM structure of human CFTR in complex with potentiator GLPG1837 and ATP",
        "conformation": "Phosphorylated, ATP-bound CFTR with potentiator GLPG1837 bound at TM8/TM12 hotspot",
        "ligands": ["GLPG1837", "ATP", "Mg2+"],
        "resolution_angstrom": 3.2,
        "method": "Cryo-EM",
        "reference": "Liu et al., Science 2019 (DOI: 10.1126/science.aaw7611)",
    },
    "8UBR": {
        "pdb_id": "8UBR",
        "title": "Cryo-EM structure of phosphorylated human CFTR in complex with inhibitor CFTRinh-172 and ATP",
        "conformation": "Phosphorylated, ATP-bound CFTR with pore blocker CFTRinh-172 in intracellular vestibule",
        "ligands": ["CFTRinh-172", "ATP", "Mg2+"],
        "resolution_angstrom": 2.7,
        "method": "Cryo-EM",
        "reference": "Young et al., Proc Natl Acad Sci USA 2024 (DOI: 10.1073/pnas.2316675121)",
    },
    "5UAR": {
        "pdb_id": "5UAR",
        "title": "Cryo-EM structure of human CFTR phosphorylated and ATP-bound pre-translocation state",
        "conformation": "Phosphorylated, ATP-bound active/pre-translocation state",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 3.9,
        "method": "Cryo-EM",
        "reference": "Liu et al., Cell 2017 (DOI: 10.1016/j.cell.2017.02.024)",
    },
    "6MSK": {
        "pdb_id": "6MSK",
        "title": "Cryo-EM structure of human CFTR phosphorylated and ATP-bound channel open state without potentiator",
        "conformation": "Phosphorylated, ATP-bound apo channel open state",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Liu et al., Science 2019 (DOI: 10.1126/science.aaw7611)",
    },
    "8EIR": {
        "pdb_id": "8EIR",
        "title": "Cryo-EM structure of human CFTR in complex with GLPG2222 (galicaftor) and ATP",
        "conformation": "GLPG2222 (Type I corrector)-bound pre-open conformation",
        "ligands": ["GLPG2222 (galicaftor)", "ATP"],
        "resolution_angstrom": 3.0,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "8EIG": {
        "pdb_id": "8EIG",
        "title": "Cryo-EM structure of phosphorylated human delta F508 CFTR in complex with elexacaftor (VX-445) and ATP/Mg",
        "conformation": "Phosphorylated F508del in complex with Type II corrector elexacaftor and ATP",
        "ligands": ["VX-445 (elexacaftor)", "ATP", "Mg2+"],
        "resolution_angstrom": 3.6,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "8GLS": {
        "pdb_id": "8GLS",
        "title": "Cryo-EM structure of human CFTR in complex with allosteric modulator Z1834339853",
        "conformation": "Phosphorylated, ATP-bound CFTR with novel allosteric potentiator/inhibitor Z1834339853",
        "ligands": ["Z1834339853", "ATP", "Mg2+"],
        "resolution_angstrom": 3.8,
        "method": "Cryo-EM",
        "reference": "Liu et al., Cell 2024 (DOI: 10.1016/j.cell.2024.04.046)",
    },
    "9DW9": {
        "pdb_id": "9DW9",
        "title": "Cryo-EM structure of phosphorylated (E1371Q) human CFTR in complex with PKA catalytic subunit (PKA-C) and ATP/Mg",
        "conformation": "Phosphorylated (E1371Q catalytic mutant) CFTR channel dimerized state with docked PKA-C",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 2.8,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk et al., Proc Natl Acad Sci USA 2024 (DOI: 10.1073/pnas.2409049121)",
    },
    "9DW5": {
        "pdb_id": "9DW5",
        "title": "Cryo-EM structure of dephosphorylated human CFTR in 1:1 complex with PKA catalytic subunit (PKA-C, site I)",
        "conformation": "Dephosphorylated inward-facing channel with PKA-C docked at catalytic station I",
        "ligands": [],
        "resolution_angstrom": 3.8,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk et al., Proc Natl Acad Sci USA 2024 (DOI: 10.1073/pnas.2409049121)",
    },
    "9DW8": {
        "pdb_id": "9DW8",
        "title": "Cryo-EM structure of dephosphorylated (E1371Q) human CFTR in complex with PKA catalytic subunit (PKA-C)",
        "conformation": "Dephosphorylated E1371Q CFTR with PKA-C docked at regulatory interface",
        "ligands": [],
        "resolution_angstrom": 3.5,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk et al., Proc Natl Acad Sci USA 2024 (DOI: 10.1073/pnas.2409049121)",
    },
    "9DW7": {
        "pdb_id": "9DW7",
        "title": "Cryo-EM structure of dephosphorylated human CFTR in 1:2 complex with PKA catalytic subunit (PKA-C)",
        "conformation": "Dephosphorylated inward-facing channel with two PKA-C subunits simultaneously engaged",
        "ligands": [],
        "resolution_angstrom": 6.0,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk et al., Proc Natl Acad Sci USA 2024 (DOI: 10.1073/pnas.2409049121)",
    },
    "8EIJ": {
        "pdb_id": "8EIJ",
        "title": "Cryo-EM structure of human delta F508 CFTR in complex with GLPG2222 (galicaftor) and elexacaftor (VX-445)",
        "conformation": "Dual corrector (GLPG2222 + elexacaftor)-bound pre-open conformation",
        "ligands": ["GLPG2222 (galicaftor)", "VX-445 (elexacaftor)", "ATP"],
        "resolution_angstrom": 3.1,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "8EIK": {
        "pdb_id": "8EIK",
        "title": "Cryo-EM structure of phosphorylated human delta F508 CFTR in complex with tezacaftor (VX-661) and ATP",
        "conformation": "Phosphorylated F508del in complex with Type I corrector tezacaftor",
        "ligands": ["VX-661 (tezacaftor)", "ATP", "Mg2+"],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Fiedorczuk & Chen, Science 2022 (DOI: 10.1126/science.ade2216 / 10.1126/science.abq7985)",
    },
    "7SVE": {
        "pdb_id": "7SVE",
        "title": "Structure of human CFTR G551D phosphorylated and ATP-bound with potentiator VX-770 (ivacaftor)",
        "conformation": "Phosphorylated G551D active channel open state with potentiator VX-770 (ivacaftor) restoring catalytic gating",
        "ligands": ["VX-770 (ivacaftor)", "ATP", "Mg2+"],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Zhang & Chen, Cell 2021 / Zhang et al., Nature 2022 (DOI: 10.1038/s41586-022-05139-2)",
    },
    "7SVF": {
        "pdb_id": "7SVF",
        "title": "Structure of human CFTR G551D phosphorylated and ATP-bound with potentiator GLPG1837",
        "conformation": "Phosphorylated G551D active channel open state with potentiator GLPG1837 restoring catalytic gating",
        "ligands": ["GLPG1837", "ATP", "Mg2+"],
        "resolution_angstrom": 3.2,
        "method": "Cryo-EM",
        "reference": "Zhang & Chen, Cell 2021 / Zhang et al., Nature 2022 (DOI: 10.1038/s41586-022-05139-2)",
    },
    "8FZQ": {
        "pdb_id": "8FZQ",
        "title": "Cryo-EM structure of dephosphorylated, ATP-bound human CFTR",
        "conformation": "Dephosphorylated inward-facing channel state with ATP bound prior to PKA kinase activation",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 4.3,
        "method": "Cryo-EM",
        "reference": "Levring et al., Nature 2023 (DOI: 10.1038/s41586-023-05854-7)",
    },
    "8V7Z": {
        "pdb_id": "8V7Z",
        "title": "Cryo-EM structure of phosphorylated, ATP-bound, E1371Q human CFTR",
        "conformation": "Phosphorylated, ATP-bound E1371Q catalytic Walker B trap conformation",
        "ligands": ["ATP", "Mg2+"],
        "resolution_angstrom": 3.4,
        "method": "Cryo-EM",
        "reference": "Gao et al., Nat Commun 2024 (DOI: 10.1038/s41467-024-50641-1)",
    },
    "8V81": {
        "pdb_id": "8V81",
        "title": "Cryo-EM structure of phosphorylated, ATP-bound, CFTRinh-172-bound E1371Q human CFTR",
        "conformation": "Inhibitor-bound closed pore conformation with CFTRinh-172 docked in transmembrane pore",
        "ligands": ["CFTRinh-172", "ATP", "Mg2+"],
        "resolution_angstrom": 3.6,
        "method": "Cryo-EM",
        "reference": "Gao et al., Nat Commun 2024 (DOI: 10.1038/s41467-024-50641-1)",
    },
}


_CODON_RE = re.compile(
    r"\b(?:p\.[A-Z][a-z]{2}|[ACDEFGHIKLMNPQRSTVWY])(\d{1,4})(?:del|dup|ins|fs|Ter|X|[A-Z][a-z]{2}|[ACDEFGHIKLMNPQRSTVWY*])\b"
)
_STANDALONE_CODON_RE = re.compile(r"(?<![-\w])(?:codon\s+)?(\d{1,4})\b", re.IGNORECASE)
_NEGATIVE_CODON_RE = re.compile(r"(?:codon\s*-\s*\d+|^-\s*\d+)", re.IGNORECASE)


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


def normalize_query(term: str) -> str:
    """Normalize user queries by expanding arrow notation, legacy delta symbols, and stripping quotes."""
    if not isinstance(term, str):
        return ""
    q = term.strip()
    q = q.strip("\"' ")
    # Normalize arrow representations to standard '>'
    q = q.replace("->", ">").replace("→", ">")
    # Normalize legacy delta/del prefix notation (e.g. ΔF508, deltaF508, delF508 -> F508del)
    q = re.sub(r"(?:Δ|\u0394|[Dd]el(?:ta)?)\s*([Ff]508|[Ii]507)", r"\1del", q)
    return q



def lookup_cftr_modulator(term: str) -> dict[str, Any] | None:
    """Resolve a CFTR modulator query (brand, API, molecular code, or abbreviation) to canonical metadata."""
    if not isinstance(term, str) or not term.strip():
        return None

    clean = term.strip().strip("\"' ")
    upper = clean.upper()
    upper_nodash = upper.replace("-", "").replace("/", " ").replace("_", " ")

    # Direct brand or key match
    for key, mod in CANONICAL_MODULATORS.items():
        if key == upper or key == upper_nodash:
            return dict(mod)

    # Check aliases, active ingredients, and molecular codes with word boundaries
    for mod in CANONICAL_MODULATORS.values():
        for alias in mod.get("aliases", []):
            alias_upper = alias.upper()
            if alias_upper == upper or alias_upper.replace("-", "") == upper_nodash:
                return dict(mod)
            if re.search(r"\b" + re.escape(alias_upper) + r"\b", upper):
                return dict(mod)
        for api in mod.get("active_ingredients", []):
            api_upper = api.upper()
            if api_upper == upper or re.search(r"\b" + re.escape(api_upper) + r"\b", upper):
                return dict(mod)
        for code in mod.get("molecular_codes", []):
            code_upper = code.upper()
            if code_upper == upper or code_upper.replace("-", "") == upper_nodash:
                return dict(mod)
            if re.search(r"\b" + re.escape(code_upper) + r"\b", upper):
                return dict(mod)

    return None


def lookup_pdb_structure(pdb_id: str) -> dict[str, Any] | None:
    """Resolve a 4-character PDB accession to curated Cryo-EM CFTR structure metadata."""
    if not isinstance(pdb_id, str) or not pdb_id.strip():
        return None
    code = pdb_id.strip().upper()
    if code in CANONICAL_PDB_STRUCTURES:
        return dict(CANONICAL_PDB_STRUCTURES[code])
    return None


def lookup_cftr_context(term: str) -> dict[str, Any] | None:
    """Resolve a query term (e.g. 'CFTR[gene] AND F508del', 'G551D', 'p.Arg117His') to CFTR structural metadata."""
    if not isinstance(term, str) or not term.strip():
        return None

    normalized = normalize_query(term)
    upper = normalized.upper()

    # Reject obvious negative numbers in codon queries (e.g. 'codon -10')
    if _NEGATIVE_CODON_RE.search(normalized):
        return None

    # 1. Direct canonical allele key match
    for key, info in CANONICAL_ALLELES.items():
        if key in upper:
            return {
                **info,
                "transcript": REFSEQ_TRANSCRIPT,
                "uniprot": UNIPROT_ACCESSION,
            }

    # 2. Check protein and cDNA HGVS aliases, plus optional clinical aliases
    for info in CANONICAL_ALLELES.values():
        hgvs_p_norm = info["hgvs_p"].upper().replace("->", ">")
        hgvs_c_norm = info["hgvs_c"].upper().replace("->", ">")
        if hgvs_p_norm in upper or hgvs_c_norm in upper:
            return {
                **info,
                "transcript": REFSEQ_TRANSCRIPT,
                "uniprot": UNIPROT_ACCESSION,
            }
        for alias in info.get("aliases", []):
            if alias.upper() in upper:
                return {
                    **info,
                    "transcript": REFSEQ_TRANSCRIPT,
                    "uniprot": UNIPROT_ACCESSION,
                }

    # 3. Generic codon extraction when query mentions CFTR or HGVS protein notation
    if "CFTR" in upper or "P." in upper or "CODON" in upper:
        m = _CODON_RE.search(normalized)
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
        m_num = _STANDALONE_CODON_RE.search(normalized)
        if m_num:
            codon = int(m_num.group(1))
            if 1 <= codon <= 1480:
                return {
                    "allele": f"codon {codon}",
                    "hgvs_c": "not stated",
                    "hgvs_p": f"codon {codon}",
                    "codon": codon,
                    "exon": exon_for_codon(codon),
                    "domain": domain_for_codon(codon),
                    "cftr_class": "not stated",
                    "transcript": REFSEQ_TRANSCRIPT,
                    "uniprot": UNIPROT_ACCESSION,
                }

    return None


def self_check() -> dict[str, Any]:
    """Run built-in positive and negative controls across CFTR domain, exon, and allele lookups."""
    checks: list[dict[str, Any]] = []

    # 1. Canonical alleles completeness check
    all_keys = list(CANONICAL_ALLELES.keys())
    has_expected_count = len(all_keys) >= 23
    checks.append({
        "name": "canonical_alleles_count",
        "ok": has_expected_count,
        "detail": f"{len(all_keys)} canonical alleles indexed",
    })

    # 2. Contiguity of CFTR domains (1..1480)
    domain_ok = True
    curr_pos = 1
    for start, end, name, _ in CFTR_DOMAINS:
        if start != curr_pos:
            domain_ok = False
            break
        curr_pos = end + 1
    domain_ok = domain_ok and (curr_pos - 1 == 1480)
    checks.append({
        "name": "cftr_domains_contiguity",
        "ok": domain_ok,
        "detail": "9 domains span residues 1 through 1480 without gaps",
    })

    # 3. Contiguity of CFTR exons (1..27)
    exon_ok = True
    curr_pos = 1
    for exon_num, start, end in CFTR_EXON_SPANS:
        if start != curr_pos:
            exon_ok = False
            break
        curr_pos = end + 1
    exon_ok = exon_ok and (curr_pos - 1 == 1480) and (len(CFTR_EXON_SPANS) == 27)
    checks.append({
        "name": "cftr_exons_contiguity",
        "ok": exon_ok,
        "detail": "27 exons span codons 1 through 1480 without gaps",
    })

    # 4. Positive lookup controls: canonical, HGVS, and normalized arrows
    positive_cases = [
        ("F508del", "F508del", 11, "NBD1 (Nucleotide-Binding Domain 1)"),
        ("ΔF508", "F508del", 11, "NBD1 (Nucleotide-Binding Domain 1)"),
        ("c.1652G>A", "G551D", 12, "NBD1 (Nucleotide-Binding Domain 1)"),
        ("621+1G->T", "621+1G>T", 4, "Intron 4 (canonical 5' donor splice site)"),
        ("3849+10kbC->T", "3849+10kbC>T", 22, "Intron 22 (84-bp pseudoexon inclusion between exons 22 and 23)"),
        ("CFTR codon 508", "codon 508", 11, "NBD1 (Nucleotide-Binding Domain 1)"),
    ]
    pos_ok = True
    for query, expected_allele, expected_exon, expected_domain in positive_cases:
        res = lookup_cftr_context(query)
        if not res or res["allele"] != expected_allele or res["exon"] != expected_exon or res["domain"] != expected_domain:
            pos_ok = False
            break
    checks.append({
        "name": "positive_lookups_and_normalizations",
        "ok": pos_ok,
        "detail": f"{len(positive_cases)} positive test cases resolved with exact coordinates",
    })

    # 5. Negative controls: invalid codons and nonsense inputs must return None
    negative_cases = [
        "",
        "   ",
        "CFTR codon 0",
        "CFTR codon 1481",
        "CFTR codon -10",
        "completely_unrelated_query_without_cftr",
    ]
    neg_ok = True
    for query in negative_cases:
        res = lookup_cftr_context(query)
        if res is not None:
            neg_ok = False
            break
    checks.append({
        "name": "negative_controls_rejected",
        "ok": neg_ok,
        "detail": f"{len(negative_cases)} negative control cases returned None",
    })

    # 6. Canonical modulators count check
    mod_count_ok = len(CANONICAL_MODULATORS) >= 5
    checks.append({
        "name": "canonical_modulators_count",
        "ok": mod_count_ok,
        "detail": f"{len(CANONICAL_MODULATORS)} canonical modulators indexed",
    })

    # 7. Modulator positive lookups (brand, code, API, abbreviation)
    mod_test_cases = [
        ("Trikafta", "Trikafta"),
        ("KAFTRIO", "Trikafta"),
        ("VX-770", "Kalydeco"),
        ("ivacaftor", "Kalydeco"),
        ("vanzacaftor", "Alyftrek"),
        ("VX-121", "Alyftrek"),
        ("ETI", "Trikafta"),
        ("Symdeko", "Symdeko"),
        ("Orkambi", "Orkambi"),
    ]
    mod_pos_ok = True
    for q, expected_brand in mod_test_cases:
        res_m = lookup_cftr_modulator(q)
        if not res_m or res_m["brand"] != expected_brand:
            mod_pos_ok = False
            break
    checks.append({
        "name": "modulator_positive_lookups",
        "ok": mod_pos_ok,
        "detail": f"{len(mod_test_cases)} modulator positive cases resolved with canonical brand",
    })

    # 8. Modulator AH-4 boxed warning boundaries (Trikafta/Alyftrek DILI vs Kalydeco/Orkambi/Symdeko not stated)
    bw_trikafta = lookup_cftr_modulator("Trikafta")
    bw_alyftrek = lookup_cftr_modulator("Alyftrek")
    bw_kalydeco = lookup_cftr_modulator("Kalydeco")
    bw_orkambi = lookup_cftr_modulator("Orkambi")
    bw_symdeko = lookup_cftr_modulator("Symdeko")

    bw_ok = (
        bw_trikafta is not None and "drug-induced liver injury" in bw_trikafta["spl_boxed_warning"]
        and bw_alyftrek is not None and "drug-induced liver injury" in bw_alyftrek["spl_boxed_warning"]
        and bw_kalydeco is not None and bw_kalydeco["spl_boxed_warning"].startswith("not stated")
        and bw_orkambi is not None and bw_orkambi["spl_boxed_warning"].startswith("not stated")
        and bw_symdeko is not None and bw_symdeko["spl_boxed_warning"].startswith("not stated")
    )
    checks.append({
        "name": "modulator_boxed_warning_boundaries",
        "ok": bw_ok,
        "detail": "Trikafta/Alyftrek DILI boxed warning vs Kalydeco/Orkambi/Symdeko not stated verified (AH-4)",
    })

    # 9. Modulator negative controls rejected
    mod_neg_cases = ["", "   ", "completely_unknown_chemical_xyz", "aspirin", "ibuprofen"]
    mod_neg_ok = True
    for q in mod_neg_cases:
        if lookup_cftr_modulator(q) is not None:
            mod_neg_ok = False
            break
    checks.append({
        "name": "modulator_negative_controls_rejected",
        "ok": mod_neg_ok,
        "detail": f"{len(mod_neg_cases)} non-CFTR modulator queries rejected",
    })

    # 10. Cryo-EM PDB structures lookup positive and negative controls
    pdb_pos_cases = [
        "6MSM", "5UAK", "6O2P", "7SVD", "7SV7", "8EIQ", "8EJ1", "8EIZ", "7SVR", "8EIA", "8EIB", "8EIU",
        "8EIO", "9MXL", "6O1V", "8UBR", "5UAR", "6MSK", "8EIR", "8EIG", "8GLS",
        "9DW9", "9DW5", "9DW8", "9DW7", "8EIJ", "8EIK", "7SVE", "7SVF",
    ]
    pdb_ok = all(lookup_pdb_structure(p) is not None for p in pdb_pos_cases)
    pdb_neg_ok = lookup_pdb_structure("9999") is None and lookup_pdb_structure("") is None
    checks.append({
        "name": "pdb_structures_positive_and_negative",
        "ok": pdb_ok and pdb_neg_ok,
        "detail": f"{len(pdb_pos_cases)} canonical CFTR Cryo-EM structures verified and invalid accessions rejected",
    })

    all_passed = all(c["ok"] for c in checks)
    return {
        "check": "self-check",
        "passed": all_passed,
        "total_checks": len(checks),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cftr_context",
        description="Deterministic CFTR RefSeq NM_000492.4 exon, UniProt P13569 domain, modulator & Cryo-EM lookup (zero network).",
    )
    parser.add_argument("term", nargs="?", help="CFTR allele name, codon, modulator brand/code/API, or PDB accession")
    parser.add_argument("--self-check", action="store_true", help="run deterministic positive and negative-control self-tests")
    parser.add_argument("--list", action="store_true", help="list all canonical alleles")
    parser.add_argument("--modulators", action="store_true", help="list all canonical CFTR modulators and NDAs")
    parser.add_argument("--structures", action="store_true", help="list canonical CFTR Cryo-EM PDB structures")
    parser.add_argument("--json", action="store_true", help="output JSON")

    args = parser.parse_args(argv)

    if args.self_check:
        res = self_check()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            status_str = "PASS" if res["passed"] else "FAIL"
            print(f"cftr_context self-check: {status_str} ({res['total_checks']} checks)")
            for c in res["checks"]:
                mark = "[PASS]" if c["ok"] else "[FAIL]"
                print(f"  {mark} {c['name']}: {c['detail']}")
        return 0 if res["passed"] else 1

    if args.list:
        if args.json:
            print(json.dumps(CANONICAL_ALLELES, indent=2))
        else:
            print(f"Canonical CFTR Alleles ({len(CANONICAL_ALLELES)} alleles indexed):")
            for k, info in sorted(CANONICAL_ALLELES.items()):
                exon_str = f"Exon {info['exon']}" if info['exon'] is not None else "Intronic"
                print(f"  {info['allele']:<15} {info['hgvs_c']:<20} {exon_str:<10} {info['cftr_class']}")
        return 0

    if args.modulators:
        if args.json:
            print(json.dumps(CANONICAL_MODULATORS, indent=2))
        else:
            print(f"Canonical CFTR Modulators ({len(CANONICAL_MODULATORS)} modulators indexed):")
            for k, mod in sorted(CANONICAL_MODULATORS.items()):
                print(f"  {mod['brand']:<12} {mod['fda_nda']:<12} {mod['primary_pdb']:<6} {mod['mechanistic_class']}")
        return 0

    if args.structures:
        if args.json:
            print(json.dumps(CANONICAL_PDB_STRUCTURES, indent=2))
        else:
            print(f"Canonical CFTR Cryo-EM Structures ({len(CANONICAL_PDB_STRUCTURES)} structures indexed):")
            for k, s in sorted(CANONICAL_PDB_STRUCTURES.items()):
                print(f"  {s['pdb_id']:<6} {s['resolution_angstrom']} A  {s['conformation']}")
        return 0

    if not args.term:
        parser.print_help(sys.stderr)
        return 2

    # Check modulator lookup first if query matches a modulator
    res_mod = lookup_cftr_modulator(args.term)
    if res_mod is not None:
        if args.json:
            print(json.dumps(res_mod, indent=2))
        else:
            print(
                f"{res_mod['brand']} ({', '.join(res_mod['active_ingredients'])}; {', '.join(res_mod['molecular_codes'])}): "
                f"{res_mod['mechanistic_class']} [{res_mod['fda_nda']}, approved {res_mod['approval_year']}]. "
                f"SPL Boxed Warning: {res_mod['spl_boxed_warning']}. Primary PDB: {res_mod['primary_pdb']}."
            )
        return 0

    # Check PDB structure
    res_pdb = lookup_pdb_structure(args.term)
    if res_pdb is not None:
        if args.json:
            print(json.dumps(res_pdb, indent=2))
        else:
            print(f"PDB {res_pdb['pdb_id']}: {res_pdb['title']} ({res_pdb['resolution_angstrom']} A Cryo-EM)")
            print(f"  Conformation: {res_pdb['conformation']}")
            print(f"  Reference: {res_pdb['reference']}")
        return 0

    # Otherwise fallback to allele / codon lookup
    res = lookup_cftr_context(args.term)
    if res is not None:
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            exon_str = f"Exon {res['exon']}" if res["exon"] is not None else "Intronic"
            print(
                f"{res['allele']} ({res['hgvs_c']}, {res['hgvs_p']}): "
                f"{exon_str} ({res['transcript']}), Domain: {res['domain']} (UniProt {res['uniprot']}), "
                f"Class: {res['cftr_class']}"
            )
        return 0
    else:
        if args.json:
            print(json.dumps({"error": f"CFTR context not found for '{args.term}'"}))
        else:
            print(f"not found: CFTR context for '{args.term}'", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
