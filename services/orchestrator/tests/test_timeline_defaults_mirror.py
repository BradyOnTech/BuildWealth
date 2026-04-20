from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
from typing import Any, get_args

import pytest

from buildwealth_orchestrator.schemas import PlanScenarioBranchEvent, PlanTimelineEvent
from buildwealth_orchestrator.services.timeline_defaults import (
    TIMELINE_DEFAULT_IMPACT_BY_EVENT,
    TIMELINE_EVENT_TYPE_VALUES,
    TIMELINE_FREQUENCY_VALUES,
    TIMELINE_IMPACT_TYPE_VALUES,
)


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


def _literal_values(annotation: Any) -> tuple[str, ...]:
    args = get_args(annotation)
    if not args:
        return ()
    if len(args) == 1 and get_args(args[0]):
        return tuple(str(value) for value in get_args(args[0]))
    return tuple(str(value) for value in args)


def _optional_literal_values(annotation: Any) -> tuple[str, ...]:
    args = get_args(annotation)
    if not args:
        return ()
    non_none = [value for value in args if value is not type(None)]
    if not non_none:
        return ()
    return tuple(str(value) for value in get_args(non_none[0]))


def test_timeline_defaults_runtime_and_schema_literals_stay_in_sync() -> None:
    timeline_event_type_values = _literal_values(PlanTimelineEvent.model_fields["event_type"].annotation)
    timeline_impact_type_values = _optional_literal_values(PlanTimelineEvent.model_fields["impact_type"].annotation)
    timeline_frequency_values = _literal_values(PlanTimelineEvent.model_fields["recurring_frequency"].annotation)

    branch_event_type_values = _literal_values(PlanScenarioBranchEvent.model_fields["event_type"].annotation)
    branch_impact_type_values = _optional_literal_values(PlanScenarioBranchEvent.model_fields["impact_type"].annotation)
    branch_frequency_values = _literal_values(PlanScenarioBranchEvent.model_fields["recurring_frequency"].annotation)

    assert timeline_event_type_values == TIMELINE_EVENT_TYPE_VALUES
    assert timeline_impact_type_values == TIMELINE_IMPACT_TYPE_VALUES
    assert timeline_frequency_values == TIMELINE_FREQUENCY_VALUES

    assert branch_event_type_values == TIMELINE_EVENT_TYPE_VALUES
    assert branch_impact_type_values == TIMELINE_IMPACT_TYPE_VALUES
    assert branch_frequency_values == TIMELINE_FREQUENCY_VALUES

    assert tuple(TIMELINE_DEFAULT_IMPACT_BY_EVENT.keys()) == TIMELINE_EVENT_TYPE_VALUES
    assert set(TIMELINE_DEFAULT_IMPACT_BY_EVENT.values()).issubset(set(TIMELINE_IMPACT_TYPE_VALUES))


def test_timeline_defaults_frontend_mirror_stays_in_sync() -> None:
    node_bin = _resolve_node_binary()
    if node_bin is None:
        pytest.skip("no node binary with --experimental-default-type support for frontend mirror checks")

    project_root = Path(__file__).resolve().parents[1]
    module_path = (
        project_root
        / "src"
        / "buildwealth_orchestrator"
        / "web"
        / "lib"
        / "timeline_defaults.js"
    )

    script = "\n".join(
        [
            (
                f"import {{ TIMELINE_EVENT_TYPES, TIMELINE_IMPACT_TYPES, TIMELINE_FREQUENCIES, "
                f"TIMELINE_DEFAULT_IMPACT_BY_EVENT }} from '{module_path.resolve().as_uri()}';"
            ),
            "const payload = {",
            "  eventTypes: TIMELINE_EVENT_TYPES,",
            "  impactTypes: TIMELINE_IMPACT_TYPES,",
            "  frequencies: TIMELINE_FREQUENCIES,",
            "  defaultImpactByEvent: TIMELINE_DEFAULT_IMPACT_BY_EVENT,",
            "};",
            "console.log(JSON.stringify(payload));",
        ]
    )

    result = subprocess.run(
        [node_bin, "--experimental-default-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Timeline defaults frontend mirror check failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    payload = json.loads(result.stdout.strip())
    assert payload["eventTypes"] == list(TIMELINE_EVENT_TYPE_VALUES)
    assert payload["impactTypes"] == list(TIMELINE_IMPACT_TYPE_VALUES)
    assert payload["frequencies"] == list(TIMELINE_FREQUENCY_VALUES)
    assert payload["defaultImpactByEvent"] == TIMELINE_DEFAULT_IMPACT_BY_EVENT
