from __future__ import annotations

import json
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# We avoid shell-based execution for cron setup; argv is safer on Windows.


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


def resolve_openclaw_exe() -> Optional[str]:
    # Windows often installs openclaw as a .cmd and a .ps1 shim.
    for cand in ("openclaw.cmd", "openclaw", "openclaw.ps1"):
        hit = shutil.which(cand)
        if hit:
            return hit
    return None


def openclaw_on_path() -> bool:
    return resolve_openclaw_exe() is not None


def build_cron_add_args(spec: CronSpec) -> list[str]:
    """Return argv for `openclaw cron add ...`.

    Using argv avoids Windows shell quoting pitfalls.
    """
    exe = resolve_openclaw_exe() or "openclaw"

    msg = (
        "Run vibeship-optimizer autopilot tick quietly (only alert on real problems). "
        f"Steps: (1) cd {spec.project_root}; "
        f"(2) python -m vibeship_optimizer autopilot tick --change-id {spec.change_id} --force --format json --ok-on-pending. "
        "If verify.ok==true: output NO_REPLY. "
        "If verify.failures contains only 'insufficient monitor ticks' (pending days): output NO_REPLY. "
        "Otherwise: output a concise summary + point to .vibeship_optimizer/ or .vibeship-optimizer/ reports/."
    )

    parts: list[str] = [
        exe,
        "cron",
        "add",
        "--name",
        str(spec.name),
        "--cron",
        str(spec.cron),
        "--tz",
        str(spec.tz),
        "--session",
        "isolated",
        "--thinking",
        str(spec.thinking),
        "--message",
        msg,
    ]

    if spec.model:
        parts.extend(["--model", str(spec.model)])

    if spec.announce:
        parts.append("--announce")
        if spec.channel:
            parts.extend(["--channel", str(spec.channel)])
        if spec.to:
            parts.extend(["--to", str(spec.to)])
    else:
        parts.append("--no-deliver")

    return parts


def build_cron_add_command(spec: CronSpec) -> str:
    """Return a shell-escaped command string for copy/paste.

    Note: this is best-effort; apply() uses argv for reliability.
    """
    parts = build_cron_add_args(spec)
    return " ".join(shlex.quote(str(p)) for p in parts)


def apply_cron_add(*, spec: CronSpec, cwd: Path) -> Dict[str, Any]:
    if not openclaw_on_path():
        return {
            "ok": False,
            "error": "openclaw CLI not found on PATH",
            "command": build_cron_add_command(spec),
        }

    argv = build_cron_add_args(spec)
    try:
        import subprocess
        import time

        t0 = time.perf_counter()
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        dt = time.perf_counter() - t0
        return {
            "ok": proc.returncode == 0,
            "rc": int(proc.returncode),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "elapsed_s": round(float(dt), 3),
            "command": build_cron_add_command(spec),
            "argv": argv,
        }
    except Exception as e:
        return {
            "ok": False,
            "rc": 1,
            "error": str(e),
            "command": build_cron_add_command(spec),
            "argv": argv,
        }
