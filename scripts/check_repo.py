#!/usr/bin/env python3
"""scripts/check_repo.py -- mechanical checker for a repository of agent skills.

Usage:  python check_repo.py [ROOT]

ROOT defaults to the folder above the folder that holds this script
(i.e. the parent of ``scripts/``).  If ROOT is not an existing directory,
print a usage message and exit 2.  Otherwise run every check, print one
line per problem (sorted), and exit 1 if any problem was found, else
print ``ok`` and exit 0.

Standard library only; no network; no subprocess; never writes a file.
"""

import json
import re
import sys
from pathlib import Path

# Skills live where Claude Code, Copilot and Cursor read project skills, so a clone of this repository works as a skills folder at once.
SKILLS_REL = ".claude/skills"
SKILLS_DIR = Path(".claude") / "skills"

# The frontmatter keys of the Agent Skills format. The same set, plus the angle-bracket and compatibility-length rules below, is what
# skill-creator's quick_validate.py in Anthropic's public skills enforces (Apache-2.0; the rules are written here from reading that script).
ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
_BLOCK_MARKERS = (">", "|", ">-", "|-", ">+", "|+")

# Who a skill is for, how much it asks of the reader, and what kind of help it is. Required for every skill, as strings under `metadata:`,
# so docs/skills-by-audience.md (written by scripts/make_index.py) can list each skill where its readers will look. Keep these lists equal
# to the ones in scripts/make_index.py.
AUDIENCES = ("patients-families", "care-teams", "researchers", "builders")
LEVELS = ("base", "advanced")
CATEGORIES = ("safe-ai-use", "communication", "evidence", "tool-evaluation", "web")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _rel(root: Path, p: Path) -> str:
    """Return *p* relative to *root* using forward slashes."""
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return str(p)


def _read_text(p: Path):
    """Read a file as UTF-8; return None if it cannot be read."""
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _parse_frontmatter(text: str):
    """Return a dict of top-level key/value pairs from YAML-ish frontmatter.

    Returns None if the text does not start with a proper frontmatter
    block (a line --- followed later by another line ---).
    Only lines that start with an ASCII letter followed eventually by :
    are treated as top-level keys; indented lines are skipped.
    Quoted values have their outer quotes stripped.
    """
    if not text or not text.startswith("---"):
        return None
    lines = text.splitlines()
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end == -1:
        return None

    fm = {}
    for line in lines[1:end]:
        if not line or line[0] in (" ", "\t"):
            continue
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        fm[key] = val
    return fm


