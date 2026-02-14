from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .core import compare_snapshots, iso_now, read_json, render_compare_markdown, resolve_state_dir, snapshot, write_json, write_text
from .configio import load_config_for_project
from .logbook import change_path, load_change


def _utc_date() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _latest_snapshot_path(project_root: Path) -> Optional[Path]:
    d = project_root / (resolve_state_dir(project_root) / "snapshots")
    if not d.exists():
        return None
    snaps = sorted(d.glob("*.json"), key=lambda p: p.name)
    return snaps[-1] if snaps else None


def _append_verification_update(
    *,
    checker_path: Path,
    change_id: str,
    day_index: int,
    report_path: Path,
    summary: str,
) -> None:
    existing = checker_path.read_text(encoding="utf-8") if checker_path.exists() else ""
    block = []
    block.append("")
    block.append(f"#### Verification update: {change_id} Day {day_index}")
    block.append(f"- Date (UTC): `{_utc_date()}`")
    block.append(f"- Report: `{report_path.as_posix()}`")
    if summary.strip():
        block.append(f"- Summary: {summary.strip()}")
    block.append("")
    write_text(checker_path, existing.rstrip() + "\n" + "\n".join(block).rstrip() + "\n")


@dataclass
class MonitorState:
    change_id: str
    baseline_snapshot: str
    days: int
    started_at: str
    last_run_utc_date: str
    runs_completed: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MonitorState":
        return MonitorState(
            change_id=str(d.get("change_id") or ""),
            baseline_snapshot=str(d.get("baseline_snapshot") or ""),
            days=int(d.get("days") or 3),
            started_at=str(d.get("started_at") or iso_now()),
            last_run_utc_date=str(d.get("last_run_utc_date") or ""),
            runs_completed=int(d.get("runs_completed") or 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "vibeship_optimizer.monitor.v1",
            "change_id": self.change_id,
            "baseline_snapshot": self.baseline_snapshot,
            "days": int(self.days),
            "started_at": self.started_at,
            "last_run_utc_date": self.last_run_utc_date,
            "runs_completed": int(self.runs_completed),
        }


def load_monitor(project_root: Path) -> Optional[MonitorState]:
    path = project_root / (resolve_state_dir(project_root) / "monitor.json")
    if not path.exists():
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        return None
    state = MonitorState.from_dict(data)
    if not state.change_id or not state.baseline_snapshot:
        return None
    return state


def save_monitor(project_root: Path, state: MonitorState) -> Path:
    path = project_root / (resolve_state_dir(project_root) / "monitor.json")
    write_json(path, state.to_dict())
    return path


def start_monitor(
    *,
    project_root: Path,
    change_id: str,
    baseline_snapshot: Optional[str],
    days: int,
) -> Path:
    if not change_id:
        raise ValueError("change_id is required")

    baseline = baseline_snapshot
    if not baseline:
        latest = _latest_snapshot_path(project_root)
        if not latest:
            raise ValueError("No snapshots found. Run: vibeship-optimizer snapshot --label after")
        baseline = str(latest)

    state = MonitorState(
        change_id=str(change_id),
        baseline_snapshot=str(baseline),
        days=max(1, int(days)),
        started_at=iso_now(),
        last_run_utc_date="",
        runs_completed=0,
    )
    return save_monitor(project_root, state)


def tick_monitor(
    *,
    project_root: Path,
    checker_path: Path,
    force: bool = False,
) -> Dict[str, Any]:
    state = load_monitor(project_root)
    if not state:
        raise ValueError("No active monitor. Run: vibeship-optimizer monitor start ...")

    today = _utc_date()
    if not force and state.last_run_utc_date == today:
        return {
            "skipped": True,
            "reason": "already_ran_today",
            "today_utc": today,
            "runs_completed": state.runs_completed,
            "days": state.days,
        }

    # Take a monitoring snapshot.
    day_index = state.runs_completed
    _cfg, cfg_path = load_config_for_project(project_root)
    snap_path = snapshot(project_root=project_root, label=f"day{day_index}", config_path=cfg_path)

    bpath = Path(state.baseline_snapshot)
    if not bpath.is_absolute():
        bpath = project_root / bpath

    apath = snap_path
    if not apath.is_absolute():
        apath = project_root / apath

    before = read_json(bpath)
    after = read_json(apath)
    diff = compare_snapshots(before, after)
    md = render_compare_markdown(diff)

    reports_dir = resolve_state_dir(project_root) / "reports"
    (project_root / reports_dir).mkdir(parents=True, exist_ok=True)
    report_path = (project_root / reports_dir / f"{today}_day{day_index}_{state.change_id}.md").resolve()
    write_text(report_path, md)

    # Append an update to the checker doc (append-only, safe).
    summary = ""
    try:
        size_delta = (diff.get("deltas") or {}).get("sizes") or {}
        if isinstance(size_delta, dict) and size_delta:
            # Pick the main '.' if present.
            main = size_delta.get(".") or next(iter(size_delta.values()))
            if isinstance(main, dict):
                summary = f"sizes delta={int(main.get('delta_bytes') or 0):+d} bytes"
    except Exception:
        pass

    _append_verification_update(
        checker_path=checker_path,
        change_id=state.change_id,
        day_index=day_index,
        report_path=report_path,
        summary=summary,
    )

    # Update state.
    state.last_run_utc_date = today
    state.runs_completed += 1
    save_monitor(project_root, state)

    # Also update the change JSON with a pointer to the last report.
    try:
        ch_path = change_path(project_root, state.change_id)
        ch = load_change(ch_path)
        if isinstance(ch, dict) and ch.get("change_id") == state.change_id:
            history = ch.get("verification_updates")
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "ts": iso_now(),
                    "utc_date": today,
                    "day": day_index,
                    "snapshot": str(snap_path),
                    "report": str(report_path),
                }
            )
            ch["verification_updates"] = history[-30:]
            write_json(ch_path, ch)
    except Exception:
        pass

    return {
        "skipped": False,
        "today_utc": today,
        "day": day_index,
        "snapshot": str(snap_path),
        "report": str(report_path),
        "runs_completed": state.runs_completed,
        "days": state.days,
    }
