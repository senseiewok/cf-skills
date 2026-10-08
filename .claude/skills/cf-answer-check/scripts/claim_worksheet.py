#!/usr/bin/env python3
"""Turn an AI answer into a worksheet of candidate claims to check, one sentence per claim.

Usage:
    python claim_worksheet.py [ANSWER] [-o WORKSHEET.json] [--flags FLAGS.json] [--all] [--drugs FILE]

Reads ANSWER, or standard input when ANSWER is missing or "-". Splits it into sentences and keeps a
sentence as a candidate claim when it has any of:
    a number, a percentage or a year, or a number word (two to ninety, hundred, thousand, "nine out
        of ten"), twice, half or double ("one" alone is too common to count)
    a drug name from a small list (see DRUG_NAMES below, or give your own list with --drugs)
    a CF variant name: F508del, p.Phe508del, G551D, N1303K, 621+1G>T, c.1521_1523del and the like
    a claim word: approved, approval, safe, safely, effective, works, worked, recommended, proven
    a widening word: only, all, every, each, never, always, none, no one, same, identical, first, last,
        no longer, new, new in, now, agrees, consistent, stronger, strongest, most, majority, any,
        entire, whole, completely, both, neither, unique, cause, causes, caused, because.
        Not counted: a widening word that opens a sentence and is followed by a comma ("First, ...",
        "Now, ..."), and each or every before visit, time, day or person when the sentence has no
        number and no drug name ("Each visit is a chance to ask.")
    an absence phrase: does not say, not stated, no evidence, absent, never reported, there is no,
        there are no, no known, not available, not approved, and their contractions (there's no,
        isn't approved, doesn't say, aren't available...)
With --all, every sentence becomes a candidate.

Lines are joined into one paragraph (a blank line, a list item, a heading or a table row starts a new
one) before the text is split into sentences, so a sentence wrapped over two lines stays one claim;
the line given for a claim is the line where it starts. Decimals and a few abbreviations (e.g., i.e.,
Dr., U.S., U.K.) do not end a sentence.

The worksheet is a JSON list. Each entry has exactly these fields:
    {"id": "c1", "claim": "...", "source": "", "quote": "", "kind": "", "scope": ""}
A person fills source (where the evidence is), quote (the exact passage), kind (observed, computed or
inferred) and scope (what was searched and where, needed for widening words and absence phrases).
This is the claims-file shape used by the claims checker in the cf-research repository
(tools/claims/check_claims.py), which fails on an empty field, so an unfilled worksheet never passes.

What was found in each sentence (numbers, drug names, variants, claim words, widening words, absence
phrases) is printed as a checklist, and written to --flags as JSON when asked. It is kept out of the
worksheet on purpose, because the claims checker rejects any field it does not know.

Exit codes:
    0  a worksheet was written
    1  no candidate claims were found (this does not mean the answer has no claims; try --all)
    2  usage error: unreadable file, not UTF-8, or an unreadable --drugs list

This finds sentences worth checking. It does not check anything, and it misses claims made without
numbers, names or the words above. English only. Python 3.9+, standard library only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# For spotting names only. Being on this list says nothing about approval, use or suitability,
# and a name that is missing is simply not flagged.
DRUG_NAMES = [
    "ivacaftor", "lumacaftor", "tezacaftor", "elexacaftor", "vanzacaftor", "deutivacaftor",
    "Kalydeco", "Orkambi", "Symdeko", "Symkevi", "Trikafta", "Kaftrio", "Alyftrek",
    "dornase alfa", "Pulmozyme", "hypertonic saline", "mannitol", "tobramycin", "aztreonam",
    "azithromycin", "colistimethate", "levofloxacin", "pancrelipase", "Creon", "ursodiol",
    "ursodeoxycholic acid", "insulin",
]

WIDENING = [
    "only", "all", "every", "each", "never", "always", "none", "no one", "same", "identical", "first",
    "last", "no longer", "new", "new in", "now", "agrees", "consistent", "stronger", "strongest", "most",
    "majority", "any", "entire", "whole", "completely", "both", "neither", "unique", "cause", "causes",
    "caused", "because",
]
ABSENCE = [
    "does not say", "not stated", "no evidence", "absent", "never reported", "there is no",
    "there are no", "no known", "not available", "not approved",
    "there's no", "there isn't", "there aren't", "isn't approved", "aren't approved", "wasn't approved",
    "isn't available", "aren't available", "doesn't say", "don't say", "didn't say", "hasn't been",
    "haven't been", "isn't known", "isn't stated",
]
ASSERTIONS = ["approved", "approval", "safe", "safely", "effective", "works", "worked", "recommended", "proven"]
NUMBER_WORDS = [
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
    "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "hundreds", "thousand", "thousands",
    "twice", "half", "double", "doubled", "triple", "tripled",
]

NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*\s?%?|\b(?:percent|per cent)\b", re.I)
NUMBER_WORD_RE = re.compile(r"(?<![\w-])(?:" + "|".join(NUMBER_WORDS) + r")(?![\w-])", re.I)
ABBREVIATIONS = ("U.S.A.", "U.S.", "U.K.", "e.g.", "i.e.", "etc.", "Dr.", "vs.", "approx.", "et al.", "No.", "Fig.")
VARIANT_RE = re.compile(
    r"(?<![\w.])(?:F508del|delta\s?F508|ΔF508|p\.\(?[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2}|del|dup|fs|\*|X)\w*\)?|"
    r"c\.[\d_+*-]+(?:[ACGT]>[ACGT]|del\w*|dup\w*|ins\w*)|[A-Z]\d{2,4}(?:[A-Z]|del|dup|fs)|"
    r"\d{2,4}[+-]\d+(?:kb)?[ACGT]>[ACGT])(?![\w>])")
LEADING_COMMA_RE = re.compile(r"^\W*(\w+),")
ROUTINE_RE = re.compile(r"\b(?:each|every)\s+(?:visit|visits|time|day|person|morning|evening|night|week)\b", re.I)


def _phrase_re(phrases):
    alt = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in sorted(phrases, key=len, reverse=True))
    alt = alt.replace("'", "['’]")    # a straight apostrophe in a phrase also matches a curly one
    return re.compile(r"(?<![\w-])(?:" + alt + r")(?![\w-])", re.I)


WIDENING_RE = _phrase_re(WIDENING)
ABSENCE_RE = _phrase_re(ABSENCE)
ASSERTION_RE = _phrase_re(ASSERTIONS)
_NEW_UNIT_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#+)\s+|^\s*\|")


def _units(text: str):
    """Yield lists of (line_number, line): paragraphs, where a list item, heading or table row starts a new one."""
    unit = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            if unit:
                yield unit
            unit = []
            continue
        if unit and _NEW_UNIT_RE.match(line):
            yield unit
            unit = []
        unit.append((line_no, line))
        if line.lstrip().startswith(("#", "|")):
            yield unit
            unit = []
    if unit:
        yield unit


def split_sentences(text: str):
    """Return a list of (line_number, sentence). Lines are joined per paragraph first; decimals, a few
    abbreviations, list markers and headings are handled. The line number is where the sentence starts."""
    out = []
    for unit in _units(text):
        pieces, starts, pos = [], [], 0
        for line_no, line in unit:
            protected = line
            for abbr in ABBREVIATIONS:
                protected = protected.replace(abbr, abbr.replace(".", "\u0000"))
            protected = re.sub(r"(?<=\d)\.(?=\d)", "\u0000", protected)
            protected = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", protected)
            protected = re.sub(r"^\s*#+\s*", "", protected)
            protected = protected.strip()
            starts.append((pos, line_no))
            pieces.append(protected)
            pos += len(protected) + 1
        joined = " ".join(pieces)
        offset = 0
        for part in re.split(r"((?<=[.!?])[\"')\]]*\s+)", joined):
            start = offset
            offset += len(part)
            if not part.strip() or re.fullmatch(r"[\"')\]]*\s+", part):
                continue
            line_no = max(no for p, no in starts if p <= start)
            part = part.strip().replace("\u0000", ".")
            if re.search(r"[A-Za-z0-9]", part):
                out.append((line_no, part))
    return out


def _widening(sentence: str, has_number_or_drug: bool) -> list:
    lead = LEADING_COMMA_RE.match(sentence)
    routine = [] if has_number_or_drug else [m.span() for m in ROUTINE_RE.finditer(sentence)]
    out = []
    for m in WIDENING_RE.finditer(sentence):
        if lead and m.span() == lead.span(1):
            continue    # "First, ..." or "Now, ..." opening a sentence orders the steps; it claims nothing
        if any(s <= m.start() < e for s, e in routine):
            continue    # "each visit", "every day" with no number or drug name
        out.append(m.group(0).lower())
    return out


def find(sentence: str, drugs_re) -> dict:
    numbers = [m.group(0).strip() for m in NUMBER_RE.finditer(sentence)]
    numbers += [m.group(0).lower() for m in NUMBER_WORD_RE.finditer(sentence)]
    drugs = sorted({m.group(0) for m in drugs_re.finditer(sentence)}) if drugs_re else []
    return {
        "numbers": numbers,
        "drugs": drugs,
        "variants": [m.group(0) for m in VARIANT_RE.finditer(sentence)],
        "assertions": [m.group(0).lower() for m in ASSERTION_RE.finditer(sentence)],
        "widening": _widening(sentence, bool(numbers or drugs)),
        "absence": [m.group(0).lower() for m in ABSENCE_RE.finditer(sentence)],
    }


def build(text: str, drugs=None, include_all=False):
    """Return (worksheet, flags). worksheet entries carry only id, claim, source, quote, kind, scope."""
    drugs = DRUG_NAMES if drugs is None else drugs
    drugs_re = _phrase_re(drugs) if drugs else None
    worksheet, flags = [], []
    for line_no, sentence in split_sentences(text):
        found = find(sentence, drugs_re)
        if not include_all and not any(found.values()):
            continue
        cid = f"c{len(worksheet) + 1}"
        worksheet.append({"id": cid, "claim": sentence, "source": "", "quote": "", "kind": "", "scope": ""})
        flags.append({"id": cid, "line": line_no, **found,
                      "needs_scope": bool(found["widening"] or found["absence"])})
    return worksheet, flags


def _read_list(path):
    with open(path, encoding="utf-8") as fh:
        items = [ln.split("#", 1)[0].strip() for ln in fh]
    items = [i for i in items if i]
    if not items:
        raise ValueError(f"{path} has no names")
    return items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a JSON worksheet of candidate claims (one per sentence with numbers, drug names, variants, "
                    "claim words, widening words or absence phrases) with empty source, quote, kind and scope fields "
                    "for a person to fill. It finds sentences worth checking; it checks nothing.",
        epilog="Exit codes: 0 worksheet written, 1 no candidate claims found, 2 usage error.")
    parser.add_argument("answer", nargs="?", default="-", help="the answer as UTF-8 text; '-' or nothing reads standard input")
    parser.add_argument("-o", "--output", help="write the worksheet here (default: standard output)")
    parser.add_argument("--flags", help="also write what was found in each sentence to this JSON file")
    parser.add_argument("--all", action="store_true", help="make every sentence a candidate claim")
    parser.add_argument("--drugs", help="a file of drug names, one per line ('#' starts a comment); replaces the built-in list")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        data = sys.stdin.buffer.read() if args.answer == "-" else open(args.answer, "rb").read()
        text = data.decode("utf-8-sig")
        drugs = _read_list(args.drugs) if args.drugs else None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    worksheet, flags = build(text, drugs=drugs, include_all=args.all)
    if not worksheet:
        print("No candidate claims found. This does not mean the answer has no claims; read it, or use --all.",
              file=sys.stderr)
        return 1

    payload = json.dumps(worksheet, ensure_ascii=False, indent=2) + "\n"
    report = sys.stdout if args.output else sys.stderr
    try:
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(payload)
        else:
            sys.stdout.write(payload)
        if args.flags:
            with open(args.flags, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(flags, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for f in flags:
        bits = []
        for key in ("numbers", "drugs", "variants", "assertions", "widening", "absence"):
            if f[key]:
                bits.append(f"{key}: {', '.join(f[key])}")
        need = " -- fill 'scope' (what was searched and where)" if f["needs_scope"] else ""
        print(f"{f['id']} (line {f['line']}): {'; '.join(bits) or 'no markers'}{need}", file=report)
    print(f"{len(worksheet)} candidate claim(s). Fill source, quote, kind and scope for each; "
          f"anything you cannot check stays unverified.", file=report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
