"""Constrained maintenance entrypoint for private agent task attachments."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from app.config import settings
from app.services.agent_runtime.attachment_recovery import reconcile_configured_storage


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Reconcile configured private task attachment storage")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("reconcile", help="recover configured attachment lifecycle state")
    return result


async def run(args: argparse.Namespace) -> int:
    if args.command != "reconcile":
        raise ValueError("unknown attachment maintenance command")
    if not settings.AGENT_TASK_ATTACHMENTS_ENABLED:
        raise PermissionError("agent task attachments are disabled")
    print(json.dumps(asdict(await reconcile_configured_storage()), sort_keys=True))
    return 0


def main() -> None:
    try:
        code = asyncio.run(run(parser().parse_args()))
    except Exception:
        # Storage and database details are operationally sensitive.
        print("Attachment reconciliation refused; verify the configured maintenance environment.")
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
