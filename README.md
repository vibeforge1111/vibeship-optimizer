# vibeship-optimizer

vibeship-optimizer is a **safe, rollback-friendly way to optimize anything** (a codebase, a service, an agent stack, an OpenClaw deployment) **without breaking it**.

Instead of “random tweaks”, it gives you a repeatable workflow:

- **one change at a time**
- **measure before & after**
- **keep a rollback path**
- **verify over real usage for days**

It ships as a small Python CLI.

> Command name: `vibeship-optimizer`
>
> If that command isn’t found on your machine (common on Windows), use module mode:
> `python -m vibeship_optimizer ...`

---

## Who this is for

### Non-technical users (yes, you can use this)
If you can:
- copy/paste commands
- run a “health check” command
- read a short report

…you can run a safe optimization loop with this.

### Technical users
Engineers/ops can wire deeper probes, richer commands, and scheduled monitoring.

---

## The 5-minute mental model

vibeship-optimizer creates three kinds of evidence:

1) **A logbook**: `VIBESHIP_OPTIMIZER.md`
2) **Snapshots**: `.vibeship-optimizer/snapshots/*.json` (legacy: `.vibeship_optimizer/snapshots/*.json`)
3) **Reports** (markdown) you can read/share

You only “declare success” when the evidence says it’s real.

---

## Installation (check the path)

### Option A — Install from GitHub (recommended)

```bash
pip install git+https://github.com/vibeforge1111/vibeship-optimizer.git
```

### Option B — Install from a local folder (developer mode)

```bash
git clone https://github.com/vibeforge1111/vibeship-optimizer.git
cd vibeship-optimizer
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e .
```

### If `vibeship-optimizer` is “not recognized” (Windows fix)

Either:
- use module mode (always works):

```bash
python -m vibeship_optimizer --help
```

Or add your Python Scripts folder to PATH (pip prints the exact path when installing).

---

## Suggested workflow (non-technical, step-by-step)

This is the simplest safe loop.

### Optional: quick onboarding (recommended)

If this is your first time using vibeship-optimizer in a project, run:

```bash
python -m vibeship_optimizer onboard
```

Tip: on a fresh project, `python -m vibeship_optimizer init` will also offer to run onboarding (only in interactive terminals).
To run onboarding non-interactively: `python -m vibeship_optimizer init --onboard --no-prompt`.

This will:
- ensure the logbook + config exist
- try to set a safe default timing command (only when it has a strong guess)
- print the next 3–5 commands to run

### Step 0 — Go to your target project folder
Example:

```bash
cd C:\path\to\your-project
```

### Step 1 — Initialize

```bash
python -m vibeship_optimizer init
```

This creates:
- `VIBESHIP_OPTIMIZER.md` (your logbook)
- `.vibeship-optimizer/` (snapshots, config)

Notes:
- If you already have an older `OPTIMIZATION_CHECKER.md`, `init` will try to migrate it to `VIBESHIP_OPTIMIZER.md`.
- The tool will use `.vibeship-optimizer/` by default, but will also detect and reuse legacy `.vibeship_optimizer/` if that’s where your project’s existing state lives.

### Step 2 — Start a change entry (what are we trying to improve?)

```bash
python -m vibeship_optimizer change start --title "Reduce memory usage"
```

### Step 3 — Capture a BEFORE snapshot

```bash
python -m vibeship_optimizer snapshot --label before --change-id <chg-id> --as before
```

### Step 4 — Make exactly ONE change
Examples:
- change a config value
- adjust a cache size
- add log rotation
- disable an expensive feature

If you have git: commit it as 1 commit.

### Step 5 — Capture an AFTER snapshot

```bash
python -m vibeship_optimizer snapshot --label after --change-id <chg-id> --as after
```

### Step 6 — Compare and get a human-readable report

```bash
python -m vibeship_optimizer compare \
  --before .vibeship-optimizer/snapshots/<before>.json \
  --after  .vibeship-optimizer/snapshots/<after>.json \
  --out reports/vibeship_optimizer_compare.md
```

Notes:
- Prefer using the exact paths printed by `snapshot` (copy/paste them).
- `compare` is strict: missing/invalid snapshot JSON will fail instead of silently producing an empty diff.

### Step 7 — Monitor over days (optional but recommended)

```bash
python -m vibeship_optimizer monitor start --change-id <chg-id> --days 5
python -m vibeship_optimizer monitor tick
```

This writes daily reports under the state dir (for example: `.vibeship-optimizer/reports/`) and appends a short “verification update” block into `VIBESHIP_OPTIMIZER.md`.

---

## OpenClaw users (recommended setup)

If you’re using OpenClaw, vibeship-optimizer can help you:
- do safe performance work on skills / services
- keep evidence-based changelogs
- schedule verification ticks

What to do:

1) Use the OpenClaw skill docs:
- `openclaw_skill/vibeship-optimizer/SKILL.md`

2) Generate/apply a cron-style tick (prints the command; can optionally apply):

```bash
python -m vibeship_optimizer openclaw cron-setup \
  --change-id <chg-id> \
  --cron "0 7 * * *" --tz "Asia/Dubai" \
  --channel telegram --to "<chat_id>"
```

### Autopilot (cron-friendly)

For OpenClaw cron jobs, `autopilot tick` is designed to be a single command that returns a single JSON payload:

```bash
python -m vibeship_optimizer autopilot tick --change-id <chg-id> --force --format json --ok-on-pending
```

If a monitor is not active, it returns `monitor.skipped=true` with `reason=no_active_monitor` (instead of crashing), so your automation can decide whether to start monitoring or just alert.

---

## Claude & Codex users (LLM-assisted, evidence-based)

The goal is **no hallucinated optimization claims**.

### Recommended pattern
1) Generate an evidence bundle:

```bash
python -m vibeship_optimizer review bundle --change-id <chg-id> --out reports/vibeship_optimizer_review_bundle.md
```

2) Paste that bundle into Claude/Codex and ask:
- “Is the before/after evidence sufficient?”
- “What could invalidate this result?”
- “What next verification step would you run?”

3) (Optional) record an attestation:

```bash
python -m vibeship_optimizer review attest \
  --change-id <chg-id> \
  --tool codex --reasoning-mode high \
  --model "<model>" --reviewer "<name>"
```

Security note: **never paste secrets/tokens** into the bundle.

---

## Configuration

vibeship-optimizer looks for config in:

- `vibeship_optimizer.yml` / `vibeship_optimizer.yaml` (project root)
- `.vibeship-optimizer/config.yml` / `.vibeship-optimizer/config.yaml` (default)
- `.vibeship-optimizer/config.json` (also supported)
- Legacy compatibility: `.vibeship_optimizer/config.yml|.json`

---

## Security / safety

- The tool **does not auto-edit your code**.
- It runs only commands you explicitly configure.
- It encourages one-change-per-commit and a rollback path.
- The repo is set up to ignore local artifacts:
  - `.vibeship-optimizer/`
  - `reports/`
  - `.venv/`

If you’re publishing reports, **check them for secrets** before sharing.

---

## Repo layout

- `src/vibeship_optimizer/` — CLI + core logic
- `VIBESHIP_OPTIMIZER.md` — logbook template
- `openclaw_skill/` — optional OpenClaw skill wrapper

---

## License

MIT (see `LICENSE`).

