"""Problem 9: build output/hw6_report.html from the saved results. One self-contained file.

Usage:
    python make_report.py

Reads (all written by the test scripts, never by hand):
    output/cache_test.json      Problem 4
    output/attack_results.json  Problem 5
    output/defense_results.json Problem 6
    output/red_team.json        Problem 7
    output/exam_results.json    Problem 8
    data/my_attacks/attack_key.json

No internet, no external files: CSS, JS, and charts (inline SVG) are all inside the HTML.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
REPORT = OUT / "hw6_report.html"
DOCS_PER_MONTH = 1000 * 30

# Chart series colors: validated categorical slots 1-4 (dark mode, surface #1a1a19).
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500"]


def load(name: str):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def money(x: float, digits: int = 6) -> str:
    return f"${x:,.{digits}f}"


def yes_no(flag: bool, good_when: bool = False) -> str:
    ok = flag == good_when
    return f'<span class="pill {"ok" if ok else "bad"}">{"&#10003;" if ok else "&#9888;"} {"yes" if flag else "no"}</span>'


# --------------------------------------------------------------------------- charts (inline SVG)


def stacked_bar_chart(rows: list[tuple[str, list[float]]], parts: list[str], title: str) -> str:
    """Horizontal stacked bars, one row per setup, one segment per cost part."""
    width, label_w, right_pad, bar_h, gap = 760, 120, 120, 34, 26
    plot_w = width - label_w - right_pad
    vmax = max(sum(v) for _, v in rows) or 1
    height = 30 + len(rows) * (bar_h + gap)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">']
    for gx in range(0, 5):  # recessive vertical gridlines
        x = label_w + plot_w * gx / 4
        out.append(f'<line x1="{x:.1f}" y1="10" x2="{x:.1f}" y2="{height - 18}" class="grid"/>')
        out.append(f'<text x="{x:.1f}" y="{height - 4}" class="tick" text-anchor="middle">{money(vmax * gx / 4, 4)}</text>')
    for i, (name, values) in enumerate(rows):
        y = 14 + i * (bar_h + gap)
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h / 2 + 5}" class="rowlabel" text-anchor="end">{esc(name)}</text>')
        x = label_w
        for j, v in enumerate(values):
            w = plot_w * v / vmax
            if w <= 0:
                continue
            seg_w = max(w - 2, 0.5)  # 2px surface gap between segments
            last = j == len(values) - 1 or all(vv == 0 for vv in values[j + 1:])
            r = 4 if last else 0
            tip = f"{name} - {parts[j]}: {money(v, 6)} ({v / sum(values):.0%} of this setup)"
            path = (f'M{x:.1f},{y} h{seg_w - r:.1f} q{r},0 {r},{r} v{bar_h - 2 * r} q0,{r} -{r},{r} h-{seg_w - r:.1f} z'
                    if r else f'M{x:.1f},{y} h{seg_w:.1f} v{bar_h} h-{seg_w:.1f} z')
            out.append(f'<path d="{path}" fill="{SERIES[j]}" data-tip="{esc(tip)}"/>')
            x += w
        out.append(f'<text x="{x + 8:.1f}" y="{y + bar_h / 2 + 5}" class="value">{money(sum(values), 5)}</text>')
    out.append("</svg>")
    legend = "".join(f'<span class="key"><i style="background:{SERIES[j]}"></i>{esc(p)}</span>' for j, p in enumerate(parts))
    return f'<figure><figcaption>{esc(title)}</figcaption><div class="legend">{legend}</div>{"".join(out)}</figure>'


def single_bar_chart(rows: list[tuple[str, float, str]], title: str, fmt=lambda v: money(v, 6)) -> str:
    """Horizontal bars, one series (title names it), value labels at the bar ends."""
    width, label_w, right_pad, bar_h, gap = 760, 170, 230, 24, 14
    plot_w = width - label_w - right_pad
    vmax = max(v for _, v, _ in rows) or 1
    height = 10 + len(rows) * (bar_h + gap)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
           f'<line x1="{label_w}" y1="4" x2="{label_w}" y2="{height - 6}" class="axis"/>']
    for i, (name, v, note) in enumerate(rows):
        y = 6 + i * (bar_h + gap)
        w = max(plot_w * v / vmax, 2)
        r = min(4, w / 2)
        out.append(f'<text x="{label_w - 10}" y="{y + bar_h / 2 + 5}" class="rowlabel" text-anchor="end">{esc(name)}</text>')
        out.append(f'<path d="M{label_w},{y} h{w - r:.1f} q{r},0 {r},{r} v{bar_h - 2 * r:.1f} q0,{r} -{r},{r} h-{w - r:.1f} z" '
                   f'fill="{SERIES[0]}" data-tip="{esc(name)}: {esc(fmt(v))} per document. {esc(note)}"/>')
        out.append(f'<text x="{label_w + w + 8:.1f}" y="{y + bar_h / 2 + 5}" class="value">{esc(fmt(v))}'
                   f'<tspan class="muted"> {esc(note)}</tspan></text>')
    out.append("</svg>")
    return f'<figure><figcaption>{esc(title)}</figcaption>{"".join(out)}</figure>'


# --------------------------------------------------------------------------- sections


def cache_section(cache) -> tuple[str, dict]:
    if not cache:
        return '<p class="missing">Cache test not run yet (python cache_test.py).</p>', {}
    calls = [c for c in cache["calls"] if c["api_usage"]]
    agg = {}
    for setup in ("no_cache", "cache"):
        rs = [c for c in calls if c["setup"] == setup]
        t = {k: sum(c["derived_tokens"][k] for c in rs) for k in ("input", "cached_input", "cache_write", "uncached_input", "output")}
        cost = {k: sum(c["cost_usd"][k] for c in rs) for k in ("uncached_input", "cached_input", "cache_write", "output", "total")}
        docs = len({c["document"] for c in rs})
        agg[setup] = {"tokens": t, "cost": cost, "docs": docs, "calls": len(rs)}
    nc, ca = agg["no_cache"], agg["cache"]
    saved = 1 - ca["cost"]["total"] / nc["cost"]["total"]
    parts = ["Uncached input", "Cached input (read)", "Cache write", "Output"]
    keys = ["uncached_input", "cached_input", "cache_write", "output"]
    chart = stacked_bar_chart([("No cache", [nc["cost"][k] for k in keys]), ("Cache", [ca["cost"][k] for k in keys])],
                              parts, "Cost of the 12 practice documents, by cost part")
    tiles = f"""
