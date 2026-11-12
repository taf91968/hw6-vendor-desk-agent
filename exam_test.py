"""Problem 8: run the final defended agent on the 10 exam documents. Results are written by code only.

Usage:
    python exam_test.py            # -> output/exam_results.json

Final agent = all three defense layers (code, design, prompt) with prompt caching on (the Problem 4 "cache"
setup). Every call is a fresh model call (Portkey's response cache is bypassed). Token counts and cost come
from the API's usage numbers and data/prices.json; trap_tool_called is true if the run made any entry in
output/trap_calls.json (attempted, even if a defense blocked it).
"""

from __future__ import annotations

import asyncio
import json
import sys

import agent as desk_agent
from agent import build_agent, run_one_with_retry as run_one
from attack_test import FRESH
from cache_test import SETUPS
from tools import DATA_DIR, OUTPUT_DIR, TRAP_LOG, ensure_trap_log

EXAM_DIR = DATA_DIR / "exam_docs"
RESULTS = OUTPUT_DIR / "exam_results.json"


async def main() -> int:
    ensure_trap_log()
    desk = build_agent(SETUPS["cache"], extra_headers=FRESH, defenses="all")
    entries = []
    for path in sorted(p for p in EXAM_DIR.iterdir() if p.is_file()):
        before = len(json.loads(TRAP_LOG.read_text(encoding="utf-8")))
        answer = await run_one(desk, f"exam_docs/{path.name}", setup="exam:final")
        run = dict(desk_agent.LAST_RUN)
        traps = json.loads(TRAP_LOG.read_text(encoding="utf-8"))[before:]
        entry = {
            "file": path.name,
            "vendor": answer.vendor,
            "sku": answer.sku,
            "unit_price": answer.unit_price,
            "lead_time_days": answer.lead_time_days,
            "min_order": answer.min_order,
            "decision": answer.decision,
            "reason": answer.reason,
            "trap_tool_called": bool(traps),
            "input_tokens": run["tokens"]["input"],
            "cached_tokens": run["tokens"]["cached_input"],
            "output_tokens": run["tokens"]["output"],
            "cost_usd": run["cost_usd"]["total"],
        }
        entries.append(entry)
        RESULTS.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")  # saved as it goes
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    print(f"wrote {len(entries)} entries to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
