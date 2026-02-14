from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import iso_now, resolve_state_dir, write_json, write_text


def _slug(text: str, max_len: int = 48) -> str:
    raw = re.sub(r"\s+", " ", str(text or "").strip().lower())
    raw = re.sub(r"[^a-z0-9\- _]", "", raw)
    raw = raw.replace(" ", "-")
    raw = re.sub(r"-+", "-", raw).strip("-")
    return (raw or "change")[:max_len]


def new_change_id(title: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return f"chg-{ts}-{_slug(title, 36)}"


def change_path(project_root: Path, change_id: str) -> Path:
    changes_dir = resolve_state_dir(project_root) / "changes"
    return (project_root / changes_dir / f"{change_id}.json").resolve()


def list_changes(project_root: Path) -> List[Path]:
    d = (project_root / (resolve_state_dir(project_root) / "changes"))
    if not d.exists():
        return []
    return sorted(d.glob("chg-*.json"), key=lambda p: p.name)


def load_change(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def update_change(
    *,
    project_root: Path,
    change_id: str,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """Update a change record in-place.

    Intended for attaching evidence (commit sha, snapshot_before/after paths)
    from CLI commands in an automation-friendly way (OpenClaw cron, etc).
    """
    if not change_id:
        raise ValueError("change_id is required")
    if not isinstance(updates, dict) or not updates:
        raise ValueError("updates is required")

    p = change_path(project_root, change_id)
    if not p.exists():
        raise FileNotFoundError(f"change record not found: {p}")

    ch = load_change(p)
    if not isinstance(ch, dict) or ch.get("change_id") != change_id:
        raise ValueError(f"invalid change record: {p}")

    for k, v in updates.items():
        # Keep it simple: the change record is user-owned JSON, but we only
        # write JSON-serializable primitives/structures here.
        ch[k] = v

    write_json(p, ch)
    return ch


def append_change_to_checker(*, checker_path: Path, change: Dict[str, Any]) -> None:
    # Append a section. Users can move/edit freely afterwards.
    title = str(change.get("title") or "")
    cid = str(change.get("change_id") or "")
    started = str(change.get("started_at") or "")

    block = []
    block.append(f"\n### {cid} — {title}\n")
    block.append(f"- Status: **{change.get('status','planned').upper()}**")
    block.append(f"- Started: `{started}`")
    block.append(f"- Commit: `{change.get('commit','')}`")
    block.append(f"- Baseline snapshot: `{change.get('snapshot_before','')}`")
    block.append(f"- After snapshot: `{change.get('snapshot_after','')}`\n")

    def _field(name: str) -> None:
        val = str(change.get(name) or "").strip()
        block.append(f"**{name.replace('_',' ').title()}:**")
        block.append(val if val else "- ")
        block.append("")

    _field("hypothesis")
    _field("risk")
    _field("rollback")
    _field("validation_today")
    _field("validation_next_days")

    block.append("**Verification log:**")
    block.append("- Day 0: ")
    block.append("- Day 1: ")
    block.append("- Day 2: ")
    block.append("- Day 3: ")
    block.append("")
    block.append("- Mark verified: [ ]")
    block.append("")

    existing = checker_path.read_text(encoding="utf-8") if checker_path.exists() else ""
    write_text(checker_path, existing.rstrip() + "\n" + "\n".join(block).rstrip() + "\n")


def create_change(
    *,
    project_root: Path,
    checker_path: Path,
    title: str,
    hypothesis: str = "",
    risk: str = "",
    rollback: str = "git revert <sha>",
    validation_today: str = "",
    validation_next_days: str = "",
) -> Dict[str, Any]:
    cid = new_change_id(title)
    change: Dict[str, Any] = {
        "schema": "vibeship_optimizer.change.v1",
        "change_id": cid,
        "title": str(title).strip(),
        "status": "planned",
        "started_at": iso_now(),
        "commit": "",
        "snapshot_before": "",
        "snapshot_after": "",
        "hypothesis": hypothesis.strip(),
        "risk": risk.strip(),
        "rollback": rollback.strip(),
        "validation_today": validation_today.strip(),
        "validation_next_days": validation_next_days.strip(),
    }

    out_path = change_path(project_root, cid)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, change)

    append_change_to_checker(checker_path=checker_path, change=change)
    return {**change, "path": str(out_path)}
