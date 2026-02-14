# vibeship-optimizer

This file is a living validation playbook.

## Rules
- One optimization per commit (easy revert).
- Prefer flags/knobs. Make risky changes opt-in.
- Always capture **before/after** snapshots.
- Monitor for a few days before marking verified.

## Workflow

Recommended loop:

1) `vibeship-optimizer init`
2) `vibeship-optimizer change start --title "..."`
3) `vibeship-optimizer snapshot --label before`
4) Make *one* optimization + commit
5) `vibeship-optimizer snapshot --label after`
6) `vibeship-optimizer compare --before ... --after ... --out reports/...`
7) Start a multi-day monitor: `vibeship-optimizer monitor start --change-id <chg-...>`
8) Run a daily tick: `vibeship-optimizer monitor tick` (once per day)
9) Mark verified when evidence is sufficient:
   - `vibeship-optimizer change verify --change-id <chg-...> --min-monitor-days -1 --apply --summary "..."`

## Optimization log

(Entries are appended here by `vibeship-optimizer change start`.)
