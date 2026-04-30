from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


def test_web_v2_plan_workspace_browser_flow() -> None:
    if shutil.which("node") is None:
        pytest.skip("node is required for the v2 Plan browser flow test")

    project_root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    playwright_candidates = [
        project_root / "node_modules" / ".bin" / "playwright",
        repo_root / "node_modules" / ".bin" / "playwright",
    ]
    playwright_bin = next((candidate for candidate in playwright_candidates if candidate.exists()), None)
    if playwright_bin is None:
        pytest.skip("run npm install from the repo root to enable Playwright browser tests")

    script_path = (
        project_root
        / "src"
        / "buildwealth_orchestrator"
        / "web-v2"
        / "tests"
        / "plan_workspace.spec.mjs"
    )
    assert script_path.exists(), f"missing browser test script: {script_path}"

    result = subprocess.run(
        [
            str(playwright_bin),
            "test",
            str(script_path),
            "--browser=chromium",
            "--reporter=line",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, (
        "v2 Plan browser flow failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
