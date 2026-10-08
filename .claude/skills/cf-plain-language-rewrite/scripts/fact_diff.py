#!/usr/bin/env python3
"""Compare the facts on the surface of a source text and its rewrite: numbers, dates, names, links and
warning words.

Usage:
    python fact_diff.py SOURCE REWRITE [--json] [--names FILE]

Both texts are first normalised (Unicode NFKC, so a full-width 2 is a 2). Extracts from both:
    numbers   every number with the unit or count word after it, if any ("2 times", "30 minutes",
              "50%", "250 mg"), counted (a dose given twice in the source must appear twice).
              Number words one to ninety ("forty-two"), "a hundred" and "half" become digits; "twice"
              and "thrice" become "2 times" and "3 times"; "once" becomes "1 times" only before
              a, per, daily, every, each, weekly, monthly or or ("Once you are home" is not a number);
              "one" is not counted in "one of", "one another" or after the, this, that, each, every,
              any, no or some. "percent" becomes "%"; a thousands separator (comma or space) is dropped;
              ".5" is "0.5"; a range such as 2-3, 2–3, 2—3 or 2 to 3 gives both numbers
    dates     "12 March 2026", "March 12, 2026" and "2026-03-12" become 2026-03-12; "March 2026"
              becomes 2026-03; other forms (such as 12/03/2026) are kept as written, because the order
              of day and month is not known
    names     capitalised words and acronyms that are not the first word of a sentence (CF, CFTR, a
              clinic or drug name), first words of a sentence that are acronyms or are capitalised
              somewhere else in either text, weekday and month names anywhere (but "May" opening a
              sentence is not counted), and medicine names from a built-in list in any case
              ("creon", "Ibuprofen"), plus any names given with --names FILE (one per line, any case)
    links     web addresses (https://..., www...., example.org)
    words     the count of each warning word: not (also don't, doesn't, can't, cannot), no, never,
              avoid, stop, without, only, before, after, and the phrase "every other"

Reports:
    dropped        in the source, not in the rewrite
    added          in the rewrite, not in the source
    changed        a dropped and an added number with the same unit ("2 times" became "3 times")
    counts         a number in both texts, but a different number of times
    words          a warning word whose count changed ("Do not take" became "Take")
    order_changed  the same numbers with units, in a different order (2 puffs and 4 puffs swapped)

A name counts as kept when the same word, with the same capital letters, appears anywhere in the
other text (a medicine or --names name in any case).

What it cannot do: it does not understand meaning. It misses a fact that changed in words other than
the warning words above, a number moved to the wrong sentence when the order of numbers stays the
same, a name it does not recognise that only ever starts a sentence, and a new instruction without a
number, a name or a warning word. A person still reads the rewrite against the source, line by line.

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
import unicodedata
from collections import Counter

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
UNIT_WORDS = {k: v for k, v in NUMBER_WORDS.items() if v < 10}
MULTIPLES = {"once": "1 times", "twice": "2 times", "thrice": "3 times"}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
CALENDAR_NAMES = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
                  "January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"}

# For spotting names only (copied from cf-answer-check's claim_worksheet.py, plus a few common medicines).
# Being on this list says nothing about approval, use or suitability; a name that is missing is not flagged.
MEDICINE_NAMES = [
    "ivacaftor", "lumacaftor", "tezacaftor", "elexacaftor", "vanzacaftor", "deutivacaftor",
    "Kalydeco", "Orkambi", "Symdeko", "Symkevi", "Trikafta", "Kaftrio", "Alyftrek",
    "dornase alfa", "Pulmozyme", "hypertonic saline", "mannitol", "tobramycin", "aztreonam",
    "azithromycin", "colistimethate", "levofloxacin", "pancrelipase", "Creon", "ursodiol",
    "ursodeoxycholic acid", "insulin",
    "ibuprofen", "paracetamol", "acetaminophen", "salbutamol", "albuterol", "prednisolone", "omeprazole",
]

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
_NUM = r"\d{1,3}(?:[, ]\d{3})+(?![\d.])|\d+(?:\.\d+)?|\.\d+"
NUMBER_RE = re.compile(
    r"(?<![\w.])(" + _NUM + r")"
    r"(?:\s*(?:-|–|—|to)\s*(" + _NUM + r"))?"
    r"(?:\s?(" + _UNIT_ALT + r")(?![A-Za-z]))?", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DMY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
MDY_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")
MY_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{4})\b")
SLASH_DATE_RE = re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b")
CAP_WORD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*\b")
URL_RE = re.compile(r"\bhttps?://\S+|\bwww\.\S+|(?<![@\w.-])[\w-]+(?:\.[\w-]+)*\.(?:org|com|gov|net|edu|uk|ie|au|ca|eu|int)"
                    r"(?:/\S*)?\b", re.I)
WARNING_WORDS = ["not", "no", "never", "avoid", "stop", "without", "only", "before", "after", "every other"]
WARNING_RE = re.compile(r"\b(?:" + "|".join(w.replace(" ", r"\s+") for w in WARNING_WORDS) + r")\b", re.I)

_ONE_SKIP_BEFORE = re.compile(r"\b(?:the|this|that|each|every|any|no|some|which)\s+$", re.I)
_ONE_SKIP_AFTER = re.compile(r"\s+(?:of|another)\b", re.I)
_ONCE_AFTER = re.compile(r"\s+(?:a|an|per|daily|every|each|weekly|monthly|or)\b", re.I)


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("’", "'")


def _words_to_digits(text: str) -> str:
    units_alt = "|".join(UNIT_WORDS)
    whole_alt = "|".join(NUMBER_WORDS)

    def and_half(m):
        return str(NUMBER_WORDS[m.group(1).lower()]) + ".5"
    text = re.sub(r"\b(" + whole_alt + r")\s+and\s+a\s+half\b", and_half, text, flags=re.I)

    def hundreds(m):
        lead = m.group(1).lower()
        return str((1 if lead in ("a", "one") else NUMBER_WORDS[lead]) * 100)
    text = re.sub(r"\b(a|one|" + units_alt + r")\s+hundred\b", hundreds, text, flags=re.I)
    text = re.sub(r"\bhundred\b", "100", text, flags=re.I)

    def tens(m):
        return str(TENS[m.group(1).lower()] + (UNIT_WORDS[m.group(2).lower()] if m.group(2) else 0))
    text = re.sub(r"\b(" + "|".join(TENS) + r")(?:[- ](" + units_alt + r"))?\b", tens, text, flags=re.I)
    text = re.sub(r"\b(?:a\s+half|half(?:\s+an?)?)\b", "0.5", text, flags=re.I)

    def repl(m):
        low = m.group(0).lower()
        before, after = text[max(0, m.start() - 12):m.start()], text[m.end():m.end() + 12]
        if low == "once":
            return MULTIPLES[low] if _ONCE_AFTER.match(after) else m.group(0)
        if low in MULTIPLES:
            return MULTIPLES[low]
        if low == "one" and (_ONE_SKIP_BEFORE.search(before) or _ONE_SKIP_AFTER.match(after)):
            return m.group(0)
        return str(NUMBER_WORDS[low])
    alt = "|".join(list(NUMBER_WORDS) + list(MULTIPLES))
    return re.sub(r"\b(?:" + alt + r")\b", repl, text, flags=re.I)


def _canon_number(raw: str) -> str:
    raw = raw.replace(",", "").replace(" ", "")
    if raw.startswith("."):
        raw = "0" + raw
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw


def extract_dates(text: str, spans_out=None):
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
    if spans_out is not None:
        spans_out.extend(spans)
    return found, "".join(chars)


def extract_number_list(text: str) -> list:
    """Every number with its unit, in the order it appears."""
    text = _words_to_digits(text)
    out = []
    for m in NUMBER_RE.finditer(text):
        unit = UNIT_CANON.get((m.group(3) or "").lower(), (m.group(3) or "").lower())
        for raw in (m.group(1), m.group(2)):
            if raw:
                n = _canon_number(raw)
                out.append(f"{n} {unit}".strip())
    return out


def extract_numbers(text: str) -> Counter:
    return Counter(extract_number_list(text))


NOT_NAMES = {"I", "I'm", "I've", "I'll", "I'd", "OK", "IU"}   # IU is a unit, compared as a number


def _at_sentence_start(text: str, pos: int) -> bool:
    """True when the word at pos is the first word of a sentence, a line, a list item or a quotation."""
    prefix = text[max(0, pos - 12):pos]
    if pos <= 12 and not text[:pos].strip(" \t\"'(*#"):
        return True
    line_start = prefix.rfind("\n")
    if line_start != -1 and re.fullmatch(r"\s*(?:[-*+#]+|\d+[.)])?\s*[\"'(]?", prefix[line_start + 1:]):
        return True
    return re.search(r"[.!?:][\"')\]]*\s+[\"'(]?$", prefix) is not None


def _list_re(names):
    alt = "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in sorted(names, key=len, reverse=True))
    return re.compile(r"(?<![\w-])(?:" + alt + r")(?![\w-])", re.I)


def extract_listed(text: str, names) -> set:
    """Medicine and --names names found in any case, reported in lower case."""
    if not names:
        return set()
    return {" ".join(m.group(0).lower().split()) for m in _list_re(names).finditer(text)}


def extract_names(text: str, other: str, listed=()) -> set:
    listed_low = {n.lower() for n in listed}
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
        if word.lower() in listed_low:
            continue    # reported, in any case, by extract_listed
        if word in CALENDAR_NAMES and not (word == "May" and _at_sentence_start(text, m.start())):
            names.add(word)
            continue
        is_acronym = sum(c.isupper() for c in word) >= 2
        if is_acronym or word in mid_caps:
            names.add(word)
    return names


def extract_links(text: str) -> set:
    return {m.group(0).rstrip(".,;:!?)]'\"").lower() for m in URL_RE.finditer(text)}


def warning_counts(text: str) -> Counter:
    low = text.lower()
    low = re.sub(r"\bcan't\b|\bcannot\b", "can not", low)
    low = re.sub(r"\bwon't\b", "will not", low)
    low = re.sub(r"n't\b", " not", low)
    return Counter(" ".join(m.group(0).split()) for m in WARNING_RE.finditer(low))


def _contains_word(text: str, word: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text) is not None


def _blank(text: str, spans) -> str:
    chars = list(text)
    for s, e in spans:
        for i in range(s, e):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def diff(source: str, rewrite: str, names=None) -> dict:
    source, rewrite = _normalise(source), _normalise(rewrite)
    listed = list(MEDICINE_NAMES) + list(names or [])
    src_spans, new_spans = [], []
    src_dates, src_rest = extract_dates(source, src_spans)
    new_dates, new_rest = extract_dates(rewrite, new_spans)
    src_list = extract_number_list(src_rest)
    new_list = extract_number_list(new_rest)
    src_nums, new_nums = Counter(src_list), Counter(new_list)

    dropped_nums = sorted(n for n in src_nums if n not in new_nums)
    added_nums = sorted(n for n in new_nums if n not in src_nums)
    counts = [{"item": n, "source": src_nums[n], "rewrite": new_nums[n]}
              for n in sorted(src_nums) if n in new_nums and src_nums[n] != new_nums[n]]
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
    order_changed = src_nums == new_nums and src_list != new_list

    # Names are read with the dates blanked out: dates are compared on their own.
    src_text, new_text = _blank(source, src_spans), _blank(rewrite, new_spans)
    src_names = extract_names(src_text, new_text, listed)
    new_names = extract_names(new_text, src_text, listed)
    dropped_names = {n for n in src_names if not _contains_word(rewrite, n)}
    added_names = {n for n in new_names if not _contains_word(source, n)}
    src_listed, new_listed = extract_listed(source, listed), extract_listed(rewrite, listed)
    dropped_names |= src_listed - new_listed
    added_names |= new_listed - src_listed

    src_links, new_links = extract_links(source), extract_links(rewrite)
    src_words, new_words = warning_counts(source), warning_counts(rewrite)
    words = [{"word": w, "source": src_words[w], "rewrite": new_words[w]}
             for w in WARNING_WORDS if src_words[w] != new_words[w]]

    return {
        "changed": changed,
        "dropped": {"numbers": dropped_nums, "dates": sorted(src_dates - new_dates), "names": sorted(dropped_names),
                    "links": sorted(src_links - new_links)},
        "added": {"numbers": added_nums, "dates": sorted(new_dates - src_dates), "names": sorted(added_names),
                  "links": sorted(new_links - src_links)},
        "counts": counts,
        "words": words,
        "order_changed": order_changed,
    }


def has_differences(result: dict) -> bool:
    return (bool(result["changed"]) or any(result["dropped"].values()) or any(result["added"].values())
            or bool(result.get("counts")) or bool(result.get("words")) or bool(result.get("order_changed")))


def _read(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig")


def _read_names(path: str) -> list:
    items = [ln.split("#", 1)[0].strip() for ln in _read(path).splitlines()]
    return [i for i in items if i]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report numbers, dates, names, links and warning words that a rewrite added, dropped or changed "
                    "compared with its source. Surface only: a person still reads the rewrite against the source.",
        epilog="Exit codes: 0 no differences, 1 at least one difference, 2 usage error.")
    parser.add_argument("source", help="the original text (UTF-8)")
    parser.add_argument("rewrite", help="the rewritten text (UTF-8)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--names", help="a UTF-8 file of extra names to compare in any case, one per line ('#' starts a comment)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        names = _read_names(args.names) if args.names else None
        result = diff(_read(args.source), _read(args.rewrite), names=names)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for c in result["changed"]:
            print(f"CHANGED number: {c['from']} -> {c['to']}")
        for kind in ("numbers", "dates", "names", "links"):
            for item in result["dropped"][kind]:
                print(f"DROPPED {kind[:-1]}: {item}")
            for item in result["added"][kind]:
                print(f"ADDED {kind[:-1]}: {item}")
        for c in result["counts"]:
            print(f"COUNT changed: '{c['item']}' appears {c['source']} time(s) in the source, {c['rewrite']} in the rewrite")
        for w in result["words"]:
            print(f"WORD count changed: '{w['word']}' appears {w['source']} time(s) in the source, {w['rewrite']} in the rewrite")
        if result["order_changed"]:
            print("ORDER changed: the same numbers appear in a different order; check each is still with the right step")
        if not has_differences(result):
            print("No numbers, dates, names, links or warning words were added, dropped or changed. This checks the "
                  "surface only; a person still reads the rewrite against the source.")
    return 1 if has_differences(result) else 0


if __name__ == "__main__":
    sys.exit(main())
