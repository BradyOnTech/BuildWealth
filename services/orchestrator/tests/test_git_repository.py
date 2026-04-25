from __future__ import annotations

from pathlib import Path
import subprocess

from buildwealth_orchestrator.services.git_repository import GitRepositoryService


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _seed_repo(path: Path, *, message: str = "Initial checkpoint") -> GitRepositoryService:
    service = GitRepositoryService(path)
    service.init_repo()
    (path / "README.md").write_text("# Versioned\n", encoding="utf-8")
    service.commit(message=message)
    return service


def _create_bare_remote(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True, text=True)
    return path


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


def test_git_repository_restore_preview_compares_selected_ref_to_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    service = GitRepositoryService(workspace)
    service.init_repo()
    plan_dir = workspace / "plans" / "plan-a"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan.md").write_text("Old plan\n", encoding="utf-8")
    (plan_dir / "old-note.md").write_text("Remove me\n", encoding="utf-8")
    service.commit(message="Old checkpoint")
    old_hash = service.history()[0]["hash"]

    (plan_dir / "plan.md").write_text("New plan\n", encoding="utf-8")
    (plan_dir / "old-note.md").unlink()
    (plan_dir / "tasks.md").write_text("New task\n", encoding="utf-8")

    preview = service.restore_preview(ref=old_hash, path="plans/plan-a")
    by_path = {item["path"]: item for item in preview["files"]}

    assert preview["status"] == "ok"
    assert preview["read_only"] is True
    assert by_path["plans/plan-a/plan.md"]["status"] == "modified"
    assert "-Old plan" in by_path["plans/plan-a/plan.md"]["diff"]
    assert "+New plan" in by_path["plans/plan-a/plan.md"]["diff"]
    assert by_path["plans/plan-a/old-note.md"]["status"] == "deleted"
    assert by_path["plans/plan-a/tasks.md"]["status"] == "added"


def test_git_repository_returns_nothing_to_commit_for_clean_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    service = GitRepositoryService(workspace)
    service.init_repo()
    (workspace / "README.md").write_text("# Versioned\n", encoding="utf-8")
    service.commit(message="Initial checkpoint")

    result = service.commit(message="Second checkpoint")

    assert result["status"] == "nothing_to_commit"
    assert result["commit"]["message"] == "Initial checkpoint"


def test_git_repository_connects_empty_remote_and_pushes_history(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    remote = _create_bare_remote(tmp_path / "remote.git")
    service = _seed_repo(workspace)

    result = service.connect_remote(remote_url=str(remote), name="origin")
    status = service.remote_status()

    assert result["status"] == "connected"
    assert status["has_remote"] is True
    assert status["name"] == "origin"
    assert status["url"] == str(remote)
    assert status["ahead"] == 0
    assert status["behind"] == 0


def test_git_repository_manual_push_updates_remote(tmp_path: Path) -> None:
    workspace = tmp_path / "versioned"
    remote = _create_bare_remote(tmp_path / "remote.git")
    service = _seed_repo(workspace)
    service.connect_remote(remote_url=str(remote), name="origin")
    (workspace / "README.md").write_text("# Versioned\n\nSecond line\n", encoding="utf-8")
    service.commit(message="Second checkpoint")

    before_push = service.remote_status()
    push = service.push(remote_name="origin")
    after_push = service.remote_status()

    assert before_push["ahead"] == 1
    assert push["status"] == "pushed"
    assert after_push["ahead"] == 0


def test_git_repository_rejects_incompatible_remote_history(tmp_path: Path) -> None:
    remote = _create_bare_remote(tmp_path / "remote.git")
    remote_seed = tmp_path / "remote-seed"
    remote_seed.mkdir()
    _run_git(remote_seed, "init")
    (remote_seed / "REMOTE.md").write_text("# Remote\n", encoding="utf-8")
    _run_git(remote_seed, "add", "-A")
    _run_git(
        remote_seed,
        "-c",
        "user.name=BuildWealth",
        "-c",
        "user.email=buildwealth@local",
        "commit",
        "-m",
        "Remote root",
    )
    _run_git(remote_seed, "branch", "-M", "main")
    _run_git(remote_seed, "remote", "add", "origin", str(remote))
    _run_git(remote_seed, "push", "-u", "origin", "main")

    service = _seed_repo(tmp_path / "versioned")

    result = service.connect_remote(remote_url=str(remote), name="origin")

    assert result["status"] == "incompatible_history"
    assert service.remote_status()["has_remote"] is False
