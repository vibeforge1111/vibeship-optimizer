from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    tags: Set[str]
    intents: Set[str]


def _q(qid: str, text: str, *, tags: Sequence[str] = (), intents: Sequence[str] = ()) -> Question:
    return Question(id=qid, text=text.strip(), tags=set(tags), intents=set(intents))


def detect_languages(project_root: Path) -> Set[str]:
    """Best-effort language/runtime detection from common files."""
    langs: Set[str] = set()

    def ex(path: str) -> bool:
        return (project_root / path).exists()

    if ex("pyproject.toml") or ex("requirements.txt") or ex("poetry.lock"):
        langs.add("python")
    if ex("package.json"):
        langs.add("node")
    if ex("go.mod"):
        langs.add("go")
    if ex("Cargo.toml"):
        langs.add("rust")
    if ex("pom.xml") or ex("build.gradle") or ex("build.gradle.kts"):
        langs.add("jvm")
    if ex("Gemfile"):
        langs.add("ruby")
    if ex("composer.json"):
        langs.add("php")
    if ex("Dockerfile") or ex("docker-compose.yml") or ex("docker-compose.yaml"):
        langs.add("docker")

    # heuristic: if repo has .csproj/.sln
    if any(project_root.glob("*.sln")) or any(project_root.glob("**/*.csproj")):
        langs.add("dotnet")

    return langs


def default_intents() -> List[str]:
    return [
        "latency",
        "throughput",
        "startup_time",
        "memory",
        "disk",
        "build_time",
        "test_time",
        "reliability",
        "developer_experience",
        "cost",
    ]