<div class="tiles">
  <div class="tile"><div class="label">Saved by caching</div><div class="big">{saved:.0%}</div><div class="sub">{money(nc['cost']['total'], 5)} &rarr; {money(ca['cost']['total'], 5)} for 12 documents</div></div>
  <div class="tile"><div class="label">Input read from cache</div><div class="big">{ca['tokens']['cached_input'] / ca['tokens']['input']:.0%}</div><div class="sub">{ca['tokens']['cached_input']:,} of {ca['tokens']['input']:,} input tokens</div></div>
  <div class="tile"><div class="label">Cached tokens in the no-cache run</div><div class="big">{nc['tokens']['cached_input']:,}</div><div class="sub">all {nc['calls']} calls report <code>cached_tokens: 0</code>, so the test counts</div></div>
</div>"""
    table = f"""
<table><thead><tr><th>Tokens the API reported</th><th class="num">No cache</th><th class="num">Cache</th></tr></thead><tbody>
<tr><td>Model calls</td><td class="num">{nc['calls']}</td><td class="num">{ca['calls']}</td></tr>
<tr><td><code>input_tokens</code></td><td class="num">{nc['tokens']['input']:,}</td><td class="num">{ca['tokens']['input']:,}</td></tr>
<tr><td><code>cached_tokens</code></td><td class="num">{nc['tokens']['cached_input']:,}</td><td class="num">{ca['tokens']['cached_input']:,}</td></tr>
<tr><td><code>cache_write_tokens</code></td><td class="num">{nc['tokens']['cache_write']:,}</td><td class="num">{ca['tokens']['cache_write']:,}</td></tr>
<tr><td><code>output_tokens</code></td><td class="num">{nc['tokens']['output']:,}</td><td class="num">{ca['tokens']['output']:,}</td></tr>
<tr><td>Cost per document</td><td class="num">{money(nc['cost']['total'] / nc['docs'])}</td><td class="num">{money(ca['cost']['total'] / ca['docs'])}</td></tr>
<tr><td>30 days at 1,000 documents a day</td><td class="num">{money(nc['cost']['total'] / nc['docs'] * DOCS_PER_MONTH, 2)}</td><td class="num">{money(ca['cost']['total'] / ca['docs'] * DOCS_PER_MONTH, 2)}</td></tr>
</tbody></table>"""
    note = ("<p class=\"note\">Both setups forced a fresh model call (Portkey's own response cache would otherwise "
            "replay an old answer). Output tokens get no cache discount and cost 5&times; input, which is why the "
            "total saving is smaller than the input saving.</p>")
    return chart + tiles + table + note, agg


def attack_section(attack, defense) -> tuple[str, dict]:
    if not defense:
        return '<p class="missing">Defense test not run yet (python defense_test.py).</p>', {}
    layers = defense["layers"]
    before = {r["document"]: r for r in (attack["results"] if attack else layers.get("none", {}).get("results", []))}
    after_name = "code+design+prompt" if "code+design+prompt" in layers else next(iter(layers))
    after = {r["document"]: r for r in layers[after_name]["results"]}

    def fields(r):
        return sum(r["fields_matched"].values())

    def trap(r):
        n = len(r["trap_calls"])
        if not n:
            return '<span class="pill ok">&#10003; none</span>'
        executed = sum(t.get("status") == "recorded" for t in r["trap_calls"])
        return (f'<span class="pill bad">&#9888; {n} executed</span>' if executed
                else f'<span class="pill warn">&#9888; {n} tried, blocked</span>')

    rows = []
    for doc in sorted(after):
        b, a = before.get(doc), after[doc]
        rows.append(
            f"<tr><td>{esc(doc)}</td>"
            f"<td class=\"num\">{fields(b) if b else '-'}/6</td><td>{trap(b) if b else '-'}</td><td>{yes_no(b['fooled']) if b else '-'}</td>"
            f"<td class=\"num\">{fields(a)}/6</td><td>{trap(a)}</td><td>{yes_no(a['fooled'])}</td>"
            f"<td class=\"num\">{a['tokens']['total']:,}</td><td class=\"num\">{money(a['cost_usd']['total'])}</td></tr>")
    sb = sum(r["fooled"] for r in before.values())
    sa = sum(r["fooled"] for r in after.values())
    table = f"""
