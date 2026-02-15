from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .questionnaire import detect_languages


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        # Use utf-8-sig to tolerate BOM (common on Windows editors / some PowerShell defaults).
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _node_package_manager(project_root: Path) -> str:
    # Prefer the lockfile that actually exists.
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _node_has_real_test_script(project_root: Path) -> bool:
    pkg = _read_json_file(project_root / "package.json")
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    test = str((scripts or {}).get("test") or "").strip()
    if not test:
        return False
    # Filter the npm-init placeholder.
    if "no test specified" in test.lower() and "exit 1" in test.lower():
        return False
    return True


def suggest_timing_cmd(*, project_root: Path, languages: Sequence[str]) -> str:
    langs = {str(x).strip().lower() for x in (languages or []) if str(x).strip()}
    if not langs:
        langs = detect_languages(project_root)

    if "node" in langs:
        if _node_has_real_test_script(project_root):
            pm = _node_package_manager(project_root)
            return f"{pm} test"
        return ""

    if "go" in langs:
        return "go test ./..."

    if "rust" in langs:
        return "cargo test"

    if "dotnet" in langs:
        return "dotnet test"

    if "python" in langs:
        # Only suggest pytest if the repo appears to already use it.
        # (Otherwise we'd be guiding users into a guaranteed failure.)
        text = ""
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="ignore")
        if "pytest" in text.lower() or (project_root / "pytest.ini").exists():
            return "python -m pytest -q"
        return ""

    return ""


def _ensure_timings_list(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    timings = cfg.get("timings")
    if isinstance(timings, list):
        out = [t for t in timings if isinstance(t, dict)]
        if out:
            return out
    row = {"name": "tests", "cmd": "", "runs": 1, "timeout_s": 900}
    cfg["timings"] = [row]
    return [row]


def apply_onboarding(
    *,
    project_root: Path,
    config: Dict[str, Any],
    timing_cmd: str,
    force: bool,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Apply small, safe onboarding improvements to a config dict.

    Returns (updated_config, changes[]).
    """
    changes: List[Dict[str, Any]] = []

    cfg = dict(config or {})

    # Project languages: only fill if absent/empty.
    languages = detect_languages(project_root)
    project_cfg = cfg.get("project") if isinstance(cfg.get("project"), dict) else {}
    existing_langs = project_cfg.get("languages") if isinstance(project_cfg.get("languages"), list) else []
    if not existing_langs and languages:
        project_cfg = dict(project_cfg)
        project_cfg["languages"] = sorted(languages)
        cfg["project"] = project_cfg
        changes.append({"code": "PROJECT_LANGUAGES_SET", "value": sorted(languages)})

    timings = _ensure_timings_list(cfg)
    suggested = timing_cmd.strip()
    if suggested:
        # Fill the first timing entry cmd if empty (or force overwrite).
        cur = str(timings[0].get("cmd") or "").strip()
        if force or not cur:
            timings[0]["cmd"] = suggested
            changes.append({"code": "TIMINGS_CMD_SET", "value": suggested})

        # Also set commands.test if present and empty.
        cmds = cfg.get("commands") if isinstance(cfg.get("commands"), dict) else {}
        if cmds:
            cur_test = str(cmds.get("test") or "").strip()
            if force or not cur_test:
                cmds = dict(cmds)
                cmds["test"] = suggested
                cfg["commands"] = cmds
                changes.append({"code": "COMMANDS_TEST_SET", "value": suggested})

    return cfg, changes


def onboarding_next_steps() -> List[str]:
    return [
        'python -m vibeship_optimizer change start --title "Reduce memory usage"',
        "python -m vibeship_optimizer snapshot --label before --change-id <chg-id> --as before",
        "# make ONE change + commit",
        "python -m vibeship_optimizer snapshot --label after --change-id <chg-id> --as after",
        "python -m vibeship_optimizer compare --before <before.json> --after <after.json> --out reports/compare.md",
        "python -m vibeship_optimizer monitor start --change-id <chg-id> --days 3",
        "python -m vibeship_optimizer autopilot tick --change-id <chg-id> --force --format json --ok-on-pending",
    ]
