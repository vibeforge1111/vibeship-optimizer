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

## Read-only analyzers (safe)

- `python -m optcheck analyze --out reports/optcheck_analyze.md`

This produces bloat/size hints and naive “maybe unused dependency” hints (heuristic; do not auto-remove without verification).
