# Vibeship Optimizer (optcheck)

**Vibeship Optimizer** is a **safe, rollback-friendly optimization workflow** for any codebase (and especially services / agents / OpenClaw deployments).

It helps you do “Carmack-style” optimization:

- one change at a time
- measurable evidence (before/after)
- reversible by default
- verified over days of real usage

This repo ships a small Python CLI called **`optcheck`**.

---

## What it does

`optcheck` gives you a disciplined loop:

1. **Log the intent** (what you’re changing + why)
2. **Capture a baseline snapshot** (health probes, commands, perf counters, etc.)
3. Make a **single optimization change** (ideally one commit)
4. **Capture an after snapshot**
5. **Compare + report** (markdown diffs)
6. **Monitor over multiple days** (tick-based verification)
7. **Verify** (only when requirements are met)

It’s designed to stop “random optimizations” from becoming untraceable or un-revertable.

---

## Core concepts

### 1) Change Logbook (`OPTIMIZATION_CHECKER.md`)
A living, auditable log of:
- what changed
- how to validate
- before/after evidence
- monitoring window + verification decision

### 2) Snapshots (`.optcheck/snapshots/*.json`)
Structured machine-readable “before/after” state:
- command outputs
- service health checks
- timings / sizes / counts

### 3) Preflight
A “diligence gate” before you claim an optimization is real:
- is there a baseline?
- is there a rollback path?
- were required checks run?
- (optionally) was an LLM review bundle generated and attested?

### 4) Monitor (multi-day)
The whole point: some regressions don’t show up immediately.

`optcheck monitor tick` is designed to run daily (cron / Task Scheduler) and append verification data.

### 5) Autopilot
A cron-friendly one-liner that runs the boring stuff:
- monitor tick
- preflight
- verify (dry-run)

---

## Install

### Developer install (editable)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e .
```

You should now have `optcheck` on PATH.

---

## Quick start (in a target project)

From your project root:

```bash
# 1) Initialize optcheck scaffolding
optcheck init

# 2) Start a change log entry
optcheck change start --title "Bound log growth"

# 3) Capture baseline
optcheck snapshot --label before

# 4) Make ONE optimization change + commit it
# ... edit code ...
# git add -A && git commit -m "Bound log growth"

# 5) Capture after snapshot
optcheck snapshot --label after

# 6) Compare snapshots → markdown report
optcheck compare \
  --before .optcheck/snapshots/<before>.json \
  --after  .optcheck/snapshots/<after>.json \
  --out reports/optcheck_compare.md

# 7) Start multi-day monitoring
optcheck monitor start --change-id <chg-id> --days 5

# 8) Run once per day (UTC)
optcheck monitor tick

# 9) When you have evidence, verify
optcheck change verify --change-id <chg-id> --min-monitor-days -1 --apply \
  --summary "No regressions observed over 3 days"
```

If `optcheck` isn’t on PATH (common on Windows):

```bash
python -m optcheck init
python -m optcheck snapshot --label before
```

---

## Configuration

`optcheck` looks for config in:

- `optcheck.yml` / `optcheck.yaml` (project root)
- `.optcheck/config.yml` / `.optcheck/config.yaml`
- `.optcheck/config.json`

Example `optcheck.yml`:

```yaml
project:
  name: my-service

checks:
  commands:
    - name: unit-tests
      cmd: "pytest -q"
    - name: service-health
      cmd: "curl -sS http://127.0.0.1:8765/health"

review:
  require_attestation: true
```

---

## OpenClaw integration

This repo includes an optional OpenClaw skill:

- `openclaw_skill/optimization-checker/SKILL.md`

And helper commands for cron-style automation:

```bash
# generate an OpenClaw cron payload to run daily
autopilot="optcheck autopilot tick --change-id <chg-id>"
optcheck openclaw cron-setup --change-id <chg-id> \
  --cron "0 7 * * *" --tz "Asia/Dubai" --channel telegram --to "<chat_id>"

# apply it (writes cron job)
optcheck openclaw cron-setup --change-id <chg-id> \
  --cron "0 7 * * *" --tz "Asia/Dubai" --channel telegram --to "<chat_id>" --apply
```

---

## Safety model

`optcheck` is intentionally conservative:

- It **does not auto-edit your code**.
- It runs only commands you explicitly configure.
- It encourages **one optimization per commit** + **always keep a rollback path**.
- It produces **audit artifacts** (snapshots, reports, logbook entries).

---

## Repo layout

- `src/optcheck/` — CLI + core logic
- `OPTIMIZATION_CHECKER.md` — template logbook
- `openclaw_skill/` — optional OpenClaw skill wrapper

---

## License

MIT (see `LICENSE`).
