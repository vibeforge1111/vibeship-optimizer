from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .core import DEFAULT_DIR, dir_size_bytes, iso_now, write_text
from .questionnaire import detect_languages, questions_from_report, select_questions


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".vibeship_optimizer",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}


def _iter_files(root: Path, *, ex_dirs: Sequence[str], ex_globs: Sequence[str]) -> Iterable[Path]:
    ex_dirs_set = {d.lower() for d in ex_dirs}
    for dirpath, dirnames, filenames in os.walk(root):
        # prune
        dirnames[:] = [d for d in dirnames if d.lower() not in ex_dirs_set]
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = p.relative_to(root)
            srel = rel.as_posix()
            if any(Path(srel).match(g) for g in ex_globs):
                continue
            yield p


def largest_files(
    *,
    root: Path,
    top_n: int = 20,
    ex_dirs: Sequence[str] = tuple(DEFAULT_EXCLUDE_DIRS),
    ex_globs: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    rows: List[Tuple[int, str]] = []
    for p in _iter_files(root, ex_dirs=ex_dirs, ex_globs=ex_globs):
        try:
            sz = p.stat().st_size
        except Exception:
            continue
        rows.append((int(sz), p.relative_to(root).as_posix()))

    rows.sort(key=lambda t: t[0], reverse=True)
    out = []
    for sz, rel in rows[: max(0, int(top_n))]:
        out.append({"path": rel, "bytes": int(sz)})
    return out


def directory_sizes(
    *,
    root: Path,
    rel_dirs: Sequence[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel in rel_dirs:
        p = (root / rel).resolve()
        out.append({"path": rel, "bytes": dir_size_bytes(p)})
    out.sort(key=lambda r: int(r.get("bytes") or 0), reverse=True)
    return out


_IMPORT_RE = re.compile(r"^\s*(from|import)\s+([a-zA-Z0-9_\.]+)")


def _collect_import_roots(py_files: Sequence[Path], root: Path) -> set[str]:
    imports: set[str] = set()
    for p in py_files:
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = _IMPORT_RE.match(line)
                if not m:
                    continue
                mod = m.group(2).split(".")[0]
                if mod:
                    imports.add(mod)
        except Exception:
            continue
    return imports


def _guess_python_deps(project_root: Path) -> List[str]:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return []
    text = pyproject.read_text(encoding="utf-8", errors="ignore")
    # ultra-minimal TOML extraction: look for dependencies = [ ... ]
    deps: List[str] = []
    in_deps = False
    for line in text.splitlines():
        ln = line.strip()
        if ln.startswith("dependencies") and "[" in ln:
            in_deps = True
        if in_deps:
            if "]" in ln:
                in_deps = False
            m = re.search(r"\"([^\"]+)\"", ln)
            if m:
                pkg = m.group(1)
                pkg = pkg.split(";")[0].strip()
                pkg = re.split(r"[ <>=\[]", pkg)[0].strip()
                if pkg:
                    deps.append(pkg)
    # normalize
    norm = []
    for d in deps:
        base = d.replace("-", "_")
        norm.append(base)
    return sorted(set(norm))


def python_unused_dep_hints(
    *,
    project_root: Path,
    top_n_files: int = 2000,
    ignore_deps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Naive unused-dependency hints.

    Heuristic:
      - parse pyproject dependencies list
      - scan .py files for top-level import roots
      - if dep root not seen as import, mark as "maybe_unused"

    This is intentionally conservative: it only *suggests* possible cleanup.
    """
    deps = _guess_python_deps(project_root)
    py_files = [
        p for p in _iter_files(project_root, ex_dirs=tuple(DEFAULT_EXCLUDE_DIRS), ex_globs=())
        if p.suffix.lower() == ".py"
    ][: max(0, int(top_n_files))]

    imports = _collect_import_roots(py_files, project_root)

    ignore = {str(x).strip().lower() for x in (ignore_deps or []) if str(x).strip()}

    maybe_unused = []
    for d in deps:
        # some deps have different import roots; we don't try to map them here.
        if str(d).strip().lower() in ignore:
            continue
        root = d.split("_")[0]
        if root and root not in imports and d not in imports:
            maybe_unused.append(d)

    return {
        "dependency_count": len(deps),
        "scanned_py_files": len(py_files),
        "import_roots_count": len(imports),
        "maybe_unused": maybe_unused,
        "note": "Heuristic only. False positives expected (optional deps, dynamic imports, plugins).",
    }


def render_analyze_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Optimization Analysis Report\n")
    lines.append(f"Generated: `{report.get('generated_at')}`\n")

    # Directory sizes
    lines.append("## Key directory sizes\n")
    for row in report.get("dir_sizes", []) or []:
        lines.append(f"- `{row.get('path')}`: {row.get('bytes')} bytes")
    lines.append("")

    # Largest files
    lines.append("## Largest files (top)\n")
    for row in report.get("largest_files", []) or []:
        lines.append(f"- `{row.get('path')}`: {row.get('bytes')} bytes")
    lines.append("")

    # Guided questions
    try:
        lines.append(questions_from_report(report))
    except Exception:
        pass

    py = report.get("python_unused_dep_hints")
    if isinstance(py, dict) and py:
        lines.append("## Python: unused dependency hints (heuristic)\n")
        lines.append(f"- dependencies: {py.get('dependency_count')}")
        lines.append(f"- scanned_py_files: {py.get('scanned_py_files')}")
        lines.append(f"- maybe_unused: {len(py.get('maybe_unused') or [])}")
        for d in (py.get("maybe_unused") or [])[:50]:
            lines.append(f"  - {d}")
        lines.append("")

    lines.append("---\n")
    lines.append("Raw JSON:\n")
    lines.append("```json")
    lines.append(json.dumps(report, indent=2, ensure_ascii=False))
    lines.append("```\n")
    return "\n".join(lines)


def analyze_project(
    *,
    project_root: Path,
    out_md: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Keep it fast + safe.
    candidates = [
        ".",
        "src",
        "lib",
        "app",
        "packages",
        "services",
        "docs",
        "tests",
        "scripts",
        "node_modules",
        ".venv",
        "dist",
        "build",
    ]
    rel_dirs = [d for d in candidates if (project_root / d).exists()]

    cfg = config if isinstance(config, dict) else {}
    project_cfg = cfg.get("project") if isinstance(cfg, dict) else {}

    languages = set(project_cfg.get("languages") or []) if isinstance(project_cfg, dict) else set()
    if not languages:
        languages = detect_languages(project_root)

    intents = list(project_cfg.get("intents") or []) if isinstance(project_cfg, dict) else []

    report: Dict[str, Any] = {
        "schema": "vibeship_optimizer.analyze.v1",
        "generated_at": iso_now(),
        "project_root": str(project_root),
        "languages_detected": sorted({str(x) for x in languages}),
        "intents": intents,
        "dir_sizes": directory_sizes(root=project_root, rel_dirs=rel_dirs),
        "largest_files": largest_files(root=project_root, top_n=25),
        "questions": [
            {
                "id": q.id,
                "text": q.text,
                "tags": sorted(list(q.tags)),
                "intents": sorted(list(q.intents)),
            }
            for q in select_questions(languages=languages, intents=intents)
        ],
    }

    if (project_root / "pyproject.toml").exists():
        ignore = []
        if isinstance(project_cfg, dict):
            ignore = list(project_cfg.get("python_ignore_deps") or [])
        report["python_unused_dep_hints"] = python_unused_dep_hints(project_root=project_root, ignore_deps=ignore)

    if out_md:
        write_text(out_md, render_analyze_markdown(report))

    return report
