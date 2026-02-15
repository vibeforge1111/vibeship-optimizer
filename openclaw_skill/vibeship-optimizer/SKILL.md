---
name: vibeship-optimizer
description: Safe, rollback-friendly optimization workflow for any codebase: capture before/after snapshots, compare performance/size/health probes, and maintain a multi-day verification log. Use in OpenClaw when a user wants to optimize a project without breaking it, wants commit-per-change rollbacks, or wants a living VIBESHIP_OPTIMIZER.md validation document.
---

# vibeship-optimizer

Use the `vibeship-optimizer` CLI from this repo to run a Carmack-style optimization loop.

## First run (recommended)

- `python -m vibeship_optimizer init --onboard --no-prompt`

This creates:
- `VIBESHIP_OPTIMIZER.md` (logbook)
- `.vibeship-optimizer/` (state dir: config, snapshots, changes, reports)

## Standard loop (one optimization)

1) Start a tracked change (appends a section into `VIBESHIP_OPTIMIZER.md`):
- `python -m vibeship_optimizer change start --title "<change title>" --risk "<risk>" --rollback "git revert <sha>"`

2) Take baseline snapshot (and attach it to the change record):
- `python -m vibeship_optimizer snapshot --label before --change-id <chg-...> --as before`

3) Make exactly one optimization + commit it.

4) Take after snapshot (and attach it to the change record; also records current commit sha):
- `python -m vibeship_optimizer snapshot --label after --change-id <chg-...> --as after`

5) Compare and write a report:
- `python -m vibeship_optimizer compare --before <before.json> --after <after.json> --out reports/vibeship_optimizer_compare.md`

## Multi-day verification

1) Start monitoring (baseline defaults to latest snapshot if omitted):
- `python -m vibeship_optimizer monitor start --change-id <chg-...> --days 5`

2) Run once per UTC day:
- `python -m vibeship_optimizer monitor tick`

This appends "Verification update" blocks to `VIBESHIP_OPTIMIZER.md` and stores reports under `.vibeship-optimizer/reports/`.

## Preflight + hallucination protections

1) Run diligence checks:
- `python -m vibeship_optimizer preflight --out reports/vibeship_optimizer_preflight.md`

2) Evidence-based review before claiming "this helped":
- `python -m vibeship_optimizer review bundle --change-id <chg-...> --out reports/vibeship_optimizer_review_bundle.md`

3) Record review attestation (required by default via config):
- `python -m vibeship_optimizer review attest --change-id <chg-...> --tool codex --reasoning-mode xhigh --model "<model>" --reviewer "<name>"`

If you want to relax attestation enforcement, set:
- `.vibeship-optimizer/config.yml` (or `.json`) -> `review.require_attestation: false`

## Read-only analyzers (safe)

- `python -m vibeship_optimizer analyze --out reports/vibeship_optimizer_analyze.md`

This produces bloat/size hints and naive "maybe unused dependency" hints (heuristic; do not auto-remove without verification).

## Automation (OpenClaw cron)

For scheduled daily verification ticks, see:
- `references/openclaw_cron_setup.md`

For cron/automation, prefer:
- `python -m vibeship_optimizer autopilot tick --change-id <chg-...> --force --format json --ok-on-pending`

