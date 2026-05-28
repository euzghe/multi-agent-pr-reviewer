"""Judge agent.

Takes the raw findings from the 4 reviewer agents, deduplicates overlapping
issues, prioritizes by severity, and emits a structured verdict that the
orchestrator formats into a single markdown PR comment.
"""
from __future__ import annotations

import json

import anthropic

MODEL = "claude-opus-4-7"

JUDGE_SYSTEM = """You are the lead reviewer in a multi-agent code review system.

Four specialist agents (security, style, coverage, logic) have independently
analyzed a PR diff. Your job is to:

  1. Deduplicate overlapping findings (the same issue may be flagged twice).
  2. Re-rank by real impact (the specialists can be over-eager).
  3. Bucket findings into must_fix / should_fix / consider.
  4. Decide an overall verdict.

Be strict about must_fix — only true blockers (security flaws, broken logic,
data loss risk). Style preferences belong in `consider`, not `should_fix`.
If the agents found nothing real, return empty buckets and verdict=approve."""

JUDGE_USER_TEMPLATE = """Here are the raw findings from the four reviewer agents.

```json
{findings_json}
```

Synthesize into the structured verdict."""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verdict": {
            "type": "string",
            "enum": ["approve", "comment", "request_changes"],
        },
        "must_fix": {"type": "array", "items": {"$ref": "#/$defs/finding"}},
        "should_fix": {"type": "array", "items": {"$ref": "#/$defs/finding"}},
        "consider": {"type": "array", "items": {"$ref": "#/$defs/finding"}},
    },
    "required": ["summary", "verdict", "must_fix", "should_fix", "consider"],
    "additionalProperties": False,
    "$defs": {
        "finding": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "file": {"type": "string"},
                "line": {"type": ["integer", "null"]},
                "details": {"type": "string"},
                "suggestion": {"type": "string"},
                "flagged_by": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["security", "style", "coverage", "logic"],
                    },
                },
            },
            "required": ["title", "file", "line", "details", "suggestion", "flagged_by"],
            "additionalProperties": False,
        }
    },
}


async def run_judge(agent_results: list[dict]) -> dict:
    """Synthesize agent findings into a final verdict."""
    payload = [
        {"agent": r["name"], "findings": r["findings"]} for r in agent_results
    ]
    findings_json = json.dumps(payload, indent=2)

    async with anthropic.AsyncAnthropic() as client:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=JUDGE_SYSTEM,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": JUDGE_USER_TEMPLATE.format(findings_json=findings_json),
                }
            ],
        )

    text = next((b.text for b in response.content if b.type == "text"), "")
    verdict = json.loads(text)
    verdict["_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return verdict
