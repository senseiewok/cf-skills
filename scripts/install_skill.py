#!/usr/bin/env python3
"""Install one or more agent skills into the folder an agent reads."""
import argparse
import json
import shutil
import sys
from pathlib import Path

AGENTS = {
    "claude": {
        "project": ".claude/skills",
        "user": ".claude/skills",
    },
    "copilot": {
        "project": ".github/skills",
        "user": ".copilot/skills",
    },
    "codex": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "gemini": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "cursor": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "amp": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "opencode": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "goose": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "windsurf": {
        "project": ".agents/skills",
        "user": ".agents/skills",
    },
    "qwen": {
        "project": ".qwen/skills",
        "user": ".qwen/skills",
    },
}

CAPABILITY_TEXT = {
    "network": "It makes requests to the internet.",
    "runs-code": "It ships scripts an agent may run: read the scripts before you let an agent run them.",
    "python": "It needs Python.",
    "reads-project-files": "It reads files in your project.",
    "writes-files": "It writes files.",
    "browser": "It uses a browser.",
    "api-key": "It needs an API key.",
}


def parse_frontmatter_description(skill_md_path):
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if stripped.startswith("description:"):
            value = stripped[len("description:"):].strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            return value.strip()
    return ""


def list_skills(skills_dir):
    skills = []
    if not skills_dir.is_dir():
        return skills
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            desc = parse_frontmatter_description(skill_md) if skill_md.is_file() else ""
            skills.append((entry.name, desc))
    return skills


def validate_skill_name(name, skills_dir):
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    candidate = skills_dir / name
    return candidate.is_dir() and (candidate / "SKILL.md").is_file()


def resolve_destination(args, skill_name):
    if args.dest:
        return Path(args.dest) / skill_name
    base = Path.cwd() if args.scope == "project" else Path.home()
    rel = AGENTS[args.agent][args.scope]
    return (base / rel) / skill_name


def should_skip(path):
    parts = path.parts
    if "__pycache__" in parts or ".pytest_cache" in parts:
        return True
    if path.name.endswith(".pyc"):
        return True
    return False


def copy_skill(src, dest):
    def ignore(directory, contents):
        ignored = []
        for item in contents:
            full = Path(directory) / item
            if should_skip(full):
                ignored.append(item)
        return ignored

    shutil.copytree(src, dest, ignore=ignore, symlinks=False)


def link_skill(src, dest):
    try:
        dest.symlink_to(src)
        return True, None
    except OSError as exc:
        return False, str(exc)


def check_and_remove_existing(dest, force):
    if dest.exists() or dest.is_symlink():
        if not force:
            print(f"destination already exists: {dest}; use --force to replace it")
            return False
        try:
            if dest.is_symlink():
                dest.unlink()
            else:
                shutil.rmtree(dest)
        except OSError as exc:
            print(f"failed to remove existing destination {dest}: {exc}")
            return False
    return True


def check_loaded_hint(agent):
    if agent in ("claude", "qwen", "codex"):
        return "check with /skills"
    if agent == "copilot":
        return "check with /skills list in the CLI"
    return "check in the agent's own list of skills"