def all_questions() -> List[Question]:
    """Curated optimization questions.

    NOTE: This list is based on common optimization dimensions and operational
    best practices. It's intentionally evidence-oriented (questions that can be
    answered by measurement or code inspection).
    """

    qs: List[Question] = []

    # --- Meta / safety
    qs.append(_q(
        "safety.one_change",
        "Are we doing one optimization per commit, with a clear rollback path (git revert)?",
        tags=["general", "safety"],
        intents=["reliability"],
    ))
    qs.append(_q(
        "safety.flags",
        "Can the change be gated behind a flag/knob so it can be turned off without reverting?",
        tags=["general", "safety"],
        intents=["reliability"],
    ))
    qs.append(_q(
        "safety.measure_before_after",
        "Do we have before/after snapshots for runtime, size, and health probes?",
        tags=["general", "measurement"],
        intents=["reliability", "cost"],
    ))

    # --- Performance: latency/throughput
    qs.append(_q(
        "perf.hot_path",
        "What is the top hot-path (p95/p99) and do we have a profiler/trace proving it?",
        tags=["general", "perf"],
        intents=["latency", "throughput"],
    ))
    qs.append(_q(
        "perf.io",
        "Are we doing unnecessary disk/network I/O on the hot path (full-file reads, chatty calls, unbounded logs)?",
        tags=["general", "perf", "io"],
        intents=["latency", "throughput", "disk"],
    ))
    qs.append(_q(
        "perf.allocations",
        "Are we creating large intermediate objects/strings that can be streamed/chunked?",
        tags=["general", "perf", "memory"],
        intents=["latency", "memory"],
    ))
    qs.append(_q(
        "perf.concurrency",
        "Do we have lock contention or single-thread bottlenecks, and can we bound critical sections?",
        tags=["general", "perf", "concurrency"],
        intents=["throughput", "latency"],
    ))

    # --- Startup
    qs.append(_q(
        "startup.imports",
        "What is contributing to startup time (imports/init, migrations, model loads, cache warmup)?",
        tags=["general", "startup"],
        intents=["startup_time"],
    ))
    qs.append(_q(
        "startup.lazy",
        "Can we lazy-load non-critical subsystems so first response is fast?",
        tags=["general", "startup"],
        intents=["startup_time", "latency"],
    ))

    # --- Memory/disk
    qs.append(_q(
        "mem.leaks",
        "Do we have memory growth over hours/days (leaks, caches without TTL/LRU, unbounded queues)?",
        tags=["general", "memory"],
        intents=["memory", "reliability", "cost"],
    ))
    qs.append(_q(
        "disk.logs",
        "Are logs/JSONL/trace outputs bounded (rotation, sampling, caps) and are caps append-only?",
        tags=["general", "disk", "observability"],
        intents=["disk", "cost", "reliability"],
    ))

    # --- Build/test
    qs.append(_q(
        "build.incremental",
        "Are builds/tests incremental and cached (compiler cache, test selection, dependency caching)?",
        tags=["general", "build"],
        intents=["build_time", "test_time", "developer_experience"],
    ))
    qs.append(_q(
        "build.deps",
        "Do we have heavy or duplicate dependencies that can be removed or replaced with lighter ones?",
        tags=["general", "build", "deps"],
        intents=["build_time", "disk", "cost"],
    ))

    # --- Reliability
    qs.append(_q(
        "reliability.timeouts",
        "Are external calls protected with timeouts, retries (bounded), and circuit breakers?",
        tags=["general", "reliability"],
        intents=["reliability", "latency"],
    ))
    qs.append(_q(
        "reliability.fallbacks",
        "Do we have safe fallbacks when optional subsystems fail (cache miss, telemetry failure, slow dependency)?",
        tags=["general", "reliability"],
        intents=["reliability"],
    ))

    # --- Python-specific
    qs.append(_q(
        "py.import_time",
        "Python: have we measured import time and eliminated expensive import side-effects?",
        tags=["python"],
        intents=["startup_time"],
    ))
    qs.append(_q(
        "py.logging",
        "Python: are debug logs guarded and structured logging sampling/batching used where high volume?",
        tags=["python"],
        intents=["latency", "disk"],
    ))

    # --- Node-specific
    qs.append(_q(
        "node.bundle",
        "Node: are we shipping minimal bundles (tree-shaking, code splitting) and avoiding huge transitive deps?",
        tags=["node"],
        intents=["startup_time", "disk", "latency"],
    ))

    # --- Go-specific
    qs.append(_q(
        "go.pprof",
        "Go: do we have pprof evidence for CPU/heap and have we fixed the top allocators?",
        tags=["go"],
        intents=["latency", "throughput", "memory"],
    ))

    # --- Docker/deploy
    qs.append(_q(
        "docker.image_size",
        "Docker: can the image be smaller (multi-stage build, slim base, prune build deps)?",
        tags=["docker"],
        intents=["disk", "startup_time", "cost"],
    ))

    return qs


def select_questions(*, languages: Set[str], intents: Sequence[str]) -> List[Question]:
    intents_set = {str(i).strip().lower() for i in intents if str(i).strip()}
    if not intents_set:
        intents_set = set(default_intents())

    langs = {str(l).strip().lower() for l in (languages or set()) if str(l).strip()}

    out: List[Question] = []
    for q in all_questions():
        # Always include general questions.
        is_general = "general" in q.tags
        is_lang = bool(q.tags & langs)
        is_intent = not q.intents or bool(q.intents & intents_set)

        if is_intent and (is_general or is_lang):
            out.append(q)

    # Stable order by id.
    out.sort(key=lambda x: x.id)
    return out


def render_questions_markdown(*, questions: List[Question]) -> str:
    lines: List[str] = []
    lines.append("## Optimization questions (guided)\n")
    lines.append("Answer these with measurements or direct code evidence. Avoid guesses.\n")
    for q in questions:
        lines.append(f"- [ ] **{q.id}**: {q.text}")
    lines.append("")
    return "\n".join(lines)


def questions_from_report(report: Dict[str, Any]) -> str:
    rows = report.get("questions") or []
    questions: List[Question] = []
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            questions.append(
                Question(
                    id=str(r.get("id") or ""),
                    text=str(r.get("text") or ""),
                    tags=set(r.get("tags") or []),
                    intents=set(r.get("intents") or []),
                )
            )
    questions = [q for q in questions if q.id and q.text]
    questions.sort(key=lambda q: q.id)
    return render_questions_markdown(questions=questions)
