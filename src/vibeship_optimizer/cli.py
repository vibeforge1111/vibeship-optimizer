from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .core import compare_snapshots, git_info, read_json, render_compare_markdown, resolve_state_dir, snapshot, write_text, write_json
from .configio import find_config_path, load_config_for_project, write_config
from .logbook import create_change, list_changes, load_change, update_change
from .monitor import load_monitor, start_monitor, tick_monitor
from .analyze import analyze_project
from .preflight import preflight
from .doctor import doctor
from .review import build_review_bundle, write_attestation
from .verify import apply_verified, verify_change
from .autopilot import autopilot_tick, render_autopilot_summary
from .openclaw_integration import CronSpec, apply_cron_add, build_cron_add_command
from .onboarding import apply_onboarding, onboarding_next_steps, suggest_timing_cmd
from .llm_instructions import build_llm_bundle, operator_prompt, render_llm_bundle_markdown


TEMPLATE_CHECKER = """# vibeship-optimizer

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
3) `vibeship-optimizer snapshot --label before --change-id <chg-id> --as before`
4) Make *one* optimization + commit
5) `vibeship-optimizer snapshot --label after --change-id <chg-id> --as after`
6) `vibeship-optimizer compare --before ... --after ... --out reports/...`
7) Monitor for 1–7 days; update the change section with results.

## Optimization log

"""


def init_project(project_root: Path) -> dict:
    """Initialize a project folder (idempotent).

    Returns a dict with paths and whether each file was created/migrated.
    """
    root = project_root
    created = {"config": False, "logbook": False, "logbook_migrated": False}

    opt_dir = root / resolve_state_dir(root)
    opt_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = find_config_path(root)
    if not cfg_path.exists():
        cfg, _path = load_config_for_project(root)
        cfg = {**cfg, **{"review": cfg.get("review"), "verification": cfg.get("verification")}}
        write_config(cfg_path, cfg)
        created["config"] = True

    checker_path = root / "VIBESHIP_OPTIMIZER.md"
    legacy_path = root / "OPTIMIZATION_CHECKER.md"

    if not checker_path.exists() and legacy_path.exists():
        try:
            legacy_path.replace(checker_path)
            created["logbook_migrated"] = True
        except Exception:
            write_text(checker_path, legacy_path.read_text(encoding="utf-8", errors="ignore"))
            created["logbook_migrated"] = True

    if not checker_path.exists():
        write_text(checker_path, TEMPLATE_CHECKER)
        created["logbook"] = True

    return {"config_path": str(cfg_path), "logbook_path": str(checker_path), "created": created}


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    res = init_project(root)
    print(f"Initialized: {res['config_path']}")
    print(f"Initialized: {res['logbook_path']}")

    # Optional onboarding prompt: only when init actually created/migrated
    # scaffolding, and only in interactive terminals (avoid OpenClaw/CI).
    created = res.get("created") or {}
    did_create = bool(created.get("config") or created.get("logbook") or created.get("logbook_migrated"))
    no_prompt = bool(getattr(args, "no_prompt", False)) or bool(os.environ.get("VIBESHIP_OPTIMIZER_NO_PROMPT"))
    run_onboard = bool(getattr(args, "onboard", False))

    # If the user explicitly asked for onboarding, run it even in non-interactive contexts.
    if did_create and run_onboard:
        return cmd_onboard(
            argparse.Namespace(
                timing_cmd="",
                force=False,
                dry_run=False,
                format="text",
            )
        )

    if did_create and not no_prompt and sys.stdin.isatty() and sys.stdout.isatty():
        try:
            ans = input("Run quick onboarding now (minimal config + next steps)? [Y/n] ").strip().lower()
            run_onboard = (ans == "" or ans.startswith("y"))
        except Exception:
            run_onboard = False

        if run_onboard:
            return cmd_onboard(
                argparse.Namespace(
                    timing_cmd="",
                    force=False,
                    dry_run=False,
                    format="text",
                )
            )
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    root = Path.cwd()
    init_project(root)

    cfg, cfg_path = load_config_for_project(root)

    timing_cmd = str(args.timing_cmd or "").strip()
    if not timing_cmd:
        timing_cmd = suggest_timing_cmd(project_root=root, languages=(cfg.get("project") or {}).get("languages") or [])

    updated, changes = apply_onboarding(
        project_root=root,
        config=cfg,
        timing_cmd=timing_cmd,
        force=bool(args.force),
    )

    if changes and not bool(args.dry_run):
        write_config(Path(cfg_path), updated)

    payload = {
        "schema": "vibeship_optimizer.onboard.v1",
        "ok": True,
        "project_root": str(root),
        "config_path": str(cfg_path),
        "dry_run": bool(args.dry_run),
        "changes": changes,
        "next_steps": onboarding_next_steps()[:6],
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"Onboarding complete. Config: {cfg_path}")
        if changes:
            print("Applied:")
            for ch in changes[:10]:
                print(f"- {ch.get('code')}: {ch.get('value')}")
        else:
            print("No config changes applied (already configured or no safe suggestion).")
        print("Next steps:")
        for line in onboarding_next_steps()[:5]:
            print(f"- {line}")

    return 0


