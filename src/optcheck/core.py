from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DIR = Path(".optcheck")
SNAPSHOT_DIR = DEFAULT_DIR / "snapshots"


def now_ts() -> float:
    return time.time()


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(path))


def which_git_root(cwd: Path) -> Optional[Path]:
    cur = cwd
    for _ in range(25):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def run_cmd(cmd: str, cwd: Path, timeout_s: Optional[int] = None) -> Tuple[int, str, str, float]:
    """Run a shell command with robust decoding.

    On Windows, subprocess defaults can raise UnicodeDecodeError when output
    contains non-cp1252 bytes. We force UTF-8 with replacement.
    """
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    dt = time.perf_counter() - t0
    return proc.returncode, proc.stdout, proc.stderr, dt


def dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except Exception:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            p = Path(root) / f
            try:
                total += p.stat().st_size
            except Exception:
                pass
    return int(total)


def git_info(project_root: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"is_git": False}
    root = which_git_root(project_root)
    if not root:
        return info

    info["is_git"] = True
    info["git_root"] = str(root)

    def _try(cmd: str) -> str:
        try:
            rc, out, _err, _dt = run_cmd(cmd, cwd=root, timeout_s=15)
            if rc == 0:
                return (out or "").strip()
        except Exception:
            pass
        return ""

    info["branch"] = _try("git rev-parse --abbrev-ref HEAD")
    info["commit"] = _try("git rev-parse HEAD")
    info["describe"] = _try("git describe --always --dirty")
    status = _try("git status --porcelain=v1")
    info["dirty"] = bool(status.strip())
    info["dirty_count"] = len([ln for ln in status.splitlines() if ln.strip()])
    info["diff_stat"] = _try("git diff --stat")
    return info


def system_info() -> Dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split("\n")[0],
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
    }


@dataclass
class CommandTiming:
    name: str
    cmd: str
    runs: int
    timeout_s: int


def time_command(ct: CommandTiming, cwd: Path) -> Dict[str, Any]:
    dts: List[float] = []
    last_rc = 0
    last_err = ""

    for _ in range(max(1, int(ct.runs))):
        try:
            rc, _out, err, dt = run_cmd(ct.cmd, cwd=cwd, timeout_s=int(ct.timeout_s))
            dts.append(float(dt))
            last_rc = int(rc)
            last_err = (err or "").strip()[:400]
        except subprocess.TimeoutExpired:
            last_rc = 124
            last_err = "timeout"
            dts.append(float(ct.timeout_s))
        except Exception as e:
            last_rc = 1
            last_err = str(e)[:400]

    dts_sorted = sorted(dts)
    mean = sum(dts_sorted) / max(1, len(dts_sorted))
    p95 = dts_sorted[int(0.95 * (len(dts_sorted) - 1))] if dts_sorted else 0.0

    return {
        "name": ct.name,
        "cmd": ct.cmd,
        "runs": int(ct.runs),
        "timeout_s": int(ct.timeout_s),
        "last_rc": int(last_rc),
        "last_err": last_err,
        "mean_s": round(float(mean), 4),
        "p95_s": round(float(p95), 4),
        "all_s": [round(float(x), 4) for x in dts_sorted],
    }


