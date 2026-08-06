#!/usr/bin/env python3
"""Self-checks for the OpenAI grader adapter in run_workflows.py.

    bin/deku-py harness/eval/test_openai_grader.py

No network. These verify the translation layer only, which is where a silent bug
would be worst: the tool-calling loop is shared by both providers, so a botched
conversion does not crash -- it regrades against the wrong observation and emits
a plausible number.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_workflows import (  # noqa: E402
    _messages_to_openai,
    _resolve_provider,
    _response_to_anthropic,
    _tools_to_openai,
    make_llm,
    Anthropic,
    OpenAI,
)

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}\n     got  {got}\n     want {want}")
        print(f"[FAIL] {label}")
    else:
        print(f"[ ok ] {label}")


# --------------------------------------------------------------- provider pick
for model, want in [
    ("claude-sonnet-4-5-20250929", "anthropic"),
    ("gpt-4o", "openai"),
    ("gpt-5", "openai"),
    ("o3-mini", "openai"),
    ("some-local-model", "anthropic"),
]:
    check(f"provider inferred for {model}", _resolve_provider(model), want)

os.environ["DEKU_GRADER_PROVIDER"] = "openai"
check("explicit env overrides inference", _resolve_provider("claude-sonnet-4-5"), "openai")
check("make_llm honours the override", type(make_llm("claude-sonnet-4-5")).__name__, "OpenAI")
del os.environ["DEKU_GRADER_PROVIDER"]
check("make_llm defaults to Anthropic", type(make_llm("claude-sonnet-4-5")).__name__, "Anthropic")

# ---------------------------------------------------------------------- tools
check(
    "tool schema: input_schema -> parameters",
    _tools_to_openai([{"name": "browser_click", "description": "Click.",
                       "input_schema": {"type": "object",
                                        "properties": {"ref": {"type": "integer"}},
                                        "required": ["ref"]}}]),
    [{"type": "function", "function": {
        "name": "browser_click", "description": "Click.",
        "parameters": {"type": "object", "properties": {"ref": {"type": "integer"}},
                       "required": ["ref"]}}}],
)

# ------------------------------------------------------------------- messages
check(
    "plain string user turn passes through, system is hoisted",
    _messages_to_openai("SYS", [{"role": "user", "content": "Substep: open the app"}]),
    [{"role": "system", "content": "SYS"},
     {"role": "user", "content": "Substep: open the app"}],
)

check(
    "assistant tool_use -> tool_calls with JSON-string arguments",
    _messages_to_openai("SYS", [{"role": "assistant", "content": [
        {"type": "text", "text": "let me look"},
        {"type": "tool_use", "id": "tu_1", "name": "browser_click", "input": {"ref": 3}},
    ]}]),
    [{"role": "system", "content": "SYS"},
     {"role": "assistant", "content": "let me look", "tool_calls": [
         {"id": "tu_1", "type": "function",
          "function": {"name": "browser_click", "arguments": '{"ref": 3}'}}]}],
)

# THE ASYMMETRY. Anthropic packs N tool results into ONE user turn; OpenAI needs
# one message per tool_call_id. Collapsing them loses the correlation and the
# grader scores against the wrong observation.
check(
    "two tool_results in one user turn -> two separate tool messages",
    _messages_to_openai("SYS", [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"},
        {"type": "tool_result", "tool_use_id": "tu_2", "content": "page text"},
    ]}]),
    [{"role": "system", "content": "SYS"},
     {"role": "tool", "tool_call_id": "tu_1", "content": "ok"},
     {"role": "tool", "tool_call_id": "tu_2", "content": "page text"}],
)

# ------------------------------------------------------------------- response
check(
    "tool_calls response -> tool_use blocks + stop_reason tool_use",
    _response_to_anthropic({"choices": [{"finish_reason": "tool_calls", "message": {
        "content": None,
        "tool_calls": [{"id": "call_9", "type": "function", "function": {
            "name": "report_result", "arguments": '{"passed": true, "note": "renders"}'}}]}}]}),
    {"content": [{"type": "tool_use", "id": "call_9", "name": "report_result",
                  "input": {"passed": True, "note": "renders"}}],
     "stop_reason": "tool_use"},
)

check(
    "plain text response -> text block + end_turn",
    _response_to_anthropic({"choices": [{"finish_reason": "stop",
                                         "message": {"content": "done"}}]}),
    {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn"},
)

check(
    "length finish maps to max_tokens",
    _response_to_anthropic({"choices": [{"finish_reason": "length",
                                         "message": {"content": "trunc"}}]})["stop_reason"],
    "max_tokens",
)

# Malformed arguments must degrade to {} rather than raise: a grader-side JSON
# fault should surface as a tool error, not kill the substep mid-workflow.
check(
    "unparseable tool arguments degrade to empty input",
    _response_to_anthropic({"choices": [{"finish_reason": "tool_calls", "message": {
        "content": None,
        "tool_calls": [{"id": "c1", "function": {"name": "browser_click",
                                                 "arguments": "{not json"}}]}}]})["content"][0]["input"],
    {},
)

check(
    "empty choices does not raise",
    _response_to_anthropic({"choices": []}),
    {"content": [], "stop_reason": "end_turn"},
)

# ------------------------------------------------------- round-trip integrity
# The loop appends the assistant blocks it received straight back into messages,
# so a response that survives conversion must convert BACK into a valid request.
resp = _response_to_anthropic({"choices": [{"finish_reason": "tool_calls", "message": {
    "content": "checking", "tool_calls": [
        {"id": "tu_a", "function": {"name": "browser_snapshot", "arguments": "{}"}}]}}]})
convo = [
    {"role": "user", "content": "Substep: verify the page"},
    {"role": "assistant", "content": resp["content"]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_a",
                                  "content": "title=Calculator"}]},
]
rt = _messages_to_openai("SYS", convo)
check("round-trip: assistant tool_call id preserved",
      rt[2]["tool_calls"][0]["id"], "tu_a")
check("round-trip: tool reply correlates to the same id",
      (rt[3]["role"], rt[3]["tool_call_id"]), ("tool", "tu_a"))
check("round-trip: arguments remain valid JSON",
      json.loads(rt[2]["tool_calls"][0]["function"]["arguments"]), {})

# ------------------------------------------------------------------ endpoints
check("OpenAI client default base_url", OpenAI("gpt-4o").base_url, "https://api.openai.com/v1")
check("Anthropic client unchanged", Anthropic("claude-sonnet-4-5").base_url,
      os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/"))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