def cmd_llm_bundle(args: argparse.Namespace) -> int:
    root = Path.cwd()
    init_project(root)

    change_id = str(getattr(args, "change_id", "") or "").strip()
    out = str(getattr(args, "out", "") or "").strip()
    fmt = str(getattr(args, "format", "md") or "md").strip().lower()

    bundle = build_llm_bundle(project_root=root, change_id=change_id)

    if fmt == "json":
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
        return 0

    out_path = Path(out) if out else (root / "reports" / "vibeship_optimizer_llm_bundle.md")
    write_text(out_path, render_llm_bundle_markdown(bundle))
    print(json.dumps({"wrote": str(out_path)}, indent=2))
    return 0


def cmd_llm_prompt(args: argparse.Namespace) -> int:
    root = Path.cwd()
    prompt = operator_prompt(project_root=root)
    if args.format == "json":
        print(json.dumps({"prompt": prompt}, indent=2, ensure_ascii=False))
    else:
        print(prompt)
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = Path.cwd()
    _cfg, cfg_path = load_config_for_project(root)
    try:
        out = snapshot(project_root=root, label=str(args.label or "snapshot"), config_path=cfg_path)
    except Exception as e:
        print(f"error: snapshot failed: {e}", file=sys.stderr)
        return 2

    # Backward-compatible: stdout stays as a single path line for easy scripting.
    print(str(out))

    # Optional: attach evidence to a change record.
    change_id = str(getattr(args, "change_id", "") or "").strip()
    attach_as = str(getattr(args, "attach_as", "") or "").strip().lower()
    if change_id:
        if attach_as not in ("before", "after"):
            print("error: when using --change-id, you must also provide --as before|after", file=sys.stderr)
            return 2

        updates = {}
        if attach_as == "before":
            updates["snapshot_before"] = str(out)
        else:
            updates["snapshot_after"] = str(out)
            # Record commit sha for the change. Best-effort: empty if not a git repo.
            updates["commit"] = str((git_info(root) or {}).get("commit") or "")

        try:
            update_change(project_root=root, change_id=change_id, updates=updates)
            print(f"attached snapshot ({attach_as}) to change_id={change_id}", file=sys.stderr)
        except Exception as e:
            print(f"error: failed to attach snapshot to change record: {e}", file=sys.stderr)
            return 2

    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    before_path = Path(args.before)
    after_path = Path(args.after)
    try:
        before = read_json(before_path)
        after = read_json(after_path)
    except Exception as e:
        print(f"error: failed to read snapshot JSON: {e}", file=sys.stderr)
        return 2

    diff_out = compare_snapshots(before, after)
    md = render_compare_markdown(diff_out)

    if args.out:
        out_path = Path(args.out)
        write_text(out_path, md)
        print(f"Wrote: {out_path}")
    else:
        print(md)

    # optional: also write JSON diff next to markdown
    if args.json_out:
        json_path = Path(args.json_out)
        write_json(json_path, diff_out)
        print(f"Wrote: {json_path}")

    return 0


