from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_default_runtime_scaffolding_is_buildwealth_native() -> None:
    checked_paths = [
        "README.md",
        "Makefile",
        "infra/docker-compose.yml",
        "infra/env/orchestrator.env.example",
        "scripts/init-env.sh",
        "services/orchestrator/pyproject.toml",
        "services/orchestrator/src/buildwealth_orchestrator/settings.py",
    ]
    forbidden = [
        "legacy-upstream",
        "up-legacy",
        "PORTFOLIO_EXTERNAL_",
        "PLAN_EXTERNAL_",
    ]

    for path in checked_paths:
        source = _read(path)
        for token in forbidden:
            assert token not in source, f"{path} still contains {token!r}"


def test_removed_upstream_env_templates_stay_removed() -> None:
    assert not (ROOT / "infra/env/portfolio_analysis.env.example").exists()
    assert not (ROOT / "infra/env/simulation.env.example").exists()
