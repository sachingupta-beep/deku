#!/bin/bash
cd /Users/apple/Downloads/testing
echo "── Headroom integration check ──────────────────────────"
ls harness/eval/grader_compress.py >/dev/null 2>&1 && echo "✅ module present" || echo "❌ module MISSING"
[ "$(grep -c compress_messages harness/eval/run_workflows.py)" -ge 4 ] && echo "✅ wired into both grader clients" || echo "❌ NOT wired"
./.venv/bin/python -m pytest harness/eval/test_grader_compress.py -q 2>&1 | tail -1 | grep -q "passed" && echo "✅ $(./.venv/bin/python -m pytest harness/eval/test_grader_compress.py -q 2>&1 | tail -1)" || echo "❌ tests FAILED"
./.venv/bin/python -m pytest harness/ claude_code/ -q 2>&1 | tail -1 | grep -q "failed" && echo "❌ regressions" || echo "✅ no regressions ($(./.venv/bin/python -m pytest harness/ claude_code/ -q 2>&1 | tail -1))"
./.venv/bin/python harness/sync_verifier.py tasks/*/ --check 2>&1 | grep -q "in sync" && echo "✅ synced to $(ls tasks/*/tests/grader_compress.py 2>/dev/null | wc -l | tr -d ' ') tasks" || echo "❌ task drift"
./.venv/bin/python - <<'PY'
import sys,types,os
sys.path.insert(0,"harness/eval")
f=types.ModuleType("headroom")
class R:
    def __init__(s,m): s.messages=m; s.tokens_saved=900; s.tokens_before=1000; s.tokens_after=100
f.compress=lambda m,**k: R([{"role":"user","content":"<crushed>"}]); f.CompressConfig=lambda **k:k
sys.modules["headroom"]=f
from run_workflows import compress_messages
m=[{"role":"user","content":"EVIDENCE "*500}]
os.environ.pop("DEKU_GRADER_HEADROOM_ENABLED",None)
off = compress_messages("claude-sonnet-4-5",m) is m
os.environ["DEKU_GRADER_HEADROOM_ENABLED"]="true"
on  = compress_messages("claude-sonnet-4-5",m)[0]["content"]=="<crushed>"
c=[{"role":"user","content":[{"type":"text","text":"x"*4000,"cache_control":{"type":"ephemeral"}}]}]
guard = compress_messages("claude-sonnet-4-5",c) is c
print("✅ default OFF (no-op)" if off else "❌ not off by default")
print("✅ compresses when enabled" if on else "❌ compression not running")
print("✅ cache interlock holds" if guard else "❌ INTERLOCK BROKEN")
PY
echo "────────────────────────────────────────────────────────"
