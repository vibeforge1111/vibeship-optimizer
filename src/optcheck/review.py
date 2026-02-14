from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .core import DEFAULT_DIR, git_info, iso_now, run_cmd, write_json, write_text
from .logbook import change_path, load_change


ATTEST_DIR = DEFAULT_DIR / "attestations"
BUNDLE_DIR = DEFAULT_DIR / "review_bundles"


@dataclass
class ReviewAttestation:
    change_id: str
    reviewer: str
    model: str
    reasoning_mode: str
    tool: str  # codex|claude|other
    created_at: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "optcheck.review_attestation.v1",
            "change_id": self.change_id,
            "reviewer": self.reviewer,
            "model": self.model,
            "reasoning_mode": self.reasoning_mode,
            "tool": self.tool,
            "created_at": self.created_at,
            "notes": self.notes,
        }


def attestation_path(project_root: Path, change_id: str) -> Path:
    return (project_root / ATTEST_DIR / f"review_{change_id}.json").resolve()


def load_attestation(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def attestation_mode_ok(*, config: Dict[str, Any], attestation: Dict[str, Any]) -> bool:
    """Check attestation matches allowed reasoning modes for the tool.

    Config keys:
      review.enforce_recommended_modes: bool
      review.allowed_modes: {codex:[...], claude:[...]}  # lowercase
    """
    review_cfg = config.get("review") if isinstance(config, dict) else {}
    if not bool((review_cfg or {}).get("enforce_recommended_modes", False)):
        return True

    tool = str(attestation.get("tool") or "").strip().lower()
    mode = str(attestation.get("reasoning_mode") or "").strip().lower()
    allowed = ((review_cfg or {}).get("allowed_modes") or {})
    if not isinstance(allowed, dict):
        return True

    allowed_list = allowed.get(tool)
    if not isinstance(allowed_list, list) or not allowed_list:
        return True

    return mode in {str(x).strip().lower() for x in allowed_list if str(x).strip()}


def write_attestation(
    *,
    project_root: Path,
    change_id: str,
    reviewer: str,
    model: str,
    reasoning_mode: str,
    tool: str,
    notes: str = "",
) -> Path:
    att = ReviewAttestation(
        change_id=str(change_id),
        reviewer=str(reviewer or "unknown"),
        model=str(model or "unknown"),
        reasoning_mode=str(reasoning_mode or "default"),
        tool=str(tool or "other"),
        created_at=iso_now(),
        notes=str(notes or "")[:2000],
    )
    out = attestation_path(project_root, change_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, att.to_dict())

    # Also attach to the change JSON (if present).
    try:
        ch_path = change_path(project_root, change_id)
        ch = load_change(ch_path)
        if isinstance(ch, dict) and ch.get("change_id") == change_id:
            ch["review_attestation"] = str(out)
            write_json(ch_path, ch)
    except Exception:
        pass

    return out


def _truncate(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[truncated {len(text) - max_chars} chars]"


def build_review_bundle(
    *,
    project_root: Path,
    change_id: str,
    out_path: Path,
    max_diff_chars: int = 120_000,
) -> Path:
    """Generate a review bundle to reduce hallucinations.

    The bundle includes *ground truth* from the repo:
    - git info
    - change record
    - git diff (working tree) + diffstat

    It's meant to be pasted into an LLM for optimization review.
    """

    g = git_info(project_root)

    ch = {}
    try:
        ch = load_change(change_path(project_root, change_id))
    except Exception:
        ch = {}

    # Git diff against HEAD (working tree). If users prefer reviewing a commit,
    # they can run this after committing and use git show manually.
    rc, diff, err, _dt = run_cmd("git diff", cwd=project_root, timeout_s=30)
    rc2, diffstat, err2, _dt2 = run_cmd("git diff --stat", cwd=project_root, timeout_s=30)

    diff_text = diff if rc == 0 else f"(git diff failed rc={rc})\n{err}"
    diffstat_text = diffstat if rc2 == 0 else f"(git diff --stat failed rc={rc2})\n{err2}"

    lines = []
    lines.append("# Optimization Review Bundle\n")
    lines.append(f"Generated: `{iso_now()}`\n")
    lines.append(f"Change: `{change_id}`\n")

    lines.append("## Anti-hallucination rules\n")
    lines.append("- Only make claims that are supported by the evidence below.")
    lines.append("- When recommending code changes, cite: file path + function/line region.")
    lines.append("- If unsure, ask for a command output instead of guessing.")
    lines.append("- Prefer reversible/flagged changes. One commit per optimization.")
    lines.append("")

    lines.append("## Git context\n")
    lines.append("```json")
    lines.append(json.dumps(g, indent=2, ensure_ascii=False))
    lines.append("```\n")

    lines.append("## Change record\n")
    lines.append("```json")
    lines.append(json.dumps(ch, indent=2, ensure_ascii=False))
    lines.append("```\n")

    lines.append("## git diff --stat\n")
    lines.append("```")
    lines.append(_truncate(diffstat_text, 20_000))
    lines.append("```\n")

    lines.append("## git diff\n")
    lines.append("```diff")
    lines.append(_truncate(diff_text, max_diff_chars))
    lines.append("```\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(out_path, "\n".join(lines))

    # Save under .optcheck by default if desired.
    try:
        default_out = (project_root / BUNDLE_DIR / f"{_safe_file_token(change_id)}_{int(time.time())}.md").resolve()
        if default_out != out_path:
            default_out.parent.mkdir(parents=True, exist_ok=True)
            write_text(default_out, "\n".join(lines))
    except Exception:
        pass

    return out_path


def _safe_file_token(text: str) -> str:
    keep = []
    for ch in str(text or ""):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
    return ("".join(keep) or "bundle")[:60]
