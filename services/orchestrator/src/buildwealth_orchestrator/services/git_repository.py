"""Thin system-git wrapper for BuildWealth versioned workspaces."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from pathlib import Path
import subprocess
from typing import Any


RESTORE_PREVIEW_ALLOWED_ROOTS = (
    "plans",
    "recommendations",
    "reports/portfolio_review_packets",
    "policy",
    "profile",
)


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

    def restore_preview(
        self,
        *,
        ref: str,
        path: str | None = None,
        max_chars: int = 120_000,
    ) -> dict[str, Any]:
        bounded_max = max(1_000, min(int(max_chars), 1_000_000))
        cleaned_ref = _clean_ref(ref)
        cleaned_path = _clean_pathspec(path)
        if cleaned_path and not _is_restore_preview_path_allowed(cleaned_path):
            raise GitRepositoryError(
                "Restore preview path must be an exported plan, recommendation, review packet, policy, or profile path."
            )
        if not self.is_repo():
            return {
                "status": "no_repo",
                "message": "Versioned workspace is not initialized as a Git repository.",
                "workspace_dir": str(self.workspace_dir),
                "ref": cleaned_ref,
                "path": cleaned_path,
                "read_only": True,
                "files": [],
                "total_files": 0,
                "warnings": ["Preview only. No canonical BuildWealth data was changed."],
            }
        if not self._commit_exists(cleaned_ref):
            raise GitRepositoryError(f"Unknown restore preview commit: {cleaned_ref}")

        historical_paths = set(self._paths_at_ref(cleaned_ref, cleaned_path))
        current_paths = set(self._current_preview_paths(cleaned_path))
        files: list[dict[str, Any]] = []
        remaining_chars = bounded_max
        for relative_path in sorted(historical_paths | current_paths):
            historical_content = self._file_at_ref(cleaned_ref, relative_path)
            current_content = self._current_file_content(relative_path)
            file_status = _restore_file_status(
                historical_content=historical_content,
                current_content=current_content,
            )
            diff_text = _restore_file_diff(
                relative_path=relative_path,
                historical_content=historical_content,
                current_content=current_content,
            )
            truncated = len(diff_text) > remaining_chars
            if truncated:
                diff_text = diff_text[: max(0, remaining_chars)]
            remaining_chars = max(0, remaining_chars - len(diff_text))
            files.append(
                {
                    "path": relative_path,
                    "status": file_status,
                    "historical_excerpt": _excerpt(historical_content),
                    "current_excerpt": _excerpt(current_content),
                    "diff": diff_text,
                    "truncated": truncated,
                }
            )

        return {
            "status": "ok",
            "message": "Read-only restore preview generated. No files were changed.",
            "workspace_dir": str(self.workspace_dir),
            "ref": cleaned_ref,
            "path": cleaned_path,
            "read_only": True,
            "files": files,
            "total_files": len(files),
            "warnings": [
                "Preview only. No canonical BuildWealth data was changed.",
                "Any future restore should be applied through BuildWealth service-layer validation, not raw git checkout.",
            ],
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
            return {"has_remote": False, "name": None, "url": None, "ahead": 0, "behind": 0}

        remotes = self._run_git(["remote"], check=False)
        names = [line.strip() for line in remotes.stdout.splitlines() if line.strip()]
        if remotes.returncode != 0 or not names:
            return {"has_remote": False, "name": None, "url": None, "ahead": 0, "behind": 0}

        remote_name = names[0]
        remote_url = self._remote_url(remote_name)
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

        return {"has_remote": True, "name": remote_name, "url": remote_url, "ahead": ahead, "behind": behind}

    def connect_remote(self, *, remote_url: str, name: str = "origin") -> dict[str, Any]:
        if not self.is_repo():
            return self._remote_operation_result(
                status="no_repo",
                message="Versioned workspace is not initialized as a Git repository.",
                remote_name=name,
            )

        remote_name = _clean_remote_name(name)
        cleaned_url = _clean_remote_url(remote_url)
        branch = self.current_branch() or "main"
        existing_url = self._remote_url(remote_name)
        if existing_url and existing_url != cleaned_url:
            return self._remote_operation_result(
                status="already_configured",
                message=f"Remote '{remote_name}' is already configured with a different URL.",
                remote_name=remote_name,
            )
        if existing_url == cleaned_url:
            return self._remote_operation_result(
                status="already_configured",
                message=f"Remote '{remote_name}' is already configured.",
                remote_name=remote_name,
            )

        add_result = self._run_git(["remote", "add", remote_name, cleaned_url], check=False)
        if add_result.returncode != 0:
            return self._classified_remote_result(
                "git remote add failed",
                add_result,
                remote_name=remote_name,
            )

        fetch_result = self._run_git(["fetch", remote_name, "--prune"], check=False)
        if fetch_result.returncode != 0:
            self._remove_remote(remote_name)
            return self._classified_remote_result(
                "git fetch failed",
                fetch_result,
                remote_name=remote_name,
            )

        remote_refs = self._remote_branch_refs(remote_name)
        if remote_refs:
            target_ref = (
                f"{remote_name}/{branch}"
                if f"{remote_name}/{branch}" in remote_refs
                else remote_refs[0]
            )
            compatible = self._run_git(["merge-base", "--is-ancestor", target_ref, "HEAD"], check=False)
            if compatible.returncode != 0:
                self._remove_remote(remote_name)
                return self._remote_operation_result(
                    status="incompatible_history",
                    message="Remote history is not an ancestor of the local BuildWealth history. Connection refused.",
                    remote_name=remote_name,
                )
            upstream = self._run_git(["branch", "--set-upstream-to", target_ref], check=False)
            if upstream.returncode != 0:
                self._remove_remote(remote_name)
                return self._classified_remote_result(
                    "git branch --set-upstream-to failed",
                    upstream,
                    remote_name=remote_name,
                )
            push_result = self._run_git(["push", remote_name, f"HEAD:{branch}"], check=False)
        else:
            push_result = self._run_git(["push", "-u", remote_name, f"HEAD:{branch}"], check=False)

        if push_result.returncode != 0:
            self._remove_remote(remote_name)
            return self._classified_remote_result(
                "git push failed",
                push_result,
                remote_name=remote_name,
            )

        return self._remote_operation_result(
            status="connected",
            message=f"Remote '{remote_name}' connected.",
            remote_name=remote_name,
        )

    def push(self, *, remote_name: str = "origin") -> dict[str, Any]:
        if not self.is_repo():
            return self._remote_operation_result(
                status="no_repo",
                message="Versioned workspace is not initialized as a Git repository.",
                remote_name=remote_name,
            )

        cleaned_name = _clean_remote_name(remote_name)
        if not self._remote_url(cleaned_name):
            return self._remote_operation_result(
                status="no_remote",
                message=f"Remote '{cleaned_name}' is not configured.",
                remote_name=cleaned_name,
            )

        branch = self.current_branch() or "main"
        result = self._run_git(["push", "-u", cleaned_name, f"HEAD:{branch}"], check=False)
        if result.returncode != 0:
            return self._classified_remote_result("git push failed", result, remote_name=cleaned_name)

        return self._remote_operation_result(
            status="pushed",
            message=f"Pushed local BuildWealth history to '{cleaned_name}'.",
            remote_name=cleaned_name,
        )

    def pull(self, *, remote_name: str = "origin") -> dict[str, Any]:
        if not self.is_repo():
            return self._remote_operation_result(
                status="no_repo",
                message="Versioned workspace is not initialized as a Git repository.",
                remote_name=remote_name,
            )

        cleaned_name = _clean_remote_name(remote_name)
        if not self._remote_url(cleaned_name):
            return self._remote_operation_result(
                status="no_remote",
                message=f"Remote '{cleaned_name}' is not configured.",
                remote_name=cleaned_name,
            )

        branch = self.current_branch() or "main"
        result = self._run_git(["pull", "--ff-only", cleaned_name, branch], check=False)
        if result.returncode != 0:
            return self._classified_remote_result("git pull failed", result, remote_name=cleaned_name)

        return self._remote_operation_result(
            status="pulled",
            message=f"Pulled fast-forward changes from '{cleaned_name}'.",
            remote_name=cleaned_name,
        )

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

    def _remote_url(self, remote_name: str) -> str | None:
        result = self._run_git(["remote", "get-url", remote_name], check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _remote_branch_refs(self, remote_name: str) -> list[str]:
        result = self._run_git(
            ["for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote_name}"],
            check=False,
        )
        if result.returncode != 0:
            return []
        refs = []
        for line in result.stdout.splitlines():
            ref = line.strip()
            if ref and not ref.endswith("/HEAD"):
                refs.append(ref)
        return sorted(refs)

    def _remove_remote(self, remote_name: str) -> None:
        self._run_git(["remote", "remove", remote_name], check=False)

    def _remote_operation_result(
        self,
        *,
        status: str,
        message: str,
        remote_name: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "message": message,
            "workspace_dir": str(self.workspace_dir),
            "branch": self.current_branch(),
            "remote": self.remote_status(),
            "remote_name": remote_name,
        }

    def _classified_remote_result(
        self,
        prefix: str,
        result: GitCommandResult,
        *,
        remote_name: str,
    ) -> dict[str, Any]:
        detail = _git_error(prefix, result)
        return self._remote_operation_result(
            status=_remote_error_status(result),
            message=detail,
            remote_name=remote_name,
        )

    def _commit_exists(self, ref: str) -> bool:
        result = self._run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], check=False)
        return result.returncode == 0

    def _paths_at_ref(self, ref: str, path: str | None) -> list[str]:
        args = ["ls-tree", "-r", "--name-only", ref]
        if path:
            args.extend(["--", path])
        result = self._run_git(args, check=False)
        if result.returncode != 0:
            raise GitRepositoryError(_git_error("git ls-tree failed", result))
        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and _is_restore_preview_path_allowed(line.strip())
        ]

    def _current_preview_paths(self, path: str | None) -> list[str]:
        candidates: list[Path] = []
        if path:
            candidate = self.workspace_dir / path
            if candidate.is_file():
                candidates = [candidate]
            elif candidate.is_dir():
                candidates = [item for item in candidate.rglob("*") if item.is_file()]
        else:
            for root in RESTORE_PREVIEW_ALLOWED_ROOTS:
                candidate = self.workspace_dir / root
                if candidate.is_file():
                    candidates.append(candidate)
                elif candidate.is_dir():
                    candidates.extend(item for item in candidate.rglob("*") if item.is_file())

        paths = []
        for candidate in candidates:
            try:
                relative = candidate.relative_to(self.workspace_dir).as_posix()
            except ValueError:
                continue
            if _is_restore_preview_path_allowed(relative):
                paths.append(relative)
        return sorted(set(paths))

    def _file_at_ref(self, ref: str, relative_path: str) -> str | None:
        result = self._run_git(["show", f"{ref}:{relative_path}"], check=False)
        if result.returncode != 0:
            return None
        return result.stdout

    def _current_file_content(self, relative_path: str) -> str | None:
        file_path = self.workspace_dir / relative_path
        if not file_path.is_file():
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

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


def _clean_ref(ref: str | None) -> str:
    cleaned = str(ref or "").strip()
    if not cleaned:
        raise GitRepositoryError("Restore preview commit ref is required.")
    if cleaned.startswith("-") or "\n" in cleaned or "\r" in cleaned:
        raise GitRepositoryError("Restore preview commit ref is invalid.")
    return cleaned


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


def _restore_file_status(*, historical_content: str | None, current_content: str | None) -> str:
    if historical_content is None and current_content is not None:
        return "added"
    if historical_content is not None and current_content is None:
        return "deleted"
    if historical_content == current_content:
        return "unchanged"
    return "modified"


def _restore_file_diff(
    *,
    relative_path: str,
    historical_content: str | None,
    current_content: str | None,
) -> str:
    historical_lines = (historical_content or "").splitlines(keepends=True)
    current_lines = (current_content or "").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            historical_lines,
            current_lines,
            fromfile=f"historical/{relative_path}",
            tofile=f"current/{relative_path}",
        )
    )


def _excerpt(content: str | None, *, max_chars: int = 4_000) -> str | None:
    if content is None:
        return None
    return content[:max_chars]


def _is_restore_preview_path_allowed(relative_path: str) -> bool:
    normalized = relative_path.strip().strip("/")
    return any(
        normalized == root or normalized.startswith(f"{root}/")
        for root in RESTORE_PREVIEW_ALLOWED_ROOTS
    )


def _remote_error_status(result: GitCommandResult) -> str:
    lowered = f"{result.stderr}\n{result.stdout}".lower()
    if any(token in lowered for token in ("permission denied", "authentication", "could not read from remote")):
        return "auth_error"
    if any(token in lowered for token in ("could not resolve", "failed to connect", "timed out", "network is unreachable")):
        return "network_error"
    if any(token in lowered for token in ("non-fast-forward", "rejected", "fetch first")):
        return "rejected"
    return "error"


def _clean_remote_name(name: str | None) -> str:
    cleaned = str(name or "origin").strip() or "origin"
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(char not in allowed for char in cleaned):
        raise GitRepositoryError("Remote name may only contain letters, numbers, dots, underscores, and hyphens.")
    return cleaned


def _clean_remote_url(remote_url: str | None) -> str:
    cleaned = str(remote_url or "").strip()
    if not cleaned:
        raise GitRepositoryError("Remote URL is required.")
    if "\n" in cleaned or "\r" in cleaned:
        raise GitRepositoryError("Remote URL must be a single line.")
    return cleaned


def _clean_pathspec(path: str | None) -> str | None:
    cleaned = str(path or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("/") or "\\" in cleaned:
        raise GitRepositoryError("Diff path must be relative to the versioned workspace.")
    if any(part == ".." for part in Path(cleaned).parts):
        raise GitRepositoryError("Diff path must stay inside the versioned workspace.")
    return cleaned
