"""Reviewer agents.

Design note — prompt caching:
    All 4 agents send the SAME `system` (generic reviewer persona + the PR diff).
    That shared prefix is marked `cache_control: ephemeral`. The first agent
    pays the ~1.25x cache-write premium; the other three read at ~0.1x.
    Each agent differs only in the short user message that specifies focus.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import anthropic

MODEL = "claude-opus-4-7"

SYSTEM_TEMPLATE = """You are an expert code reviewer for a GitHub pull-request review system.

You will be given:
  1. The full PR diff (in this system prompt).
  2. A specific review focus (in the user message).

Be precise. Cite file paths and line numbers from the diff when possible.
Only flag real issues — do not invent findings. Empty findings is a valid output.

PR DIFF (unified diff format):
---
{diff}
---
"""

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "file": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["severity", "file", "line", "title", "details", "suggestion"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class AgentSpec:
    name: str
    focus_prompt: str


AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="security",
        focus_prompt=(
            "Perform a SECURITY review of the diff. Look for: injection vulnerabilities "
            "(SQL, command, XSS), authn/authz flaws, hardcoded secrets or credentials, "
            "insecure deserialization, missing input validation at trust boundaries, "
            "unsafe crypto, path traversal, SSRF. Ignore stylistic issues."
        ),
    ),
    AgentSpec(
        name="style",
        focus_prompt=(
            "Perform a STYLE and READABILITY review of the diff. Look for: unclear "
            "naming, dead code, overly complex functions, inconsistent formatting, "
            "missing or wrong type hints (in typed languages), and violations of "
            "the project's apparent conventions. Ignore correctness/security issues."
        ),
    ),
    AgentSpec(
        name="coverage",
        focus_prompt=(
            "Perform a TEST COVERAGE review of the diff. For each non-trivial code "
            "change, check whether the diff also adds or updates a test covering it. "
            "Flag untested logic, untested error paths, and tests that look superficial "
            "(e.g., only assert no exception was raised). Ignore non-code changes."
        ),
    ),
    AgentSpec(
        name="logic",
        focus_prompt=(
            "Perform a LOGIC and CORRECTNESS review of the diff. Look for: off-by-one "
            "errors, incorrect null/None handling, race conditions, resource leaks, "
            "wrong API usage, broken invariants, edge cases not handled, and "
            "regressions in behavior. Ignore style and security issues."
        ),
    ),
]


def _build_system(diff: str) -> list[dict]:
    return [
        {
            "type": "text",
            "text": SYSTEM_TEMPLATE.format(diff=diff),
            "cache_control": {"type": "ephemeral"},
        }
    ]


async def run_agent(
    client: anthropic.AsyncAnthropic, diff: str, spec: AgentSpec
) -> dict:
    """Run a single reviewer agent. Returns a dict: {name, findings, usage}."""
    response = await client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=_build_system(diff),
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": FINDINGS_SCHEMA},
        },
        messages=[{"role": "user", "content": spec.focus_prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
        findings = parsed.get("findings", [])
    except json.JSONDecodeError:
        findings = []

    return {
        "name": spec.name,
        "findings": findings,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0
            ),
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", 0
            ),
        },
    }


async def run_all_agents(diff: str) -> list[dict]:
    """Fan out all 4 reviewer agents in parallel."""
    async with anthropic.AsyncAnthropic() as client:
        return await asyncio.gather(*(run_agent(client, diff, spec) for spec in AGENTS))
