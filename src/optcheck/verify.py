from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import DEFAULT_DIR, git_info, iso_now, write_json, write_text
from .logbook import change_path, load_change
from .review import attestation_path


@dataclass
class CheckResult:
    ok: bool
    failures: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "failures": list(self.failures),
            "warnings": list(self.warnings),
        }


def _utc_date() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _append_verified_block(checker_path: Path, change_id: str, summary: str = "") -> None:
    existing = checker_path.read_text(encoding="utf-8") if checker_path.exists() else ""
    block = []
    block.append("")
    block.append(f"#### VERIFIED: {change_id}")
    block.append(f"- Date (UTC): `{_utc_date()}`")
    if summary.strip():
        block.append(f"- Summary: {summary.strip()}")
    block.append("")
    write_text(checker_path, existing.rstrip() + "\n" + "\n".join(block).rstrip() + "\n")


def verify_change(
    *,
    project_root: Path,
    change_id: str,
    config: Dict[str, Any],
    min_monitor_days: int = 3,
    require_clean_git: bool = False,
) -> CheckResult:
    failures: List[str] = []
    warnings: List[str] = []

    if not change_id:
        failures.append("missing change_id")
        return CheckResult(ok=False, failures=failures, warnings=warnings)

    ch_path = change_path(project_root, change_id)
    if not ch_path.exists():
        failures.append(f"change record not found: {ch_path}")
        return CheckResult(ok=False, failures=failures, warnings=warnings)

    ch = load_change(ch_path)

    # Git hygiene.
    g = git_info(project_root)
    if require_clean_git and bool(g.get("dirty")):
        failures.append("git working tree is dirty (require_clean_git=true)")
    elif bool(g.get("dirty")):
        warnings.append("git working tree is dirty")

    # Review enforcement.
    review_cfg = config.get("review") if isinstance(config, dict) else {}
    require_att = bool((review_cfg or {}).get("require_attestation", False))
    if require_att:
        ap = attestation_path(project_root, change_id)
        if not ap.exists():
            failures.append("review attestation missing (review.require_attestation=true)")
    else:
        ap = attestation_path(project_root, change_id)
        if not ap.exists():
            warnings.append("review attestation missing (recommended)")

    # Monitor evidence.
    min_days = max(0, int(min_monitor_days))
    updates = ch.get("verification_updates")
    if not isinstance(updates, list):
        updates = []

    if min_days > 0 and len(updates) < min_days:
        failures.append(f"insufficient monitor ticks: have {len(updates)} need {min_days}")

    # Snapshot evidence (weak but helpful).
    if not ch.get("snapshot_before"):
        warnings.append("snapshot_before not recorded in change record")
    if not ch.get("snapshot_after"):
        warnings.append("snapshot_after not recorded in change record")
    if not ch.get("commit"):
        warnings.append("commit sha not recorded in change record")

    ok = len(failures) == 0
    return CheckResult(ok=ok, failures=failures, warnings=warnings)


def apply_verified(
    *,
    project_root: Path,
    checker_path: Path,
    change_id: str,
    config: Dict[str, Any],
    min_monitor_days: int,
    require_clean_git: bool,
    summary: str = "",
) -> Dict[str, Any]:
    """Mark a change as verified if checks pass."""

    result = verify_change(
        project_root=project_root,
        change_id=change_id,
        config=config,
        min_monitor_days=min_monitor_days,
        require_clean_git=require_clean_git,
    )

    payload: Dict[str, Any] = {
        "schema": "optcheck.verify_apply.v1",
        "change_id": change_id,
        "ok": result.ok,
        "failures": result.failures,
        "warnings": result.warnings,
        "applied": False,
    }

    if not result.ok:
        return payload

    ch_path = change_path(project_root, change_id)
    ch = load_change(ch_path)
    if not isinstance(ch, dict):
        return payload

    ch["status"] = "verified"
    ch["verified_at"] = iso_now()
    ch["verified_summary"] = str(summary or "")[:2000]
    write_json(ch_path, ch)

    _append_verified_block(checker_path, change_id, summary=summary)

    payload["applied"] = True
    payload["change_path"] = str(ch_path)
    payload["checker_path"] = str(checker_path)
    return payload
