# OpenClaw automation: cron setup for vibeship-optimizer

Goal: run multi-day verification without breaking things.

We schedule an **isolated cron job** that runs a single command:
- `vibeship-optimizer autopilot tick --change-id ...`

This internally runs:
- monitor tick
- preflight (with change_id enforcement)
- verify (dry-run)

By default it exits non-zero if verification fails (ideal for cron alerting).

If you want cron to stay quiet while a change is simply "pending more monitor days", pass:
- `--ok-on-pending`

## Recommended: generate a cron command via vibeship-optimizer

`vibeship-optimizer` can generate the correct OpenClaw cron command for you:

```bash
vibeship-optimizer openclaw cron-setup \
  --change-id <CHANGE_ID> \
  --project-root <PROJECT_PATH> \
  --cron "0 7 * * *" \
  --tz "Asia/Dubai" \
  --channel telegram \
  --to "<YOUR_CHAT_ID>"
```

To apply immediately (runs `openclaw cron add ...`):

```bash
vibeship-optimizer openclaw cron-setup \
  --change-id <CHANGE_ID> \
  --project-root <PROJECT_PATH> \
  --cron "0 7 * * *" \
  --tz "Asia/Dubai" \
  --channel telegram \
  --to "<YOUR_CHAT_ID>" \
  --apply
```

This sets up an isolated job that runs:
- `python -m vibeship_optimizer autopilot tick --change-id <CHANGE_ID> --force --format json --ok-on-pending`

Notes:
- `--min-monitor-days -1` means: use config `verification.min_monitor_days`.
- Preflight enforces review attestation by default.
- For noisy runs, set `--no-deliver` and check `.vibeship-optimizer/reports/` later.
