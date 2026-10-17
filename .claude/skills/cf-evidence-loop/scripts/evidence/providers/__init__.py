"""Providers, one per question family. Each returns Evidence records and nothing else."""

from . import clinvar, crossref, datacommons, ema, europepmc, gnomad, myvariant, openalex, openfda, preprints, pubmed, reporter, trials, ukri_gtr  # noqa: F401

ALL = {"crossref": crossref, "openfda": openfda, "preprints": preprints, "clinvar": clinvar, "reporter": reporter,
       "pubmed": pubmed, "trials": trials, "europepmc": europepmc, "datacommons": datacommons, "openalex": openalex,
       "myvariant": myvariant, "gnomad": gnomad, "ema": ema, "ukri_gtr": ukri_gtr}

