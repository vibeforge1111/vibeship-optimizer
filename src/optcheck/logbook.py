from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import DEFAULT_DIR, iso_now, write_json, write_text


CHANGES_DIR = DEFAULT_DIR / "changes"


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
    return (project_root / CHANGES_DIR / f"{change_id}.json").resolve()


def list_changes(project_root: Path) -> List[Path]:
    d = (project_root / CHANGES_DIR)
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
        "schema": "optcheck.change.v1",
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
