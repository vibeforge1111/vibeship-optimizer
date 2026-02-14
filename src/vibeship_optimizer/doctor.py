from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import DEFAULT_DIR, default_config
from .configio import load_config_for_project, write_config, find_config_path


@dataclass
class DoctorAction:
    code: str
    changed: bool
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "changed": bool(self.changed), "message": self.message}


def _config_path(project_root: Path) -> Path:
    return find_config_path(project_root)


def _merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def doctor(
    *,
    project_root: Path,
    apply: bool,
) -> Dict[str, Any]:
    """Repair/normalize vibeship-optimizer scaffolding.

    Safety:
    - only touches .vibeship_optimizer/config.json (and creates .vibeship_optimizer/ dir)
    - never edits project source code
    """

    actions: List[DoctorAction] = []

    cfg_path = _config_path(project_root)
    if not cfg_path.exists():
        actions.append(DoctorAction(code="CONFIG_CREATE", changed=apply, message=f"Create config at {cfg_path}"))
        if apply:
            write_config(cfg_path, default_config())

    cfg, cfg_path2 = load_config_for_project(project_root)
    cfg_path = cfg_path2

    changed = False

    # Ensure size_paths has something meaningful.
    size_paths = cfg.get("size_paths")
    if not isinstance(size_paths, list) or not any(str(x).strip() for x in size_paths):
        cfg["size_paths"] = ["."]
        changed = True
        actions.append(DoctorAction(code="SIZE_PATHS_SET", changed=apply, message="Set size_paths to ['.']"))

    # Ensure timings list exists.
    timings = cfg.get("timings")
    if not isinstance(timings, list):
        cfg["timings"] = [{"name": "tests", "cmd": "", "runs": 1, "timeout_s": 900}]
        changed = True
        actions.append(DoctorAction(code="TIMINGS_CREATE", changed=apply, message="Create timings list"))

    # Provide gentle placeholders when all cmd fields are empty.
    timings2 = cfg.get("timings") or []
    if isinstance(timings2, list) and timings2:
        any_cmd = False
        for row in timings2:
            if isinstance(row, dict) and str(row.get("cmd") or "").strip():
                any_cmd = True
        if not any_cmd:
            # Don't guess the user's stack; provide common options in the first entry.
            for row in timings2:
                if isinstance(row, dict):
                    row.setdefault("name", "tests")
                    row["cmd"] = row.get("cmd") or ""
                    row.setdefault("runs", 1)
                    row.setdefault("timeout_s", 900)
                    break
            changed = True
            actions.append(
                DoctorAction(
                    code="TIMINGS_PLACEHOLDER",
                    changed=apply,
                    message="Timings cmds are empty; left placeholders for you to fill (pytest / npm test / go test).",
                )
            )

    # Ensure http_probes list exists.
    probes = cfg.get("http_probes")
    if not isinstance(probes, list):
        cfg["http_probes"] = []
        changed = True
        actions.append(DoctorAction(code="HTTP_PROBES_CREATE", changed=apply, message="Create http_probes list"))

    if changed and apply:
        write_config(cfg_path, cfg)

    return {
        "schema": "vibeship_optimizer.doctor.v1",
        "apply": bool(apply),
        "config_path": str(cfg_path),
        "actions": [a.to_dict() for a in actions],
        "note": "Doctor only edits the vibeship-optimizer config file (YAML/JSON). It does not edit your code.",
    }