def run_how(skill_name, agent):
    repo_root = Path(__file__).resolve().parent.parent
    index_path = repo_root / "skills-index.json"

    if not index_path.is_file():
        print(f"missing {index_path}; run make_index.py to create the skills index")
        return 1

    try:
        with index_path.open(encoding="utf-8") as fh:
            index = json.load(fh)
    except Exception as exc:
        print(f"could not read {index_path}: {exc}")
        return 1

    skills = index.get("skills", [])
    known_names = [s.get("name") for s in skills if s.get("name")]

    skill = None
    for entry in skills:
        if entry.get("name") == skill_name:
            skill = entry
            break
    if skill is None:
        print(f"unknown skill '{skill_name}'. Known skills: {', '.join(known_names)}")
        return 2

    agents_map = index.get("agents", {})
    if agent not in agents_map:
        known_agents = ", ".join(sorted(agents_map.keys()))
        print(f"unknown agent '{agent}'. Known agents: {known_agents}")
        return 2

    agent_info = agents_map[agent] or {}
    gh_agent = agent_info.get("gh_agent")

    repository = index.get("repository", "")
    marketplace = index.get("marketplace", "")

    print(f"{skill_name}: {skill.get('description', '')}")

    print("What this skill can do:")
    for cap in skill.get("capabilities", []):
        text = CAPABILITY_TEXT.get(cap, f"It has the '{cap}' capability.")
        print(text)
    for cap in skill.get("optional_capabilities", []):
        text = CAPABILITY_TEXT.get(cap, f"It has the '{cap}' capability.")
        print(f"Optional: {text}")

    print(f"Ways to install it for {agent}:")
    print(f"1. python scripts/install_skill.py {skill_name} --agent {agent}")

    gh_found = shutil.which("gh") is not None
    if gh_agent is not None:
        if gh_found:
            print(f"2. gh skill install {repository} .claude/skills/{skill_name} --agent {gh_agent}")
        else:
            print("2. The GitHub CLI option needs the 'gh' program, which was not found.")
    else:
        print("2. (No GitHub CLI agent id is documented for this agent.)")

    if agent == "claude":
        print(f"3. /plugin marketplace add {repository}")
        print(f"   /plugin install {skill_name}@{marketplace}")
        next_num = 4
    else:
        next_num = 3

    print(f"{next_num}. Paste the prompt for your agent from docs/prompts.md and have the agent do it.")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="install_skill.py",
        description="Copy or link one agent skill into the folder an agent reads.",
    )
    parser.add_argument("skills", nargs="*", help="skill names to install")
    parser.add_argument("--all", action="store_true", help="install every skill")
    parser.add_argument("--list", action="store_true", help="list skills and their descriptions")
    parser.add_argument("--how", metavar="SKILL", default=None, help="read-only report for one skill (no install)")
    parser.add_argument("--agent", default="claude", help="target agent name")
    parser.add_argument("--scope", choices=["project", "user"], default="project")
    parser.add_argument("--dest", help="destination folder (overrides agent/scope)")
    parser.add_argument("--link", action="store_true", help="create a symlink instead of copying")
    parser.add_argument("--force", action="store_true", help="replace an existing install")
    parser.add_argument("--dry-run", action="store_true", help="show what would be done, write nothing")

    args = parser.parse_args()

    if args.how is not None:
        return run_how(args.how, args.agent)

    if args.agent not in AGENTS:
        known = ", ".join(sorted(AGENTS.keys()))
        print(f"unknown agent '{args.agent}'. Known agents: {known}")
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    skills_dir = repo_root / ".claude" / "skills"

    if args.list:
        for name, desc in list_skills(skills_dir):
            print(f"{name}\t{desc}")
        return 0

    if not args.skills and not args.all:
        parser.print_usage()
        return 2

    if args.all:
        names = [entry.name for entry in sorted(skills_dir.iterdir()) if entry.is_dir()]
    else:
        names = list(args.skills)

    known_names = [entry.name for entry in sorted(skills_dir.iterdir()) if entry.is_dir()]

    for name in names:
        if not validate_skill_name(name, skills_dir):
            print(f"unknown or unsafe skill name '{name}'. Known skills: {', '.join(known_names)}")
            return 2

    exit_code = 0
    hint = check_loaded_hint(args.agent)

    for name in names:
        src = skills_dir / name
        dest = resolve_destination(args, name)

        if args.dry_run:
            verb = "link" if args.link else "copy"
            print(f"would {verb} {src} to {dest}")
            continue

        if not check_and_remove_existing(dest, args.force):
            exit_code = 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)

        if args.link:
            ok, reason = link_skill(src, dest)
            if not ok:
                print(f"could not create symlink for {name}: {reason}")
                try:
                    if dest.exists() or dest.is_symlink():
                        if dest.is_symlink():
                            dest.unlink()
                        else:
                            shutil.rmtree(dest)
                except OSError:
                    pass
                exit_code = 1
                continue
        else:
            copy_skill(src, dest)

        print(str(dest))
        print("Read SKILL.md and the scripts before you use this skill.")
        print(hint)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
