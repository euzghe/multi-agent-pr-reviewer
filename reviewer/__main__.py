"""CLI entrypoint.

Local:
    reviewer --repo owner/name --pr 123 [--dry-run]

GitHub Action:
    No flags needed — reads GITHUB_REPOSITORY and GITHUB_EVENT_PATH.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from .orchestrator import review_pr


def _pr_from_event() -> int | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        return None
    with open(event_path) as f:
        event = json.load(f)
    pr = event.get("pull_request") or {}
    return pr.get("number")


def main() -> None:
    parser = argparse.ArgumentParser(prog="reviewer")
    parser.add_argument("--repo", help="owner/name (default: $GITHUB_REPOSITORY)")
    parser.add_argument("--pr", type=int, help="PR number (default: from event)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the comment to stdout instead of posting",
    )
    args = parser.parse_args()

    repo = args.repo or os.environ.get("GITHUB_REPOSITORY")
    pr = args.pr or _pr_from_event()

    if not repo or not pr:
        parser.error("repo and pr are required (via flags or env)")

    result = asyncio.run(review_pr(repo, pr, dry_run=args.dry_run))

    if result["verdict"] == "request_changes":
        sys.exit(1)


if __name__ == "__main__":
    main()
