from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .analyze import analyze_project
from .core import DEFAULT_DIR, SNAPSHOT_DIR, git_info, iso_now, load_config, read_json, render_compare_markdown, write_text


@dataclass
class Finding:
    level: str  # info|warn|fail
    code: str
    message: str
    hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


def _level_rank(level: str) -> int:
    order = {"info": 0, "warn": 1, "fail": 2}
    return order.get(str(level or "info").lower(), 0)


def _snapshots_exist(project_root: Path) -> bool:
    d = project_root / SNAPSHOT_DIR
    return d.exists() and any(d.glob("*.json"))


def _config_path(project_root: Path) -> Path:
    return project_root / DEFAULT_DIR / "config.json"


def preflight(
    *,
    project_root: Path,
    out_md: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run safe diligence checks.

    Preflight does NOT change code. It only:
    - inspects git status
    - checks optcheck config
    - runs read-only analyze report
    - emits actionable warnings
    """

    findings: List[Finding] = []

    # --- Git checks ---
    g = git_info(project_root)
    if not g.get("is_git"):
        findings.append(
            Finding(
                level="warn",
                code="GIT_NOT_FOUND",
                message="Not a git repo (or .git not found in parents).",
                hint="For safe rollback, initialize git and prefer one-commit-per-change.",
            )
        )
    else:
        if g.get("dirty"):
            findings.append(
                Finding(
                    level="warn",
                    code="GIT_DIRTY",
                    message=f"Working tree is dirty ({g.get('dirty_count')} changed files).",
                    hint="Commit or stash before snapshotting so before/after is attributable.",
                )
            )
        if not (g.get("commit") or "").strip():
            findings.append(
                Finding(
                    level="warn",
                    code="GIT_NO_COMMIT",
                    message="Could not resolve current commit sha.",
                    hint="Ensure git is installed and the repo has at least one commit.",
                )
            )

    # --- Config checks ---
    cfg_path = _config_path(project_root)
    if not cfg_path.exists():
        findings.append(
            Finding(
                level="fail",
                code="CONFIG_MISSING",
                message=".optcheck/config.json is missing.",
                hint="Run: optcheck init",
            )
        )
        cfg = {}
    else:
        cfg = load_config(cfg_path)

    timings = cfg.get("timings") or []
    if not timings:
        findings.append(
            Finding(
                level="warn",
                code="TIMINGS_EMPTY",
                message="No timings configured (no commands will be timed).",
                hint="Edit .optcheck/config.json and set timings[].cmd to your test/build commands.",
            )
        )
    else:
        empty = [t for t in timings if isinstance(t, dict) and not str(t.get("cmd") or "").strip()]
        if empty and len(empty) == len([t for t in timings if isinstance(t, dict)]):
            findings.append(
                Finding(
                    level="warn",
                    code="TIMINGS_NO_CMDS",
                    message="Timings entries exist but all cmds are empty.",
                    hint="Add at least one: tests/build/lint command you care about (e.g., pytest, npm test).",
                )
            )

    size_paths = cfg.get("size_paths") or []
    if not size_paths:
        findings.append(
            Finding(
                level="warn",
                code="SIZE_PATHS_EMPTY",
                message="No size_paths configured; snapshot won't capture disk footprint.",
                hint="Add paths like ['.', 'src', 'node_modules'] depending on project.",
            )
        )

    http_probes = cfg.get("http_probes") or []
    if not http_probes:
        findings.append(
            Finding(
                level="info",
                code="HTTP_PROBES_EMPTY",
                message="No http_probes configured.",
                hint="Optional: add a /health endpoint probe for services.",
            )
        )

    # --- Snapshot presence ---
    if not _snapshots_exist(project_root):
        findings.append(
            Finding(
                level="info",
                code="NO_SNAPSHOTS",
                message="No snapshots found yet.",
                hint="Run: optcheck snapshot --label before",
            )
        )

    # --- Analyze report (read-only) ---
    analysis = analyze_project(project_root=project_root, out_md=None)

    # Highlight obvious bloat dirs if present.
    dir_sizes = analysis.get("dir_sizes") or []
    for row in dir_sizes:
        if not isinstance(row, dict):
            continue
        p = str(row.get("path") or "")
        b = int(row.get("bytes") or 0)
        if p in ("node_modules", ".venv", "dist", "build") and b > 0:
            findings.append(
                Finding(
                    level="info",
                    code="BLOAT_DIR_PRESENT",
                    message=f"Directory present: {p} ({b} bytes).",
                    hint="Consider excluding from size_paths if it's not part of shipped artifact, or measure it separately.",
                )
            )

    # Summarize
    worst = "info"
    if findings:
        worst = max((f.level for f in findings), key=_level_rank)

    report: Dict[str, Any] = {
        "schema": "optcheck.preflight.v1",
        "generated_at": iso_now(),
        "project_root": str(project_root),
        "worst_level": worst,
        "git": g,
        "config_path": str(cfg_path),
        "findings": [f.to_dict() for f in sorted(findings, key=lambda x: _level_rank(x.level), reverse=True)],
        "analysis": analysis,
    }

    if out_md:
        write_text(out_md, render_preflight_markdown(report))

    return report


def render_preflight_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Optimization Preflight Report\n")
    lines.append(f"Generated: `{report.get('generated_at')}`\n")
    lines.append(f"Worst level: **{report.get('worst_level')}**\n")

    g = report.get("git") or {}
    lines.append("## Git\n")
    if g.get("is_git"):
        lines.append(f"- branch: `{g.get('branch')}`")
        lines.append(f"- describe: `{g.get('describe')}`")
        lines.append(f"- dirty: `{g.get('dirty')}` ({g.get('dirty_count')})\n")
    else:
        lines.append("- (not a git repo)\n")

    lines.append("## Findings\n")
    findings = report.get("findings") or []
    if not findings:
        lines.append("- No findings.\n")
    else:
        for f in findings:
            lines.append(f"- **{f.get('level','info').upper()}** `{f.get('code')}` - {f.get('message')}")
            if f.get("hint"):
                lines.append(f"  - hint: {f.get('hint')}")
        lines.append("")

    lines.append("## Analyze (high level)\n")
    analysis = report.get("analysis") or {}
    ds = analysis.get("dir_sizes") or []
    if ds:
        for row in ds[:10]:
            if isinstance(row, dict):
                lines.append(f"- `{row.get('path')}`: {row.get('bytes')} bytes")
        lines.append("")

    lines.append("---\n")
    lines.append("Raw JSON:\n")
    lines.append("```json")
    lines.append(json.dumps(report, indent=2, ensure_ascii=False))
    lines.append("```\n")
    return "\n".join(lines)
