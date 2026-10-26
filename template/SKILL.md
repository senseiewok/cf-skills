---
name: template
description: Replace this with what the skill does and when an agent should use it, in one or two sentences. Name the tasks and the words a user would say.
license: CC0-1.0
compatibility: "Plain Markdown; works in any assistant."
metadata:
    version: "0.1.0"
    capabilities: ""
    optional-capabilities: ""
    audience: "patients-families, care-teams"
    level: "base"
    category: "communication"
    summary: "One-line summary of what the skill does (at most 160 characters)."
---

# Template skill

Replace this file and set `name:` in the frontmatter to match your skill folder's name. Keep it short: an agent reads it whenever your request matches the description above.

## When to use

- The situations that should trigger this skill.

## Steps

1. What to do first.
2. What to check before finishing.

## Limits

- What this skill does not do, so an agent does not overreach.

## Files

- `scripts/` for code an agent may run (say what each one does and whether it uses the network).
- `references/` for longer notes loaded only when needed.

## Frontmatter metadata

Set `capabilities`, `audience`, `level` and `category` under `metadata` to what this skill really is; the allowed words are listed in this repository's `spec/README.md`.
