#!/usr/bin/env python3
"""Tests for grader_compress.

    python3 -m pytest harness/eval/test_grader_compress.py

These run on the HOST, where `headroom` is not installed. That is deliberate:
the no-headroom path is the one every task container is on today, so it is the
path that has to be proven safe. The tests that need a real compressor install a
fake one, so the suite never depends on the private package being available.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import grader_compress  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Each test starts with a clean probe, clean stats, and compression ON.

    The module caches its import probe and warning set process-wide, which is
    correct in production (one stderr line per run, not per dimension) and wrong
    across tests.
    """
    monkeypatch.setattr(grader_compress, "_HEADROOM_AVAILABLE", None)
    monkeypatch.setattr(grader_compress, "_compress", None)
    monkeypatch.setattr(grader_compress, "_CompressConfig", None)
    monkeypatch.setattr(grader_compress, "_WARNED", set())
    grader_compress.reset_stats()
    monkeypatch.setenv("DEKU_GRADER_HEADROOM_ENABLED", "true")
    yield
    grader_compress.reset_stats()


class _Result:
    def __init__(self, messages, saved, before=1000, after=600):
        self.messages = messages
        self.tokens_saved = saved
        self.tokens_before = before
        self.tokens_after = after


def _install_fake(monkeypatch, fn):
    """Stand in for headroom.compress without needing the real package."""
    monkeypatch.setattr(grader_compress, "_HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(grader_compress, "_compress", fn)
    monkeypatch.setattr(grader_compress, "_CompressConfig", lambda **kw: kw)


MESSAGES = [
    {"role": "user", "content": "a" * 4000},
    {"role": "assistant", "content": "ok"},
]


# --- default-off ------------------------------------------------------------

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DEKU_GRADER_HEADROOM_ENABLED", raising=False)
    assert grader_compress.enabled() is False
    assert grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES) is MESSAGES


def test_disabled_does_not_even_probe(monkeypatch):
    """An opted-out run must not pay the import attempt or emit a warning."""
    monkeypatch.delenv("DEKU_GRADER_HEADROOM_ENABLED", raising=False)
    called = []
    monkeypatch.setattr(grader_compress, "_probe", lambda: called.append(1) or True)
    grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    assert called == []


# --- fail-open --------------------------------------------------------------

def test_missing_headroom_returns_original_unchanged():
    """The state every task container is in today."""
    out = grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    assert out is MESSAGES
    assert grader_compress.stats()["calls_compressed"] == 0
    assert grader_compress.stats()["calls_skipped"] == 1


def test_compress_raising_returns_original(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("compressor exploded")
    _install_fake(monkeypatch, boom)
    assert grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES) is MESSAGES


def test_wrong_length_return_is_rejected(monkeypatch):
    """A compressor that drops a message would desync tool_use/tool_result."""
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(msgs[:1], saved=500))
    assert grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES) is MESSAGES


def test_zero_saving_returns_original(monkeypatch):
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(msgs, saved=0))
    assert grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES) is MESSAGES


def test_empty_and_malformed_inputs_pass_through():
    assert grader_compress.compress_messages("claude-sonnet-4-5", []) == []
    assert grader_compress.compress_messages("claude-sonnet-4-5", None) is None


# --- the cache interlock ----------------------------------------------------

def test_cache_control_on_block_stands_down(monkeypatch):
    """The whole reason this module is grader-only. Must never compress a
    cached prefix -- that trades a 0.10x read for a 1.0x read + 1.25x write."""
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(msgs, saved=9999))
    cached = [{
        "role": "user",
        "content": [{"type": "text", "text": "x" * 4000,
                     "cache_control": {"type": "ephemeral"}}],
    }]
    assert grader_compress.compress_messages("claude-sonnet-4-5", cached) is cached
    assert grader_compress.stats()["calls_compressed"] == 0


def test_cache_control_at_message_level_stands_down(monkeypatch):
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(msgs, saved=9999))
    cached = [{"role": "user", "content": "hi",
               "cache_control": {"type": "ephemeral"}}]
    assert grader_compress.compress_messages("claude-sonnet-4-5", cached) is cached


def test_uncached_messages_are_not_stood_down(monkeypatch):
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(
        [{"role": "user", "content": "short"}, msgs[1]], saved=500))
    out = grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    assert out is not MESSAGES
    assert grader_compress.stats()["calls_compressed"] == 1


# --- tokenizer hint ---------------------------------------------------------

