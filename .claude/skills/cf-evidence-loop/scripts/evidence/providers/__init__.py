"""Providers, one per question family. Each returns Evidence records and nothing else."""

from . import chembl, clinvar, crossref, datacommons, ema, europepmc, gnomad, myvariant, open_targets, openalex, openfda, preprints, pubmed, reporter, semantic_scholar, trials, ukri_gtr, unpaywall  # noqa: F401

ALL = {"crossref": crossref, "openfda": openfda, "preprints": preprints, "clinvar": clinvar, "reporter": reporter,
       "pubmed": pubmed, "trials": trials, "europepmc": europepmc, "datacommons": datacommons, "openalex": openalex,
       "myvariant": myvariant, "gnomad": gnomad, "ema": ema, "ukri_gtr": ukri_gtr,
       "unpaywall": unpaywall, "semantic_scholar": semantic_scholar,
       "chembl": chembl, "open_targets": open_targets}
