"""Runtime patches applied to every Python process in the agent container.

Python imports `sitecustomize` automatically at interpreter startup if it is
found on sys.path, so placing this directory on PYTHONPATH patches processes that
do not exist yet -- which is the only way to reach OpenHands, since Harbor
installs it into /opt/openhands-venv at RUN time, long after this image is built.

Every patch is best-effort: an ImportError just means the target is not installed
in this particular process, and a failure here must never stop the agent starting.
"""

# ---------------------------------------------------------------------------
# binaryornot.helpers.is_binary_string -- Python 2 leftover, fatal on Python 3.
#
# OpenHands calls binaryornot on every file READ to decide whether it is binary.
# binaryornot asks chardet for an encoding; when chardet cannot tell (an empty
# file, or unusual bytes) it returns None, and the library then does:
#
#     bytes.decode(encoding=None)      -> TypeError
#     except ...: isinstance(x, unicode)   -> NameError: name 'unicode' is not defined
#
# The recovery path references a Python 2 builtin, so a recoverable decode
# problem becomes an unhandled NameError, which FastAPI turns into a 500, which
# drives AgentState.RUNNING -> ERROR. Measured 2026-08-07: killed a 132-step run
# outright, and Harbor recorded no exception at all because OpenHands' wrapper
# still exited 0.
#
# binaryornot has not shipped since 2017, so there is no version to upgrade to.
# Replace the function with an equivalent that treats "cannot decode" as "binary"
# -- which is what the original was trying to express before it crashed.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - defensive by design
    from binaryornot import helpers as _bon_helpers

    _TEXTCHARS = bytearray(
        {7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F}
    )

    def _is_binary_string(bytes_to_check):
        if not bytes_to_check:
            return False                      # an empty file is not binary
        if b"\x00" in bytes_to_check:
            return True                       # a NUL byte is decisive
        try:
            import chardet
            detected = chardet.detect(bytes_to_check) or {}
            encoding = detected.get("encoding")
        except Exception:
            encoding = None
        if encoding:
            try:
                bytes_to_check.decode(encoding)
                return False
            except (UnicodeDecodeError, LookupError, TypeError, ValueError):
                return True
        # No usable encoding: fall back to the control-character heuristic rather
        # than the decode() call that raised.
        return bool(bytes_to_check.translate(None, _TEXTCHARS))

    _bon_helpers.is_binary_string = _is_binary_string

    try:  # check.py may have bound the original by value at import time
        from binaryornot import check as _bon_check
        if getattr(_bon_check, "is_binary_string", None) is not None:
            _bon_check.is_binary_string = _is_binary_string
    except Exception:
        pass
except Exception:
    pass
