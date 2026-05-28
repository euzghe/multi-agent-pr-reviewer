"""Async GitHub REST client — just the endpoints we need."""
from __future__ import annotations

import httpx


class GitHubClient:
    def __init__(self, token: str, repo: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.repo = repo
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "multi-agent-pr-reviewer",
            },
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def get_pr_diff(self, pr_number: int) -> str:
        r = await self._client.get(
            f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        r.raise_for_status()
        return r.text

    async def get_pr_metadata(self, pr_number: int) -> dict:
        r = await self._client.get(f"{self.base_url}/repos/{self.repo}/pulls/{pr_number}")
        r.raise_for_status()
        return r.json()

    async def post_comment(self, pr_number: int, body: str) -> dict:
        r = await self._client.post(
            f"{self.base_url}/repos/{self.repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        r.raise_for_status()
        return r.json()
