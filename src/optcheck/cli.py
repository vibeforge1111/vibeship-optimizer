from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import DEFAULT_DIR, compare_snapshots, read_json, render_compare_markdown, snapshot, write_text, write_json
from .logbook import create_change, list_changes, load_change
from .monitor import load_monitor, start_monitor, tick_monitor
from .analyze import analyze_project
from .preflight import preflight


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

    cfg_path = opt_dir / "config.json"
    if not cfg_path.exists():
        # Minimal config: users edit commands they care about.
        write_json(
            cfg_path,
            {
                "version": 1,
                "size_paths": ["."],
                "timings": [
                    {"name": "tests", "cmd": "", "runs": 1, "timeout_s": 900},
                    {"name": "build", "cmd": "", "runs": 1, "timeout_s": 900},
                ],
                "http_probes": [],
            },
        )

    checker_path = root / "OPTIMIZATION_CHECKER.md"
    if not checker_path.exists():
        write_text(checker_path, TEMPLATE_CHECKER)

    print(f"Initialized: {cfg_path}")
    print(f"Initialized: {checker_path}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = Path.cwd()
    cfg_path = root / DEFAULT_DIR / "config.json"
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
    report = analyze_project(project_root=root, out_md=out)
    if out:
        print(json.dumps({"wrote": str(out)}, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    root = Path.cwd()
    out = Path(args.out) if args.out else None
    report = preflight(project_root=root, out_md=out)
    if out:
        print(json.dumps({"wrote": str(out), "worst_level": report.get("worst_level")}, indent=2))
    else:
        print(json.dumps(report, indent=2))
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
    sp.set_defaults(func=cmd_preflight)

    return p


def main() -> None:
    p = build_parser()
    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