def cmd_change_start(args: argparse.Namespace) -> int:
    # Convenience: ensure init has been run (idempotent).
    init_project(Path.cwd())

    root = Path.cwd()
    checker_path = root / "VIBESHIP_OPTIMIZER.md"
    change = create_change(
        project_root=root,
        checker_path=checker_path,
        title=str(args.title),
        hypothesis=str(args.hypothesis or ""),
        risk=str(args.risk or ""),
        rollback=str(args.rollback or "git revert <sha>"),
        validation_today=str(args.validation_today or ""),
        validation_next_days=str(args.validation_next_days or ""),
    )
    print(
        json.dumps(
            {k: change.get(k) for k in ("change_id", "title", "status", "started_at", "path")},
            indent=2,
        )
    )
    return 0


def cmd_change_list(args: argparse.Namespace) -> int:
    root = Path.cwd()
    items = []
    for pth in list_changes(root):
        data = load_change(pth)
        items.append({
            "change_id": data.get("change_id"),
            "title": data.get("title"),
            "status": data.get("status"),
            "started_at": data.get("started_at"),
            "path": str(pth),
        })
    print(json.dumps(items, indent=2))
    return 0


def cmd_change_verify(args: argparse.Namespace) -> int:
    root = Path.cwd()
    init_project(root)

    cfg, _cfg_path = load_config_for_project(root)

    vcfg = cfg.get("verification") if isinstance(cfg, dict) else {}
    default_days = int((vcfg or {}).get("min_monitor_days", 3) or 3)
    min_days = default_days if int(args.min_monitor_days) < 0 else int(args.min_monitor_days)

    default_clean = bool((vcfg or {}).get("require_clean_git", False))
    require_clean = bool(args.require_clean_git) or default_clean

    if args.apply:
        payload = apply_verified(
            project_root=root,
            checker_path=root / "VIBESHIP_OPTIMIZER.md",
            change_id=str(args.change_id),
            config=cfg,
            min_monitor_days=int(min_days),
            require_clean_git=bool(require_clean),
            summary=str(args.summary or ""),
        )
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 2

    # dry-run
    result = verify_change(
        project_root=root,
        change_id=str(args.change_id),
        config=cfg,
        min_monitor_days=int(min_days),
        require_clean_git=bool(require_clean),
    )
    print(json.dumps({"change_id": str(args.change_id), **result.to_dict()}, indent=2))
    return 0 if result.ok else 2