def _parse_metadata(text: str) -> dict:
    """Return the indented ``key: value`` pairs under a top-level ``metadata:`` key in the frontmatter.

    Values are strings with their outer quotes stripped. Returns an empty dict when there is no metadata block.
    """
    meta = {}
    in_meta = False
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        if not line.strip():
            continue
        if line[0] not in (" ", "\t"):
            in_meta = bool(re.match(r"^metadata:\s*$", line))
            continue
        if not in_meta:
            continue
        m = re.match(r"^\s+([A-Za-z][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        val = m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        meta[m.group(1)] = val
    return meta


def _check_audience_keys(rel_md: str, meta: dict, errors: list):
    """audience, level and category: required under metadata, each value from its fixed list."""
    raw = meta.get("audience")
    if raw is None or not raw.strip():
        errors.append(
            "ERROR {}: missing metadata 'audience'; add it under metadata: as a comma-separated string of one or more of: {}".format(
                rel_md, ", ".join(AUDIENCES))
        )
    else:
        for word in [w.strip() for w in raw.split(",")]:
            if word and word not in AUDIENCES:
                errors.append(
                    "ERROR {}: unknown audience '{}' in metadata; allowed (comma-separated): {}".format(rel_md, word, ", ".join(AUDIENCES))
                )
    for key, allowed in (("level", LEVELS), ("category", CATEGORIES)):
        val = meta.get(key)
        if val is None or not val.strip():
            errors.append(
                "ERROR {}: missing metadata '{}'; add it under metadata: as one of: {}".format(rel_md, key, ", ".join(allowed))
            )
        elif val.strip() not in allowed:
            errors.append(
                "ERROR {}: unknown {} '{}' in metadata; allowed (exactly one): {}".format(rel_md, key, val.strip(), ", ".join(allowed))
            )


# ---------------------------------------------------------------------------
# checks 1-4: frontmatter / name / description / license
# ---------------------------------------------------------------------------

def _check_skill_meta(root: Path, folder_name: str, errors: list):
    skill_dir = root / SKILLS_DIR / folder_name
    skill_md = skill_dir / "SKILL.md"
    rel_md = _rel(root, skill_md)
    rel_folder = SKILLS_REL + "/" + folder_name

    if not skill_md.is_file():
        errors.append("ERROR {}: no SKILL.md".format(rel_folder))
        return

    text = _read_text(skill_md)
    if text is None:
        errors.append("ERROR {}: unreadable file".format(rel_md))
        return

    fm = _parse_frontmatter(text)
    if fm is None:
        errors.append("ERROR {}: missing or malformed frontmatter".format(rel_md))
        return

    # name
    name = fm.get("name")
    if name is None:
        errors.append("ERROR {}: missing required field 'name' in frontmatter".format(rel_md))
    else:
        if name != folder_name:
            errors.append(
                "ERROR {}: name '{}' does not match folder name '{}'".format(rel_md, name, folder_name)
            )
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
            errors.append(
                "ERROR {}: name '{}' must consist only of lowercase letters, digits and single hyphens in the middle".format(rel_md, name)
            )
        if len(name) > 64:
            errors.append("ERROR {}: name is longer than 64 characters".format(rel_md))

    # description
    desc = fm.get("description")
    if desc in _BLOCK_MARKERS:
        errors.append("ERROR {}: description must be a one-line string (a folded or literal block is not read by this checker)".format(rel_md))
    elif desc is None or desc == "":
        errors.append(
            "ERROR {}: missing or empty required field 'description' in frontmatter".format(rel_md)
        )
    elif len(desc) > 1024:
        errors.append(
            "ERROR {}: description is longer than 1024 characters".format(rel_md)
        )

    # angle brackets can be read as markup by an agent that puts the description into its prompt
    if desc and desc not in _BLOCK_MARKERS and ("<" in desc or ">" in desc):
        errors.append("ERROR {}: description must not contain angle brackets (< or >)".format(rel_md))

    # license
    if "license" not in fm or fm["license"] == "":
        errors.append("ERROR {}: missing required field 'license' in frontmatter".format(rel_md))

    # compatibility (optional)
    compat = fm.get("compatibility")
    if compat and compat not in _BLOCK_MARKERS and len(compat) > 500:
        errors.append("ERROR {}: compatibility is longer than 500 characters".format(rel_md))

    # keys outside the Agent Skills format are not read the same way by every agent
    unknown = sorted(set(fm) - ALLOWED_KEYS)
    if unknown:
        hint = ""
        if set(unknown) & {"audience", "level", "category", "capabilities", "optional-capabilities", "version"}:
            hint = " (audience, level, category, capabilities and version go indented under metadata:)"
        errors.append(
            "ERROR {}: unexpected frontmatter key(s): {}. Allowed: {}{}".format(rel_md, ", ".join(unknown), ", ".join(sorted(ALLOWED_KEYS)), hint)
        )

    _check_audience_keys(rel_md, _parse_metadata(text), errors)


# ---------------------------------------------------------------------------
# check 5: relative links
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_IGNORE_PREFIXES = ("http://", "https://", "mailto:", "#")


def _check_links(root: Path, errors: list):
    files = []

    readme = root / "README.md"
    if readme.is_file():
        files.append(readme)

    for sub in ("docs", "spec", "template"):
        d = root / sub
        if d.is_dir():
            for p in sorted(d.rglob("*.md")):
                if p.is_file():
                    files.append(p)

    skills_dir = root / SKILLS_DIR
    if skills_dir.is_dir():
        for folder in sorted(skills_dir.iterdir()):
            if not folder.is_dir():
                continue
            sm = folder / "SKILL.md"
            if sm.is_file():
                files.append(sm)

    for f in files:
        text = _read_text(f)
        if text is None:
            continue
        rel_f = _rel(root, f)
        in_fence = False
        for line in text.splitlines():
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in _LINK_RE.finditer(line):
                target = m.group(2).strip()
                if any(target.startswith(p) for p in _IGNORE_PREFIXES):
                    continue
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (f.parent / path_part).resolve()
                if not resolved.exists():
                    errors.append("ERROR {}: broken link {}".format(rel_f, target))


# ---------------------------------------------------------------------------
# check 6: marketplace
# ---------------------------------------------------------------------------

def _check_marketplace(root: Path, skill_folders: list, errors: list):
    mp_path = root / ".claude-plugin" / "marketplace.json"
    rel_mp = ".claude-plugin/marketplace.json"

    if not mp_path.is_file():
        if skill_folders:
            errors.append("ERROR {}: file is missing but skill folders exist".format(rel_mp))
        return

    raw = _read_text(mp_path)
    if raw is None:
        errors.append("ERROR {}: unreadable file".format(rel_mp))
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        errors.append("ERROR {}: invalid JSON".format(rel_mp))
        return

    if not isinstance(data, dict):
        errors.append("ERROR {}: top-level value is not an object".format(rel_mp))
        return

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        errors.append("ERROR {}: 'plugins' is not a list".format(rel_mp))
        return

    folder_counts = {}
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        skills = plugin.get("skills", [])
        if not isinstance(skills, list):
            continue
        for entry in skills:
            if not isinstance(entry, str):
                continue
            e = entry.replace("\\", "/")
            if e.startswith("./"):
                e = e[2:]
            prefix = SKILLS_REL + "/"
            if e.startswith(prefix) and e[len(prefix):]:
                folder = e[len(prefix):].split("/")[0]
                folder_counts[folder] = folder_counts.get(folder, 0) + 1
                skill_dir = root / SKILLS_DIR / folder
                if not skill_dir.is_dir():
                    errors.append(
                        "ERROR {}: marketplace references missing skill folder '{}'".format(rel_mp, folder)
                    )

    for sf in skill_folders:
        if sf not in folder_counts:
            errors.append(
                "ERROR {}/{}: skill folder is not listed in any marketplace plugin".format(SKILLS_REL, sf)
            )

    for folder in sorted(folder_counts):
        if folder_counts[folder] > 1:
            errors.append(
                "ERROR {}/{}: skill folder is listed twice (or more) in marketplace plugins".format(SKILLS_REL, folder)
            )


# ---------------------------------------------------------------------------
# check 7: hygiene
# ---------------------------------------------------------------------------

_HYGIENE_PATTERNS = [
    ("Windows drive path", re.compile(r"[A-Za-z]:\\[A-Za-z]")),
    ("home folder path", re.compile(r"/Users/|/home/")),
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("token", re.compile(r"(?:ghp_|github_pat_|sk-)[A-Za-z0-9_]{20,}")),
    ("private key text", re.compile(r"PRIVATE KEY")),
]


def _check_hygiene(root: Path, errors: list):
    files = []

    readme = root / "README.md"
    if readme.is_file():
        files.append(readme)

    for sub in ("docs", "spec", "template"):
        d = root / sub
        if d.is_dir():
            for p in sorted(d.rglob("*.md")):
                if p.is_file():
                    files.append(p)

    skills_dir = root / SKILLS_DIR
    if skills_dir.is_dir():
        for folder in sorted(skills_dir.iterdir()):
            if not folder.is_dir():
                continue
            sm = folder / "SKILL.md"
            if sm.is_file():
                files.append(sm)
            refs = folder / "references"
            if refs.is_dir():
                for p in sorted(refs.rglob("*.md")):
                    if p.is_file():
                        files.append(p)

    for f in files:
        text = _read_text(f)
        if text is None:
            continue
        rel_f = _rel(root, f)
        for kind, pat in _HYGIENE_PATTERNS:
            if pat.search(text):
                errors.append("ERROR {}: {} found".format(rel_f, kind))


# ---------------------------------------------------------------------------
# check 8: eval cases that point at pasted text they do not contain
# ---------------------------------------------------------------------------

# A tester sends a case's user_message, or its situation when there is none. A prompt such as "Translate this handout" with no handout
# in it tests nothing the case's expected lines describe, so the case fails here unless a person has marked it suspect with a note.
_DOC_WORDS = (r"(?:handout|leaflet|letter|flyer|guide|report|answer|text|note|post|sheet|document|record|message|page|paragraph"
              r"|summary|email|article)s?")
_REFERS_TO_PASTED = [
    re.compile(r"\b(?:translate|rewrite|simplify|summari[sz]e|explain|check|shorten|reword|make)\s+(?:this|these|it)\b", re.I),
    re.compile(r"\b(?:this|these|the following|the attached|the pasted)\s+(?:[\w'-]+\s+){0,3}?" + _DOC_WORDS + r"\b", re.I),
    re.compile(r"\b(?:the text|the passage|the words)\s+below\b", re.I),
    re.compile(r"\bhere(?:'s| is| are)\s+(?:my|the|a|our)\b", re.I),
]
# Pasted text counts as present when the prompt quotes at least 20 characters, has text after a colon, or has a block on a new line.
_HAS_PASTED = re.compile(r"'[^']{20,}'|\"[^\"]{20,}\"|‘[^’]{20,}’|“[^”]{20,}”|:\s*\S.{19,}|\n\s*\S")


def refers_to_missing_text(case: dict) -> bool:
    """True when the case has no user_message and its situation points at pasted text that is not there."""
    um = case.get("user_message")
    if isinstance(um, str) and um.strip():
        return False
    sit = case.get("situation") or ""
    return any(p.search(sit) for p in _REFERS_TO_PASTED) and not _HAS_PASTED.search(sit)


def _check_eval_cases(root: Path, errors: list):
    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    for f in sorted(skills_dir.glob("*/evals/cases.json")):
        rel_f = _rel(root, f)
        raw = _read_text(f)
        try:
            data = json.loads(raw) if raw is not None else None
        except (json.JSONDecodeError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
            errors.append("ERROR {}: not a JSON object with a 'cases' list".format(rel_f))
            continue
        for case in data["cases"]:
            if not isinstance(case, dict):
                continue
            cid = case.get("id", "?")
            suspect = case.get("suspect", False)
            if not isinstance(suspect, bool):
                errors.append("ERROR {}: case '{}': 'suspect' must be true or false".format(rel_f, cid))
                continue
            note = case.get("suspect_note")
            if suspect and not (isinstance(note, str) and note.strip()):
                errors.append("ERROR {}: case '{}' is suspect but has no 'suspect_note' saying why".format(rel_f, cid))
            if refers_to_missing_text(case) and not suspect:
                errors.append(
                    "ERROR {}: case '{}' refers to pasted text but has no user_message holding it; add the text as user_message "
                    "(a person writes it), or mark the case \"suspect\": true with a \"suspect_note\"".format(rel_f, cid)
                )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv):
    if len(argv) > 1:
        root = Path(argv[1])
    else:
        script_dir = Path(__file__).resolve().parent
        root = script_dir.parent

    if not root.is_dir():
        print("error: ROOT is not an existing directory: {}".format(root))
        return 2

    errors = []

    skill_folders = []
    skills_dir = root / SKILLS_DIR
    if skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            if entry.is_dir():
                skill_folders.append(entry.name)

    for sf in skill_folders:
        _check_skill_meta(root, sf, errors)

    _check_links(root, errors)

    _check_marketplace(root, skill_folders, errors)

    _check_hygiene(root, errors)

    _check_eval_cases(root, errors)

    if errors:
        for e in sorted(errors):
            print(e)
        return 1
    else:
        print("ok")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
