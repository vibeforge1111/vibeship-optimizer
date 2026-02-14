---
name: vibeship-optimizer
description: Safe, rollback-friendly optimization workflow for any codebase: capture before/after snapshots, compare performance/size/health probes, and maintain a multi-day verification log. Use in OpenClaw when a user wants to optimize a project without breaking it, wants commit-per-change rollbacks, or wants a living OPTIMIZATION_CHECKER.md validation document.
---

# vibeship-optimizer

Use the `vibeship-optimizer` CLI from this repo to run a Carmack-style optimization loop:

## Standard loop (one optimization)

1) Initialize templates:
- `python -m vibeship_optimizer init`

2) Start a tracked change (appends a section into `OPTIMIZATION_CHECKER.md`):
- `python -m vibeship_optimizer change start --title "<change title>" --risk "<risk>" --rollback "git revert <sha>"`

3) Take baseline snapshot:
- `python -m vibeship_optimizer snapshot --label before`

4) Make exactly one optimization + commit it.

5) Take after snapshot:
- `python -m vibeship_optimizer snapshot --label after`

6) Compare and write a report:
- `python -m vibeship_optimizer compare --before <before.json> --after <after.json> --out reports/vibeship_optimizer_compare.md`

## Multi-day verification

1) Start monitoring (baseline defaults to latest snapshot if omitted):
- `python -m vibeship_optimizer monitor start --change-id <chg-...> --days 5`

2) Run once per day:
- `python -m vibeship_optimizer monitor tick`

This appends “Verification update” blocks to `OPTIMIZATION_CHECKER.md` and stores reports under `.vibeship_optimizer/reports/`.

## Preflight + hallucination protections

1) Run diligence checks:
- `python -m vibeship_optimizer preflight --out reports/vibeship_optimizer_preflight.md`

2) Recommended: do an evidence-based review before applying an optimization.

- Generate an evidence bundle (git context + diff) you can paste into an LLM:
  - `python -m vibeship_optimizer review bundle --change-id <chg-...> --out reports/vibeship_optimizer_review_bundle.md`

- If the user agrees, run the review in:
  - **Codex** with **reasoning_mode=xhigh** (or high)
  - **Claude** in **Plan mode**

- Record the review as an attestation (so the checker can enforce it if configured):
  - `python -m vibeship_optimizer review attest --change-id <chg-...> --tool codex --reasoning-mode xhigh --model "<model>" --reviewer "<name>"`

Review attestations are **required by default** (config `review.require_attestation=true`).
If you want to relax this, set:
- `.vibeship_optimizer/config.yml` (or `.vibeship_optimizer/config.json`) → `review.require_attestation: false`

## Read-only analyzers (safe)

- `python -m vibeship_optimizer analyze --out reports/vibeship_optimizer_analyze.md`

This produces bloat/size hints and naive “maybe unused dependency” hints (heuristic; do not auto-remove without verification).

## Automation (OpenClaw cron)

For scheduled daily verification ticks, see:
- `references/openclaw_cron_setup.md`
