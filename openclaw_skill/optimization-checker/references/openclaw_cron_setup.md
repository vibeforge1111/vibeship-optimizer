# OpenClaw automation: cron setup for optcheck

Goal: run multi-day verification without breaking things.

We schedule an **isolated cron job** that runs a single command:
- `optcheck autopilot tick --change-id ...`

This internally runs:
- monitor tick
- preflight (with change_id enforcement)
- verify (dry-run)

And exits non-zero if verification fails (ideal for cron alerting).

## Recommended: generate a cron command via optcheck

`optcheck` can generate the correct OpenClaw cron command for you:

```bash
optcheck openclaw cron-setup \
  --change-id <CHANGE_ID> \
  --project-root <PROJECT_PATH> \
  --cron "0 7 * * *" \
  --tz "Asia/Dubai" \
  --channel telegram \
  --to "<YOUR_CHAT_ID>"
```

To apply immediately (runs `openclaw cron add ...`):

```bash
optcheck openclaw cron-setup \
  --change-id <CHANGE_ID> \
  --project-root <PROJECT_PATH> \
  --cron "0 7 * * *" \
  --tz "Asia/Dubai" \
  --channel telegram \
  --to "<YOUR_CHAT_ID>" \
  --apply
```

This sets up an isolated job that runs:
- `python -m optcheck autopilot tick --change-id <CHANGE_ID>`

Notes:
- `--min-monitor-days -1` means: use config `verification.min_monitor_days`.
- Preflight enforces review attestation by default.
- For noisy runs, set `--no-deliver` and check `.optcheck/reports/` later.
