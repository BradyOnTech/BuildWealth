"""Embedding settings must reach the services that actually embed.

Regression tests for the split-brain that shipped embeddings dark: the
workspace factory built every ContextIntelligenceService with a disabled
embedding client regardless of configuration, and saved workspace settings
were never read back when services were rebuilt per request.
"""

from __future__ import annotations

from copy import copy
from pathlib import Path
from types import SimpleNamespace

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.context_intelligence import ContextIntelligenceService
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.embedding_clients import (
    DisabledEmbeddingClient,
    apply_context_embedding_overrides,
    build_embedding_client_from_settings,
)
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


def _embedding_settings(tmp_path: Path, *, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        durable_storage_dir=tmp_path / "storage",
        context_embeddings_enabled=enabled,
        context_embedding_provider="ollama",
        context_embedding_model="nomic-embed-text",
        context_embedding_base_url="http://host.docker.internal:11434",
        context_embedding_timeout_seconds=5.0,
    )


def test_from_settings_builds_enabled_client_when_configured(tmp_path: Path) -> None:
    service = ContextIntelligenceService.from_settings(
        _embedding_settings(tmp_path, enabled=True),
        financial_profile_store=None,
        plan_workspace=None,
        recommendation_inbox=None,
    )
    assert service.embedding_client.enabled is True
    assert service.embedding_client.provider == "ollama"
    assert service.embedding_client.model == "nomic-embed-text"


def test_from_settings_builds_disabled_client_when_off(tmp_path: Path) -> None:
    service = ContextIntelligenceService.from_settings(
        _embedding_settings(tmp_path, enabled=False),
        financial_profile_store=None,
        plan_workspace=None,
        recommendation_inbox=None,
    )
    assert service.embedding_client.enabled is False


def test_apply_context_embedding_overrides_layering() -> None:
    target = SimpleNamespace(
        context_embeddings_enabled=False,
        context_embedding_provider="disabled",
        context_embedding_model="",
        context_embedding_base_url="http://localhost:11434",
        context_embedding_timeout_seconds=5.0,
    )
    apply_context_embedding_overrides(
        target,
        {
            "context_embeddings_enabled": "true",
            "context_embedding_provider": "ollama",
            "context_embedding_model": "nomic-embed-text",
            # Empty strings mean "not saved" and must not clobber defaults.
            "context_embedding_base_url": "",
            "context_embedding_timeout_seconds": "8",
        },
    )
    assert target.context_embeddings_enabled is True
    assert target.context_embedding_provider == "ollama"
    assert target.context_embedding_model == "nomic-embed-text"
    assert target.context_embedding_base_url == "http://localhost:11434"
    assert target.context_embedding_timeout_seconds == 8.0

    enabled_client = build_embedding_client_from_settings(target)
    assert enabled_client.enabled is True

    apply_context_embedding_overrides(target, {"context_embeddings_enabled": False})
    assert target.context_embeddings_enabled is False
    assert isinstance(build_embedding_client_from_settings(target), DisabledEmbeddingClient)


def test_factory_prefers_saved_workspace_settings_over_globals(tmp_path: Path) -> None:
    test_settings = copy(main.settings)
    test_settings.control_db_path = tmp_path / "control" / "control.db"
    test_settings.workspace_root_dir = tmp_path / "workspaces"
    test_settings.secret_key_path = tmp_path / "control" / "local_secret.key"
    # Globals say disabled — the stale legacy-store boot override scenario.
    test_settings.context_embeddings_enabled = False
    test_settings.context_embedding_provider = "disabled"

    control_plane = ControlPlaneStore(test_settings.control_db_path)
    control_plane.bootstrap_default_household(
        owner_email="owner@example.test",
        default_storage_root=tmp_path / "real",
        demo_storage_root=tmp_path / "demo",
    )
    factory = WorkspaceServiceFactory(settings=test_settings, control_plane=control_plane)
    context = control_plane.dev_request_context(auth_mode="dev")

    services = factory.for_context(context)
    assert services.context_intelligence_service.embedding_client.enabled is False

    services.settings_store.save(
        {
            "context_embeddings_enabled": True,
            "context_embedding_provider": "ollama",
            "context_embedding_model": "nomic-embed-text",
            "context_embedding_base_url": "http://host.docker.internal:11434",
        }
    )

    rebuilt = factory.for_context(context)
    client = rebuilt.context_intelligence_service.embedding_client
    assert client.enabled is True
    assert client.provider == "ollama"
    assert client.model == "nomic-embed-text"
    assert client.base_url == "http://host.docker.internal:11434"
