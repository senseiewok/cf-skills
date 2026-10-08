#!/usr/bin/env python3
"""Measure the reading level of a text, so the level is measured and not claimed.

Usage:
    python readability.py [FILE] [--max-grade N] [--json]

Reads FILE, or standard input when FILE is missing or "-". Prints the word, sentence and syllable
counts, the average sentence length in words, the Flesch-Kincaid grade level, and the longest sentences.

Flesch-Kincaid grade = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59

How the counts are made (deterministic; the same text always gives the same numbers):
    words      runs of letters, digits, apostrophes and inner hyphens; "2" and "30%" count as one word
    sentences  a run of text ending in . ! or ? followed by a space or the end; a line break also ends a
               sentence when the line has no end mark (list items and headings); decimals such as 2.5
               and a short list of abbreviations (e.g., i.e., Dr., etc.) do not end a sentence
    syllables  per word: lower-case it; count groups of vowels (a e i o u y); take one off for a final
               silent "e" (but not "le" after a consonant, as in "table"), and for a final "es" or "ed"
               that is not voiced (as in "makes", "liked" but not "uses", "added"); at least 1.
               A word with digits counts as 1 syllable.

The syllable rule is a heuristic. It is wrong for some words (for example "recipe"), so treat the
grade as an estimate within about one grade, and compare texts measured the same way.
A grade level measures sentence and word length only. It does not tell you a text is clear, kind or correct.

Exit codes:
    0  measured (and at or under --max-grade, when given)
    1  the grade is above --max-grade
    2  usage error: unreadable file, not UTF-8, or no words to measure

Python 3.9+, standard library only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

WORD_RE = re.compile(r"[A-Za-z0-9À-ɏ]+(?:['’\-][A-Za-z0-9À-ɏ]+)*%?")
ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "Dr.", "Mr.", "Mrs.", "Ms.", "vs.", "approx.", "St.", "No.")
VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    """Count syllables in one word with the documented heuristic."""
    if any(c.isdigit() for c in word):
        return 1
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    count = len(VOWEL_GROUP_RE.findall(w))
    if len(w) > 2 and w.endswith("e") and not w.endswith(("le", "ee", "ye")):
        count -= 1
    elif len(w) > 2 and w.endswith("le") and w[-3] in "aeiouy":
        count -= 1
    elif len(w) > 3 and w.endswith("es") and w[-3] not in "aeiouysxzgc" and not w.endswith(("ches", "shes")):
        count -= 1
    elif len(w) > 3 and w.endswith("ed") and w[-3] not in "aeiouytd":
        count -= 1
    return max(1, count)


def sentences(text: str) -> list:
    """Split text into sentences with the documented rules."""
    protected = text
    for abbr in ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", "\u0000"))
    protected = re.sub(r"(?<=\d)\.(?=\d)", "\u0000", protected)
    out = []
    for line in protected.splitlines():
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)  # list markers are not words
        line = re.sub(r"^\s*#+\s*", "", line)                 # nor are heading marks
        for part in re.split(r"(?<=[.!?])[\"')\]]*\s+", line):
            part = part.strip()
            if part and WORD_RE.search(part):
                out.append(part.replace("\u0000", "."))
    return out


def measure(text: str) -> dict:
    sents = sentences(text)
    per_sentence = [WORD_RE.findall(s) for s in sents]
    words = [w for ws in per_sentence for w in ws]
    if not words:
        raise ValueError("no words to measure")
    n_words = len(words)
    n_sents = len(sents)
    n_syll = sum(syllables(w) for w in words)
    grade = 0.39 * (n_words / n_sents) + 11.8 * (n_syll / n_words) - 15.59
    longest = sorted(zip(sents, (len(ws) for ws in per_sentence)), key=lambda p: -p[1])[:3]
    return {
        "words": n_words,
        "sentences": n_sents,
        "syllables": n_syll,
        "average_sentence_length": round(n_words / n_sents, 1),
        "flesch_kincaid_grade": round(grade, 1),
        "longest_sentences": [{"words": n, "sentence": s} for s, n in longest],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the Flesch-Kincaid grade level and average sentence length of a text "
                    "(a documented syllable heuristic; an estimate within about one grade).",
        epilog="Exit codes: 0 measured (and within --max-grade), 1 above --max-grade, 2 usage error.")
    parser.add_argument("file", nargs="?", default="-", help="a UTF-8 text file; '-' or nothing reads standard input")
    parser.add_argument("--max-grade", type=float, default=None, help="exit 1 when the grade is above this number")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        data = sys.stdin.buffer.read() if args.file == "-" else open(args.file, "rb").read()
        result = measure(data.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    over = args.max_grade is not None and result["flesch_kincaid_grade"] > args.max_grade
    result["max_grade"] = args.max_grade
    result["above_max_grade"] = over
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Flesch-Kincaid grade: {result['flesch_kincaid_grade']} (an estimate)")
        print(f"Average sentence length: {result['average_sentence_length']} words")
        print(f"Words {result['words']}, sentences {result['sentences']}, syllables {result['syllables']}")
        print("Longest sentences:")
        for item in result["longest_sentences"]:
            print(f"  {item['words']} words: {item['sentence']}")
        if args.max_grade is not None:
            print(f"{'ABOVE' if over else 'within'} the target of grade {args.max_grade}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
