#!/usr/bin/env python3
"""Compare the facts on the surface of a source text and its rewrite: numbers, dates and names.

Usage:
    python fact_diff.py SOURCE REWRITE [--json]

Extracts from both texts:
    numbers   every number with the unit or count word after it, if any ("2 times", "30 minutes",
              "50%", "250 mg"); number words one to twenty become digits; "once", "twice" and "thrice"
              become "1 times", "2 times", "3 times"; "percent" becomes "%"; commas in 1,000 are dropped;
              a range such as 2-3 or 2 to 3 gives both numbers
    dates     "12 March 2026", "March 12, 2026" and "2026-03-12" become 2026-03-12; "March 2026"
              becomes 2026-03; other forms (such as 12/03/2026) are kept as written, because the order
              of day and month is not known
    names     capitalised words and acronyms that are not the first word of a sentence (CF, CFTR,
              Monday, a clinic or drug name), and first words of a sentence that are acronyms or are
              capitalised somewhere else in either text

Reports:
    dropped   in the source, not in the rewrite
    added     in the rewrite, not in the source
    changed   a dropped and an added number with the same unit (for example "2 times" became "3 times")

A name counts as kept when the same word, with the same capital letters, appears anywhere in the
other text. A number counts as kept when the same number with the same unit is in the other text.

What it cannot do: it does not understand meaning. It misses a fact that changed in words only
("before meals" became "after meals"), a number moved to the wrong sentence, a name that only ever
starts a sentence, and a new instruction without a number or a name. A person still reads the rewrite
against the source, line by line.

Exit codes:
    0  nothing added, dropped or changed
    1  at least one difference
    2  usage error: a file cannot be read or is not UTF-8

Python 3.9+, standard library only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
MULTIPLES = {"once": "1 times", "twice": "2 times", "thrice": "3 times"}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

UNIT_CANON = {
    "%": "%", "percent": "%", "per cent": "%",
    "mg": "mg", "milligram": "mg", "milligrams": "mg", "mcg": "mcg", "microgram": "mcg", "micrograms": "mcg",
    "g": "g", "gram": "g", "grams": "g", "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "unit": "units", "units": "units", "iu": "units",
    "time": "times", "times": "times",
    "second": "seconds", "seconds": "seconds", "minute": "minutes", "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
    "day": "days", "days": "days", "week": "weeks", "weeks": "weeks", "month": "months", "months": "months",
    "year": "years", "years": "years",
    "puff": "puffs", "puffs": "puffs", "capsule": "capsules", "capsules": "capsules", "tablet": "tablets", "tablets": "tablets",
    "drop": "drops", "drops": "drops", "spray": "sprays", "sprays": "sprays", "breath": "breaths", "breaths": "breaths",
    "glass": "glasses", "glasses": "glasses", "cup": "cups", "cups": "cups", "meal": "meals", "meals": "meals",
    "snack": "snacks", "snacks": "snacks", "dose": "doses", "doses": "doses",
    "°c": "°C", "°f": "°F", "degrees": "degrees",
}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNIT_CANON), key=len, reverse=True))
NUMBER_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
    r"(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?"
    r"(?:\s?(" + _UNIT_ALT + r")(?![A-Za-z]))?", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DMY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
MDY_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")
MY_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{4})\b")
SLASH_DATE_RE = re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b")
CAP_WORD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*\b")


def _words_to_digits(text: str) -> str:
    def repl(m):
        word = m.group(0)
        low = word.lower()
        if low in MULTIPLES:
            return MULTIPLES[low]
        return str(NUMBER_WORDS[low])
    alt = "|".join(list(NUMBER_WORDS) + list(MULTIPLES))
    return re.sub(r"\b(?:" + alt + r")\b", repl, text, flags=re.I)


def _canon_number(raw: str) -> str:
    raw = raw.replace(",", "")
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw


def extract_dates(text: str):
    """Return (set of normalised dates, text with the dates removed so their digits are not counted as numbers)."""
    found = set()
    spans = []

    def month(name):
        return MONTHS.get(name.lower().rstrip("."))

    for m in ISO_DATE_RE.finditer(text):
        found.add(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        spans.append(m.span())
    for m in DMY_RE.finditer(text):
        mo = month(m.group(2))
        if mo:
            found.add(f"{m.group(3)}-{mo:02d}-{int(m.group(1)):02d}")
            spans.append(m.span())
    for m in MDY_RE.finditer(text):
        mo = month(m.group(1))
        if mo and not any(s <= m.start() < e for s, e in spans):
            found.add(f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}")
            spans.append(m.span())
    for m in MY_RE.finditer(text):
        mo = month(m.group(1))
        if mo and not any(s <= m.start() < e for s, e in spans):
            found.add(f"{m.group(2)}-{mo:02d}")
            spans.append(m.span())
    for m in SLASH_DATE_RE.finditer(text):
        found.add(m.group(0))
        spans.append(m.span())
    chars = list(text)
    for s, e in spans:
        for i in range(s, e):
            if not chars[i].isalpha():
                chars[i] = " "
    return found, "".join(chars)


def extract_numbers(text: str) -> set:
    text = _words_to_digits(text)
    out = set()
    for m in NUMBER_RE.finditer(text):
        unit = UNIT_CANON.get((m.group(3) or "").lower(), (m.group(3) or "").lower())
        for raw in (m.group(1), m.group(2)):
            if raw:
                n = _canon_number(raw)
                out.add(f"{n} {unit}".strip())
    return out


NOT_NAMES = {"I", "I'm", "I've", "I'll", "I'd", "OK"}


def _at_sentence_start(text: str, pos: int) -> bool:
    """True when the word at pos is the first word of a sentence, a line, a list item or a quotation."""
    prefix = text[max(0, pos - 12):pos]
    if pos <= 12 and not text[:pos].strip(" \t\"'(*#"):
        return True
    line_start = prefix.rfind("\n")
    if line_start != -1 and re.fullmatch(r"\s*(?:[-*+#]+|\d+[.)])?\s*[\"'(]?", prefix[line_start + 1:]):
        return True
    return re.search(r"[.!?:][\"')\]]*\s+[\"'(]?$", prefix) is not None


def extract_names(text: str, other: str) -> set:
    mid_caps = set()
    for t in (text, other):
        for m in CAP_WORD_RE.finditer(t):
            if not _at_sentence_start(t, m.start()):
                mid_caps.add(m.group(0))
    names = set()
    for m in CAP_WORD_RE.finditer(text):
        word = m.group(0)
        if word in NOT_NAMES:
            continue
        is_acronym = sum(c.isupper() for c in word) >= 2
        if is_acronym or word in mid_caps:
            names.add(word)
    return names


def _contains_word(text: str, word: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text) is not None


def diff(source: str, rewrite: str) -> dict:
    src_dates, src_rest = extract_dates(source)
    new_dates, new_rest = extract_dates(rewrite)
    src_nums = extract_numbers(src_rest)
    new_nums = extract_numbers(new_rest)

    dropped_nums = sorted(src_nums - new_nums)
    added_nums = sorted(new_nums - src_nums)
    changed = []
    for d in list(dropped_nums):
        unit = d.partition(" ")[2]
        if not unit:
            continue
        for a in list(added_nums):
            if a.partition(" ")[2] == unit:
                changed.append({"from": d, "to": a})
                dropped_nums.remove(d)
                added_nums.remove(a)
                break

    src_names = extract_names(source, rewrite)
    new_names = extract_names(rewrite, source)
    dropped_names = sorted(n for n in src_names if not _contains_word(rewrite, n))
    added_names = sorted(n for n in new_names if not _contains_word(source, n))

    return {
        "changed": changed,
        "dropped": {"numbers": dropped_nums, "dates": sorted(src_dates - new_dates), "names": dropped_names},
        "added": {"numbers": added_nums, "dates": sorted(new_dates - src_dates), "names": added_names},
    }


def has_differences(result: dict) -> bool:
    return bool(result["changed"]) or any(result["dropped"].values()) or any(result["added"].values())


def _read(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report numbers, dates and names that a rewrite added, dropped or changed compared with its source. "
                    "Surface only: a person still reads the rewrite against the source.",
        epilog="Exit codes: 0 no differences, 1 at least one difference, 2 usage error.")
    parser.add_argument("source", help="the original text (UTF-8)")
    parser.add_argument("rewrite", help="the rewritten text (UTF-8)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        result = diff(_read(args.source), _read(args.rewrite))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for c in result["changed"]:
            print(f"CHANGED number: {c['from']} -> {c['to']}")
        for kind in ("numbers", "dates", "names"):
            for item in result["dropped"][kind]:
                print(f"DROPPED {kind[:-1]}: {item}")
            for item in result["added"][kind]:
                print(f"ADDED {kind[:-1]}: {item}")
        if not has_differences(result):
            print("No numbers, dates or names were added, dropped or changed. This checks the surface only; "
                  "a person still reads the rewrite against the source.")
    return 1 if has_differences(result) else 0


if __name__ == "__main__":
    sys.exit(main())