@pytest.mark.parametrize("model", [
    "claude-sonnet-4-5-20250929",   # DEFAULT_GRADER_MODEL
    "claude-sonnet-4-5",
    "claude-opus-4-8",
    "claude-haiku-4-5",
])
def test_hint_fires_for_every_model_this_repo_actually_uses(model):
    """Regression guard for a real bug seen elsewhere: a hint written against
    Bedrock ARNs that never matched the ids actually on the wire, so it was dead
    code across 1,394 production calls. Assert against the real ids instead."""
    assert grader_compress._model_hint(model) == "anthropic/claude-opus-4-20250514"


@pytest.mark.parametrize("model", ["gpt-5.6", "o4-mini"])
def test_hint_passes_through_openai_models(model):
    assert grader_compress._model_hint(model) == model


# --- block flattening -------------------------------------------------------

def test_pure_text_blocks_are_flattened():
    msg = {"role": "user", "content": [{"type": "text", "text": "a"},
                                       {"type": "text", "text": "b"}]}
    assert grader_compress._flatten_text_blocks(msg)["content"] == "a\nb"


@pytest.mark.parametrize("block", [
    {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
    {"type": "tool_result", "tool_use_id": "t1", "content": "r"},
    {"type": "image", "source": {}},
    {"type": "thinking", "thinking": "...", "signature": "sig"},
    {"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}},
])
def test_structured_blocks_are_left_alone(block):
    """Flattening these would desync tool pairing, drop images, or invalidate a
    thinking signature -- all upstream 400s rather than smaller prompts."""
    msg = {"role": "user", "content": [block]}
    assert grader_compress._flatten_text_blocks(msg) is msg


def test_string_content_is_untouched():
    msg = {"role": "user", "content": "already a string"}
    assert grader_compress._flatten_text_blocks(msg) is msg


def test_uncompressed_messages_keep_original_block_shape(monkeypatch):
    """Flattening is an input transform for the compressor only. Anything the
    compressor did not rewrite must go on the wire in its original shape."""
    original = [
        {"role": "user", "content": [{"type": "text", "text": "untouched"}]},
        {"role": "user", "content": [{"type": "text", "text": "rewritten"}]},
    ]
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(
        [msgs[0], {"role": "user", "content": "smaller"}], saved=100))
    out = grader_compress.compress_messages("claude-sonnet-4-5", original)
    assert out[0] == original[0]          # restored to block shape
    assert out[1]["content"] == "smaller"  # kept compressed


# --- config + telemetry -----------------------------------------------------

def test_system_messages_are_never_compressed(monkeypatch):
    """Grader/judge system prompts carry the JSON verdict contract score parsing
    depends on."""
    seen = {}
    def capture(msgs, **kw):
        seen.update(kw.get("config") or {})
        return _Result(msgs, saved=0)
    _install_fake(monkeypatch, capture)
    grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    assert seen["compress_system_messages"] is False
    assert seen["compress_user_messages"] is True


def test_env_knobs_are_honoured(monkeypatch):
    monkeypatch.setenv("DEKU_GRADER_HEADROOM_TARGET_RATIO", "0.7")
    monkeypatch.setenv("DEKU_GRADER_HEADROOM_PROTECT_RECENT", "5")
    monkeypatch.setenv("DEKU_GRADER_HEADROOM_MIN_TOKENS", "123")
    seen = {}
    def capture(msgs, **kw):
        seen.update(kw.get("config") or {})
        return _Result(msgs, saved=0)
    _install_fake(monkeypatch, capture)
    grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    assert seen["target_ratio"] == 0.7
    assert seen["protect_recent"] == 5
    assert seen["min_tokens_to_compress"] == 123


def test_malformed_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("DEKU_GRADER_HEADROOM_TARGET_RATIO", "not-a-float")
    monkeypatch.setenv("DEKU_GRADER_HEADROOM_MIN_TOKENS", "")
    seen = {}
    def capture(msgs, **kw):
        seen.update(kw.get("config") or {})
        return _Result(msgs, saved=0)
    _install_fake(monkeypatch, capture)
    grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    assert seen["target_ratio"] == 0.4
    assert seen["min_tokens_to_compress"] == 500


def test_stats_accumulate(monkeypatch):
    _install_fake(monkeypatch, lambda msgs, **_k: _Result(
        [{"role": "user", "content": "s"}, msgs[1]], saved=400,
        before=1000, after=600))
    grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    grader_compress.compress_messages("claude-sonnet-4-5", MESSAGES)
    stats = grader_compress.stats()
    assert stats["calls_compressed"] == 2
    assert stats["tokens_saved"] == 800
    assert stats["tokens_before"] == 2000


def test_stats_is_a_copy():
    grader_compress.stats()["tokens_saved"] = 999
    assert grader_compress.stats()["tokens_saved"] == 0
