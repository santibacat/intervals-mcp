"""Small diagnostics CLI; planning work is exposed through MCP."""

import argparse
import asyncio
import json
from collections.abc import Sequence

from pydantic import ValidationError

from .client import IntervalsClient
from .config import get_settings
from .errors import IntervalsError
from .mcp_server import main as run_mcp


async def doctor() -> int:
    try:
        settings = get_settings()
        async with IntervalsClient(settings) as client:
            folders = await client.list_folders()
    except (IntervalsError, ValidationError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "athlete_id": settings.intervals_athlete_id,
                "library_containers_visible": len(folders),
                "draft_prefix": settings.draft_prefix,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="intervals-mcp-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check credentials and read access")
    subparsers.add_parser("mcp", help="Run the MCP server over stdio")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        run_mcp()
        return
    raise SystemExit(asyncio.run(doctor()))
