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

- `optcheck` CLI (Python, minimal deps)
- templates: `OPTIMIZATION_CHECKER.md`, `optcheck.yml`
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

## Quick start in a target project

From your project root:

```bash
# initialize templates + config
optcheck init

# take a baseline snapshot
optcheck snapshot --label before

# ...make a single optimization change + commit...

# take an after snapshot
optcheck snapshot --label after

# compare
optcheck compare --before .optcheck/snapshots/<before>.json --after .optcheck/snapshots/<after>.json \
  --out reports/optcheck_compare.md
```

### If `optcheck` isn’t on PATH (common on Windows)

Use module mode:

```bash
python -m optcheck init
python -m optcheck snapshot --label before
```

## OpenClaw integration

This repo will include an optional OpenClaw skill directory (`openclaw_skill/`) so you can:
- run `optcheck snapshot` on a schedule
- post diffs into your OpenClaw workspace checker doc

(We’ll wire this up as we iterate.)

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