def cmd_monitor_start(args: argparse.Namespace) -> int:
    root = Path.cwd()
    init_project(root)
    try:
        path = start_monitor(
            project_root=root,
            change_id=str(args.change_id),
            baseline_snapshot=str(args.baseline) if args.baseline else None,
            days=int(args.days),
        )
        print(json.dumps({"monitor": str(path)}, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 2


def cmd_monitor_tick(args: argparse.Namespace) -> int:
    root = Path.cwd()
    init_project(root)
    checker_path = root / "VIBESHIP_OPTIMIZER.md"
    try:
        res = tick_monitor(project_root=root, checker_path=checker_path, force=bool(args.force))
        print(json.dumps(res, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 2


def cmd_monitor_status(args: argparse.Namespace) -> int:
    root = Path.cwd()
    try:
        state = load_monitor(root)
        if not state:
            print(json.dumps({"active": False}, indent=2))
            return 0
        print(json.dumps({"active": True, **state.to_dict()}, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"active": False, "error": str(e)}, indent=2))
        return 2


def cmd_analyze(args: argparse.Namespace) -> int:
    root = Path.cwd()
    out = Path(args.out) if args.out else None
    cfg, _cfg_path = load_config_for_project(root)
    report = analyze_project(project_root=root, out_md=out, config=cfg)
    if out:
        print(json.dumps({"wrote": str(out)}, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    root = Path.cwd()
    out = Path(args.out) if args.out else None
    report = preflight(project_root=root, out_md=out, change_id=str(args.change_id or ""))
    if out:
        print(json.dumps({"wrote": str(out), "worst_level": report.get("worst_level")}, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path.cwd()
    report = doctor(project_root=root, apply=bool(args.apply))
    print(json.dumps(report, indent=2))
    return 0


def cmd_review_bundle(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state_dir = root / resolve_state_dir(root)
    out = Path(args.out) if args.out else (state_dir / "review_bundles" / f"{args.change_id}.md")
    p = build_review_bundle(project_root=root, change_id=str(args.change_id), out_path=out)
    print(json.dumps({"wrote": str(p)}, indent=2))
    return 0


def cmd_review_attest(args: argparse.Namespace) -> int:
    root = Path.cwd()
    p = write_attestation(
        project_root=root,
        change_id=str(args.change_id),
        reviewer=str(args.reviewer or "unknown"),
        model=str(args.model or "unknown"),
        reasoning_mode=str(args.reasoning_mode or "default"),
        tool=str(args.tool or "other"),
        notes=str(args.notes or ""),
    )
    print(json.dumps({"wrote": str(p)}, indent=2))
    return 0


def cmd_autopilot_tick(args: argparse.Namespace) -> int:
    root = Path.cwd()
    init_project(root)

    payload = autopilot_tick(project_root=root, change_id=str(args.change_id), force=bool(args.force))

    if args.format == "text":
        print(render_autopilot_summary(payload))
    else:
        print(json.dumps(payload, indent=2))

    # exit non-zero if verify failed
    ok = bool(((payload.get("verify") or {}).get("ok")))
    if ok:
        return 0

    failures = ((payload.get("verify") or {}).get("failures") or [])
    mon = payload.get("monitor") or {}
    mon_reason = str(mon.get("reason") or "")

    # "Pending" means only waiting for more monitor days, and we do have/expect a monitor.
    pending_only = (
        isinstance(failures, list)
        and failures
        and all(str(f).startswith("insufficient monitor ticks:") for f in failures)
        and mon_reason not in ("no_active_monitor",)
    )

    return 0 if (bool(args.ok_on_pending) and pending_only) else 2


def cmd_openclaw_cron_setup(args: argparse.Namespace) -> int:
    """Generate (and optionally apply) an OpenClaw cron job for vibeship-optimizer autopilot."""
    root = Path.cwd()

    project_root = str((Path(args.project_root).resolve() if args.project_root else root.resolve()))
    change_id = str(args.change_id)
    name = str(args.name or f"vibeship-optimizer autopilot tick ({change_id})")

    spec = CronSpec(
        name=name,
        cron=str(args.cron),
        tz=str(args.tz),
        project_root=project_root,
        change_id=change_id,
        thinking=str(args.thinking or "xhigh"),
        model=str(args.model or ""),
        announce=not bool(args.no_deliver),
        channel=str(args.channel or "last"),
        to=str(args.to or ""),
    )

    cmd = build_cron_add_command(spec)

    if bool(args.apply):
        res = apply_cron_add(spec=spec, cwd=root)
        print(json.dumps({"spec": spec.to_dict(), "result": res}, indent=2))
        return 0 if res.get("ok") else 2

    print(json.dumps({"spec": spec.to_dict(), "command": cmd}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vibeship-optimizer", description="vibeship-optimizer: safe optimization workflow (snapshot + compare + verify)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Create .vibeship-optimizer config and VIBESHIP_OPTIMIZER.md template")
    sp.add_argument("--onboard", action="store_true", help="Run quick onboarding immediately after init")
    sp.add_argument("--no-prompt", action="store_true", help="Disable the onboarding prompt (TTY only)")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("onboard", help="First-run onboarding: set minimal config + print next steps")
    sp.add_argument("--timing-cmd", default="", help="Optional: set timings[0].cmd and commands.test to this command")
    sp.add_argument("--force", action="store_true", help="Overwrite existing config values when possible")
    sp.add_argument("--dry-run", action="store_true", help="Print what would change without writing config")
    sp.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    sp.set_defaults(func=cmd_onboard)

    sp = sub.add_parser("llm", help="Generate prompts/bundles for controlling vibeship-optimizer from any LLM")
    sub2 = sp.add_subparsers(dest="llm_cmd", required=True)

    sp2 = sub2.add_parser("prompt", help="Print a pasteable operator prompt (no project data)")
    sp2.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    sp2.set_defaults(func=cmd_llm_prompt)

    sp2 = sub2.add_parser("bundle", help="Write a context bundle to paste into an LLM (preflight+analyze+config summary)")
    sp2.add_argument("--change-id", default="", help="Optional: include change_id enforcement in preflight")
    sp2.add_argument("--out", default="", help="Write markdown bundle to this path (default: reports/vibeship_optimizer_llm_bundle.md)")
    sp2.add_argument("--format", default="md", choices=["md", "json"], help="Output format")
    sp2.set_defaults(func=cmd_llm_bundle)

    sp = sub.add_parser("snapshot", help="Capture a snapshot (sizes, timings, probes)")
    sp.add_argument("--label", default="", help="label for snapshot")
    sp.add_argument("--change-id", default="", help="Optional: attach this snapshot to a change record")
    sp.add_argument("--as", dest="attach_as", default="", choices=["before", "after"], help="Attach role when using --change-id")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("compare", help="Compare two snapshots")
    sp.add_argument("--before", required=True, help="path to before snapshot JSON")
    sp.add_argument("--after", required=True, help="path to after snapshot JSON")
    sp.add_argument("--out", default="", help="write markdown report to path")
    sp.add_argument("--json-out", default="", help="write JSON diff to path")
    sp.set_defaults(func=cmd_compare)

    # Change logbook helpers
    sp = sub.add_parser("change", help="Track an optimization as a durable change record")
    sub2 = sp.add_subparsers(dest="change_cmd", required=True)

    sp2 = sub2.add_parser("start", help="Create a change record and append it to VIBESHIP_OPTIMIZER.md")
    sp2.add_argument("--title", required=True)
    sp2.add_argument("--hypothesis", default="")
    sp2.add_argument("--risk", default="")
    sp2.add_argument("--rollback", default="git revert <sha>")
    sp2.add_argument("--validation-today", dest="validation_today", default="")
    sp2.add_argument("--validation-next-days", dest="validation_next_days", default="")
    sp2.set_defaults(func=cmd_change_start)

    sp2 = sub2.add_parser("list", help="List change records")
    sp2.set_defaults(func=cmd_change_list)

    sp2 = sub2.add_parser("verify", help="Check evidence and (optionally) mark change as VERIFIED")
    sp2.add_argument("--change-id", required=True)
    sp2.add_argument("--min-monitor-days", type=int, default=-1, help="If -1, use config verification.min_monitor_days")
    sp2.add_argument("--require-clean-git", action="store_true", help="If set, override config verification.require_clean_git")
    sp2.add_argument("--summary", default="", help="Summary to append when applying verified")
    sp2.add_argument("--apply", action="store_true", help="Actually mark verified + append to VIBESHIP_OPTIMIZER.md")
    sp2.set_defaults(func=cmd_change_verify)

    # Multi-day monitor
    sp = sub.add_parser("monitor", help="Multi-day verification runner (snapshots + compare + append updates)")
    sub2 = sp.add_subparsers(dest="monitor_cmd", required=True)

    sp2 = sub2.add_parser("start", help="Start monitoring a change against a baseline snapshot")
    sp2.add_argument("--change-id", required=True)
    sp2.add_argument("--baseline", default="", help="baseline snapshot path (defaults to latest snapshot)")
    sp2.add_argument("--days", type=int, default=5)
    sp2.set_defaults(func=cmd_monitor_start)

    sp2 = sub2.add_parser("tick", help="Run one monitoring tick (once per UTC day by default)")
    sp2.add_argument("--force", action="store_true")
    sp2.set_defaults(func=cmd_monitor_tick)

    sp2 = sub2.add_parser("status", help="Show active monitor status")
    sp2.set_defaults(func=cmd_monitor_status)

    # Analyzers (safe, read-only)
    sp = sub.add_parser("analyze", help="Read-only analyzers for bloat / unused-dep hints")
    sp.add_argument("--out", default="", help="Write markdown report to path")
    sp.set_defaults(func=cmd_analyze)

    # Preflight
    sp = sub.add_parser("preflight", help="Diligence checks before optimizing (safe, read-only)")
    sp.add_argument("--out", default="", help="Write markdown report to path")
    sp.add_argument("--change-id", default="", help="Optional: enforce checks for a specific change_id")
    sp.set_defaults(func=cmd_preflight)

    # Doctor
    sp = sub.add_parser(
        "doctor",
        help="Repair/normalize vibeship-optimizer scaffolding (config file only: .vibeship-optimizer/config.yml|.json)",
    )
    sp.add_argument("--apply", action="store_true", help="Write changes (otherwise dry-run)")
    sp.set_defaults(func=cmd_doctor)

    # Review (LLM-assisted, but evidence-based)
    sp = sub.add_parser("review", help="Generate evidence bundles + record review attestations")
    sub2 = sp.add_subparsers(dest="review_cmd", required=True)

    sp2 = sub2.add_parser("bundle", help="Write a review bundle (git context + diff) to reduce hallucinations")
    sp2.add_argument("--change-id", required=True)
    sp2.add_argument("--out", default="", help="Write bundle markdown to this path")
    sp2.set_defaults(func=cmd_review_bundle)

    sp2 = sub2.add_parser("attest", help="Record which model/mode reviewed a change")
    sp2.add_argument("--change-id", required=True)
    sp2.add_argument("--tool", default="codex", choices=["codex", "claude", "other"]) 
    sp2.add_argument("--reasoning-mode", default="high", help="e.g. high|xhigh|plan")
    sp2.add_argument("--model", default="")
    sp2.add_argument("--reviewer", default="")
    sp2.add_argument("--notes", default="")
    sp2.set_defaults(func=cmd_review_attest)

    # Autopilot
    sp = sub.add_parser("autopilot", help="One-command daily loop for cron (monitor + preflight + verify)")
    sub2 = sp.add_subparsers(dest="autopilot_cmd", required=True)

    sp2 = sub2.add_parser("tick", help="Run monitor tick + preflight + verify, emit concise output")
    sp2.add_argument("--change-id", required=True)
    sp2.add_argument("--force", action="store_true", help="Force monitor tick even if already ran today (UTC)")
    sp2.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    sp2.add_argument("--ok-on-pending", action="store_true", help="Exit 0 if only pending more monitor ticks (for cron)")
    sp2.set_defaults(func=cmd_autopilot_tick)

    # OpenClaw helper
    sp = sub.add_parser("openclaw", help="OpenClaw integration helpers")
    sub2 = sp.add_subparsers(dest="openclaw_cmd", required=True)

    sp2 = sub2.add_parser("cron-setup", help="Generate (or apply) an OpenClaw cron job for vibeship-optimizer autopilot")
    sp2.add_argument("--change-id", required=True)
    sp2.add_argument("--project-root", default="", help="Path to the target project (default: current directory)")
    sp2.add_argument("--name", default="", help="Cron job name")
    sp2.add_argument("--cron", default="0 7 * * *", help="Cron expression (5-field)")
    sp2.add_argument("--tz", default="UTC", help="IANA timezone")
    sp2.add_argument("--thinking", default="xhigh", help="OpenClaw thinking level for isolated job")
    sp2.add_argument("--model", default="", help="Optional model override")
    sp2.add_argument("--channel", default="last", help="Delivery channel (telegram/slack/etc or last)")
    sp2.add_argument("--to", default="", help="Delivery target (chat id, channel id, etc)")
    sp2.add_argument("--no-deliver", action="store_true", help="Disable delivery (internal only)")
    sp2.add_argument("--apply", action="store_true", help="Run 'openclaw cron add ...' now")
    sp2.set_defaults(func=cmd_openclaw_cron_setup)

    return p


def main() -> None:
    p = build_parser()
    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

