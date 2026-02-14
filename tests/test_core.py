import json
import subprocess
import sys
from pathlib import Path

import pytest

from vibeship_optimizer.core import read_json, resolve_state_dir
from vibeship_optimizer.autopilot import autopilot_tick


def test_read_json_strict(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError):
        read_json(p)

    p2 = tmp_path / "arr.json"
    p2.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        read_json(p2)

    p3 = tmp_path / "ok.json"
    p3.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert read_json(p3) == {"a": 1}


def test_resolve_state_dir_prefers_existing_state(tmp_path: Path) -> None:
    # Both dirs exist; the one with a config should win.
    legacy = tmp_path / ".vibeship_optimizer"
    canon = tmp_path / ".vibeship-optimizer"
    legacy.mkdir()
    canon.mkdir()

    (canon / "config.yml").write_text("version: 1\n", encoding="utf-8")
    assert resolve_state_dir(tmp_path).as_posix() == ".vibeship-optimizer"


def test_autopilot_tick_no_monitor_does_not_raise(tmp_path: Path) -> None:
    # No monitor started; autopilot should return JSON describing the skip.
    payload = autopilot_tick(project_root=tmp_path, change_id="chg-does-not-exist", force=False)
    assert payload["schema"] == "vibeship_optimizer.autopilot_tick.v1"
    assert payload["monitor"]["skipped"] is True


def test_cli_compare_invalid_json_exits_nonzero(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("{bad json", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "vibeship_optimizer", "compare", "--before", str(a), "--after", str(b)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2