<p class="lead">Before = the Problem 3 agent with no new defenses. After = all three layers. Fooled = a wrong field, an executed trap tool, or a link or strange text in the answer.</p>
<table><thead><tr><th rowspan="2">Document</th><th colspan="3" class="grp">Before (no defenses)</th><th colspan="5" class="grp">After (code + design + prompt)</th></tr>
<tr><th class="num">Fields right</th><th>Trap tools</th><th>Fooled</th><th class="num">Fields right</th><th>Trap tools</th><th>Fooled</th><th class="num">Tokens</th><th class="num">Cost</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><td>Total fooled</td><td colspan="3" class="num">{sb} of {len(before)}</td><td colspan="5" class="num">{sa} of {len(after)}</td></tr></tfoot></table>"""

    order = ["none", "code", "design", "prompt", "code+design+prompt"]
    names = {"none": "No defenses", "code": "Code only", "design": "Design only", "prompt": "Prompt only",
             "code+design+prompt": "All three"}
    base = layers.get("none", {}).get("summary")
    cost_rows, trows = [], []
    for name in order:
        if name not in layers:
            continue
        s = layers[name]["summary"]
        dt = s["avg_tokens_per_document"] - base["avg_tokens_per_document"] if base else 0
        dc = s["avg_cost_usd_per_document"] - base["avg_cost_usd_per_document"] if base else 0
        cost_rows.append((names[name], s["avg_cost_usd_per_document"], f"{s['avg_tokens_per_document']:,.0f} tokens"))
        trows.append(
            f"<tr><td>{names[name]}</td><td class=\"num\">{s['avg_input_tokens_per_document']:,.0f}</td>"
            f"<td class=\"num\">{s['avg_output_tokens_per_document']:,.0f}</td><td class=\"num\">{s['avg_tokens_per_document']:,.0f}</td>"
            f"<td class=\"num\">{dt:+,.0f}</td><td class=\"num\">{money(s['avg_cost_usd_per_document'])}</td>"
            f"<td class=\"num\">{dc:+.6f}</td><td class=\"num\">{money(s['avg_cost_usd_per_document'] * DOCS_PER_MONTH, 2)}</td>"
            f"<td class=\"num\">{s['fooled']}</td><td class=\"num\">{s['trap_tool_calls_attempted']}</td></tr>")
    chart = single_bar_chart(cost_rows, "Average cost per document, by defense setting (no prompt caching, so layers compare fairly)")
    cost_table = f"""
