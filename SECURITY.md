# Security policy

Sensei Ewok's CF Lab is an independent, donated-time open-source research project. We take security seriously, especially because agent skills and helper scripts run alongside AI coding tools.

## Reporting a vulnerability

If you find a security issue in this repository (`senseiewok/cf-skills`), including a prompt-injection vector, unsafe tool permission, or credential leak in a skill or script, please **do not open a public issue or pull request**. Instead, report it privately through one of two channels:

- **GitHub Private Vulnerability Reporting:** use **Report a vulnerability** under this repository's **Security** tab (`Security -> Advisories -> New draft security advisory`).
- **Email:** write to **contact@senseiewok.ai** with `[security]` in the subject line.

We acknowledge reports and work on a fix before public disclosure.

## Using skills safely

Skills in `.claude/skills/` and helper scripts in `scripts/` are written for AI agents, and several run Python code or make bounded network requests on your machine. Before you use a skill:

- Read the skill's `SKILL.md` and read a skill's scripts before you let an agent run them.
- Keep `.claude/settings.json` secret-file deny rules enabled when running an agent inside a clone, and put personal overrides in `.claude/settings.local.json`.
- Treat updates to `SKILL.md` files, hooks, and scripts as executable code and review diffs before trusting them.
- Keep patient health information, API keys, and private credentials out of chat prompts and tracked files.

## Disclosure and liability

This project is provided as-is (see `LICENSE` and individual skill licenses). Research, not medical advice. We appreciate responsible disclosure and credit reporters who ask to be credited.
