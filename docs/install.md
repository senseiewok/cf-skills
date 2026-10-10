# How each agent finds skills

Research notes for installing a skill from this repository. Every path and command below was read on a vendor's own documentation page on 2026-10-05 unless it says otherwise. Commands that name this repository were built from the documented syntax and have not been run. Many of those pages reached the researcher through a summarising tool, so check a path in your own copy of the agent before you rely on it, and tell us when a page has changed.

Labels: **documented** means a vendor page says it. **partial** means the vendor page is silent or two vendor pages disagree. **not stated** means the page does not say. Nothing here was run in a real client.

## The open format

A skill is a folder with at least a `SKILL.md`. The open Agent Skills specification at [agentskills.io](https://agentskills.io) defines what goes inside: a required `name` (lowercase letters, digits and hyphens, up to 64 characters, equal to the folder name) and `description` (up to 1,024 characters), and optional `license`, `compatibility` and `metadata`, with `scripts/`, `references/` and `assets/` folders. The specification does not say where skill folders live; its client guide says the `.agents/skills/` paths "have emerged as a widely-adopted convention".

## One table

| Agent | Project folder(s) | Personal folder(s) | Install from a GitHub repository | Use it, and check it loaded | Status |
| --- | --- | --- | --- | --- | --- |
| Claude Code (CLI documented; VS Code and desktop inferred) | `.claude/skills/` (also in parent folders up to the repository root) | `~/.claude/skills/` | `/plugin marketplace add senseiewok/cf-skills`, then `/plugin install <skill>@<marketplace>`; or copy the folder. A plugin skill is called `/<plugin>:<skill>` | automatic by description, or `/<skill-name>`; check with `/skills`; `/reload-skills` after adding a folder | documented |
| claude.ai and Claude desktop chat | none: upload | none: upload | zip the skill folder and upload it (Customize > Skills) | automatic; how to check is not stated | partial: two Anthropic pages disagree on the menu path, the plans and sharing (menu path may read Customize > Skills or Settings > Features) |
| Claude API | none | none | upload through the `/v1/skills` endpoints, then name the `skill_id` in the `container` with the code execution tool | automatic | partial: only the overview page was read |
| GitHub Copilot (VS Code agent mode, CLI, cloud agent) | `.github/skills/`, `.claude/skills/`, `.agents/skills/` | `~/.copilot/skills/`, `~/.agents/skills/` (VS Code also lists `~/.claude/skills/`) | `gh skill install senseiewok/cf-skills .claude/skills/<skill>` (see [`gh skill`](#gh-skill)); or copy the folder | automatic by description, or `/<skill-name>`; VS Code: Chat: Open Customizations; CLI: `/skills list`, `/skills info <skill>` | documented |
| OpenAI Codex | `.agents/skills/` from the working folder up to the repository root | `$HOME/.agents/skills/` | `gh skill install senseiewok/cf-skills .claude/skills/<skill> --agent codex` (see [`gh skill`](#gh-skill)); `$skill-installer` has no documented GitHub-address form | automatic; `$<skill>` in Codex, `/skills` | partial |
| Gemini CLI | `.gemini/skills/` or `.agents/skills/` | `~/.gemini/skills/` or `~/.agents/skills/` | `gemini skills install <git-url> --path .claude/skills/<skill> --scope workspace` (or `user`) | the model activates it and you approve; `/skills list` | documented (that the docs site is Google's is not confirmed) |
| Cursor | `.cursor/skills/`, `.agents/skills/`, `.claude/skills/`, `.codex/skills/` | `~/.cursor/skills/`, `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/` | Customize > "From GitHub Repository" needs a `.cursor-plugin/marketplace.json` that this repository does not have yet; so copy the folder | automatic, or `/` then the name; Customize > Skills | documented |
| Windsurf (now Devin Desktop) | `.devin/skills/`, `.windsurf/skills/` (older), `.agents/skills/`, `.claude/skills/` (if enabled) | `~/.codeium/windsurf/skills/`, `~/.config/devin/skills/`, `~/.agents/skills/` | not stated: copy the folder | automatic, or `@<skill>`; the Skills panel | partial |
| Qwen Code | `.qwen/skills/` | `~/.qwen/skills/` | not stated: copy the folder | automatic, or `/<skill>`; `/skills` | partial: its page does not mention `.agents/skills/` or `.claude/skills/` |
| Amp | `.agents/skills/` (and `.claude/skills/`) | `~/.config/agents/skills/`, `~/.agents/skills/`, `~/.config/amp/skills/` | `amp skill add <source>` (`--global` for the machine) | automatic; `amp skills list` | documented, no worked GitHub example |
| OpenCode | `.opencode/skills/`, `.claude/skills/`, `.agents/skills/` | `~/.config/opencode/skills/`, `~/.claude/skills/`, `~/.agents/skills/` | not stated: copy the folder | the model calls a `skill` tool; no listing command documented | partial |
| Goose | `.agents/skills/` (older: `.goose/skills/`, `.claude/skills/`) | `~/.agents/skills/` | not stated: copy the folder | ask by name, or `/skills <name>`; `goose skills list` | partial |

### Which folder, if I use several agents?

`.agents/skills/` (project) and `~/.agents/skills/` (personal) are read by Copilot, Codex, Gemini CLI, Cursor, Windsurf/Devin, Amp, OpenCode and Goose. `.claude/skills/` is read by Claude Code, Copilot, Cursor, Amp, OpenCode and, if enabled, Windsurf/Devin. Claude Code's skills page does not mention `.agents/skills/`, and Qwen Code's page does not mention either shared folder, so a project that uses both keeps the folder in `.claude/skills/` and links or copies it to `.agents/skills/` and `.qwen/skills/`. No single folder reaches every agent.

## `gh skill`

GitHub's CLI documents `gh skill install <repository> [<skill>] [--agent <id>] [--scope project|user]` for GitHub Copilot, Claude Code, Cursor, Codex, Gemini CLI, Amp, OpenCode, Goose and Qwen Code. It finds skills with the `skills/*/SKILL.md` convention, and its documentation says the skill argument may also be an exact repository path, so for this repository give the path: `gh skill install senseiewok/cf-skills .claude/skills/<skill>` (built from the documented syntax, not run). This repository keeps its skills in `.claude/skills/` so that Claude Code, Copilot and Cursor load them straight from a clone. The minimum `gh` version is not stated.

## Limits worth knowing before you install

- **Network.** `cf-evidence-loop` fetches from public sources. The Claude API's code execution has no network access, and claude.ai says network access depends on user and admin settings, so its network steps may not work there. A skill's `SKILL.md` says what it needs.
- **Scripts.** Copilot's documentation says to pre-approve shell tools only for a skill you have reviewed. Do the same in every agent.
- **Names.** The Claude API refuses skill names that contain "anthropic" or "claude".
- **Windows.** Only Claude Code and Copilot documentation was read for Windows details; use `/` path separators inside skill files.

## What was not verified

- Nothing was tested in a real client. Discovery is claimed only where a vendor says it.
- claude.ai: the upload menu path, the plans that include skills and how a skill is shared (two Anthropic pages disagree).
- Claude Code in the VS Code extension reads the same folders (inferred); whether any version reads `.agents/skills/`.
- Whether a Claude Code plugin with `"source": "./"` and a `skills` list loads only its own skill or every skill under `.claude/skills/` (it was not tested).
- Codex: `~/.codex/skills/` is not on the page; `$skill-installer` with a GitHub address.
- Gemini CLI: whether some versions still need an experimental setting.
- Windsurf/Devin, Qwen Code, OpenCode, Goose: any install-from-GitHub step; OpenCode's way to list loaded skills.
- `gh skill` with a skill at the top of a repository, and its minimum version.
- The Claude API request details (the skills guide was not read).

If you find a path or command here that is wrong for your version, please tell the lab on the [Contact page](https://senseiewok.ai/contact/) of senseiewok.ai, with the vendor page and version. This repository does not take outside issues or pull requests.
