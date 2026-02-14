# OpenClaw automation: cron setup for optcheck

Goal: run multi-day verification without breaking things.

We schedule an **isolated cron job** that:
- runs `optcheck monitor tick`
- runs `optcheck preflight --change-id ...`
- runs `optcheck change verify --change-id ...` (dry-run)
- announces only when something is wrong (recommended)

## Option A: main-session cron (system event)

This queues a system event so the main heartbeat run can do the work.
Use when you want full main context.

```bash
openclaw cron add \
  --name "optcheck daily tick" \
  --cron "0 7 * * *" \
  --tz "Asia/Dubai" \
  --session main \
  --system-event "optcheck: run daily tick for <PROJECT_PATH> change=<CHANGE_ID>" \
  --wake now
```

Then, in your heartbeat instructions (or manual), you run:
- `python -m optcheck monitor tick`
- `python -m optcheck preflight --change-id <CHANGE_ID>`
- `python -m optcheck change verify --change-id <CHANGE_ID>`

## Option B (recommended): isolated cron job with xhigh reasoning

This runs a dedicated agent turn, where you can set model + thinking.

```bash
openclaw cron add \
  --name "optcheck daily tick (isolated)" \
  --cron "0 7 * * *" \
  --tz "Asia/Dubai" \
  --session isolated \
  --thinking xhigh \
  --message "Run optcheck daily tick in <PROJECT_PATH> for change <CHANGE_ID>. Steps: (1) cd <PROJECT_PATH>; (2) python -m optcheck monitor tick; (3) python -m optcheck preflight --change-id <CHANGE_ID> --out reports/optcheck_preflight.md; (4) python -m optcheck change verify --change-id <CHANGE_ID> --min-monitor-days -1; If any FAIL, summarize." \
  --announce \
  --channel telegram \
  --to "<YOUR_CHAT_ID>"
```

Notes:
- `--min-monitor-days -1` means: use config `verification.min_monitor_days`.
- Preflight enforces review attestation by default.
- For noisy runs, set `--no-deliver` and check `.optcheck/reports/` later.
