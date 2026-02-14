from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import DEFAULT_DIR, compare_snapshots, read_json, render_compare_markdown, snapshot, write_text, write_json
from .configio import find_config_path, load_config_for_project, write_config
from .logbook import create_change, list_changes, load_change
from .monitor import load_monitor, start_monitor, tick_monitor
from .analyze import analyze_project
from .preflight import preflight
from .doctor import doctor
from .review import build_review_bundle, write_attestation
from .verify import apply_verified, verify_change
from .autopilot import autopilot_tick, render_autopilot_summary
from .openclaw_integration import CronSpec, apply_cron_add, build_cron_add_command


TEMPLATE_CHECKER = """# Optimization Checker

This file is a living validation playbook.

## Rules
- One optimization per commit (easy revert).
- Prefer flags/knobs. Make risky changes opt-in.
- Always capture **before/after** snapshots.
- Monitor for a few days before marking verified.

## Workflow

Recommended loop:

1) `optcheck init`
2) `optcheck change start --title "..."`
3) `optcheck snapshot --label before`
4) Make *one* optimization + commit
5) `optcheck snapshot --label after`
6) `optcheck compare --before ... --after ... --out reports/...`
7) Monitor for 1–7 days; update the change section with results.

## Optimization log

"""


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    opt_dir = root / DEFAULT_DIR
    opt_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = find_config_path(root)
    if not cfg_path.exists():
        # Minimal config: users edit commands they care about.
        cfg, _path = load_config_for_project(root)
        # Ensure strict defaults are written for new projects.
        cfg = {**cfg, **{"review": cfg.get("review"), "verification": cfg.get("verification")}}
        write_config(cfg_path, cfg)

    checker_path = root / "OPTIMIZATION_CHECKER.md"
    if not checker_path.exists():
        write_text(checker_path, TEMPLATE_CHECKER)

    print(f"Initialized: {cfg_path}")
    print(f"Initialized: {checker_path}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = Path.cwd()
    _cfg, cfg_path = load_config_for_project(root)
    out = snapshot(project_root=root, label=str(args.label or "snapshot"), config_path=cfg_path)
    print(str(out))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    before_path = Path(args.before)
    after_path = Path(args.after)
    diff_out = compare_snapshots(read_json(before_path), read_json(after_path))
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
    cmd_init(argparse.Namespace())

    root = Path.cwd()
    checker_path = root / "OPTIMIZATION_CHECKER.md"
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
    cmd_init(argparse.Namespace())

    cfg, _cfg_path = load_config_for_project(root)

    vcfg = cfg.get("verification") if isinstance(cfg, dict) else {}
    default_days = int((vcfg or {}).get("min_monitor_days", 3) or 3)
    min_days = default_days if int(args.min_monitor_days) < 0 else int(args.min_monitor_days)

    default_clean = bool((vcfg or {}).get("require_clean_git", False))
    require_clean = bool(args.require_clean_git) or default_clean

    if args.apply:
        payload = apply_verified(
            project_root=root,
            checker_path=root / "OPTIMIZATION_CHECKER.md",
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
    cmd_init(argparse.Namespace())
    path = start_monitor(
        project_root=root,
        change_id=str(args.change_id),
        baseline_snapshot=str(args.baseline) if args.baseline else None,
        days=int(args.days),
    )
    print(json.dumps({"monitor": str(path)}, indent=2))
    return 0


def cmd_monitor_tick(args: argparse.Namespace) -> int:
    root = Path.cwd()
    cmd_init(argparse.Namespace())
    checker_path = root / "OPTIMIZATION_CHECKER.md"
    res = tick_monitor(project_root=root, checker_path=checker_path, force=bool(args.force))
    print(json.dumps(res, indent=2))
    return 0


def cmd_monitor_status(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_monitor(root)
    if not state:
        print(json.dumps({"active": False}, indent=2))
        return 0
    print(json.dumps({"active": True, **state.to_dict()}, indent=2))
    return 0


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
    out = Path(args.out) if args.out else (root / ".optcheck" / "review_bundles" / f"{args.change_id}.md")
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
    cmd_init(argparse.Namespace())

    payload = autopilot_tick(project_root=root, change_id=str(args.change_id), force=bool(args.force))

    if args.format == "text":
        print(render_autopilot_summary(payload))
    else:
        print(json.dumps(payload, indent=2))

    # exit non-zero if verify failed
    ok = bool(((payload.get("verify") or {}).get("ok")))
    return 0 if ok else 2


def cmd_openclaw_cron_setup(args: argparse.Namespace) -> int:
    """Generate (and optionally apply) an OpenClaw cron job for optcheck autopilot."""
    root = Path.cwd()

    project_root = str((Path(args.project_root).resolve() if args.project_root else root.resolve()))
    change_id = str(args.change_id)
    name = str(args.name or f"optcheck autopilot tick ({change_id})")

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
    p = argparse.ArgumentParser(prog="optcheck", description="Optimization checker: snapshot + compare")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Create .optcheck config and OPTIMIZATION_CHECKER.md template")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("snapshot", help="Capture a snapshot (sizes, timings, probes)")
    sp.add_argument("--label", default="", help="label for snapshot")
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

    sp2 = sub2.add_parser("start", help="Create a change record and append it to OPTIMIZATION_CHECKER.md")
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
    sp2.add_argument("--apply", action="store_true", help="Actually mark verified + append to OPTIMIZATION_CHECKER.md")
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
    sp = sub.add_parser("doctor", help="Repair/normalize optcheck scaffolding (.optcheck/config.json only)")
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
    sp2.set_defaults(func=cmd_autopilot_tick)

    # OpenClaw helper
    sp = sub.add_parser("openclaw", help="OpenClaw integration helpers")
    sub2 = sp.add_subparsers(dest="openclaw_cmd", required=True)

    sp2 = sub2.add_parser("cron-setup", help="Generate (or apply) an OpenClaw cron job for optcheck autopilot")
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