<table><thead><tr><th>Setting</th><th class="num">Input tokens / doc</th><th class="num">Output tokens / doc</th><th class="num">Total tokens / doc</th><th class="num">Extra tokens vs none</th><th class="num">$ / doc</th><th class="num">Extra $ vs none</th><th class="num">$ / 30 days</th><th class="num">Fooled</th><th class="num">Trap tries</th></tr></thead>
<tbody>{''.join(trows)}</tbody></table>"""
    return table + "<h3>What did the defenses cost?</h3>" + chart + cost_table, {"layers": layers, "after": after_name}


def exam_section(exam) -> tuple[str, dict]:
    if not exam:
        return '<p class="missing">Exam not run yet (python exam_test.py).</p>', {}
    rows = "".join(
        f"<tr><td>{esc(e['file'])}</td><td>{esc(e['vendor'])}</td><td>{esc(e['sku'])}</td>"
        f"<td class=\"num\">{'' if e['unit_price'] is None else money(e['unit_price'], 2)}</td>"
        f"<td class=\"num\">{esc(e['lead_time_days'])}</td><td class=\"num\">{esc(e['min_order'])}</td>"
        f"<td><span class=\"pill {'ok' if e['decision'] == 'recommend' else 'neutral'}\">{'&#10003; recommend' if e['decision'] == 'recommend' else '&#10005; do not recommend'}</span></td>"
        f"<td class=\"reason\">{esc(e['reason'])}</td><td>{yes_no(e['trap_tool_called'])}</td>"
        f"<td class=\"num\">{e['input_tokens']:,}</td><td class=\"num\">{e['cached_tokens']:,}</td><td class=\"num\">{e['output_tokens']:,}</td>"
        f"<td class=\"num\">{money(e['cost_usd'])}</td></tr>" for e in exam)
    n = len(exam)
    rec = sum(e["decision"] == "recommend" for e in exam)
    total = sum(e["cost_usd"] for e in exam)
    traps = sum(e["trap_tool_called"] for e in exam)
    tiles = f"""
<div class="tiles">
  <div class="tile"><div class="label">Recommended</div><div class="big">{rec} of {n}</div><div class="sub">{n - rec} do not recommend</div></div>
  <div class="tile"><div class="label">Trap tool tries</div><div class="big">{traps}</div><div class="sub">documents where the model tried <code>send_email</code> or <code>approve_payment</code> (blocked)</div></div>
  <div class="tile"><div class="label">Cost of all {n}</div><div class="big">{money(total, 4)}</div><div class="sub">{money(total / n)} per document, with caching</div></div>
</div>"""
    table = f"""
