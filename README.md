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

1) **A logbook**: `OPTIMIZATION_CHECKER.md`
2) **Snapshots**: `.vibeship_optimizer/snapshots/*.json`
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
- `OPTIMIZATION_CHECKER.md` (your logbook)
- `.vibeship_optimizer/` (snapshots, config)

### Step 2 — Start a change entry (what are we trying to improve?)

```bash
python -m vibeship_optimizer change start --title "Reduce memory usage"
```

### Step 3 — Capture a BEFORE snapshot

```bash
python -m vibeship_optimizer snapshot --label before
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
python -m vibeship_optimizer snapshot --label after
```

### Step 6 — Compare and get a human-readable report

```bash
python -m vibeship_optimizer compare \
  --before .vibeship_optimizer/snapshots/<before>.json \
  --after  .vibeship_optimizer/snapshots/<after>.json \
  --out reports/vibeship_optimizer_compare.md
```

### Step 7 — Monitor over days (optional but recommended)

```bash
python -m vibeship_optimizer monitor start --change-id <chg-id> --days 5
python -m vibeship_optimizer monitor tick
```

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
- `.vibeship_optimizer/config.yml` / `.vibeship_optimizer/config.yaml`
- `.vibeship_optimizer/config.json`

---

## Security / safety

- The tool **does not auto-edit your code**.
- It runs only commands you explicitly configure.
- It encourages one-change-per-commit and a rollback path.
- The repo is set up to ignore local artifacts:
  - `.vibeship_optimizer/`
  - `reports/`
  - `.venv/`

If you’re publishing reports, **check them for secrets** before sharing.

---

## Repo layout

- `src/vibeship_optimizer/` — CLI + core logic
- `OPTIMIZATION_CHECKER.md` — logbook template
- `openclaw_skill/` — optional OpenClaw skill wrapper

---

## License

MIT (see `LICENSE`).
