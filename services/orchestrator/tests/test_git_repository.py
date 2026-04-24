from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.git_repository import GitRepositoryService


def test_git_repository_reports_no_repo_before_initialization(tmp_path: Path) -> None:
    service = GitRepositoryService(tmp_path / "versioned")

    status = service.status()

    assert status["status"] == "no_repo"
    assert status["dirty"] is False
    assert status["changed_files"] == []


def test_git_repository_initializes_commits_and_reads_history(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    service = GitRepositoryService(workspace)

    init_result = service.init_repo()
    (workspace / "README.md").write_text("# Versioned\n", encoding="utf-8")
    dirty_status = service.status()
    commit_result = service.commit(message="Initial checkpoint")
    clean_status = service.status()
    history = service.history()

    assert init_result["status"] == "initialized"
    assert dirty_status["dirty"] is True
    assert dirty_status["changed_files"][0]["path"] == "README.md"
    assert commit_result["status"] == "committed"
    assert commit_result["commit"]["message"] == "Initial checkpoint"
    assert clean_status["dirty"] is False
    assert history[0]["message"] == "Initial checkpoint"


def test_git_repository_current_diff_includes_untracked_files(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    service = GitRepositoryService(workspace)
    service.init_repo()
    (workspace / "README.md").write_text("# Versioned\n", encoding="utf-8")

    diff = service.diff()

    assert diff["status"] == "ok"
    assert diff["ref"] is None
    assert "diff --git a/README.md b/README.md" in diff["diff"]
    assert "+# Versioned" in diff["diff"]


def test_git_repository_commit_diff_returns_selected_patch(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    service = GitRepositoryService(workspace)
    service.init_repo()
    readme = workspace / "README.md"
    readme.write_text("# Versioned\n", encoding="utf-8")
    service.commit(message="Initial checkpoint")
    readme.write_text("# Versioned\n\nSecond line\n", encoding="utf-8")
    current_diff = service.diff()
    service.commit(message="Second checkpoint")
    history = service.history()

    commit_diff = service.diff(ref=history[0]["hash"])

    assert "+Second line" in current_diff["diff"]
    assert commit_diff["ref"] == history[0]["hash"]
    assert "+Second line" in commit_diff["diff"]


def test_git_repository_returns_nothing_to_commit_for_clean_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    service = GitRepositoryService(workspace)
    service.init_repo()
    (workspace / "README.md").write_text("# Versioned\n", encoding="utf-8")
    service.commit(message="Initial checkpoint")

    result = service.commit(message="Second checkpoint")

    assert result["status"] == "nothing_to_commit"
    assert result["commit"]["message"] == "Initial checkpoint"
