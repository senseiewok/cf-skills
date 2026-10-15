"""Providers, one per question family. Each returns Evidence records and nothing else."""

from . import clinvar, crossref, datacommons, europepmc, myvariant, openalex, openfda, preprints, pubmed, reporter, trials  # noqa: F401

ALL = {"crossref": crossref, "openfda": openfda, "preprints": preprints, "clinvar": clinvar, "reporter": reporter,
       "pubmed": pubmed, "trials": trials, "europepmc": europepmc, "datacommons": datacommons, "openalex": openalex,
       "myvariant": myvariant}
