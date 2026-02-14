# Optimization Checker

This file is a living validation playbook.

## Rules
- One optimization per commit (easy revert).
- Prefer flags/knobs. Make risky changes opt-in.
- Always capture **before/after** snapshots.
- Monitor for a few days before marking verified.

## Workflow

Recommended loop:

1) `optcheck init`
2) `optcheck change start --title "..."`
3) `optcheck snapshot --label before`
4) Make *one* optimization + commit
5) `optcheck snapshot --label after`
6) `optcheck compare --before ... --after ... --out reports/...`
7) Start a multi-day monitor: `optcheck monitor start --change-id <chg-...>`
8) Run a daily tick: `optcheck monitor tick` (once per day)

## Optimization log

(Entries are appended here by `optcheck change start`.)
