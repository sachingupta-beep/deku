#!/usr/bin/env python3
"""Optional Headroom prompt compression for the grader / judge LLM calls.

    DEKU_GRADER_HEADROOM_ENABLED=true    # default false -- opt in explicitly

Applies to the grader path only: `run_workflows.Anthropic.message`,
`run_workflows.OpenAI.message`, and the `run_rubric` judge that subclasses them.
The agent path (`claude_code/bridge.py`) is deliberately NOT wired up -- see
"WHY NOT THE AGENT PATH" below, which is the whole reason this module is scoped
the way it is.

py3.9-compatible: the graders run inside the task container, whose interpreter
is older than the 3.12 host (see requirements.txt).

# ---------------------------------------------------------------------------
# WHY NOT THE AGENT PATH
# ---------------------------------------------------------------------------
# Measured over the 230 recorded completions in `jobs/*/agent/completions/`:
#
#     requests carrying cache_control:  230 / 230
#     cache_read_input_tokens:       16,299,305   (98.5% of prompt tokens)
#     cache_creation_input_tokens:      244,473   ( 1.5%)
#     fresh input_tokens:                     0   ( 0.0%)
#
# At this repo's own rates (harness/finance/pricing.py: read 0.10x, write
# 1.25x) that traffic costs ~1.94M token-equivalents. Compression rewrites the
# message prefix, so every downstream cache breakpoint misses; at the ~9%
# compression Headroom actually achieves on comparable agentic traffic the same
# traffic would cost ~15.0M -- about 7.8x MORE. Prefix compression and prompt
# caching are mutually exclusive, and caching is already winning by ~10x.
#
# The grader path is the opposite case: it sends plain system/tools/messages
# with no cache_control anywhere, so every prompt token bills at full 1.0x and
# there is no cache to break. That is the only place compression pays here.
#
# `_has_cache_control` below is the interlock that keeps this true. If anyone
# later adds prompt caching to the grader path, compression stands down
# automatically rather than silently costing ~8x.
#
# ---------------------------------------------------------------------------
# FAIL-OPEN / FAIL-QUIET
# ---------------------------------------------------------------------------
# `headroom` is NOT in requirements.txt and is NOT installed in any task
# container today. Every failure mode -- missing import, compress() raising,
# a malformed return -- yields the ORIGINAL messages unchanged. Grading is a
# scoring path: a compression bug must never be able to change a trial's score.
# That is also what makes this file safe to land with no Dockerfile changes;
# enabling it is a separate, deliberate step (see README note at the bottom).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

# Tri-state probe: None = not yet attempted, True/False = result. One-shot so a
# missing install costs one stderr line per process, not one per judged
# dimension.
_HEADROOM_AVAILABLE = None  # type: Any
_compress = None  # type: Any
_CompressConfig = None  # type: Any

# Cumulative, process-wide. Read via stats() so a caller can fold it into the
# run's usage record without this module owning a file format.
_STATS = {
    "calls_compressed": 0,
    "calls_skipped": 0,
    "tokens_before": 0,
    "tokens_after": 0,
    "tokens_saved": 0,
}

_WARNED = set()  # type: set


def _warn_once(key: str, msg: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    sys.stderr.write("[grader_compress] {}\n".format(msg))


def _probe() -> bool:
    global _HEADROOM_AVAILABLE, _compress, _CompressConfig
    if _HEADROOM_AVAILABLE is not None:
        return _HEADROOM_AVAILABLE
    try:
        from headroom import compress, CompressConfig  # type: ignore
        _compress = compress
        _CompressConfig = CompressConfig
        _HEADROOM_AVAILABLE = True
    except Exception as exc:
        _warn_once(
            "import",
            "headroom not importable, compression disabled "
            "(grading proceeds uncompressed): {}".format(exc),
        )
        _HEADROOM_AVAILABLE = False
    return _HEADROOM_AVAILABLE


def _truthy(value) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    """Default OFF. Compression must be opted into, never inherited."""
    return _truthy(os.environ.get("DEKU_GRADER_HEADROOM_ENABLED"))


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _model_hint(model: str) -> str:
    """Route Deku model ids to a tokenizer Headroom actually recognises.

    Headroom sizes messages by string-matching the model name against its
    internal table; an unknown name silently falls back to a generic tokenizer
    that over-estimates Anthropic models by ~30%, which skews both the
    min-tokens gate and the target-ratio budget.

    Deku ids are bare families -- `claude-sonnet-4-5` (the grader/judge
    default), `claude-opus-4-8`, `claude-haiku-4-5` (harness/finance/pricing.py)
    -- and none of them match Headroom's table. They are all the same Anthropic
    tokenizer, so mapping the whole `claude-*` family to one known id is correct
    for sizing regardless of which family is selected.

    Passed through untouched for non-Anthropic ids (gpt-*, o*), where Headroom's
    own OpenAI tokenizers already match.
    """
    name = (model or "").strip().lower()
    if name.startswith("claude"):
        return "anthropic/claude-opus-4-20250514"
    return model


def _has_cache_control(messages) -> bool:
    """True if ANY message carries a cache_control breakpoint.

    The interlock described in the module docstring. Compressing a cached
    prefix trades a 0.10x cache read for a 1.0x fresh read plus a 1.25x
    rewrite -- strictly worse than doing nothing, at any compression ratio
    Headroom achieves. So a cached conversation is never compressed.
    """
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        if "cache_control" in message:
            return True
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    return True
    return False


def _flatten_text_blocks(message):
    """Collapse a pure-text-block message to bare-string content.

    Headroom's text/JSON compressors only engage on string content; they no-op
    on the block-shaped content the Anthropic Messages API uses, which is what
    the grader loop builds. Flattening exposes prose to the compressor.

    Returned UNCHANGED when content is already a string, is empty, or holds ANY
    non-plain-text block -- tool_use, tool_result, image, thinking, or a text
    block carrying cache_control/citations. Those encode structure the grader's
    tool loop depends on, and a tool_use/tool_result pair that stops matching
    is an upstream 400, not a smaller prompt.
    """
    if not isinstance(message, dict):
        return message
    content = message.get("content")
    if not isinstance(content, list) or not content:
        return message
    parts = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            return message
        if set(block.keys()) - {"type", "text"}:
            return message
        parts.append(block.get("text") or "")
    flattened = {k: v for k, v in message.items() if k != "content"}
    flattened["content"] = "\n".join(parts)
    return flattened


def compress_messages(model: str, messages: List[Dict]) -> List[Dict]:
    """Return `messages` compressed, or the original list on any doubt.

    NEVER raises. The system prompt is not passed in and is never compressed:
    the grader and judge system prompts carry the verdict/JSON contract that
    score parsing depends on, so they are load-bearing verbatim.
    """
    if not enabled():
        return messages
    if not isinstance(messages, list) or not messages:
        return messages
    if _has_cache_control(messages):
        _warn_once(
            "cache",
            "messages carry cache_control -- compression stood down "
            "(compressing a cached prefix costs more than it saves)",
        )
        _STATS["calls_skipped"] += 1
        return messages
    if not _probe():
        _STATS["calls_skipped"] += 1
        return messages

    try:
        config = _CompressConfig(
            compress_user_messages=True,
            compress_system_messages=False,
            protect_recent=_int_env("DEKU_GRADER_HEADROOM_PROTECT_RECENT", 2),
            min_tokens_to_compress=_int_env("DEKU_GRADER_HEADROOM_MIN_TOKENS", 500),
            target_ratio=_float_env("DEKU_GRADER_HEADROOM_TARGET_RATIO", 0.4),
        )
        flattened = [_flatten_text_blocks(m) for m in messages]
        result = _compress(flattened, model=_model_hint(model), config=config)
    except Exception as exc:
        _warn_once("compress", "compress() raised, sending uncompressed: {!r}".format(exc))
        _STATS["calls_skipped"] += 1
        return messages

    saved = int(getattr(result, "tokens_saved", 0) or 0)
    out = getattr(result, "messages", None)
    if saved <= 0 or not isinstance(out, list) or len(out) != len(flattened):
        _STATS["calls_skipped"] += 1
        return messages

    # Restore the original block-shaped message wherever compression was a
    # no-op, so flattening never alters the wire shape of anything Headroom
    # did not actually rewrite.
    merged = [
        new if new != flat else original
        for original, flat, new in zip(messages, flattened, out)
    ]

    before = int(getattr(result, "tokens_before", 0) or 0)
    after = int(getattr(result, "tokens_after", 0) or 0)
    _STATS["calls_compressed"] += 1
    _STATS["tokens_before"] += before
    _STATS["tokens_after"] += after
    _STATS["tokens_saved"] += saved

    # One line per compressed call, to stderr, which lands in the run log.
    # Without this a working integration and a silently-inert one look
    # identical -- every failure path here returns the input unchanged, so
    # "no errors" is not evidence that anything happened. This is the only
    # signal that compression actually ran.
    sys.stderr.write(
        "[grader_compress] {} -> {} tokens (saved {}, {:.1f}%)\n".format(
            before, after, saved, (saved / before * 100) if before else 0.0
        )
    )
    return merged


def stats() -> Dict[str, int]:
    """Process-wide compression totals, safe to fold into a run's usage record."""
    return dict(_STATS)


def reset_stats() -> None:
    for key in _STATS:
        _STATS[key] = 0
