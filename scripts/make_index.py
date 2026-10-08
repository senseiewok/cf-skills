#!/usr/bin/env python3
"""Build skills-index.json from the frontmatter of each skill in .claude/skills/, and from the same facts the generated
page docs/skills-by-audience.md and the small table between the skills-table markers in README.md.

Usage:  python scripts/make_index.py [ROOT] [--check] [--out PATH]

Without --check it writes all three. With --check it writes nothing and exits 1 if any of them is out of date.
A README.md without the markers is an error; a repository without a README.md gets the index and the page only.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ALLOWED_CAPABILITIES = {
    "network",
    "runs-code",
    "python",
    "reads-project-files",
    "writes-files",
    "browser",
    "api-key",
}

# Keep these lists equal to the ones in scripts/check_repo.py. The order here is the order of the generated page.
AUDIENCES = ("patients-families", "care-teams", "researchers", "builders")
AUDIENCE_LABELS = {
    "patients-families": "Patients and families",
    "care-teams": "Care teams",
    "researchers": "Researchers",
    "builders": "Builders",
}
LEVELS = ("base", "advanced")
CATEGORIES = ("safe-ai-use", "communication", "evidence", "tool-evaluation", "web")

PAGE_REL = "docs/skills-by-audience.md"
README_START = "<!-- skills-table:start -->"
README_END = "<!-- skills-table:end -->"

AGENTS = [
    ("claude", ".claude/skills", ".claude/skills", "claude-code"),
    ("copilot", ".github/skills", ".copilot/skills", "github-copilot"),
    ("codex", ".agents/skills", ".agents/skills", "codex"),
    ("gemini", ".agents/skills", ".agents/skills", "gemini-cli"),
    ("cursor", ".agents/skills", ".agents/skills", "cursor"),
    ("amp", ".agents/skills", ".agents/skills", "amp"),
    ("opencode", ".agents/skills", ".agents/skills", "opencode"),
    ("goose", ".agents/skills", ".agents/skills", "goose"),
    ("windsurf", ".agents/skills", ".agents/skills", None),
    ("qwen", ".qwen/skills", ".qwen/skills", "qwen-code"),
]


def strip_quotes(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        return v[1:-1]
    return v


def parse_frontmatter(text: str):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}

    body = lines[1:end_idx]
    result = {"metadata": {}}
    in_metadata = False

    for line in body:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 0:
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = strip_quotes(value)
            if key == "metadata":
                in_metadata = True
                result["metadata"] = {}
            else:
                in_metadata = False
                result[key] = value
        else:
            if in_metadata and ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = strip_quotes(value)
                result["metadata"][key] = value

    return result


def clean_cap_list(raw: str):
    words = [w.strip() for w in raw.split(",")]
    words = [w for w in words if w]
    seen = set()
    unique = []
    for w in words:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return sorted(unique)


def check_capabilities(name: str, caps_list: list):
    problems = []
    for word in caps_list:
        if word not in ALLOWED_CAPABILITIES:
            problems.append(f"ERROR {name}: unknown capability '{word}'")
    return problems


def read_audience_keys(folder: str, meta: dict):
    """Return (audience list in AUDIENCES order, level, category, problems) from a skill's metadata."""
    where = f"ERROR .claude/skills/{folder}/SKILL.md"
    problems = []
    raw = meta.get("audience", "")
    words = [w.strip() for w in raw.split(",") if w.strip()]
    if not words:
        problems.append(f"{where}: missing metadata 'audience'; one or more of: {', '.join(AUDIENCES)}")
    for w in words:
        if w not in AUDIENCES:
            problems.append(f"{where}: unknown audience '{w}'; allowed: {', '.join(AUDIENCES)}")
    audience_list = [a for a in AUDIENCES if a in words]
    values = {}
    for key, allowed in (("level", LEVELS), ("category", CATEGORIES)):
        val = meta.get(key, "").strip()
        if not val:
            problems.append(f"{where}: missing metadata '{key}'; one of: {', '.join(allowed)}")
        elif val not in allowed:
            problems.append(f"{where}: unknown {key} '{val}'; allowed: {', '.join(allowed)}")
        values[key] = val
    return audience_list, values["level"], values["category"], problems


