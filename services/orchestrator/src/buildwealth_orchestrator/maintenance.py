from __future__ import annotations

import argparse
import json
from typing import Any

from buildwealth_orchestrator import main as app_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="buildwealth-maintenance",
        description="Run BuildWealth hosted maintenance jobs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    purge_parser = subparsers.add_parser(
        "purge-due-account-data-deletions",
        help="Purge account data deletion requests whose recovery window has ended.",
    )
    purge_parser.add_argument(
        "--due-at",
        default=None,
        help="ISO timestamp used as the due cutoff. Defaults to now.",
    )
    purge_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of due deletion requests to process.",
    )
    purge_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print indented JSON.",
    )
    return parser


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "purge-due-account-data-deletions":
        return app_main.purge_due_account_data_deletions(
            due_at=args.due_at,
            limit=max(1, int(args.limit)),
        )
    raise ValueError(f"Unknown maintenance command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_command(args)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
