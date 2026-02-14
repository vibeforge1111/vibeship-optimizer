from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .configio import load_config_for_project
from .monitor import tick_monitor
from .preflight import preflight
from .verify import verify_change


def autopilot_tick(*, project_root: Path, change_id: str, force: bool = False) -> Dict[str, Any]:
    """Run the daily automation loop in one call.

    Order:
      1) monitor tick
      2) preflight for change_id
      3) verify change (dry-run)

    This is designed for OpenClaw cron jobs: one command, one JSON output.
    """

    cfg, _cfg_path = load_config_for_project(project_root)
    checker_path = project_root / "VIBESHIP_OPTIMIZER.md"

    monitor_res = tick_monitor(project_root=project_root, checker_path=checker_path, force=force)

    preflight_report = preflight(project_root=project_root, out_md=None, change_id=change_id)

    vcfg = cfg.get("verification") if isinstance(cfg, dict) else {}
    min_days = int((vcfg or {}).get("min_monitor_days", 3) or 3)
    require_clean = bool((vcfg or {}).get("require_clean_git", False))

    verify_res = verify_change(
        project_root=project_root,
        change_id=change_id,
        config=cfg,
        min_monitor_days=min_days,
        require_clean_git=require_clean,
    )

    return {
        "schema": "vibeship_optimizer.autopilot_tick.v1",
        "change_id": change_id,
        "monitor": monitor_res,
        "preflight": {
            "worst_level": preflight_report.get("worst_level"),
            "finding_count": len(preflight_report.get("findings") or []),
            "findings": (preflight_report.get("findings") or [])[:12],
        },
        "verify": verify_res.to_dict(),
    }


def render_autopilot_summary(payload: Dict[str, Any]) -> str:
    change_id = payload.get("change_id")
    mon = payload.get("monitor") or {}
    pf = payload.get("preflight") or {}
    vr = payload.get("verify") or {}

    lines = []
    lines.append(f"vibeship-optimizer autopilot tick: {change_id}")
    if mon.get("skipped"):
        lines.append(f"- monitor: skipped ({mon.get('reason')})")
    else:
        lines.append(f"- monitor: day={mon.get('day')} report={mon.get('report')}")

    lines.append(f"- preflight: worst={pf.get('worst_level')} findings={pf.get('finding_count')}")

    ok = bool(vr.get("ok"))
    lines.append(f"- verify: ok={ok} failures={len(vr.get('failures') or [])} warnings={len(vr.get('warnings') or [])}")

    if vr.get("failures"):
        lines.append("Failures:")
        for f in (vr.get("failures") or [])[:10]:
            lines.append(f"- {f}")

    return "\n".join(lines) + "\n"