def default_config() -> Dict[str, Any]:
    return {
        "version": 1,
        "commands": {
            "test": "",
            "build": "",
            "lint": "",
        },
        "timings": [
            {"name": "tests", "cmd": "", "runs": 1, "timeout_s": 900},
        ],
        "size_paths": ["."],
        "http_probes": [],
        "review": {
            "recommended": True,
            "require_attestation": False,
            "recommended_tools": {
                "codex": {"reasoning_mode": "xhigh"},
                "claude": {"reasoning_mode": "plan"},
            },
        },
    }


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load config from JSON or YAML.

    This keeps core snapshot functionality working even when callers pass a
    YAML config path.

    Prefer using `optcheck.configio.load_config_for_project()` when possible.
    """
    if not config_path.exists():
        return default_config()

    suffix = config_path.suffix.lower()
    if suffix in (".yml", ".yaml"):
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(read_text(config_path))
            if isinstance(data, dict):
                return {**default_config(), **data}
        except Exception:
            return default_config()
        return default_config()

    cfg = read_json(config_path)
    if not isinstance(cfg, dict):
        return default_config()
    return {**default_config(), **cfg}


def snapshot(
    *,
    project_root: Path,
    label: str,
    config_path: Path,
) -> Path:
    # config_path is explicit for now; higher-level code should resolve YAML vs JSON.
    cfg = load_config(config_path)

    timings_cfg = cfg.get("timings") or []
    timings: List[CommandTiming] = []
    for row in timings_cfg:
        if not isinstance(row, dict):
            continue
        cmd = str(row.get("cmd") or "").strip()
        if not cmd:
            continue
        timings.append(
            CommandTiming(
                name=str(row.get("name") or "cmd"),
                cmd=cmd,
                runs=int(row.get("runs") or 1),
                timeout_s=int(row.get("timeout_s") or 900),
            )
        )

    size_paths = [str(p) for p in (cfg.get("size_paths") or []) if str(p).strip()]
    http_probes = [dict(p) for p in (cfg.get("http_probes") or []) if isinstance(p, dict)]

    # build snapshot
    snap: Dict[str, Any] = {
        "schema": "optcheck.snapshot.v1",
        "generated_at": iso_now(),
        "label": label,
        "system": system_info(),
        "git": git_info(project_root),
        "sizes": {},
        "timings": [],
        "http": [],
    }

    # sizes
    for rel in size_paths:
        p = (project_root / rel).resolve()
        snap["sizes"][rel] = {
            "path": str(p),
            "bytes": dir_size_bytes(p),
        }

    # timings
    for ct in timings:
        snap["timings"].append(time_command(ct, cwd=project_root))

    # probes
    for pr in http_probes:
        url = str(pr.get("url") or "").strip()
        if not url:
            continue
        expect = str(pr.get("expect_contains") or "").strip()
        timeout_s = int(pr.get("timeout_s") or 5)
        res = {
            "url": url,
            "timeout_s": timeout_s,
            "ok": False,
            "status": None,
            "error": "",
        }
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                body = resp.read(3000).decode("utf-8", errors="ignore")
                res["status"] = int(getattr(resp, "status", 200) or 200)
                if expect:
                    res["ok"] = expect in body
                else:
                    res["ok"] = res["status"] >= 200 and res["status"] < 400
        except Exception as e:
            res["error"] = str(e)[:300]
        snap["http"].append(res)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    out = SNAPSHOT_DIR / f"{ts}_{_safe_token(label)}.json"
    write_json(out, snap)
    return out


def _safe_token(text: str) -> str:
    clean = "".join(ch for ch in str(text or "") if ch.isalnum() or ch in ("-", "_"))
    return (clean or "snapshot")[:40]


def compare_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "schema": "optcheck.compare.v1",
        "before": {
            "label": before.get("label"),
            "generated_at": before.get("generated_at"),
            "git": (before.get("git") or {}),
        },
        "after": {
            "label": after.get("label"),
            "generated_at": after.get("generated_at"),
            "git": (after.get("git") or {}),
        },
        "deltas": {
            "sizes": {},
            "timings": [],
            "http": [],
        },
    }

    b_sizes = (before.get("sizes") or {}) if isinstance(before.get("sizes"), dict) else {}
    a_sizes = (after.get("sizes") or {}) if isinstance(after.get("sizes"), dict) else {}
    for key in sorted(set(b_sizes.keys()) | set(a_sizes.keys())):
        b = int(((b_sizes.get(key) or {}).get("bytes") or 0))
        a = int(((a_sizes.get(key) or {}).get("bytes") or 0))
        out["deltas"]["sizes"][key] = {
            "before_bytes": b,
            "after_bytes": a,
            "delta_bytes": a - b,
        }

    def _timings_map(snap: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        rows = snap.get("timings") or []
        m: Dict[str, Dict[str, Any]] = {}
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and r.get("name"):
                    m[str(r.get("name"))] = r
        return m

    bt = _timings_map(before)
    at = _timings_map(after)
    for name in sorted(set(bt.keys()) | set(at.keys())):
        b = bt.get(name) or {}
        a = at.get(name) or {}
        out["deltas"]["timings"].append(
            {
                "name": name,
                "before_mean_s": b.get("mean_s"),
                "after_mean_s": a.get("mean_s"),
                "delta_mean_s": _float(a.get("mean_s")) - _float(b.get("mean_s")),
                "before_p95_s": b.get("p95_s"),
                "after_p95_s": a.get("p95_s"),
                "delta_p95_s": _float(a.get("p95_s")) - _float(b.get("p95_s")),
                "before_last_rc": b.get("last_rc"),
                "after_last_rc": a.get("last_rc"),
            }
        )

    # HTTP probes: align by url
    def _http_map(snap: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        rows = snap.get("http") or []
        m: Dict[str, Dict[str, Any]] = {}
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and r.get("url"):
                    m[str(r.get("url"))] = r
        return m

    bh = _http_map(before)
    ah = _http_map(after)
    for url in sorted(set(bh.keys()) | set(ah.keys())):
        b = bh.get(url) or {}
        a = ah.get(url) or {}
        out["deltas"]["http"].append(
            {
                "url": url,
                "before_ok": bool(b.get("ok")),
                "after_ok": bool(a.get("ok")),
                "before_status": b.get("status"),
                "after_status": a.get("status"),
                "after_error": a.get("error"),
            }
        )

    return out


def _float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def render_compare_markdown(diff: Dict[str, Any]) -> str:
    b = diff.get("before") or {}
    a = diff.get("after") or {}
    d = diff.get("deltas") or {}

    lines: List[str] = []
    lines.append("# Optimization Compare Report\n")
    lines.append(f"Before: `{b.get('label')}` @ {b.get('generated_at')}\n")
    lines.append(f"After: `{a.get('label')}` @ {a.get('generated_at')}\n")

    bg = b.get("git") or {}
    ag = a.get("git") or {}
    if bg.get("is_git") or ag.get("is_git"):
        lines.append("## Git\n")
        lines.append(f"- before: `{bg.get('describe') or bg.get('commit')}` (dirty={bg.get('dirty')})")
        lines.append(f"- after: `{ag.get('describe') or ag.get('commit')}` (dirty={ag.get('dirty')})\n")

    lines.append("## Size deltas\n")
    sizes = (d.get("sizes") or {}) if isinstance(d.get("sizes"), dict) else {}
    if not sizes:
        lines.append("- (none)\n")
    else:
        for key, row in sizes.items():
            delta = int((row or {}).get("delta_bytes") or 0)
            lines.append(f"- `{key}`: {int(row.get('before_bytes',0))} -> {int(row.get('after_bytes',0))} bytes (delta {delta:+d})")
        lines.append("")

    lines.append("## Timing deltas\n")
    timings = d.get("timings") or []
    if not timings:
        lines.append("- (none)\n")
    else:
        for row in timings:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            lines.append(
                f"- **{name}**: mean {row.get('before_mean_s')}s -> {row.get('after_mean_s')}s (delta {row.get('delta_mean_s'):+.4f}s), "
                f"p95 {row.get('before_p95_s')}s -> {row.get('after_p95_s')}s (delta {row.get('delta_p95_s'):+.4f}s) "
                f"rc {row.get('before_last_rc')} -> {row.get('after_last_rc')}"
            )
        lines.append("")

    lines.append("## HTTP probes\n")
    http = d.get("http") or []
    if not http:
        lines.append("- (none)\n")
    else:
        for row in http:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- `{row.get('url')}`: ok {row.get('before_ok')} -> {row.get('after_ok')} "
                f"status {row.get('before_status')} -> {row.get('after_status')} err={row.get('after_error') or ''}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
