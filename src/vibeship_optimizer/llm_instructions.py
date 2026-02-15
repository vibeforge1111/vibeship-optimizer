from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analyze import analyze_project
from .configio import load_config_for_project
from .core import git_info, iso_now
from .preflight import preflight


def _config_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    commands = cfg.get("commands") if isinstance(cfg.get("commands"), dict) else {}
    timings = cfg.get("timings") if isinstance(cfg.get("timings"), list) else []
    size_paths = cfg.get("size_paths") if isinstance(cfg.get("size_paths"), list) else []
    http_probes = cfg.get("http_probes") if isinstance(cfg.get("http_probes"), list) else []

    def _timing_row(r: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(r, dict):
            return None
        return {
            "name": r.get("name"),
            "runs": r.get("runs"),
            "timeout_s": r.get("timeout_s"),
            # Commands may contain secrets; include only a small prefix.
            "cmd_prefix": (str(r.get("cmd") or "")[:120] if str(r.get("cmd") or "").strip() else ""),
        }

    return {
        "commands": {
            "test_prefix": str(commands.get("test") or "")[:120],
            "build_prefix": str(commands.get("build") or "")[:120],
            "lint_prefix": str(commands.get("lint") or "")[:120],
        },
        "timings": [x for x in (_timing_row(r) for r in timings[:10]) if x],
        "size_paths": [str(x) for x in size_paths[:20]],
        "http_probe_count": len(http_probes),
    }


def operator_prompt(*, project_root: Path) -> str:
    # Keep it short and tool-oriented; user will paste this into any LLM.
    return "\n".join(
        [
            "# vibeship-optimizer: LLM Operator Prompt",
            "",
            "You are an assistant helping run vibeship-optimizer safely in a local project.",
            "You do NOT edit code directly. You only propose exact CLI commands for the user to run.",
            "",
            "Rules:",
            "- One optimization per commit. Always keep rollback simple (`git revert <sha>`).",
            "- Prefer reversible changes (flags/knobs).",
            "- Never claim an improvement without before/after snapshots + compare output.",
            "- If you need information, ask for specific command outputs (don't guess).",
            "",
            "Working directory:",
            f"- `{project_root}`",
            "",
            "Allowed commands (examples):",
            "- `python -m vibeship_optimizer onboard`",
            "- `python -m vibeship_optimizer change start --title \"...\"`",
            "- `python -m vibeship_optimizer snapshot --label before --change-id <chg-id> --as before`",
            "- `python -m vibeship_optimizer snapshot --label after  --change-id <chg-id> --as after`",
            "- `python -m vibeship_optimizer compare --before <before.json> --after <after.json> --out reports/compare.md`",
            "- `python -m vibeship_optimizer preflight --change-id <chg-id>`",
            "- `python -m vibeship_optimizer monitor start --change-id <chg-id> --days 3`",
            "- `python -m vibeship_optimizer autopilot tick --change-id <chg-id> --force --format json --ok-on-pending`",
            "",
            "Output format you should use:",
            "1) A short plan (3-7 bullets).",
            "2) A code block with the exact commands to run (copy/paste).",
            "3) A list of what outputs to paste back (filenames or JSON fields).",
            "",
        ]
    )


def build_llm_bundle(*, project_root: Path, change_id: str = "") -> Dict[str, Any]:
    cfg, cfg_path = load_config_for_project(project_root)
    analysis = analyze_project(project_root=project_root, out_md=None, config=cfg)
    pf = preflight(project_root=project_root, out_md=None, change_id=change_id)

    return {
        "schema": "vibeship_optimizer.llm_bundle.v1",
        "generated_at": iso_now(),
        "project_root": str(project_root),
        "change_id": str(change_id or ""),
        "git": git_info(project_root),
        "config_path": str(cfg_path),
        "config_summary": _config_summary(cfg),
        "preflight": pf,
        "analyze": analysis,
        "prompt": operator_prompt(project_root=project_root),
        "note": "Review for secrets before pasting into a third-party LLM. This bundle intentionally avoids dumping full config values.",
    }


def render_llm_bundle_markdown(bundle: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# vibeship-optimizer LLM Bundle\n")
    lines.append(f"Generated: `{bundle.get('generated_at')}`\n")
    lines.append(f"Project: `{bundle.get('project_root')}`\n")
    if bundle.get("change_id"):
        lines.append(f"Change: `{bundle.get('change_id')}`\n")

    lines.append("## Operator prompt\n")
    lines.append("```text")
    lines.append(str(bundle.get("prompt") or "").rstrip())
    lines.append("```\n")

    lines.append("## Context (JSON)\n")
    lines.append("```json")
    lines.append(json.dumps({k: bundle.get(k) for k in ("git", "config_path", "config_summary", "preflight", "analyze")}, indent=2, ensure_ascii=False))
    lines.append("```\n")

    lines.append(str(bundle.get("note") or "") + "\n")
    return "\n".join(lines)
