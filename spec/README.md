# The format, and what this repository adds

The format is the open Agent Skills specification: <https://agentskills.io/specification>. This repository does not copy it; read it there. In short, a skill is a folder named like its `name`, holding a `SKILL.md` with YAML frontmatter (`name` and `description` required; `license`, `compatibility`, `metadata` optional) and optional `scripts/`, `references/` and `assets/`.

## What this repository adds

`scripts/check_repo.py` checks, for every `.claude/skills/<name>/`:

- the folder name equals `name`, and `name` is lowercase letters, digits and hyphens, at most 64 characters;
- `description` is present, at most 1,024 characters, and has no angle brackets (`<` or `>`);
- `license` is declared;
- `compatibility`, when present, is at most 500 characters;
- the frontmatter has no key outside `name`, `description`, `license`, `allowed-tools`, `metadata` and `compatibility`;
- relative links resolve in `README.md`, in the Markdown files under `docs/`, `spec/` and `template/`, and in each `SKILL.md` (not in other files, and not inside code fences);
- the Claude Code plugin marketplace in `.claude-plugin/marketplace.json` lists each skill once and only skills that exist;
- nothing that looks like a local path, a key or an email address is in the README, the Markdown files under `docs/`, `spec/` and `template/`, and each `SKILL.md` and `references/*.md`;
- `description` is a one-line string (a folded `>` or `|` block is reported, because the checker does not read it);
- `audience`, `level` and `category` are set under `metadata`, each with words from the lists below (a missing key or an unknown word is reported with the allowed words).

Each skill also declares what it can do in its frontmatter, under `metadata`: `capabilities` (required) and `optional-capabilities`, comma-separated words from this list: `network` (makes requests to the internet), `runs-code` (ships scripts an agent may run), `python` (needs Python), `reads-project-files`, `writes-files`, `browser`, `api-key`. `scripts/make_index.py` turns those into `skills-index.json` (`--check` fails when the index is out of date), and `scripts/install_skill.py --how <skill>` shows them to a person before they install.

Each skill also says who it is for, under `metadata`, as strings:

- `audience` (required): comma-separated, one or more of `patients-families`, `care-teams`, `researchers`, `builders`;
- `level` (required): `base` (a person can follow it with no setup, in a plain chat) or `advanced` (needs a tool, a script or care to apply);
- `category` (required): one of `safe-ai-use`, `communication`, `evidence`, `tool-evaluation`, `web`.

For example `audience: "researchers, builders"`, `level: "advanced"`, `category: "evidence"`. `scripts/make_index.py` carries them into `skills-index.json` and writes [docs/skills-by-audience.md](../docs/skills-by-audience.md) and the small table between the `skills-table` markers in the README; `--check` fails when any of the three is out of date.

These checks are mechanical. They do not decide whether a skill is safe, correct or honest; a person reads each skill before it is published.
