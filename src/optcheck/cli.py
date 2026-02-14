from __future__ import annotations

import argparse
from pathlib import Path

from .core import DEFAULT_DIR, SNAPSHOT_DIR, compare_snapshots, read_json, render_compare_markdown, snapshot, write_text, write_json


TEMPLATE_CHECKER = """# Optimization Checker

This file is a living validation playbook.

## Rules
- One optimization per commit (easy revert).
- Prefer flags/knobs. Make risky changes opt-in.
- Always capture **before/after** snapshots.
- Monitor for a few days before marking verified.

## Optimization log

### 2026-__-__
1) <commit> — <what changed>
- Hypothesis:
- Risk:
- Rollback:
- Validation (today):
- Validation (next 3 days):
- Outcome:
- Mark verified: [ ]

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

    return p


def main() -> None:
    p = build_parser()
    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
