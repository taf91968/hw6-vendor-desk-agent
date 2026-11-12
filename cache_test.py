"""Problem 4: run the practice documents with and without prompt caching and record every model call.

Usage:
    python cache_test.py                       # both setups, all 12 practice documents
    python cache_test.py --setup no_cache      # one setup only
    python cache_test.py --files p01_bluehen_quote.html

Setups (both use gpt-6-luna via Portkey, same prompt, same tools):
    no_cache  openai_prompt_cache_options.mode = "explicit" and no cache breakpoints, so OpenAI writes and
              reads nothing. Proof: every call must report input_tokens_details.cached_tokens == 0.
    cache     mode = "implicit" (OpenAI's automatic caching) + an explicit breakpoint after the static
              instructions + a fixed prompt_cache_key so every call routes to the same cache.

Writes output/cache_test.json: one record per model call, with the setup, document, every token count the
API reported (the raw `usage` block), and the dollar cost from data/prices.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from agent import build_agent, practice_files, run_one
from tools import DATA_DIR, OUTPUT_DIR, ensure_trap_log

CACHE_TEST = OUTPUT_DIR / "cache_test.json"
PRICES = json.loads((DATA_DIR / "prices.json").read_text(encoding="utf-8"))[config.OPENAI_MODEL]

SETUPS: dict[str, dict] = {
    "no_cache": {
        "openai_prompt_cache_options": {"mode": "explicit"},
    },
    "cache": {
        "openai_prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
        "openai_cache_instructions": True,
        "openai_prompt_cache_key": "campus-customs-vendor-desk",
    },
}


def _first(d: dict, *keys: str) -> int:
    for k in keys:
        if isinstance(d.get(k), int):
            return d[k]
    return 0


def price_call(usage: dict) -> dict:
    """Dollar cost of one model call from the raw API usage block."""
    in_details = usage.get("input_tokens_details") or {}
    out_details = usage.get("output_tokens_details") or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cached = _first(in_details, "cached_tokens", "cache_read_tokens")
    written = _first(in_details, "cache_write_tokens", "cache_creation_tokens", "cache_creation_input_tokens")
    uncached = max(input_tokens - cached - written, 0)
    cost = {
        "uncached_input": uncached * PRICES["input_per_1m"] / 1e6,
        "cached_input": cached * PRICES["cached_input_per_1m"] / 1e6,
        "cache_write": written * PRICES["cache_write_per_1m"] / 1e6,
        "output": output_tokens * PRICES["output_per_1m"] / 1e6,
    }
    return {
        "derived_tokens": {
            "input": input_tokens,
            "uncached_input": uncached,
            "cached_input": cached,
            "cache_write": written,
            "output": output_tokens,
            "reasoning": _first(out_details, "reasoning_tokens"),
            "total": usage.get("total_tokens", input_tokens + output_tokens),
        },
        "cost_usd": {k: round(v, 10) for k, v in cost.items()} | {"total": round(sum(cost.values()), 10)},
    }


# Portkey's gateway response cache would replay an old response without calling the model at all.
# Force a fresh model call every time so both setups measure real API usage.
FRESH = {"x-portkey-cache-force-refresh": "true"}


async def run_setup(setup: str, files: list[str], records: list[dict]) -> None:
    agent = build_agent(SETUPS[setup], extra_headers=FRESH, defenses="none")  # Problem 3 agent, as measured
    for doc in files:
        config.API_CALLS.clear()
        answer = await run_one(agent, doc, setup=setup)
        for i, call in enumerate(config.API_CALLS, start=1):
            usage = call.get("usage") or {}
            records.append({
                "setup": setup,
                "document": doc,
                "call": i,
                "response_id": call.get("response_id"),
                "model": call.get("model"),
                "status_code": call.get("status_code"),
                "portkey_cache_status": call.get("portkey_cache_status"),
                "api_usage": usage,  # exactly what the API sent back
                **price_call(usage),
            })
        calls = [r for r in records if r["setup"] == setup and r["document"] == doc]
        cached = sum(r["derived_tokens"]["cached_input"] for r in calls)
        print(f"[{setup:8}] {doc:30} calls={len(calls)} input={sum(r['derived_tokens']['input'] for r in calls):6} "
              f"cached={cached:6} output={sum(r['derived_tokens']['output'] for r in calls):5} "
              f"${sum(r['cost_usd']['total'] for r in calls):.6f}  -> {answer.decision}", flush=True)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Problem 4 cache test")
    parser.add_argument("--setup", choices=[*SETUPS, "both"], default="both")
    parser.add_argument("--files", nargs="*", help="documents to run (default: all 12 practice documents)")
    parser.add_argument("--out", default=str(CACHE_TEST), help="where to write the call records")
    args = parser.parse_args(argv)

    files = args.files or practice_files()
    setups = list(SETUPS) if args.setup == "both" else [args.setup]
    ensure_trap_log()
    records: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()
    for setup in setups:
        await run_setup(setup, files, records)

    leaked = [r for r in records if r["setup"] == "no_cache"
              and (r["derived_tokens"]["cached_input"] or r["derived_tokens"]["cache_write"])]
    replayed = [r for r in records if r["portkey_cache_status"] == "HIT"]
    out = {
        "started_at": started,
        "model": config.OPENAI_MODEL,
        "prices_per_1m": PRICES,
        "setups": {s: SETUPS[s] for s in setups},
        "portkey_headers": FRESH,
        "checks": {
            "no_cache_calls_with_cached_or_written_tokens": len(leaked),
            "calls_replayed_from_portkey_cache": len(replayed),
            "valid": not leaked and not replayed,
        },
        "calls": records,
    }
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {len(records)} call records to {args.out}")
    if leaked or replayed:
        print(f"WARNING: {len(leaked)} no_cache calls used the prompt cache and {len(replayed)} calls were "
              "Portkey cache replays - this test does not count.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
