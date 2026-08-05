#!/usr/bin/env python3
"""Render the trial comparison as a self-contained HTML report with SVG charts.

    python harness/eval/charts.py --csv delivery/trials.csv --out delivery/report.html

Inline SVG rather than matplotlib: no dependency to install, no binary artifact,
opens in any browser and diffs as text in review.
"""

from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from pathlib import Path

PALETTE = {"opus": "#4F46E5", "sonnet": "#0EA5E9", "other": "#64748B"}
BAR_H, GAP, LABEL_W, PLOT_W = 26, 10, 250, 560


def family(model: str) -> str:
    m = (model or "").lower()
    if "opus" in m:
        return "opus"
    if "sonnet" in m:
        return "sonnet"
    return "other"


def num(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bar_chart(title: str, rows: list[tuple[str, float, str]], unit: str = "") -> str:
    """rows: (label, value, colour-key). Values are drawn to the largest one."""
    if not rows:
        return ""
    top = max(v for _, v, _ in rows) or 1.0
    height = len(rows) * (BAR_H + GAP) + 46
    out = [f'<svg viewBox="0 0 {LABEL_W + PLOT_W + 90} {height}" '
           f'width="100%" role="img" aria-label="{html.escape(title)}">',
           f'<text x="0" y="18" font-size="14" font-weight="600" '
           f'fill="#0F172A">{html.escape(title)}</text>']
    for i, (label, value, key) in enumerate(rows):
        y = 36 + i * (BAR_H + GAP)
        w = max(2, (value / top) * PLOT_W)
        out.append(f'<text x="0" y="{y + 17}" font-size="12" fill="#334155" '
                   f'font-family="ui-monospace,monospace">{html.escape(label)}</text>')
        out.append(f'<rect x="{LABEL_W}" y="{y}" width="{w:.1f}" height="{BAR_H}" '
                   f'rx="4" fill="{PALETTE[key]}"/>')
        shown = f"{value:,.2f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"
        out.append(f'<text x="{LABEL_W + w + 8:.1f}" y="{y + 17}" font-size="12" '
                   f'fill="#0F172A" font-family="ui-monospace,monospace">'
                   f'{shown}{html.escape(unit)}</text>')
    out.append("</svg>")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=Path("delivery/trials.csv"))
    ap.add_argument("--out", type=Path, default=Path("delivery/report.html"))
    args = ap.parse_args()

    rows = list(csv.DictReader(args.csv.open()))
    real = [r for r in rows if r["agent"] and r["agent"] != "nop" and int(r["steps"] or 0) > 0]

    charts: list[str] = []

    def label(r: dict) -> str:
        return f"{r['job'][11:16]} {r['agent'][:11]} {family(r['model'])}"

    charts.append(bar_chart("Cost per trial (USD)",
                            [(label(r), num(r["cost_usd"]), family(r["model"])) for r in real],
                            " $"))
    charts.append(bar_chart("Agent steps per trial",
                            [(label(r), num(r["steps"]), family(r["model"])) for r in real]))
    charts.append(bar_chart("Output tokens per trial",
                            [(label(r), num(r["out_tokens"]), family(r["model"])) for r in real]))

    # Model-family means, the only aggregate the data currently supports.
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for r in real:
        by_fam[family(r["model"])].append(r)
    means = []
    for fam, group in sorted(by_fam.items()):
        means.append((f"{fam}  (n={len(group)})",
                      sum(num(g["cost_usd"]) for g in group) / len(group), fam))
    charts.append(bar_chart("Mean cost per trial by model family (USD)", means, " $"))

    scored = [r for r in real if r["substeps_total"]]
    charts.append(bar_chart(
        "Substeps passed (of total graded)",
        [(f"{label(r)}  {r['substeps_passed']}/{r['substeps_total']}",
          num(r["substeps_passed"]), family(r["model"])) for r in scored]))

    total_spend = sum(num(r["cost_usd"]) for r in rows)
    graded = [r for r in rows if r["reward"] not in ("", None)]

    body = f"""<!doctype html><meta charset="utf-8">
<title>Deku — trial comparison</title>
<style>
 body{{font:14px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif;color:#0F172A;
      background:#F8FAFC;margin:0;padding:40px;max-width:1080px}}
 h1{{font-size:30px;margin:0 0 4px}} h2{{font-size:20px;margin:36px 0 8px}}
 .muted{{color:#64748B}} .card{{background:#fff;border:1px solid #E2E8F0;border-radius:12px;
      padding:20px 24px;margin:16px 0;box-shadow:0 1px 2px rgba(15,23,42,.06)}}
 table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
 th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid #E2E8F0;font-size:13px}}
 th{{color:#64748B;font-weight:600}} td.n{{text-align:right;font-family:ui-monospace,monospace}}
 .pill{{display:inline-block;padding:2px 9px;border-radius:9999px;font-size:12px;
      background:#EEF2FF;color:#4F46E5}}
</style>
<h1>Deku — trial comparison</h1>
<p class="muted">{len(rows)} trials · {len(graded)} scored · total inference spend
${total_spend:.2f} · every reward below is 0.0</p>

<div class="card">
<h2 style="margin-top:0">Reading this</h2>
<p>No trial has yet produced a non-zero reward. Each zero had a distinct, identified
cause — verifier teardown, a lost trial, contract holes, rate limiting, a timeout
mismatch — documented in <code>README.md</code>. <strong>Cost, steps and token
counts are valid comparisons; rewards are not yet a capability measurement.</strong></p>
</div>

{''.join(f'<div class="card">{c}</div>' for c in charts if c)}

<h2>All trials</h2>
<div class="card"><table>
<tr><th>started</th><th>agent</th><th>model</th><th class="n">steps</th>
<th class="n">cost $</th><th class="n">reward</th><th class="n">deployed</th>
<th class="n">substeps</th></tr>
{''.join(
    "<tr><td>" + html.escape(r['job'][11:]) + "</td><td>" + html.escape(r['agent'] or '-')
    + "</td><td>" + html.escape(r['model'] or '-') + "</td><td class='n'>" + str(r['steps'])
    + "</td><td class='n'>" + f"{num(r['cost_usd']):.2f}"
    + "</td><td class='n'>" + (r['reward'] or '-')
    + "</td><td class='n'>" + (r['deployed'] or '-')
    + "</td><td class='n'>" + (f"{r['substeps_passed']}/{r['substeps_total']}"
                               if r['substeps_total'] else '-') + "</td></tr>"
    for r in rows)}
</table></div>
<p class="muted"><span class="pill">indigo</span> opus &nbsp;
<span class="pill" style="background:#E0F2FE;color:#0369A1">sky</span> sonnet &nbsp;
<span class="pill" style="background:#F1F5F9;color:#475569">slate</span> other</p>
"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body)
    print(f"wrote {args.out}  ({len(charts)} charts, {len(rows)} trials)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
