---
name: optimization-checker
description: Safe, rollback-friendly optimization workflow for any codebase: capture before/after snapshots, compare performance/size/health probes, and maintain a multi-day verification log. Use in OpenClaw when a user wants to optimize a project without breaking it, wants commit-per-change rollbacks, or wants a living OPTIMIZATION_CHECKER.md validation document.
---

# Optimization Checker (optcheck)

Use the `optcheck` CLI from this repo to run a Carmack-style optimization loop:

## Standard loop (one optimization)

1) Initialize templates:
- `python -m optcheck init`

2) Start a tracked change (appends a section into `OPTIMIZATION_CHECKER.md`):
- `python -m optcheck change start --title "<change title>" --risk "<risk>" --rollback "git revert <sha>"`

3) Take baseline snapshot:
- `python -m optcheck snapshot --label before`

4) Make exactly one optimization + commit it.

5) Take after snapshot:
- `python -m optcheck snapshot --label after`

6) Compare and write a report:
- `python -m optcheck compare --before <before.json> --after <after.json> --out reports/optcheck_compare.md`

## Multi-day verification

1) Start monitoring (baseline defaults to latest snapshot if omitted):
- `python -m optcheck monitor start --change-id <chg-...> --days 5`

2) Run once per day:
- `python -m optcheck monitor tick`

This appends “Verification update” blocks to `OPTIMIZATION_CHECKER.md` and stores reports under `.optcheck/reports/`.

## Preflight + hallucination protections

1) Run diligence checks:
- `python -m optcheck preflight --out reports/optcheck_preflight.md`

2) Recommended: do an evidence-based review before applying an optimization.

- Generate an evidence bundle (git context + diff) you can paste into an LLM:
  - `python -m optcheck review bundle --change-id <chg-...> --out reports/optcheck_review_bundle.md`

- If the user agrees, run the review in:
  - **Codex** with **reasoning_mode=xhigh** (or high)
  - **Claude** in **Plan mode**

- Record the review as an attestation (so the checker can enforce it if configured):
  - `python -m optcheck review attest --change-id <chg-...> --tool codex --reasoning-mode xhigh --model "<model>" --reviewer "<name>"`

Review attestations are **required by default** (config `review.require_attestation=true`).
If you want to relax this, set:
- `.optcheck/config.yml` (or `.optcheck/config.json`) → `review.require_attestation: false`

## Read-only analyzers (safe)

- `python -m optcheck analyze --out reports/optcheck_analyze.md`

This produces bloat/size hints and naive “maybe unused dependency” hints (heuristic; do not auto-remove without verification).

## Automation (OpenClaw cron)

For scheduled daily verification ticks, see:
- `references/openclaw_cron_setup.md`
