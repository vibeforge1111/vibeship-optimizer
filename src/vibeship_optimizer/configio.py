from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .core import DEFAULT_DIR, default_config, read_text


CONFIG_CANDIDATES = [
    Path("vibeship_optimizer.yml"),
    Path("vibeship_optimizer.yaml"),
    DEFAULT_DIR / "config.yml",
    DEFAULT_DIR / "config.yaml",
    DEFAULT_DIR / "config.json",
]


def _has_yaml() -> bool:
    try:
        import yaml  # type: ignore

        return True
    except Exception:
        return False


def find_config_path(project_root: Path) -> Path:
    for rel in CONFIG_CANDIDATES:
        p = (project_root / rel)
        if p.exists():
            return p
    # default to YAML in new projects
    return project_root / (DEFAULT_DIR / "config.yml")


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config_for_project(project_root: Path) -> Tuple[Dict[str, Any], Path]:
    path = find_config_path(project_root)

    if not path.exists():
        return default_config(), path

    suffix = path.suffix.lower()
    if suffix in (".yml", ".yaml"):
        if not _has_yaml():
            # YAML requested but not available; fall back to defaults.
            return default_config(), path
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(read_text(path))
            if isinstance(data, dict):
                return _deep_merge(default_config(), data), path
        except Exception:
            return default_config(), path
        return default_config(), path

    # JSON
    try:
        data = json.loads(read_text(path))
        if isinstance(data, dict):
            return _deep_merge(default_config(), data), path
    except Exception:
        pass
    return default_config(), path


def write_config(path: Path, cfg: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix in (".yml", ".yaml"):
        import yaml  # type: ignore

        text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
        return

    # JSON
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
