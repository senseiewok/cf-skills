# Sensei Ewok skills

Reusable agent skills from the Sensei Ewok Research Lab, an independent open-source lab building small tools for cystic fibrosis (CF) research. Each skill is a folder with a `SKILL.md` that an AI agent reads when your task matches, plus scripts and references it can use. The format is the open [Agent Skills](https://agentskills.io) format, so one folder works in many agents.

```text
                         .
                         |
                         |
                       _.|._
                      /     \
                     |       |
                     |   .   |
                     |  (:)  |
                     |   '   |
                     |       |
                      \_____/
                        '-'
```

*A single hanging lantern, drawn in plain line characters, hangs from a short chain in an empty field with a small flame inside.*

> *Whoever lit the lamp is not the one who reads by it.*

**Seven skills so far, an install helper, an index of what each skill can do, and notes on where every major agent looks for skills.** The catalog is CC0; each skill declares its own licence. Research, not medical advice.

**Using AI around cystic fibrosis care?** Five skills here help patients, families and care teams use an AI chat app more safely. You need no install: [Where to paste](docs/paste-ready.md) shows how to copy one into your chat app.

## What this is

A skill is a folder: a `SKILL.md` that an agent reads when your task matches its description, plus the scripts, references and tests it may use. The lab writes skills for its own agents and publishes here the ones that are useful outside its workspace, in the open [Agent Skills](https://agentskills.io) format, so one folder works in Claude Code, GitHub Copilot, Cursor and the other agents in the table under [Use a skill](#use-a-skill).

**`cf-evidence-loop`** is the skill the lab's website uses for its evidence records. A researcher does not begin with an answer; they walk a fixed set of questions against the public record. This skill gives an agent that walk as a command line: eight kinds of question through fifteen commands (what has been published, whether a paper was retracted, when a drug was approved in the United States and what its label says, which trials list a condition, what a preprint is, how a variant is classified, who NIH funds on a topic, and what the tool may reach at all). Every answer is an evidence record with its source, the date it was read, the exact fields relied on and a limitation that the code refuses to leave empty. It never calls a language model, and it reaches only the sources its catalog permits, under network rules that are code with tests: `robots.txt` obeyed, one request at a time, a budget, a circuit breaker, one honest user agent. **`site-seo-review`** is a careful search-and-sharing review for a small website, with rules for health and research sites; it is not specific to CF.

**Five skills for people who use AI in cystic fibrosis care**: `cf-ai-safe-use`, `cf-plain-language-rewrite`, `cf-visit-prep`, `cf-answer-check` and `cf-ai-tool-review`. They are for patients, families and care teams as well as builders. Each has a paste-ready version you copy into a chat assistant: no install and no scripts. If you are on a care team, use the AI tool your organisation approves. If the question is about your own or your family's health, think about who can see your chats. A work account belongs to your workplace, so check its policy, or use a personal account. [Where to paste](docs/paste-ready.md) says how, product by product, and [skills by audience](docs/skills-by-audience.md) says who each skill is for. They give general information only, never medical advice, and every rule's evidence (or the lack of it) is in the skill's `references/evidence.md`.

These skills are "in review": the maintainer has not yet confirmed every licence or read every file, and the install notes were read from vendors' pages, not tested in each client. Read a skill's `SKILL.md` and its scripts before you let an agent run them.

What this is not: a medical device, a clinical tool, or a claim about treatment. An approval date is not anyone's eligibility, a label's text is a public document and not advice, and a record is a thing to check, not a conclusion.

## Try it

```sh
git clone https://github.com/senseiewok/cf-skills.git
python cf-skills/scripts/install_skill.py --list
python cf-skills/scripts/install_skill.py --how cf-evidence-loop --agent claude
```

`--list` names the skills; `--how` says in plain words what a skill does (it makes network requests, it ships scripts an agent may run, it needs Python) and lists only the install routes that work on your machine. The script runs nothing from the skill. The per-agent folders, the plugin marketplace and the paste-in prompts are under [Use a skill](#use-a-skill). The evidence tool's own tests touch no network: `cd cf-skills/.claude/skills/cf-evidence-loop && python -m pytest -q tests` (needs `pytest`).

## What's inside

[What is in this repository](#what-is-in-this-repository) below lists every file. In short: the skills under `.claude/skills/`, each with its tests; `scripts/` with the install helper, the index builder and the repository check; `docs/` with how each agent finds skills, the paste-in prompts and recommended skills from other people; `template/` and `spec/` for writing a skill; `skills-index.json` for tools; `.claude-plugin/` for Claude Code's marketplace.

## How we check it

- **The repository checks itself.** `python scripts/check_repo.py` checks every skill's frontmatter and links before a pull request, and fails an eval case that asks to rewrite or translate "this" text without giving it, unless a person has marked it `suspect`; `python scripts/make_index.py --check` fails when `skills-index.json`, `docs/skills-by-audience.md` or the README's audience table is out of date; `python scripts/make_tested_grid.py --check` recounts every result in [where each skill has been tried](docs/tested-with.md) from the judged rows in `docs/tested-with-runs/`; `python -m unittest discover tests` tests the three helper scripts.
- **The evidence tool refuses before it reaches.** Its offline tests include at least one per network-conduct rule (`tests/test_conduct.py`); `tests/test_gate.py` fails any test that opens a socket, which is how it proves that forbidden, manual and unknown sources are refused before the network; `tests/test_hardening.py` holds the defects found in review, each reproduced by a failing test first; `tests/test_providers.py` runs each parser on a saved response captured 2026-10-04.
- **A record is checkable.** The skill's [`SKILL.md`](.claude/skills/cf-evidence-loop/SKILL.md) lists the fifteen commands, and [`references/NETWORK-RULES.md`](.claude/skills/cf-evidence-loop/references/NETWORK-RULES.md) lists the eleven network rules, each with the code that enforces it and its test. The website's [Evidence](https://senseiewok.ai/evidence/) page shows one record exactly as the tool wrote it.
- **Tests and the maintainer decide what is kept.** The helper scripts here were drafted by a small local model against tests written first, then planned, reviewed and corrected with Claude models; the account, with its counts and limits, is linked from [How this repository was made](#how-this-repository-was-made).
- **Before a skill is published here** it must be useful outside the lab, declare its licence and provenance, and ship runnable checks; a model's review is not a test. The list is under [Before a skill is published here](#before-a-skill-is-published-here).

## Working with the other lab repositories

This repository is one of three that sit side by side; the control repository, [`cf-lab`](https://github.com/senseiewok/cf-lab), holds the shared agent rules. If you work on the lab itself, start agent sessions from the `cf-lab` folder where you can, and add this one as a working directory: its section [Working across the sibling repos](https://github.com/senseiewok/cf-lab/blob/main/AGENTS.md#working-across-the-sibling-repos) says how, and what does and does not load.

If you do start a session here, `.claude/settings.json` keeps the same secret-file deny rules as `cf-lab`, so the agent may not read `.env` files, keys or credential folders. A change that spans repositories is one pull request in each.

## To our CF community

To people living with cystic fibrosis, families, caregivers and researchers: this repository holds the skills we hand on, folders an AI agent can read and use in your own project, so that the care we take over sources does not stay in one lab. The evidence tool returns records, not answers: a paper's retraction notice, a United States approval date, a trial's listing, each with its source, its date and what it does not establish. That is useful for checking a claim and useless for deciding anyone's treatment, and it is meant to be. None of this is medicine or medical advice; a label's text is a public document, not your eligibility, and a care team is the place for that conversation. The sixty-five roses on the lab's [CF story](https://senseiewok.ai/cf/) page are our tribute, independent of the Cystic Fibrosis Foundation. You deserve care, dignity and room for ordinary life, and you owe no one an inspiring story. If you use an agent we have not listed, or one of our install notes does not match what your agent actually does, open an issue here and tell us; that is how the notes get corrected.

With care,

Sensei Ewok

This repository is modelled on [anthropics/skills](https://github.com/anthropics/skills) and adds two things that repository does not try to do: a documented install path for each major agent, with the vendor page it came from, and a prompt you can paste into any agent that points it at a skill on GitHub.

Research, not medical advice. Nothing here is a medical device, a clinical tool or a claim about treatment.

## Skills

| Skill | What it does | Status |
| --- | --- | --- |
| [`cf-evidence-loop`](.claude/skills/cf-evidence-loop/SKILL.md) | A command line that answers a CF researcher's evidence questions (retractions, FDA approvals and labels, preprints, ClinVar classifications, NIH funding) as evidence records: source, date, exact fields and a limitation every time. It reaches only the sources its catalog permits and follows the network rules in its `references/`. | v1.0.0, offline tests, in review |
| [`site-seo-review`](.claude/skills/site-seo-review/SKILL.md) | A careful, honest search-and-sharing review of a small website: a checker script for static sites, a review workflow, rules for health and research sites, and a way to hand the mechanical parts to a small local model with a test as the judge. Not specific to CF. | draft, in review |
| [`cf-ai-safe-use`](.claude/skills/cf-ai-safe-use/SKILL.md) | Baseline rules for an AI assistant asked about CF or health: general information only, no doses, diagnosis or eligibility, no identifying details, and a label for what each answer rests on. A small script flags cheap failures in an answer. | draft, in review |
| [`cf-plain-language-rewrite`](.claude/skills/cf-plain-language-rewrite/SKILL.md) | Rewrites a CF handout or message in plain language without adding, dropping or changing any fact, with a verify-before-use list and scripts for reading level and fact differences. | draft, in review |
| [`cf-visit-prep`](.claude/skills/cf-visit-prep/SKILL.md) | Helps a person with CF, a parent or a carer turn their worries into a short, ordered list of questions for the care team. It never answers the medical question. | draft, in review |
| [`cf-answer-check`](.claude/skills/cf-answer-check/SKILL.md) | Checks an AI answer about CF one claim at a time against primary sources, and marks what could not be checked as unverified. | draft, in review |
| [`cf-ai-tool-review`](.claude/skills/cf-ai-tool-review/SKILL.md) | A structured review of an AI tool before a CF care team or patient group uses it: every answer points to a document, demo or test, and people make the decision. | draft, in review |

"In review" means the maintainer has not yet confirmed the licence or read every file. Read a skill's `SKILL.md` and scripts before you let an agent run them.

The five CF care skills also come as plain text to paste into any chat assistant, with no install: [docs/paste-ready.md](docs/paste-ready.md) says where to paste it in Claude, Gemini, Microsoft Copilot and ChatGPT.

<!-- skills-table:start -->
Who each skill is for, and where to use it with no install (generated by `python scripts/make_index.py`; a table per group, with categories, in [docs/skills-by-audience.md](docs/skills-by-audience.md)):

| Skill | What it does | For whom | Use it now, no install | Level |
| --- | --- | --- | --- | --- |
| [`cf-ai-safe-use`](.claude/skills/cf-ai-safe-use/SKILL.md) | Ground rules so an AI gives general CF information, keeps your details private, and sends urgent worries to people. | Patients and families, Care teams | [Use it now](.claude/skills/cf-ai-safe-use/references/paste-ready.md) | base |
| [`cf-ai-tool-review`](.claude/skills/cf-ai-tool-review/SKILL.md) | A step-by-step review a clinic or patient group can use before trusting an AI tool; people make the final decision. | Care teams, Builders | [Use it now](.claude/skills/cf-ai-tool-review/references/paste-ready.md) | advanced |
| [`cf-answer-check`](.claude/skills/cf-answer-check/SKILL.md) | Checks an AI answer about CF with you, one claim at a time, and marks what nobody could check yet. | Patients and families, Care teams, Researchers, Builders | [Use it now](.claude/skills/cf-answer-check/references/paste-ready.md) | advanced |
| [`cf-evidence-loop`](.claude/skills/cf-evidence-loop/SKILL.md) | Answer a research question about cystic fibrosis, sickle cell disease, or any condition the way a researcher does, one public source at a time, and return evidence records instead of answers. | Researchers, Builders | (install route only) | advanced |
| [`cf-plain-language-rewrite`](.claude/skills/cf-plain-language-rewrite/SKILL.md) | Makes a CF handout or letter easier to read without changing any number, name or warning, as a draft to check. | Patients and families, Care teams | [Use it now](.claude/skills/cf-plain-language-rewrite/references/paste-ready.md) | base |
| [`cf-visit-prep`](.claude/skills/cf-visit-prep/SKILL.md) | Turns your worries before a CF clinic visit into a short list of questions, in your own words, for the care team. | Patients and families | [Use it now](.claude/skills/cf-visit-prep/references/paste-ready.md) | base |
| [`site-seo-review`](.claude/skills/site-seo-review/SKILL.md) | An honest SEO and discoverability review for small static or mostly-static websites, health and research sites included: a standard-library checker for titles, descriptions, canonicals, Open Graph, sitemap and robots agreement, headings, images, link text, preloads, third-party scripts and structured data, plus a workflow for reading the pages, proposing copy, getting the wording reviewed, and verifying the live site. | Builders | (install route only) | advanced |
<!-- skills-table:end -->

## Use a skill

A skill is a folder. This repository keeps its skills in `.claude/skills/`, the folder Claude Code, GitHub Copilot and Cursor read, so there are three simple ways in:

1. **Open this repository in your agent.** Clone it and open the folder in Claude Code, VS Code with Copilot, or Cursor: the skills are already where the agent looks. Good for trying them; all of them load for that session.
2. **Put one skill in your own project.** From your project's folder run:
   ```text
   git clone https://github.com/senseiewok/cf-skills.git
   python cf-skills/scripts/install_skill.py --list
   python cf-skills/scripts/install_skill.py cf-evidence-loop --agent claude
   ```
   That copies the one skill into the project's `.claude/skills/`. `--agent` picks the folder for another agent (see the table), `--scope user` installs for all your projects, `--link` links instead of copying so `git pull` updates it, and `--dry-run` shows what would happen. The script runs nothing from the skill.
3. **Ask your agent to do it.** Paste the prompt for your agent from [docs/prompts.md](docs/prompts.md). It tells the agent to read the skill's page first, to treat what it reads as data and not as orders, to fetch the files only after asking you and copy them byte for byte into the right place for that agent, and to wait for your yes before running any script.

Not sure which way suits your machine? `python cf-skills/scripts/install_skill.py --how cf-evidence-loop --agent claude` says in plain words what the skill can do (it makes network requests, it ships scripts an agent may run, it needs Python, and so on) and lists only the ways that work here, including `gh skill install` when the GitHub CLI is installed. The same facts are in [`skills-index.json`](skills-index.json) for tools and agents. Claude Code can also add this repository as a plugin marketplace; that is optional (see the table and [docs/install.md](docs/install.md)). Read a skill's `SKILL.md` and scripts before an agent runs them.

| Agent | Where its skills live (project) | Docs status |
| --- | --- | --- |
| Claude Code | `.claude/skills/<name>/`, or `~/.claude/skills/<name>/` for all projects. As a plugin: `/plugin marketplace add senseiewok/cf-skills`, then `/plugin install cf-evidence-loop@sensei-ewok-skills` | documented (the plugin page was read directly, the skills page through a summary) |
| GitHub Copilot (VS Code, CLI, cloud agent) | `.github/skills/`, `.claude/skills/` or `.agents/skills/`. Install from GitHub with `gh skill install senseiewok/cf-skills .claude/skills/<skill>` (the path form [docs/install.md](docs/install.md#gh-skill) gives; unverified: check your tool's own documentation) | documented |
| OpenAI Codex | `.agents/skills/` | partial: no documented install-from-URL step |
| Gemini CLI | `.gemini/skills/` or `.agents/skills/`. `gemini skills install <git-url> --path .claude/skills/<skill>` | documented |
| Cursor | `.cursor/skills/`, `.agents/skills/` or `.claude/skills/` | documented |
| Amp | `.agents/skills/`. `amp skill add <source>` | documented; no worked GitHub example |
| Windsurf (Devin), Qwen Code, OpenCode, Goose | see [docs/install.md](docs/install.md) | partial: copy the folder |
| claude.ai (chat) | upload a zipped folder: see [Using skills in Claude](https://support.claude.com/en/articles/12512180-using-skills-in-claude) | partial: two Anthropic pages disagree on the menu path |
| Claude API | upload through the `/v1/skills` endpoints: see the [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) | partial: only the overview was read |

**Documented** means a vendor's own page says it, read on 2026-10-05 and partly through a summarising tool. Nothing was tested in a real client, and commands that name this repository were built from the documented syntax and have not been run.

There is no single folder that every agent reads. `.agents/skills/` is read by most of them and `.claude/skills/` by several, but Claude Code's documentation names only `.claude/skills/`, and Qwen Code names only `.qwen/skills/`. Details, quotes and the date each page was read are in [docs/install.md](docs/install.md).

### Calling a skill once it is installed

Most agents load a skill by itself when your request matches its description. To ask for one by name: `/<skill>` in Claude Code, Copilot, Cursor and Qwen Code (a skill installed as a Claude Code plugin is `/<plugin>:<skill>`), `$<skill>` in Codex, `@<skill>` in Windsurf. Gemini CLI, Amp, OpenCode and Goose pick it from your request. The check command for each agent is in [docs/prompts.md](docs/prompts.md#calling-a-skill-once-it-is-installed).

## What is in this repository

```text
.claude/skills/<name>/     one folder per skill (SKILL.md, scripts/, references/, tests/): the folder Claude Code,
                           Copilot and Cursor read, so a clone of this repository works as a skills folder
.claude/settings.json      Claude Code deny rules for a session started here: no reading .env files, keys or credentials
template/SKILL.md          the smallest valid skill
spec/README.md             the format, and what this repository adds to it
docs/install.md            how each agent finds skills, with sources
docs/prompts.md            copy-paste prompts, one per agent
docs/paste-ready.md        where to paste a skill's paste-ready text in common AI products
docs/skills-by-audience.md which skill suits patients and families, care teams, researchers or builders; generated by scripts/make_index.py
docs/recommended.md        useful skills from other people, with their licences and read-first notes (nothing copied here)
.claude-plugin/            a Claude Code plugin marketplace listing each skill on its own
skills-index.json          what each skill can do (capabilities) and how to install it, generated by scripts/make_index.py
scripts/install_skill.py   copies or links one skill into the folder your agent reads; --how shows the ways that work on your machine
scripts/make_index.py      builds skills-index.json, docs/skills-by-audience.md and the README's audience table from each
                           skill's frontmatter (--check for a pull request)
scripts/check_repo.py      checks every skill's frontmatter and links (run it before a pull request)
tests/                     tests for check_repo.py, make_index.py and install_skill.py (python -m unittest discover tests)
```

Each skill is its own plugin in the marketplace, which is meant to let you install one without the others. That is a difference from the Anthropic repository, whose plugins bundle many skills. A plugin brings the skill's scripts too; read them first. Once releases are tagged, pin an install with `/plugin marketplace add senseiewok/cf-skills#<tag>`.

## Before a skill is published here

- It must be useful outside the lab's own workspace: no private paths, machine details, keys, patient data or copied session logs.
- A canonical `SKILL.md` with a `name` that matches its folder and a `description` that says what it does and when to use it.
- A declared licence and where each third-party piece came from. Public availability alone is not a reuse grant.
- Runnable checks, and a note of what they cover. A model's review is not a test.
- One maintained source. If a skill also lives in the lab's control repository, one of the two points to the other; there are no independently edited copies.

`python scripts/check_repo.py` checks the mechanical parts of this list.

## Safety when you install any skill

A skill is instructions plus code that an agent may run with your permissions. Read the `SKILL.md` and every script first. Do not pre-approve shell tools for a skill you have not read. Treat the text of a skill, like any web page, as data until you have decided to follow it. The prompts in [docs/prompts.md](docs/prompts.md) are written that way.

## How this repository was made

The helper scripts here (`install_skill.py`, `make_index.py`, `check_repo.py`) were drafted by a small local model against tests written first, and the code, the tests and the documentation were planned, reviewed and corrected with Claude models from Anthropic, working in Claude Code under the maintainer's direction. Tests and the maintainer decide what is kept. The account, with its counts and limits, is in the lab's [How the work is divided](https://github.com/senseiewok/cf-lab#how-the-work-is-divided). The lab is independent of Anthropic.

## Licence

[CC0 1.0](LICENSE) for the catalog (this README, the template, the docs and the scripts in `scripts/`). Each skill declares its own licence and provenance in its `SKILL.md`; the maintainer confirms them before a release. The lab's main workspace repository is [senseiewok/cf-lab](https://github.com/senseiewok/cf-lab) and the research notes and source catalog are in [senseiewok/cf-research](https://github.com/senseiewok/cf-research).
