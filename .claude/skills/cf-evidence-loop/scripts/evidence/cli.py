"""Command line for the evidence layer.

    python -m evidence.cli retractions 10.1038/ng.2745 10.1002/humu.23276
    python -m evidence.cli doi 10.1038/ng.2745
    python -m evidence.cli approval TRIKAFTA
    python -m evidence.cli label TRIKAFTA --sections indications_and_usage
    python -m evidence.cli preprint medrxiv 10.1101/2025.02.14.25322057
    python -m evidence.cli preprints medrxiv 2026-09-01 2026-09-30
    python -m evidence.cli variants "CFTR[gene] AND F508del"
    python -m evidence.cli grants "cystic fibrosis" --fy 2025
    python -m evidence.cli pubmed "cystic fibrosis[tiab] AND modulator[tiab]" --limit 10
    python -m evidence.cli reviews "sickle cell disease"
    python -m evidence.cli trials "cystic fibrosis" --status RECRUITING
    python -m evidence.cli trial NCT05033080
    python -m evidence.cli epmc 'TITLE:"cystic fibrosis" AND OPEN_ACCESS:y'
    python -m evidence.cli cited 10.1038/ng.2745

Every command accepts --json (one JSON object per line) and --ledger PATH (append records). --contact must be a plain email address.
With EVIDENCE_DRY_RUN=1 nothing is sent; each planned request is printed to stderr as "planned: METHOD url".
Exit code 0 when every record is found/not_found, 3 when any record is blocked, rate_limited or error, or when a
conduct rule refused the request before it was sent. The last stderr line is always the request accounting summary.
"""

from __future__ import annotations

import argparse
import sys

from . import catalog
from .http import BudgetExhausted, Client, HostInCooldown, PaperworkMissing, RobotsDisallow
from .providers import clinvar, crossref, europepmc, openfda, preprints, pubmed, reporter, trials
from .record import Evidence, Status, append_ledger, clean_for_terminal

BAD = {Status.BLOCKED, Status.RATE_LIMITED, Status.ERROR}


def main(argv: list[str] | None = None) -> int:
    def common(inherit: bool) -> argparse.ArgumentParser:
        # The subcommands accept the same options as the main parser. Their defaults must not overwrite a value given before
        # the subcommand, so for them the default is "leave the attribute alone" (SUPPRESS).
        extra = {"default": argparse.SUPPRESS} if inherit else {}
        c = argparse.ArgumentParser(add_help=False)
        c.add_argument("--json", action="store_true", help="one JSON object per record", **extra)
        c.add_argument("--ledger", metavar="PATH", help="append records to this JSONL file", **extra)
        c.add_argument("--contact", help="contact for polite-pool headers (a plain email address); defaults to EVIDENCE_CONTACT env var", **extra)
        return c

    ap = argparse.ArgumentParser(prog="evidence", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[common(False)])
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=lambda **kw: argparse.ArgumentParser(parents=[common(True)], **kw))

    sub.add_parser("sources", help="list catalog sources this tool may reach")
    sub.add_parser("doi").add_argument("doi")
    sub.add_parser("retractions").add_argument("dois", nargs="+")
    sub.add_parser("approval").add_argument("brand")
    p = sub.add_parser("label"); p.add_argument("brand"); p.add_argument("--sections", nargs="+", default=list(openfda.DEFAULT_SECTIONS))
    p = sub.add_parser("preprint"); p.add_argument("server", choices=preprints.SERVERS); p.add_argument("doi")
    p = sub.add_parser("preprints"); p.add_argument("server", choices=preprints.SERVERS); p.add_argument("start"); p.add_argument("end")
    p.add_argument("--pattern", default=preprints.CF_PATTERN)
    p = sub.add_parser("variants"); p.add_argument("term"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("grants"); p.add_argument("text"); p.add_argument("--fy", type=int, nargs="*"); p.add_argument("--limit", type=int, default=25)
    p = sub.add_parser("pubmed", help="PubMed search; use field tags like [tiab] or [MeSH] for precision"); p.add_argument("term"); p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", default="relevance", choices=["relevance", "pub_date"])
    p = sub.add_parser("reviews", help="systematic reviews and Cochrane reviews matching a term"); p.add_argument("term"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("trial"); p.add_argument("nct_id")
    p = sub.add_parser("trials"); p.add_argument("condition"); p.add_argument("--term"); p.add_argument("--status", help="e.g. RECRUITING, COMPLETED")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("epmc", help="Europe PMC search (its own query syntax, e.g. TITLE:\"cystic fibrosis\" AND OPEN_ACCESS:y)"); p.add_argument("query"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("cited", help="Europe PMC record for a DOI: citation count and open-access status"); p.add_argument("doi")

    a = ap.parse_args(argv)
    if a.cmd == "sources":
        for sid, e in sorted(catalog.load().items()):
            if e.get("access") in catalog.AUTOMATABLE and e.get("base_url"):
                print(f"{sid:24} {e['base_url']}")
        return 0

    try:
        client = Client(contact=a.contact)
    except ValueError as exc:                     # a bad --contact or EVIDENCE_CONTACT: a usage error, before any request
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    recs: list[Evidence]
    try:
        recs = _dispatch(a, ap, client)
    except (BudgetExhausted, HostInCooldown, PaperworkMissing, RobotsDisallow, catalog.AccessDenied, catalog.UnknownSource) as exc:
        print(f"refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(client.accounting.summary(), file=sys.stderr)
        return 3

    for r in recs:
        print(r.to_json() if a.json else r.one_line())
    if a.ledger:
        n = append_ledger(a.ledger, recs)
        print(f"ledger: appended {n} record(s) to {a.ledger}", file=sys.stderr)
    if client.dry_run:
        for method, url in client.planned:
            print(clean_for_terminal(f"planned: {method} {url}"), file=sys.stderr)
        print("dry run: requests whose URLs depend on an earlier response (summaries for the ids a search finds, further pages) are not listed",
              file=sys.stderr)
    print(client.accounting.summary(), file=sys.stderr)
    return 3 if any(r.status in BAD for r in recs) else 0


def _dispatch(a, ap, client: Client) -> list[Evidence]:
    if a.cmd == "doi":
        return [crossref.work(client, a.doi)]
    elif a.cmd == "retractions":
        return crossref.check_dois(client, a.dois)
    elif a.cmd == "approval":
        return [openfda.approval(client, a.brand)]
    elif a.cmd == "label":
        return [openfda.label(client, a.brand, tuple(a.sections))]
    elif a.cmd == "preprint":
        return preprints.details(client, a.server, a.doi)
    elif a.cmd == "preprints":
        return preprints.window(client, a.server, a.start, a.end, a.pattern)
    elif a.cmd == "variants":
        return clinvar.variants(client, a.term, a.limit)
    elif a.cmd == "grants":
        return reporter.projects(client, a.text, a.fy or None, a.limit)
    elif a.cmd == "pubmed":
        return pubmed.search(client, a.term, a.limit, a.sort)
    elif a.cmd == "reviews":
        return pubmed.reviews(client, a.term, a.limit)
    elif a.cmd == "trial":
        return trials.study(client, a.nct_id)
    elif a.cmd == "trials":
        return trials.search(client, a.condition, a.term, a.status, a.limit)
    elif a.cmd == "epmc":
        return europepmc.search(client, a.query, a.limit)
    elif a.cmd == "cited":
        return europepmc.lookup(client, a.doi)
    ap.error(a.cmd)  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