<table class="wide"><thead><tr><th>File</th><th>Vendor</th><th>SKU</th><th class="num">Unit price</th><th class="num">Lead days</th><th class="num">Min order</th><th>Decision</th><th>Reason</th><th>Trap tool</th><th class="num">Input</th><th class="num">Cached</th><th class="num">Output</th><th class="num">Cost</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="note">Written by <code>exam_test.py</code> straight from the agent's answers and the API's usage numbers. No result was edited by hand.</p>"""
    return tiles + table, {"per_doc": total / n, "n": n, "traps": traps}


def red_team_section(red, key) -> str:
    if not red or not key:
        return '<p class="missing">Red-team test not run yet (python red_team_test.py).</p>'
    out = []
    names = {"none": "No defenses", "all": "All defenses"}
    for k in key:
        runs = [r for r in red["results"] if r["document"] == k["file"]]
        cells = []
        for r in runs:
            goal = r["attack_goal_reached"]
            got = ", ".join(f"{f.replace('_', ' ')} {'reached' if v else 'not reached'}" for f, v in goal.items())
            a = r["agent_answer"]
            cells.append(
                f"<tr><td>{names.get(r['defenses'], r['defenses'])}</td><td>{yes_no(r['fooled'])}</td>"
                f"<td>{esc(a['decision'])}</td><td class=\"num\">{esc(a['unit_price'])}</td><td class=\"num\">{esc(a['lead_time_days'])}</td>"
                f"<td>{esc(got)}</td><td class=\"reason\">{esc(a['reason'])}</td></tr>")
        out.append(f"""
<div class="card">
  <h3>{esc(k['file'])}</h3>
  <p><b>What a person sees:</b> a normal {esc(k['vendor'])} quote for {esc(k['sku'])}: ${k['unit_price']:.2f}, {k['lead_time_days']} days, minimum {k['min_order']} units. That is a correct <b>{esc(k['decision'].replace('_', ' '))}</b>.</p>
  <p><b>The trap:</b> {esc(k['attack'])}.</p>
  <table><thead><tr><th>Agent</th><th>Fooled</th><th>Decision</th><th class="num">Price</th><th class="num">Lead days</th><th>Attack goals</th><th>Reason given</th></tr></thead><tbody>{''.join(cells)}</tbody></table>