def first_sentence(text: str) -> str:
    """The description up to and including its first full stop, question or exclamation mark followed by a space or the end."""
    m = re.match(r"(.+?[.!?])(?:\s|$)", text.strip(), re.S)
    return (m.group(1) if m else text.strip())


def _cell(text: str) -> str:
    """Make text safe inside one Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def render_page(obj: dict) -> str:
    """docs/skills-by-audience.md: for each audience, a table of the skills written for it."""
    lines = [
        "# Skills by audience",
        "",
        "<!-- Generated file: do not edit by hand. -->",
        "",
        "*Generated by `python scripts/make_index.py` from each skill's frontmatter; `python scripts/make_index.py --check` fails when this page is out of date.*",
        "",
        "Find your group below, pick a skill, then install it the way [install.md](install.md) describes for your agent, "
        "or paste a prompt from [prompts.md](prompts.md). A skill can be listed under more than one group.",
        "",
        "Some skills also have a `references/paste-ready.md`: plain text to copy into any chat assistant, with no install. "
        "[paste-ready.md](paste-ready.md) says where to paste it in common AI products.",
        "",
        "- **base**: a person can follow it with no setup, in a plain chat.",
        "- **advanced**: needs a tool, a script or care to apply.",
        "",
        "Read a skill's `SKILL.md` and its scripts before you let an agent run them. Research, not medical advice.",
    ]
    for aud in AUDIENCES:
        lines += ["", f"## {AUDIENCE_LABELS[aud]}", ""]
        skills = [s for s in obj["skills"] if aud in s["audience"]]
        if not skills:
            lines.append("No skill for this group yet.")
            continue
        lines += [
            "| Skill | Level | Category | What it does | Install |",
            "| --- | --- | --- | --- | --- |",
        ]
        for s in skills:
            lines.append(
                f"| [`{s['name']}`](../{s['path']}/SKILL.md) | {s['level']} | {s['category']} | "
                f"{_cell(first_sentence(s['description']))} | [install](install.md) |"
            )
    return "\n".join(lines) + "\n"


def render_readme_table(obj: dict) -> str:
    """The small table that goes between the skills-table markers in README.md."""
    lines = [
        f"Who each skill is for (generated by `python scripts/make_index.py`; a table per group, with categories, in [docs/skills-by-audience.md]({PAGE_REL})):",
        "",
        "| Skill | For whom | Level |",
        "| --- | --- | --- |",
    ]
    for s in obj["skills"]:
        who = ", ".join(AUDIENCE_LABELS[a] for a in s["audience"])
        lines.append(f"| [`{s['name']}`]({s['path']}/SKILL.md) | {who} | {s['level']} |")
    return "\n".join(lines)


def splice_readme(readme: str, table: str):
    """Return README text (LF line ends) with the table between the markers, or None if the markers are missing or out of order."""
    text = readme.replace("\r\n", "\n")
    start = text.find(README_START)
    end = text.find(README_END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[: start + len(README_START)] + "\n" + table + "\n" + text[end:]


def build_index(root: Path):
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return None, ["ERROR .claude/skills: directory does not exist"]

    folders = sorted(
        [d.name for d in skills_dir.iterdir() if d.is_dir()]
    )

    problems = []
    entries = []

    for folder in folders:
        skill_md = skills_dir / folder / "SKILL.md"
        if not skill_md.is_file():
            problems.append(f"ERROR .claude/skills/{folder}: no SKILL.md")
            continue

        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception as e:
            problems.append(f"ERROR .claude/skills/{folder}: cannot read SKILL.md ({e})")
            continue

        fm = parse_frontmatter(text)
        name = fm.get("name", folder)

        meta = fm.get("metadata", {})
        caps_raw = meta.get("capabilities")
        if caps_raw is None:
            problems.append(f"ERROR .claude/skills/{folder}: missing capabilities for skill '{name}'")
            continue

        caps_list = clean_cap_list(caps_raw)
        opt_raw = meta.get("optional-capabilities", "")
        opt_list = clean_cap_list(opt_raw) if opt_raw else []

        cap_problems = check_capabilities(name, caps_list)
        problems.extend(cap_problems)

        audience_list, level, category, aud_problems = read_audience_keys(folder, meta)
        problems.extend(aud_problems)

        entry = {
            "name": name,
            "description": fm.get("description", ""),
            "license": fm.get("license", ""),
            "version": meta.get("version", ""),
            "path": f".claude/skills/{folder}",
            "capabilities": caps_list,
            "optional_capabilities": opt_list,
            "audience": audience_list,
            "level": level,
            "category": category,
            "install": {
                "script": f"python scripts/install_skill.py {name} --agent claude",
                "gh": f"gh skill install senseiewok/cf-skills .claude/skills/{name} --agent claude-code",
                "claude_plugin": f"/plugin install {name}@sensei-ewok-skills",
            },
        }
        entries.append(entry)

    if problems:
        return None, sorted(problems)

    agents_obj = {}
    for agent_name, project, user, gh_agent in AGENTS:
        agents_obj[agent_name] = {
            "project": project,
            "user": user,
            "gh_agent": gh_agent,
        }

    obj = {
        "schema": 1,
        "repository": "senseiewok/cf-skills",
        "marketplace": "sensei-ewok-skills",
        "skills": entries,
        "agents": agents_obj,
    }
    return obj, []


def main():
    parser = argparse.ArgumentParser(description="Build skills-index.json")
    parser.add_argument("root", nargs="?", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).resolve()
    else:
        script_dir = Path(__file__).resolve().parent
        root = script_dir.parent

    if not root.is_dir():
        print(f"ERROR: ROOT '{root}' is not an existing folder", file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.out).resolve() if args.out else root / "skills-index.json"

    obj, problems = build_index(root)

    if problems:
        for p in problems:
            print(p)
        sys.exit(1)

    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    page_path = root / PAGE_REL
    page_text = render_page(obj)

    # README.md: optional, but when present it must carry the markers.
    readme_path = root / "README.md"
    readme_old = None
    readme_new = None
    readme_crlf = False
    if readme_path.is_file():
        readme_old = readme_path.read_bytes().decode("utf-8")  # bytes, so CRLF line ends are seen and kept
        readme_crlf = "\r\n" in readme_old
        readme_new = splice_readme(readme_old, render_readme_table(obj))
        if readme_new is None:
            print(f"ERROR README.md: missing or misordered markers; add a line {README_START} and, below it, a line {README_END} where the skills table goes")
            sys.exit(1)

    def current(path: Path, expected: str) -> bool:
        return path.is_file() and path.read_text(encoding="utf-8").replace("\r\n", "\n") == expected

    if args.check:
        stale = []
        if not current(out_path, text):
            stale.append("skills-index.json")
        if not current(page_path, page_text):
            stale.append(PAGE_REL)
        if readme_old is not None and readme_old.replace("\r\n", "\n") != readme_new:
            stale.append("README.md (skills table)")
        if stale:
            for s in stale:
                print(f"ERROR {s}: out of date; run python scripts/make_index.py")
            sys.exit(1)
        print("ok")
        sys.exit(0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    with open(page_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page_text)
    written = [out_path, page_path]
    if readme_new is not None and readme_old.replace("\r\n", "\n") != readme_new:
        # keep the README's own line endings
        with open(readme_path, "w", encoding="utf-8", newline="") as f:
            f.write(readme_new.replace("\n", "\r\n") if readme_crlf else readme_new)
        written.append(readme_path)

    for p in written:
        try:
            rel = os.path.relpath(str(p), str(root))
        except ValueError:
            rel = str(p)
        print(f"wrote {Path(rel).as_posix()}")
    sys.exit(0)


if __name__ == "__main__":
    main()
