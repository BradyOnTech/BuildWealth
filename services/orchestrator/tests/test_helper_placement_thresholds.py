from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


_IMPORTER_THRESHOLD = 5
_LOC_THRESHOLD = 120

_TRACKED_HELPERS = {
    "portfolio_metrics": {
        "module": "buildwealth_orchestrator.services.portfolio_metrics",
        "path": Path("src/buildwealth_orchestrator/services/portfolio_metrics.py"),
    },
    "timeline_defaults": {
        "module": "buildwealth_orchestrator.services.timeline_defaults",
        "path": Path("src/buildwealth_orchestrator/services/timeline_defaults.py"),
    },
}


@dataclass(frozen=True)
class _HelperPlacementStats:
    line_count: int
    importer_count: int
    importers: tuple[str, ...]


def _module_name_for_path(src_root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(src_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_import_from_module(importer_module: str, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    package_parts = importer_module.split(".")[:-1]
    if node.level > len(package_parts) + 1:
        return None

    keep = len(package_parts) - (node.level - 1)
    resolved = package_parts[:keep]
    if node.module:
        resolved.extend(node.module.split("."))
    return ".".join(resolved)


def _module_imports_target(parsed: ast.Module, importer_module: str, target_module: str) -> bool:
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == target_module or alias.name.startswith(f"{target_module}."):
                    return True
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        resolved = _resolve_import_from_module(importer_module, node)
        if not resolved:
            continue
        if resolved == target_module or resolved.startswith(f"{target_module}."):
            return True
        for alias in node.names:
            imported_module = f"{resolved}.{alias.name}"
            if imported_module == target_module or imported_module.startswith(f"{target_module}."):
                return True
    return False


def _line_count(module_path: Path) -> int:
    return len(module_path.read_text(encoding="utf-8").splitlines())


def _collect_importers(src_root: Path, target_module: str) -> tuple[str, ...]:
    importers: set[str] = set()
    for file_path in src_root.rglob("*.py"):
        module_name = _module_name_for_path(src_root, file_path)
        if module_name == target_module:
            continue
        parsed = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        if _module_imports_target(parsed, module_name, target_module):
            importers.add(module_name)
    return tuple(sorted(importers))


def _collect_stats(project_root: Path, helper_name: str) -> _HelperPlacementStats:
    helper_config = _TRACKED_HELPERS[helper_name]
    src_root = project_root / "src"
    helper_path = project_root / helper_config["path"]
    importers = _collect_importers(src_root, helper_config["module"])
    return _HelperPlacementStats(
        line_count=_line_count(helper_path),
        importer_count=len(importers),
        importers=importers,
    )


def test_tracked_neutral_helpers_exist_for_threshold_scoring() -> None:
    project_root = Path(__file__).resolve().parents[1]
    for helper_name, helper_config in _TRACKED_HELPERS.items():
        helper_path = project_root / helper_config["path"]
        assert helper_path.is_file(), f"Missing tracked neutral helper file: {helper_name} ({helper_path})"


def test_neutral_helper_placement_threshold_crossings_are_explicit() -> None:
    """
    Enforce continuous re-scoring for neutral helper placement.

    This automated guardrail tracks the measurable move criteria from
    CODEBASE_QUALITY_FOLLOW_UP_2026-04-15.md:
    - reuse breadth (importer count)
    - surface size (line count)

    If thresholds are crossed, the slice should explicitly re-score helper
    placement and decide whether to keep local or introduce services/shared/.
    """

    project_root = Path(__file__).resolve().parents[1]
    threshold_crossings: list[str] = []
    for helper_name in _TRACKED_HELPERS:
        stats = _collect_stats(project_root, helper_name)
        if stats.importer_count >= _IMPORTER_THRESHOLD or stats.line_count > _LOC_THRESHOLD:
            threshold_crossings.append(
                (
                    f"{helper_name}: importers={stats.importer_count} "
                    f"(threshold >= {_IMPORTER_THRESHOLD}), "
                    f"line_count={stats.line_count} (threshold > {_LOC_THRESHOLD}), "
                    f"importers_list={list(stats.importers)}"
                )
            )

    if not threshold_crossings:
        return

    follow_up = (
        "Multiple neutral helpers crossed thresholds together; evaluate one bounded "
        "services/shared/ introduction with domain splits."
        if len(threshold_crossings) > 1
        else "A neutral helper crossed thresholds; perform documented placement re-score and record keep/move decision."
    )
    raise AssertionError(
        "Neutral helper placement thresholds crossed. "
        f"{follow_up} Details: {threshold_crossings}"
    )
