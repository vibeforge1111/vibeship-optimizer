from __future__ import annotations

import json
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .core import run_cmd


@dataclass
class CronSpec:
    name: str
    cron: str
    tz: str
    project_root: str
    change_id: str
    thinking: str = "xhigh"
    model: str = ""
    announce: bool = True
    channel: str = "last"
    to: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cron": self.cron,
            "tz": self.tz,
            "project_root": self.project_root,
            "change_id": self.change_id,
            "thinking": self.thinking,
            "model": self.model,
            "announce": self.announce,
            "channel": self.channel,
            "to": self.to,
        }


def openclaw_on_path() -> bool:
    return shutil.which("openclaw") is not None


def build_cron_add_command(spec: CronSpec) -> str:
    # Use the documented CLI surface.
    # Note: we avoid leaking env/config; this is pure command generation.
    msg = (
        f"Run optcheck autopilot tick in {spec.project_root} for change {spec.change_id}. "
        f"Steps: (1) cd {spec.project_root}; "
        f"(2) python -m optcheck autopilot tick --change-id {spec.change_id} --format text; "
        f"If verify fails, summarize + point to .optcheck/reports/."
    )

    parts = [
        "openclaw",
        "cron",
        "add",
        "--name",
        spec.name,
        "--cron",
        spec.cron,
        "--tz",
        spec.tz,
        "--session",
        "isolated",
        "--thinking",
        spec.thinking,
        "--message",
        msg,
    ]

    if spec.model:
        parts.extend(["--model", spec.model])

    if spec.announce:
        parts.append("--announce")
        if spec.channel:
            parts.extend(["--channel", spec.channel])
        if spec.to:
            parts.extend(["--to", spec.to])
    else:
        parts.append("--no-deliver")

    # Quote for shells.
    return " ".join(shlex.quote(str(p)) for p in parts)


def apply_cron_add(*, spec: CronSpec, cwd: Path) -> Dict[str, Any]:
    if not openclaw_on_path():
        return {
            "ok": False,
            "error": "openclaw CLI not found on PATH",
            "command": build_cron_add_command(spec),
        }

    cmd = build_cron_add_command(spec)
    rc, out, err, dt = run_cmd(cmd, cwd=cwd, timeout_s=30)
    return {
        "ok": rc == 0,
        "rc": rc,
        "stdout": (out or "").strip(),
        "stderr": (err or "").strip(),
        "elapsed_s": round(float(dt), 3),
        "command": cmd,
    }
