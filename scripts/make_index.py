#!/usr/bin/env python3
"""Build skills-index.json from the frontmatter of each skill in .claude/skills/."""

import argparse
import json
import os
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

        entry = {
            "name": name,
            "description": fm.get("description", ""),
            "license": fm.get("license", ""),
            "version": meta.get("version", ""),
            "path": f".claude/skills/{folder}",
            "capabilities": caps_list,
            "optional_capabilities": opt_list,
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

    if args.check:
        if out_path.is_file():
            existing = out_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            if existing == text:
                print("ok")
                sys.exit(0)
        print("ERROR skills-index.json: out of date; run python scripts/make_index.py")
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    try:
        rel = os.path.relpath(str(out_path), str(root))
    except ValueError:
        rel = str(out_path)

    print(f"wrote {rel}")
    sys.exit(0)


if __name__ == "__main__":
    main()
