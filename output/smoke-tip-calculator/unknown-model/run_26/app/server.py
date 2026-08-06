"""Reference tip calculator for deku/smoke-tip-calculator.

One file, one process, one port. Python stdlib only. Serves:
  GET /              -> the single-page calculator (HTML/JS inline)
  GET /api/health    -> {"ok": true}
  GET /api/calculate -> {"bill", "tip_percent", "people", "tip_amount",
                         "total", "per_person"} or {"error": "..."} on 400

Rounding rule pinned by instruction.md: compute in full precision, then round
each returned monetary field to two decimals using ROUND_HALF_UP.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("APP_PUBLIC_PORT", "4173"))
Q = Decimal("0.01")


def round_half_up(value: Decimal) -> float:
    return float(value.quantize(Q, rounding=ROUND_HALF_UP))


def parse_decimal(raw: str | None, field: str, allow_negative: bool = False) -> Decimal:
    if raw is None or raw == "":
        raise ValueError(f"{field} is required")
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number") from None
    if not allow_negative and value < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return value


def parse_people(raw: str | None) -> int:
    if raw is None or raw == "":
        return 1
    try:
        # Reject floats like "1.5" -- Decimal parses them but int(Decimal(...)) would truncate.
        if "." in raw or "e" in raw.lower():
            raise ValueError
        value = int(raw)
    except (ValueError, InvalidOperation):
        raise ValueError("people must be a positive integer")
    if value < 1:
        raise ValueError("people must be a positive integer")
    return value


def calculate(params: dict[str, list[str]]) -> dict:
    def first(name: str) -> str | None:
        vals = params.get(name)
        return vals[0] if vals else None

    bill = parse_decimal(first("bill"), "bill")
    tip_percent = parse_decimal(first("tip"), "tip")
    people = parse_people(first("people"))

    tip_amount = bill * tip_percent / Decimal(100)
    total = bill + tip_amount
    per_person = total / Decimal(people)

    return {
        "bill":        round_half_up(bill),
        "tip_percent": round_half_up(tip_percent),
        "people":      people,
        "tip_amount":  round_half_up(tip_amount),
        "total":       round_half_up(total),
        "per_person":  round_half_up(per_person),
    }


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tip Calculator</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         margin: 0; background: #f6f7f9; color: #111827; }
  main { max-width: 480px; margin: 40px auto; padding: 24px;
         background: #fff; border-radius: 12px;
         box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  h1 { font-size: 22px; margin: 0 0 24px; }
  label { display: block; font-size: 13px; color: #6b7280; margin-top: 16px; }
  input[type=number] { width: 100%; padding: 10px 12px; font-size: 16px;
                       border: 1px solid #d1d5db; border-radius: 8px;
                       margin-top: 6px; }
  input:focus { outline: 2px solid #4f46e5; border-color: #4f46e5; }
  .outputs { margin-top: 28px; padding-top: 20px; border-top: 1px solid #e5e7eb; }
  .row { display: flex; justify-content: space-between; padding: 8px 0;
         font-variant-numeric: tabular-nums; }
  .row .label { color: #6b7280; }
  .row .value { font-weight: 600; }
  #validation { color: #dc2626; font-size: 13px; margin-top: 12px;
                min-height: 18px; }
</style>
</head>
<body>
<main>
  <h1>Tip Calculator</h1>

  <label for="bill">Bill amount ($)</label>
  <input id="bill" type="number" step="0.01" min="0" placeholder="0.00">

  <label for="tip">Tip percentage (%)</label>
  <input id="tip" type="number" step="1" min="0" value="15">

  <label for="people">Split between (people)</label>
  <input id="people" type="number" step="1" min="1" value="1">

  <div id="validation" role="alert" aria-live="polite"></div>

  <section class="outputs" aria-label="results">
    <div class="row"><span class="label">Tip</span>
                     <span class="value" id="out-tip">--</span></div>
    <div class="row"><span class="label">Total</span>
                     <span class="value" id="out-total">--</span></div>
    <div class="row"><span class="label">Per person</span>
                     <span class="value" id="out-per-person">--</span></div>
  </section>
</main>

<script>
  const $ = (id) => document.getElementById(id);
  const bill = $("bill"), tip = $("tip"), people = $("people");
  const outTip = $("out-tip"), outTotal = $("out-total"), outPer = $("out-per-person");
  const validation = $("validation");

  function blank() { outTip.textContent = "--"; outTotal.textContent = "--";
                     outPer.textContent = "--"; }

  async function recompute() {
    const params = new URLSearchParams({
      bill: bill.value, tip: tip.value, people: people.value || "1"
    });
    try {
      const res = await fetch("/api/calculate?" + params.toString());
      if (!res.ok) {
        const body = await res.json().catch(() => ({error: "invalid input"}));
        validation.textContent = body.error || "invalid input";
        blank();
        return;
      }
      const data = await res.json();
      validation.textContent = "";
      outTip.textContent = data.tip_amount.toFixed(2);
      outTotal.textContent = data.total.toFixed(2);
      outPer.textContent = data.per_person.toFixed(2);
    } catch (err) {
      validation.textContent = "network error";
      blank();
    }
  }

  [bill, tip, people].forEach(el => el.addEventListener("input", recompute));
  // Nothing to show until the user types a bill.
  blank();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    # Keep stdout clean; the App Contract wants structured logging to stdout
    # but access-log spam drowns real errors.
    def log_message(self, fmt, *args):
        return

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, body: str) -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._send_html(INDEX_HTML)
            return
        if path == "/api/health":
            self._send_json(200, {"ok": True})
            return
        if path == "/api/calculate":
            try:
                result = calculate(parse_qs(parsed.query, keep_blank_values=True))
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, result)
            return

        self._send_json(404, {"error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"tip-calculator listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
