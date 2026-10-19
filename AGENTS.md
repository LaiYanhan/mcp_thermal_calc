# Agent Instructions

## Agent skills

### Issue tracker

Local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context (`GLOSSARY.md` and `docs/adr/` at repo root). See `docs/agents/domain.md`.

## Documentation privacy

Published documentation must use repository-relative paths, environment variables, or explicit placeholders. Do not commit real usernames, machine-specific absolute paths, local configuration contents, or personal installation and backup records. Keep local audit notes in ignored `.scratch/` files, and check the diff for such information before committing or pushing.
