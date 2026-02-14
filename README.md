# optimization-checker

A **safe, rollback-friendly optimization workflow** for any codebase (and especially OpenClaw deployments):

- Optimize “Carmack-style”: one change at a time, measurable, reversible.
- Capture **before/after snapshots** (runtime, disk, commands, health probes).
- Maintain a living **OPTIMIZATION_CHECKER.md** that tracks:
  - what changed
  - how to validate
  - what the measured effect was
  - when it was considered verified (after days of real use)

This repo provides:

- `optcheck` CLI (Python, minimal deps; YAML config supported)
- templates: `OPTIMIZATION_CHECKER.md`
- config formats supported:
  - `optcheck.yml` / `optcheck.yaml` (project root)
  - `.optcheck/config.yml` / `.optcheck/config.yaml`
  - `.optcheck/config.json`
- a snapshot+compare system that produces diffs as markdown reports

## Philosophy

1. **One commit per feature/optimization.**
2. Prefer **feature flags** and bounded knobs.
3. Always keep a **revert path** (`git revert <sha>`).
4. Measure **before** and **after**, then keep monitoring for a few days.

## Install (dev)

```bash
python -m venv .venv
# windows: .venv\Scripts\activate
# mac/linux: source .venv/bin/activate
pip install -e .
```

YAML config uses `PyYAML` (included as a dependency).

## Quick start in a target project

From your project root:

```bash
# initialize templates + config
optcheck init

# start a tracked change (appends to OPTIMIZATION_CHECKER.md)
optcheck change start --title "Bound log growth"

# take a baseline snapshot
optcheck snapshot --label before

# ...make a single optimization change + commit...

# take an after snapshot
optcheck snapshot --label after

# compare
optcheck compare --before .optcheck/snapshots/<before>.json --after .optcheck/snapshots/<after>.json \
  --out reports/optcheck_compare.md

# start multi-day monitoring (baseline defaults to latest snapshot if omitted)
optcheck monitor start --change-id <chg-id> --days 5

# run once per day (UTC) to append verification updates
optcheck monitor tick

# run diligence checks before optimizing
optcheck preflight --out reports/optcheck_preflight.md

# (recommended; required by default in new configs) generate evidence bundle for LLM review + attest the review mode
optcheck review bundle --change-id <chg-id> --out reports/optcheck_review_bundle.md
optcheck review attest --change-id <chg-id> --tool codex --reasoning-mode xhigh --model "openai-codex/..." --reviewer "<name>"

# preflight can enforce attestation (new default is require_attestation=true)
optcheck preflight --change-id <chg-id> --out reports/optcheck_preflight.md

# to relax enforcement:
# edit your config and set: review.require_attestation: false

# when you have enough evidence, mark the change verified (refuses if missing requirements)
optcheck change verify --change-id <chg-id> --min-monitor-days -1
optcheck change verify --change-id <chg-id> --min-monitor-days -1 --apply --summary "No regressions observed over 3 days"

# cron-friendly one-liner (runs monitor tick + preflight + verify dry-run)
optcheck autopilot tick --change-id <chg-id>

# repair/normalize optcheck scaffolding (dry-run by default)
optcheck doctor
optcheck doctor --apply

# run read-only analyzers (bloat / maybe-unused deps)
optcheck analyze --out reports/optcheck_analyze.md
```

### If `optcheck` isn’t on PATH (common on Windows)

Use module mode:

```bash
python -m optcheck init
python -m optcheck snapshot --label before
```

## OpenClaw integration

This repo includes an optional OpenClaw skill:
- `openclaw_skill/optimization-checker/SKILL.md`

It documents the safe workflow (change logbook + snapshots + multi-day monitor).

## Safety

`optcheck` does **not** auto-edit your code. It only:
- runs commands you explicitly configure
- records measurements
- writes snapshots + reports

## Roadmap

- language-specific modules (Python/Node/Go) for unused-dep hints
- service health probes + latency budgets
- multi-day monitoring helper
- OpenClaw skill packaging
