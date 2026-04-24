"""Thin system-git wrapper for BuildWealth versioned workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any


class GitRepositoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitCommandResult:
    returncode: int
    stdout: str
    stderr: str


class GitRepositoryService:
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir

    def is_repo(self) -> bool:
        if not self.workspace_dir.exists():
            return False
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def init_repo(self) -> dict[str, Any]:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        if self.is_repo():
            return {
                "status": "already_initialized",
                "message": "Git repository already initialized.",
                "workspace_dir": str(self.workspace_dir),
            }

        result = self._run_git(["init"], check=False)
        if result.returncode != 0:
            raise GitRepositoryError(_git_error("git init failed", result))

        return {
            "status": "initialized",
            "message": "Git repository initialized.",
            "workspace_dir": str(self.workspace_dir),
        }

    def status(self) -> dict[str, Any]:
        if not self.is_repo():
            return {
                "status": "no_repo",
                "message": "Versioned workspace is not initialized as a Git repository.",
                "workspace_dir": str(self.workspace_dir),
                "branch": None,
                "dirty": False,
                "changed_files": [],
                "last_commit": None,
                "has_remote": False,
                "remote": None,
            }

        changed_files = self._changed_files()
        remote = self.remote_status()
        return {
            "status": "ok",
            "message": "Git repository status loaded.",
            "workspace_dir": str(self.workspace_dir),
            "branch": self.current_branch(),
            "dirty": bool(changed_files),
            "changed_files": changed_files,
            "last_commit": self.last_commit(),
            "has_remote": bool(remote.get("has_remote")),
            "remote": remote,
        }

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.is_repo():
            return []

        bounded_limit = max(1, min(int(limit), 100))
        result = self._run_git(
            ["log", f"-n{bounded_limit}", "--format=%H%x1f%h%x1f%aI%x1f%s"],
            check=False,
        )
        if result.returncode != 0:
            if _looks_like_no_commits(result.stderr):
                return []
            raise GitRepositoryError(_git_error("git log failed", result))

        commits: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            parts = line.split("\x1f", 3)
            if len(parts) != 4:
                continue
            commits.append(
                {
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                }
            )
        return commits

    def diff(
        self,
        *,
        ref: str | None = None,
        path: str | None = None,
        max_chars: int = 200_000,
    ) -> dict[str, Any]:
        bounded_max = max(1_000, min(int(max_chars), 1_000_000))
        cleaned_path = _clean_pathspec(path)
        if not self.is_repo():
            return {
                "status": "no_repo",
                "message": "Versioned workspace is not initialized as a Git repository.",
                "workspace_dir": str(self.workspace_dir),
                "ref": ref,
                "path": cleaned_path,
                "diff": "",
                "truncated": False,
            }

        cleaned_ref = (ref or "").strip() or None
        if cleaned_ref:
            diff_text = self._commit_diff(cleaned_ref, cleaned_path)
            message = "Commit diff loaded."
        else:
            diff_text = self._current_diff(cleaned_path)
            message = "Current workspace diff loaded."

        truncated = len(diff_text) > bounded_max
        if truncated:
            diff_text = diff_text[:bounded_max]

        return {
            "status": "ok",
            "message": message,
            "workspace_dir": str(self.workspace_dir),
            "ref": cleaned_ref,
            "path": cleaned_path,
            "diff": diff_text,
            "truncated": truncated,
        }

    def commit(self, *, message: str, body: str | None = None) -> dict[str, Any]:
        cleaned_message = message.strip()
        if not cleaned_message:
            raise GitRepositoryError("Commit message is required.")
        if not self.is_repo():
            return {
                "status": "no_repo",
                "message": "Versioned workspace is not initialized as a Git repository.",
                "commit": None,
            }

        add_result = self._run_git(["add", "-A"], check=False)
        if add_result.returncode != 0:
            raise GitRepositoryError(_git_error("git add failed", add_result))

        staged = self._run_git(["diff", "--cached", "--quiet"], check=False)
        if staged.returncode == 0:
            return {
                "status": "nothing_to_commit",
                "message": "No versioned workspace changes to commit.",
                "commit": self.last_commit(),
            }
        if staged.returncode != 1:
            raise GitRepositoryError(_git_error("git diff --cached failed", staged))

        args = [
            "-c",
            "user.name=BuildWealth",
            "-c",
            "user.email=buildwealth@local",
            "commit",
            "-m",
            cleaned_message,
        ]
        cleaned_body = (body or "").strip()
        if cleaned_body:
            args.extend(["-m", cleaned_body])

        commit_result = self._run_git(args, check=False)
        if commit_result.returncode != 0:
            raise GitRepositoryError(_git_error("git commit failed", commit_result))

        return {
            "status": "committed",
            "message": "Versioned workspace checkpoint committed.",
            "commit": self.last_commit(),
        }

    def current_branch(self) -> str | None:
        result = self._run_git(["branch", "--show-current"], check=False)
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        return branch or None

    def last_commit(self) -> dict[str, Any] | None:
        commits = self.history(limit=1)
        return commits[0] if commits else None

    def remote_status(self) -> dict[str, Any]:
        if not self.is_repo():
            return {"has_remote": False, "name": None, "ahead": 0, "behind": 0}

        remotes = self._run_git(["remote"], check=False)
        names = [line.strip() for line in remotes.stdout.splitlines() if line.strip()]
        if remotes.returncode != 0 or not names:
            return {"has_remote": False, "name": None, "ahead": 0, "behind": 0}

        ahead = 0
        behind = 0
        counts = self._run_git(
            ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
            check=False,
        )
        if counts.returncode == 0:
            parts = counts.stdout.strip().split()
            if len(parts) >= 2:
                ahead = _safe_int(parts[0])
                behind = _safe_int(parts[1])

        return {"has_remote": True, "name": names[0], "ahead": ahead, "behind": behind}

    def _commit_diff(self, ref: str, path: str | None) -> str:
        args = ["show", "--format=", "--patch", "--find-renames", ref]
        if path:
            args.extend(["--", path])
        result = self._run_git(args, check=False)
        if result.returncode != 0:
            raise GitRepositoryError(_git_error("git show failed", result))
        return result.stdout

    def _current_diff(self, path: str | None) -> str:
        args = ["diff", "--find-renames", "HEAD", "--"]
        if path:
            args.append(path)
        result = self._run_git(args, check=False)
        diff_text = ""
        if result.returncode == 0:
            diff_text = result.stdout
        elif _looks_like_bad_revision(result.stderr):
            diff_text = ""
        else:
            raise GitRepositoryError(_git_error("git diff failed", result))

        untracked_diffs = [
            self._untracked_file_diff(row["path"])
            for row in self._changed_files()
            if row["status"] == "untracked" and (path is None or row["path"] == path)
        ]
        if untracked_diffs:
            parts = [part for part in [diff_text, *untracked_diffs] if part]
            return "\n".join(parts)
        return diff_text

    def _untracked_file_diff(self, relative_path: str) -> str:
        file_path = self.workspace_dir / relative_path
        try:
            content = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            return (
                f"diff --git a/{relative_path} b/{relative_path}\n"
                "new file mode 100644\n"
                f"Binary files /dev/null and b/{relative_path} differ\n"
            )
        lines = content.splitlines()
        added_lines = "\n".join(f"+{line}" for line in lines)
        if added_lines:
            added_lines = f"{added_lines}\n"
        return (
            f"diff --git a/{relative_path} b/{relative_path}\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            f"+++ b/{relative_path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n"
            f"{added_lines}"
        )

    def _changed_files(self) -> list[dict[str, str]]:
        result = self._run_git(["status", "--porcelain", "--untracked-files=all"], check=False)
        if result.returncode != 0:
            raise GitRepositoryError(_git_error("git status failed", result))

        rows: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            status_code = line[:2].strip() or line[:2]
            raw_path = line[3:].strip()
            relative_path = raw_path.split(" -> ")[-1].strip()
            rows.append(
                {
                    "path": relative_path,
                    "status": _status_label(status_code),
                }
            )
        return rows

    def _run_git(self, args: list[str], *, check: bool = True) -> GitCommandResult:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.workspace_dir,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise GitRepositoryError(f"Failed to run git: {exc}") from exc

        result = GitCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            raise GitRepositoryError(_git_error(f"git {args[0]} failed", result))
        return result


def _git_error(prefix: str, result: GitCommandResult) -> str:
    detail = result.stderr.strip() or result.stdout.strip()
    return f"{prefix}: {detail}" if detail else prefix


def _looks_like_no_commits(stderr: str) -> bool:
    lowered = stderr.lower()
    return "does not have any commits yet" in lowered or "your current branch" in lowered


def _looks_like_bad_revision(stderr: str) -> bool:
    lowered = stderr.lower()
    return "ambiguous argument 'head'" in lowered or "bad revision 'head'" in lowered


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _status_label(status_code: str) -> str:
    normalized = status_code.strip()
    if normalized == "??":
        return "untracked"
    if "A" in normalized:
        return "added"
    if "D" in normalized:
        return "deleted"
    if "R" in normalized:
        return "renamed"
    return "modified"


def _clean_pathspec(path: str | None) -> str | None:
    cleaned = str(path or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("/") or "\\" in cleaned:
        raise GitRepositoryError("Diff path must be relative to the versioned workspace.")
    if any(part == ".." for part in Path(cleaned).parts):
        raise GitRepositoryError("Diff path must stay inside the versioned workspace.")
    return cleaned
