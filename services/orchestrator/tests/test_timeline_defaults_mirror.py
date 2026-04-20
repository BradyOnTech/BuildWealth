from __future__ import annotations

from pathlib import Path
import re
from typing import Any, get_args

from buildwealth_orchestrator.schemas import PlanScenarioBranchEvent, PlanTimelineEvent
from buildwealth_orchestrator.services import timeline_defaults
from buildwealth_orchestrator.services.timeline_defaults import (
    TIMELINE_DEFAULT_IMPACT_BY_EVENT,
    TIMELINE_EVENT_TYPE_VALUES,
    TIMELINE_EVENT_TYPES,
    TIMELINE_FREQUENCY_VALUES,
    TIMELINE_FREQUENCIES,
    TIMELINE_IMPACT_TYPE_VALUES,
    TIMELINE_IMPACT_TYPES,
)


_MIRRORED_TIMELINE_CONSTANTS = {
    "TIMELINE_EVENT_TYPE_VALUES",
    "TIMELINE_IMPACT_TYPE_VALUES",
    "TIMELINE_FREQUENCY_VALUES",
    "TIMELINE_DEFAULT_IMPACT_BY_EVENT",
}

_BACKEND_ONLY_TIMELINE_CONSTANTS = {
    "TIMELINE_EVENT_TYPES",
    "TIMELINE_IMPACT_TYPES",
    "TIMELINE_FREQUENCIES",
}

_FRONTEND_TIMELINE_EXPORT_NAMES = {
    "TIMELINE_EVENT_TYPES",
    "TIMELINE_IMPACT_TYPES",
    "TIMELINE_FREQUENCIES",
    "TIMELINE_DEFAULT_IMPACT_BY_EVENT",
}


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


def test_timeline_defaults_constant_coverage_is_explicit() -> None:
    discovered_constants = {
        name
        for name, value in vars(timeline_defaults).items()
        if name.startswith("TIMELINE_") and name.isupper() and not callable(value)
    }
    expected_constants = _MIRRORED_TIMELINE_CONSTANTS | _BACKEND_ONLY_TIMELINE_CONSTANTS
    assert discovered_constants == expected_constants

    # Runtime set constants should remain derived from ordered tuple values.
    assert TIMELINE_EVENT_TYPES == frozenset(TIMELINE_EVENT_TYPE_VALUES)
    assert TIMELINE_IMPACT_TYPES == frozenset(TIMELINE_IMPACT_TYPE_VALUES)
    assert TIMELINE_FREQUENCIES == frozenset(TIMELINE_FREQUENCY_VALUES)


def _extract_js_array_values(module_text: str, const_name: str) -> tuple[str, ...]:
    pattern = rf"export const {const_name}\s*=\s*Object\.freeze\(\[(.*?)\]\);"
    match = re.search(pattern, module_text, re.DOTALL)
    if match is None:
        raise AssertionError(f"Unable to locate {const_name} array export in timeline_defaults.js")
    values = re.findall(r"'([^']+)'", match.group(1))
    return tuple(values)


def _extract_js_object_values(module_text: str, const_name: str) -> dict[str, str]:
    pattern = rf"export const {const_name}\s*=\s*Object\.freeze\(\{{(.*?)\}}\);"
    match = re.search(pattern, module_text, re.DOTALL)
    if match is None:
        raise AssertionError(f"Unable to locate {const_name} object export in timeline_defaults.js")
    pairs = re.findall(r"([A-Za-z0-9_]+)\s*:\s*'([^']+)'", match.group(1))
    return {key: value for key, value in pairs}


def test_timeline_defaults_frontend_mirror_stays_in_sync() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = (
        project_root
        / "src"
        / "buildwealth_orchestrator"
        / "web"
        / "lib"
        / "timeline_defaults.js"
    )
    module_text = module_path.read_text(encoding="utf-8")

    exported_names = set(re.findall(r"export const (TIMELINE_[A-Z0-9_]+)\s*=", module_text))
    assert exported_names == _FRONTEND_TIMELINE_EXPORT_NAMES

    payload = {
        "eventTypes": list(_extract_js_array_values(module_text, "TIMELINE_EVENT_TYPES")),
        "impactTypes": list(_extract_js_array_values(module_text, "TIMELINE_IMPACT_TYPES")),
        "frequencies": list(_extract_js_array_values(module_text, "TIMELINE_FREQUENCIES")),
        "defaultImpactByEvent": _extract_js_object_values(module_text, "TIMELINE_DEFAULT_IMPACT_BY_EVENT"),
    }
    assert payload["eventTypes"] == list(TIMELINE_EVENT_TYPE_VALUES)
    assert payload["impactTypes"] == list(TIMELINE_IMPACT_TYPE_VALUES)
    assert payload["frequencies"] == list(TIMELINE_FREQUENCY_VALUES)
    assert payload["defaultImpactByEvent"] == TIMELINE_DEFAULT_IMPACT_BY_EVENT
