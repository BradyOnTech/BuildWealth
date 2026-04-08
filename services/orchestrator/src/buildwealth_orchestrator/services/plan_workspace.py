from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class PlanNotFoundError(FileNotFoundError):
    pass


class PlanWorkspace:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "index.json"
        self._initialize_index()

    def _initialize_index(self) -> None:
        if self.index_path.exists():
            return

        self._save_index(
            {
                "active_plan_id": None,
                "plans": [],
            }
        )

    def _load_index(self) -> dict[str, Any]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._initialize_index()
            return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index_payload: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")

    def _plan_dir(self, plan_id: str) -> Path:
        return self.base_dir / plan_id

    def _artifacts_dir(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "artifacts"

    @staticmethod
    def _slug(value: str, default: str = "artifact") -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return cleaned or default

    @staticmethod
    def _find_plan_metadata(index_payload: dict[str, Any], plan_id: str) -> dict[str, Any]:
        for plan in index_payload.get("plans", []):
            if plan.get("id") == plan_id:
                return plan
        raise PlanNotFoundError(f"Plan not found: {plan_id}")

    def _touch_plan(self, index_payload: dict[str, Any], plan_id: str) -> dict[str, Any]:
        plan = self._find_plan_metadata(index_payload, plan_id)
        plan["updated_at"] = utc_now_iso()
        return plan

    @staticmethod
    def _template_plan_markdown(title: str, description: str) -> str:
        lines = [f"# {title}", ""]
        if description:
            lines.extend([description.strip(), ""])
        lines.extend(
            [
                "## Goal",
                "",
                "- Define the primary financial outcome this plan is trying to achieve.",
                "",
                "## Constraints",
                "",
                "- Add constraints (tax, liquidity, risk, timeline).",
                "",
                "## Strategy",
                "",
                "- Document the high-level approach and tradeoffs.",
                "",
                "## Questions For Copilot",
                "",
                "- Add the next research questions to run through the agent workflow.",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _template_plan_yaml() -> str:
        return "\n".join(
            [
                "currency: USD",
                "state: MN",
                "targets:",
                "  retirement_age: null",
                "  annual_savings_usd: null",
                "risk_limits:",
                "  max_single_holding_pct: null",
                "  max_equity_allocation_pct: null",
                "assumptions:",
                "  expected_return_baseline: null",
                "  expected_return_optimistic: null",
                "  expected_return_conservative: null",
                "notes: []",
                "",
            ]
        )

    @staticmethod
    def _template_tasks() -> str:
        return "\n".join(
            [
                "# Tasks",
                "",
                "- [ ] Run latest portfolio sync",
                "- [ ] Ask Copilot for concentration-risk review",
                "- [ ] Compare at least two contribution scenarios",
                "",
            ]
        )

    def create_plan(self, title: str, description: str = "") -> dict[str, Any]:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Plan title is required")

        plan_id = f"plan-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        plan_dir = self._plan_dir(plan_id)
        plan_dir.mkdir(parents=True, exist_ok=False)
        (plan_dir / "scenarios").mkdir(parents=True, exist_ok=True)
        (plan_dir / "artifacts").mkdir(parents=True, exist_ok=True)

        (plan_dir / "plan.md").write_text(
            self._template_plan_markdown(cleaned_title, description),
            encoding="utf-8",
        )
        (plan_dir / "plan.yaml").write_text(self._template_plan_yaml(), encoding="utf-8")
        (plan_dir / "tasks.md").write_text(self._template_tasks(), encoding="utf-8")
        (plan_dir / "context.md").write_text("", encoding="utf-8")
        (plan_dir / "decisions.jsonl").write_text("", encoding="utf-8")

        now = utc_now_iso()
        metadata = {
            "id": plan_id,
            "title": cleaned_title,
            "description": description.strip() or "",
            "created_at": now,
            "updated_at": now,
        }

        index_payload = self._load_index()
        index_payload.setdefault("plans", []).append(metadata)
        if not index_payload.get("active_plan_id"):
            index_payload["active_plan_id"] = plan_id
        self._save_index(index_payload)

        self.refresh_context(plan_id)
        return self.get_plan(plan_id)

    def list_plans(self, limit: int = 100) -> list[dict[str, Any]]:
        index_payload = self._load_index()
        active_plan_id = index_payload.get("active_plan_id")
        plans = list(index_payload.get("plans", []))
        plans.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

        summaries: list[dict[str, Any]] = []
        for plan in plans[: max(1, limit)]:
            summaries.append(
                {
                    "id": plan.get("id"),
                    "title": plan.get("title", "Untitled Plan"),
                    "description": plan.get("description", ""),
                    "created_at": plan.get("created_at"),
                    "updated_at": plan.get("updated_at"),
                    "is_active": plan.get("id") == active_plan_id,
                }
            )
        return summaries

    def _load_decisions(self, plan_id: str, limit: int = 200) -> list[dict[str, Any]]:
        decisions_path = self._plan_dir(plan_id) / "decisions.jsonl"
        if not decisions_path.exists():
            return []

        rows: list[dict[str, Any]] = []
        for raw in decisions_path.read_text(encoding="utf-8").splitlines():
            text = raw.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError:
                continue

        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows[: max(1, limit)]

    def _list_artifacts(self, plan_id: str, limit: int = 40) -> list[dict[str, Any]]:
        artifacts_dir = self._artifacts_dir(plan_id)
        if not artifacts_dir.exists():
            return []

        files = sorted(artifacts_dir.glob("*.md"), reverse=True)
        artifacts: list[dict[str, Any]] = []

        for path in files[: max(1, limit)]:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            title = ""
            if lines:
                first = lines[0].strip()
                if first.startswith("# "):
                    title = first[2:].strip()
            artifacts.append(
                {
                    "id": path.stem,
                    "file_name": path.name,
                    "title": title or path.stem,
                    "created_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
            )

        return artifacts

    def read_artifact(self, plan_id: str, artifact_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        artifact_name = artifact_id if artifact_id.endswith(".md") else f"{artifact_id}.md"
        artifact_path = self._artifacts_dir(plan_id) / artifact_name
        if not artifact_path.exists():
            raise PlanNotFoundError(f"Artifact not found: {artifact_id}")

        text = artifact_path.read_text(encoding="utf-8")
        title = artifact_path.stem
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            title = lines[0][2:].strip()

        return {
            "id": artifact_path.stem,
            "file_name": artifact_path.name,
            "title": title,
            "created_at": datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "content": text,
        }

    def write_artifact(
        self,
        plan_id: str,
        title: str,
        markdown: str,
        kind: str = "workflow",
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        artifacts_dir = self._artifacts_dir(plan_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        file_stem = f"{timestamp}-{self._slug(kind, default='workflow')}-{self._slug(title)}"
        artifact_path = artifacts_dir / f"{file_stem}.md"
        artifact_path.write_text(markdown, encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        return {
            "id": artifact_path.stem,
            "file_name": artifact_path.name,
            "title": title,
            "created_at": datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=timezone.utc).isoformat(),
        }

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        index_payload = self._load_index()
        metadata = self._find_plan_metadata(index_payload, plan_id)

        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan directory not found for {plan_id}")

        def read_optional(path: Path) -> str:
            if not path.exists():
                return ""
            return path.read_text(encoding="utf-8")

        return {
            "id": metadata.get("id"),
            "title": metadata.get("title", "Untitled Plan"),
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "is_active": metadata.get("id") == index_payload.get("active_plan_id"),
            "files": {
                "plan_markdown": read_optional(plan_dir / "plan.md"),
                "plan_yaml": read_optional(plan_dir / "plan.yaml"),
                "tasks_markdown": read_optional(plan_dir / "tasks.md"),
                "context_markdown": read_optional(plan_dir / "context.md"),
            },
            "decisions": self._load_decisions(plan_id),
            "artifacts": self._list_artifacts(plan_id),
        }

    def set_active_plan(self, plan_id: str) -> dict[str, Any]:
        index_payload = self._load_index()
        metadata = self._find_plan_metadata(index_payload, plan_id)
        index_payload["active_plan_id"] = plan_id
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        return {
            "id": metadata.get("id"),
            "title": metadata.get("title", "Untitled Plan"),
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "is_active": True,
        }

    def update_plan_files(
        self,
        plan_id: str,
        plan_markdown: str | None = None,
        tasks_markdown: str | None = None,
    ) -> dict[str, Any]:
        if plan_markdown is None and tasks_markdown is None:
            raise ValueError("At least one file payload is required")

        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        if plan_markdown is not None:
            (plan_dir / "plan.md").write_text(plan_markdown, encoding="utf-8")
        if tasks_markdown is not None:
            (plan_dir / "tasks.md").write_text(tasks_markdown, encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        self.refresh_context(plan_id)
        return self.get_plan(plan_id)

    def append_decision(
        self,
        plan_id: str,
        summary: str,
        rationale: str | None = None,
        status: str = "proposed",
    ) -> dict[str, Any]:
        cleaned_summary = summary.strip()
        if not cleaned_summary:
            raise ValueError("Decision summary is required")

        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        decision = {
            "id": f"decision-{uuid.uuid4().hex[:10]}",
            "created_at": utc_now_iso(),
            "summary": cleaned_summary,
            "rationale": (rationale or "").strip(),
            "status": (status or "proposed").strip().lower(),
        }

        decisions_path = plan_dir / "decisions.jsonl"
        with decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision))
            handle.write("\n")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        self.refresh_context(plan_id)
        return decision

    def refresh_context(self, plan_id: str) -> str:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        index_payload = self._load_index()
        metadata = self._find_plan_metadata(index_payload, plan_id)

        plan_text = (plan_dir / "plan.md").read_text(encoding="utf-8") if (plan_dir / "plan.md").exists() else ""
        tasks_text = (plan_dir / "tasks.md").read_text(encoding="utf-8") if (plan_dir / "tasks.md").exists() else ""
        decisions = self._load_decisions(plan_id, limit=8)

        decision_lines: list[str] = []
        for item in decisions:
            decision_lines.append(
                f"- [{item.get('status', 'proposed')}] {item.get('summary', '')} ({item.get('created_at', '')})"
            )

        context_lines = [
            f"# Plan Context: {metadata.get('title', 'Untitled Plan')}",
            "",
            "## Plan Summary",
            "",
            plan_text.strip()[:4000] or "No plan markdown yet.",
            "",
            "## Task Snapshot",
            "",
            tasks_text.strip()[:2000] or "No tasks documented yet.",
            "",
            "## Recent Decisions",
            "",
            "\n".join(decision_lines) if decision_lines else "- No decisions logged yet.",
            "",
        ]
        context_text = "\n".join(context_lines)
        (plan_dir / "context.md").write_text(context_text, encoding="utf-8")
        return context_text

    def get_context_payload(self, plan_id: str | None = None, max_chars: int = 6000) -> dict[str, Any]:
        index_payload = self._load_index()
        resolved_plan_id = plan_id or index_payload.get("active_plan_id")
        if not resolved_plan_id:
            return {"note": "No active plan is configured."}

        detail = self.get_plan(str(resolved_plan_id))
        context_markdown = detail["files"].get("context_markdown", "")
        if not context_markdown:
            context_markdown = self.refresh_context(str(resolved_plan_id))
            detail = self.get_plan(str(resolved_plan_id))

        trimmed = context_markdown[:max_chars]
        if len(context_markdown) > max_chars:
            trimmed = f"{trimmed}..."

        return {
            "id": detail.get("id"),
            "title": detail.get("title"),
            "description": detail.get("description", ""),
            "is_active": detail.get("is_active", False),
            "updated_at": detail.get("updated_at"),
            "context_excerpt": trimmed,
        }

    def get_active_plan_id(self) -> str | None:
        index_payload = self._load_index()
        active_plan_id = index_payload.get("active_plan_id")
        if isinstance(active_plan_id, str) and active_plan_id.strip():
            return active_plan_id
        return None