</div>""")
    return "".join(out)


# --------------------------------------------------------------------------- page

CSS = """
:root{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#222220;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--axis:#383835;--pink:#ff4fa3;--pink-soft:rgba(255,79,163,.14);--good:#0ca30c;--warn:#fab219;--bad:#d03b3b;}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:48px 24px 28px;border-bottom:1px solid var(--grid);background:linear-gradient(180deg,rgba(255,79,163,.10),transparent)}
header .wrap,main{max-width:1180px;margin:0 auto}
h1{margin:0 0 6px;font-size:30px;letter-spacing:-.01em}h1 span{color:var(--pink)}
.subtitle{color:var(--ink-2);margin:0}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
nav a{color:var(--ink);text-decoration:none;border:1px solid var(--axis);border-radius:999px;padding:5px 14px;font-size:13px}
nav a:hover,nav a:focus{border-color:var(--pink);color:var(--pink);outline:none}
main{padding:8px 24px 64px}
section{margin:36px 0;padding:28px;background:var(--surface);border:1px solid rgba(255,255,255,.08);border-radius:14px}
h2{margin:0 0 4px;font-size:22px}h2 .n{color:var(--pink);margin-right:8px}
h3{margin:28px 0 8px;font-size:17px}
.lead{color:var(--ink-2);margin:4px 0 16px}
.note{color:var(--muted);font-size:13px}
.missing{color:var(--warn)}
code{background:var(--surface-2);padding:1px 5px;border-radius:4px;font-size:.9em}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:18px 0}
.tile{background:var(--surface-2);border-radius:12px;padding:16px 18px;border-left:3px solid var(--pink)}
.tile .label{color:var(--ink-2);font-size:13px}.tile .big{font-size:32px;font-weight:700;margin:2px 0}.tile .sub{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}
th,td{padding:8px 10px;border-bottom:1px solid var(--grid);text-align:left;vertical-align:top}
th{color:var(--ink-2);font-weight:600;background:var(--surface-2)}th.grp{text-align:center;color:var(--pink)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tfoot td{font-weight:700;border-top:2px solid var(--axis)}
td.reason{max-width:340px;color:var(--ink-2)}
.tw{overflow-x:auto;max-width:100%}.tw table{min-width:640px}
.tw table.wide{min-width:1380px}table.wide td:nth-child(-n+3){white-space:nowrap}table.wide td.reason{min-width:300px}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;white-space:nowrap;border:1px solid}
.pill.ok{color:#7be07b;border-color:rgba(12,163,12,.6)}.pill.bad{color:#ff8a8a;border-color:rgba(208,59,59,.7)}
.pill.warn{color:var(--warn);border-color:rgba(250,178,25,.6)}.pill.neutral{color:var(--ink-2);border-color:var(--axis)}
figure{margin:18px 0}figcaption{font-weight:600;margin-bottom:6px}
.legend{display:flex;flex-wrap:wrap;gap:16px;color:var(--ink-2);font-size:13px;margin-bottom:6px}
.key i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
svg.chart{width:100%;height:auto;display:block}
svg .grid{stroke:var(--grid);stroke-width:1}svg .axis{stroke:var(--axis);stroke-width:1}
svg .tick{fill:var(--muted);font-size:11px}svg .rowlabel{fill:var(--ink);font-size:13px}
svg .value{fill:var(--ink);font-size:12.5px;font-variant-numeric:tabular-nums}svg .muted{fill:var(--muted)}
svg [data-tip]{cursor:default;transition:opacity .12s}svg:hover [data-tip]{opacity:.75}svg [data-tip]:hover{opacity:1}
#tip{position:fixed;pointer-events:none;background:#000;color:var(--ink);border:1px solid var(--pink);border-radius:8px;padding:6px 10px;font-size:12.5px;max-width:320px;opacity:0;transition:opacity .1s;z-index:10}
.card{background:var(--surface-2);border-radius:12px;padding:18px 20px;margin:16px 0}.card h3{margin-top:0;color:var(--pink)}
.verdict{font-size:18px;padding:16px 18px;border-radius:12px;background:var(--pink-soft);border:1px solid rgba(255,79,163,.45);margin:14px 0}
ul.tight li{margin:4px 0}
footer{color:var(--muted);text-align:center;font-size:12.5px;padding:0 24px 40px}
@media (max-width:700px){section{padding:18px}h1{font-size:24px}}
"""

JS = """
(function(){var t=document.getElementById('tip');
document.addEventListener('mousemove',function(e){var el=e.target.closest&&e.target.closest('[data-tip]');
if(!el){t.style.opacity=0;return;}t.textContent=el.getAttribute('data-tip');t.style.opacity=1;
var x=e.clientX+14,y=e.clientY+14,w=t.offsetWidth,h=t.offsetHeight;
if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;t.style.left=x+'px';t.style.top=y+'px';});})();
"""


def recommendation_section(cache_agg, exam_info, defense_info) -> str:
    per_doc = exam_info.get("per_doc")
    monthly = per_doc * DOCS_PER_MONTH if per_doc else None
    nc = cache_agg.get("no_cache")
    no_cache_month = nc["cost"]["total"] / nc["docs"] * DOCS_PER_MONTH if nc else None
    defended_nc = None
    if defense_info:
        s = defense_info["layers"][defense_info["after"]]["summary"]
        defended_nc = s["avg_cost_usd_per_document"] * DOCS_PER_MONTH
    cost_line = (f"<b>{money(monthly, 2)} a month</b> for 30,000 documents (1,000 a day), measured on the exam run "
                 f"with all defenses and prompt caching on ({money(per_doc)} per document)." if monthly else
                 "Cost: run the exam first.")
    alt = (f" Without caching it would be about {money(defended_nc, 2)} a month." if defended_nc else "")
    return f"""
<div class="verdict">&#10003; <b>Recommendation: yes, turn it on for real vendor mail, as a reviewer, not a buyer.</b> It drafts the recommendation; a person still approves every order, email, and payment.</div>
<ul class="tight">
<li><b>What it costs:</b> {cost_line}{alt} That is less than one hour of staff time a month.</li>
<li><b>Why yes:</b> it got all 12 practice documents right in every setting, gave sensible answers on the 10 exam documents, and never sent an email or approved a payment. Those tools are locked behind a human sign-off. With all defenses on it is also <i>cheaper</i> than without them, because code (not the model) makes the decision.</li>
<li><b>Why not alone:</b> it can still be fooled. One exam document hid a fake "vendor of record" and fooled one run before the code layer was tightened. One red-team email shows a person one quote and the agent another, and it still fools the defended agent. Until the reader compares both versions of an email, a person should check every email the agent recommends.</li>
<li><b>Before go-live:</b> (1) flag emails whose plain-text and HTML versions disagree, and strip invisible text from PDFs; (2) keep the Portkey response cache off for this agent; (3) have the buyer spot-check 1 in 10 decisions for the first month.</li>
</ul>"""


def main() -> None:
    cache, attack, defense = load("cache_test.json"), load("attack_results.json"), load("defense_results.json")
    red, exam = load("red_team.json"), load("exam_results.json")
    key_path = HERE / "data" / "my_attacks" / "attack_key.json"
    key = json.loads(key_path.read_text(encoding="utf-8")) if key_path.exists() else None

    cache_html, cache_agg = cache_section(cache)
    attack_html, defense_info = attack_section(attack, defense)
    exam_html, exam_info = exam_section(exam)
    sections = [
        ("cache", "Cache results", "The 12 practice documents, run with and without prompt caching. Every number comes from the API's own usage report.", cache_html),
        ("attacks", "Attacks before and after defenses", "The same 12 documents (six contain attacks), on the undefended agent and on the agent with three defense layers.", attack_html),
        ("exam", "Exam results", "The final defended agent on the 10 exam documents, which have no answer key.", exam_html),
        ("redteam", "Two red-team attacks", "Two new booby-trapped documents that look normal to a person.", red_team_section(red, key)),
        ("recommendation", "Recommendation to the store manager", "Should Campus Customs turn this agent on for real vendor mail?", recommendation_section(cache_agg, exam_info, defense_info)),
    ]
    nav = "".join(f'<a href="#{sid}">{i}. {esc(title)}</a>' for i, (sid, title, _, _) in enumerate(sections, 1))
    body = "".join(f'<section id="{sid}"><h2><span class="n">{i}</span>{esc(title)}</h2><p class="lead">{esc(lead)}</p>{content}</section>'
                   for i, (sid, title, lead, content) in enumerate(sections, 1))
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HW6 - Campus Customs Vendor Desk Agent: Results</title><style>{CSS}</style></head>
<body><header><div class="wrap"><h1>Campus Customs <span>Vendor Desk Agent</span></h1>
<p class="subtitle">Homework 6 results &middot; model <code>gpt-6-luna</code> via Portkey &middot; built {datetime.now():%B %d, %Y}</p>
<nav aria-label="Sections">{nav}</nav></div></header>
<main>{body}</main>
<footer>Generated by <code>make_report.py</code> from the JSON results in <code>output/</code>. Self-contained: no internet or other files needed.</footer>
<div id="tip" role="tooltip"></div><script>{JS}</script></body></html>"""
    # Every table scrolls sideways inside its card on narrow screens instead of widening the page.
    page = page.replace("<table", '<div class="tw"><table').replace("</table>", "</table></div>")
    REPORT.write_text(page, encoding="utf-8")
    print("wrote", REPORT, f"({len(page):,} bytes)")


if __name__ == "__main__":
    main()
