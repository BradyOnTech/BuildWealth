from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


def _node_supports_default_type_flag(node_bin: str) -> bool:
    result = subprocess.run(
        [node_bin, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    help_text = f"{result.stdout}\n{result.stderr}"
    return "--experimental-default-type" in help_text


def _resolve_node_binary() -> str | None:
    candidates: list[str] = []
    preferred = shutil.which("node")
    if preferred:
        candidates.append(preferred)

    nvm_nodes = sorted(
        Path.home().glob(".nvm/versions/node/*/bin/node"),
        reverse=True,
    )
    for candidate in nvm_nodes:
        candidates.append(str(candidate))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _node_supports_default_type_flag(candidate):
            return candidate
    return None


def test_recommendations_template_smoke() -> None:
    node_bin = _resolve_node_binary()
    if node_bin is None:
        pytest.skip("no node binary with --experimental-default-type support for frontend smoke checks")

    project_root = Path(__file__).resolve().parents[1]
    test_path = project_root / "src" / "buildwealth_orchestrator" / "web" / "tests" / "recommendations_template.test.mjs"
    result = subprocess.run(
        [node_bin, "--experimental-default-type=module", "--test", str(test_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "Frontend recommendations template smoke test failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
