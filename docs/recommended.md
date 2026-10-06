# Skills from other people that we found useful

These skills are not part of this repository and nothing of theirs is copied here. They are listed because the lab tried them and found them useful; that is not an endorsement or a security review. Read a skill's `SKILL.md` and every script before an agent runs it.

Install one at a time with GitHub's CLI, which takes a single skill from a repository and can pin a version (the command is built from GitHub's documentation, `gh skill install <repository> [<skill>] [--agent <id>] [--scope project|user]`, and needs the GitHub CLI):

```text
gh skill install anthropics/skills <skill> --agent claude-code --scope user
```

Change `claude-code` to the agent id for your agent (see [install.md](install.md)). Anthropic's plugin marketplace groups its skills in bundles, so `/plugin marketplace add anthropics/skills` followed by an install loads about a dozen skills at once; the single-skill route above avoids that.

| Skill | From | Licence (as read) | What it is | Read this first |
| --- | --- | --- | --- | --- |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | Guidance for distinctive, production-quality front-end work | Guidance only, no scripts. It is opinionated about visual style, so check it against your own accessibility rules |
| `skill-creator` | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | A method for writing and testing skills | Its scripts make model calls on your own login, write a temporary command file into your project and serve a local review page |
| `algorithmic-art` | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | Seeded generative-art examples | Its viewer template loads a script from a CDN and carries branding; remove both before any public use |
| `theme-factory` | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 | Colour and font presets as Markdown | Contrast was not checked; test any theme against your own accessibility checks |

The notes above come from reading those folders at commit `8a1541c` (2026-09-28). The skills have since changed upstream; check the licence file in the folder you install. Skills in that repository under Anthropic's proprietary licence (the document skills) and one without a licence file are not listed.
