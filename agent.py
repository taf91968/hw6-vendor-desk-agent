"""Campus Customs vendor desk agent (gpt-6-luna via Portkey).

Usage:
    python agent.py p01_bluehen_quote.html                    # one document, all defenses on
    python agent.py --practice                                # every file in data/practice_docs
    python agent.py --practice --defenses none                # the undefended Problem 3 agent
    python agent.py p06_qtextile_quote.pdf --defenses code,prompt

Defense layers (see defenses.py): code, design, prompt. Default: all three. "none" = Problem 3 agent.

Every run (one document = one run) appends to:
    output/usage_log.json   tokens and dollar cost (prices from data/prices.json)
    output/audit_trail.json every tool call with its arguments and a short result, plus the final answer
Trap tools append to output/trap_calls.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, Tool, ToolDenied
from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import RunUsage

import tools
from config import OPENAI_MODEL, build_model
from defenses import (DESIGN_NOTE, LAYERS, Extraction, cross_check, label, parse_defenses, reason_from_checks,
                      scrub_reason, suspicious_lines, vendor_check)
from models import VendorDecision
from tools import DATA_DIR, OUTPUT_DIR, REAL_TOOLS, TRAP_LOG, TRAP_TOOLS, append_json, ensure_trap_log

HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"                    # defended prompt (prompt layer)
BASELINE_PROMPT_PATH = HERE / "prompts" / "prompt_baseline.md"  # Problem 3 prompt, no new defenses
PRICES_PATH = DATA_DIR / "prices.json"
USAGE_LOG = OUTPUT_DIR / "usage_log.json"
AUDIT_LOG = OUTPUT_DIR / "audit_trail.json"
SHORT = 200  # characters kept from each tool result in the audit trail
MAX_APPROVAL_ROUNDS = 3
ALL_DEFENSES = frozenset(LAYERS)

# Details of the most recent run_one call (tokens, cost, defense notes), for test scripts.
LAST_RUN: dict = {}


@dataclass
class DeskAgent:
    agent: Agent
    defenses: frozenset[str]


def build_agent(model_settings: dict | None = None, extra_headers: dict | None = None,
                defenses: frozenset[str] | str = ALL_DEFENSES) -> DeskAgent:
    if isinstance(defenses, str):
        defenses = parse_defenses(defenses)
    instructions = (PROMPT_PATH if "prompt" in defenses else BASELINE_PROMPT_PATH).read_text(encoding="utf-8")
    if "design" in defenses:
        # Least privilege: side-effect tools pause the run for a human instead of executing.
        trap_tools = [Tool(fn, requires_approval=True) for fn in TRAP_TOOLS]
        output_type = [Extraction, DeferredToolRequests]  # the model extracts facts; code decides
        instructions += DESIGN_NOTE
    else:
        trap_tools = list(TRAP_TOOLS)
        output_type = VendorDecision
    agent = Agent(
        build_model(extra_headers),
        output_type=output_type,
        instructions=instructions,
        tools=[*REAL_TOOLS, *trap_tools],
        retries=2,
        model_settings=model_settings,
    )
    return DeskAgent(agent, frozenset(defenses))


# --------------------------------------------------------------------------- logging


def price_run(usage) -> dict:
    """Dollar cost of one run from data/prices.json. Cached tokens are part of input_tokens."""
    p = json.loads(PRICES_PATH.read_text(encoding="utf-8"))[OPENAI_MODEL]
    cached = usage.cache_read_tokens or 0
    written = usage.cache_write_tokens or 0
    uncached = max(usage.input_tokens - cached - written, 0)
    parts = {
        "uncached_input": uncached * p["input_per_1m"] / 1e6,
        "cached_input": cached * p["cached_input_per_1m"] / 1e6,
        "cache_write": written * p["cache_write_per_1m"] / 1e6,
        "output": usage.output_tokens * p["output_per_1m"] / 1e6,
    }
    return {
        "tokens": {
            "input": usage.input_tokens,
            "uncached_input": uncached,
            "cached_input": cached,
            "cache_write": written,
            "output": usage.output_tokens,
            "total": usage.input_tokens + usage.output_tokens,
        },
        "cost_usd": {k: round(v, 8) for k, v in parts.items()} | {"total": round(sum(parts.values()), 8)},
    }


def _short(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= SHORT else text[: SHORT - 3] + "..."


def tool_calls_from(messages) -> list[dict]:
    """Pair every tool call with its result (or retry message) from the run's message history."""
    calls: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    calls[part.tool_call_id] = {"tool": part.tool_name, "args": part.args_as_dict(), "result": None}
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, (ToolReturnPart, RetryPromptPart)) and part.tool_call_id in calls:
                    content = part.content if isinstance(part, ToolReturnPart) else f"RETRY: {part.model_response()}"
                    calls[part.tool_call_id]["result"] = _short(content)
    # The final_result call is how PydanticAI returns structured output; it is the final answer, not a tool.
    return [c for c in calls.values() if not c["tool"].startswith("final_result")]


# --------------------------------------------------------------------------- run


async def _run_with_human_gate(agent: Agent, prompt: str, notes: list[str]):
    """Run the agent; any approval-required call is logged and denied (no human in a batch run)."""
    usage = RunUsage()
    result = await agent.run(prompt)
    usage.incr(result.usage)
    for _ in range(MAX_APPROVAL_ROUNDS):
        if not isinstance(result.output, DeferredToolRequests):
            break
        denials = {}
        for call in result.output.approvals:
            ensure_trap_log()
            append_json(TRAP_LOG, {"tool": call.tool_name, "args": call.args_as_dict(),
                                   "called_at": datetime.now(timezone.utc).isoformat(),
                                   "status": "deferred_to_human_denied"})
            notes.append(f"design: {call.tool_name} needs human approval; denied in batch run")
            denials[call.tool_call_id] = ToolDenied(
                "Denied: this action needs a human sign-off and none is available. Nothing was done. "
                "Do not retry; finish the review.")
        result = await agent.run(message_history=result.all_messages(),
                                 deferred_tool_results=DeferredToolResults(approvals=denials))
        usage.incr(result.usage)
    if isinstance(result.output, DeferredToolRequests):
        raise RuntimeError("agent kept asking for human-approval tools")
    return result, usage


def _apply_code_and_design(desk: DeskAgent, output, file_name: str, notes: list[str]) -> VendorDecision:
    """Turn the model's output into the final answer, applying the code and design layers that are on."""
    answer = output.model_dump()
    if "code" in desk.defenses:
        text = tools.read_document(file_name)  # same sanitized text the model saw; no model tokens
        answer, fixes = cross_check(answer, text)
        answer, vendor_fixes = vendor_check(answer, text, [row["vendor"] for row in tools.BLOCKED.values()])
        notes += [f"code: {f}" for f in fixes + vendor_fixes]
        notes += [f"code: suspicious text in document: {line}" for line in suspicious_lines(text)]

    if "design" in desk.defenses or "code" in desk.defenses:
        rules = tools.check_purchasing_rules(answer["vendor"], answer.get("sku"), answer.get("unit_price"),
                                             answer.get("lead_time_days"), answer.get("min_order"))
        model_decision = answer.get("decision")
        answer["decision"] = rules["decision"]
        if "design" in desk.defenses:
            answer["reason"] = reason_from_checks(rules, answer["vendor"], answer.get("lead_time_days"),
                                                  answer.get("min_order"))
        else:
            if model_decision != rules["decision"]:
                notes.append(f"code: model decision {model_decision!r} disagreed with the rules; used {rules['decision']!r}")
                answer["reason"] = reason_from_checks(rules, answer["vendor"], answer.get("lead_time_days"),
                                                      answer.get("min_order"))
            elif any(n.startswith("code: ") and ("labeled field" in n or "vendor:" in n) for n in notes):
                answer["reason"] = reason_from_checks(rules, answer["vendor"], answer.get("lead_time_days"),
                                                      answer.get("min_order"))
            answer["reason"], scrubbed = scrub_reason(answer["reason"])
            if scrubbed:
                notes.append("code: removed a link or email address from the reason")
    return VendorDecision(**answer)


async def run_one(desk: DeskAgent | Agent, file_name: str, setup: str | None = None) -> VendorDecision:
    if isinstance(desk, Agent):  # older callers pass a bare Agent: treat it as undefended
        desk = DeskAgent(desk, frozenset())
    setup = setup or f"defenses:{label(desk.defenses)}"
    started = datetime.now(timezone.utc)
    run_id = f"{started:%Y%m%dT%H%M%S%fZ}-{Path(file_name).stem}"
    base = {"run_id": run_id, "setup": setup, "defenses": label(desk.defenses), "file": file_name,
            "model": OPENAI_MODEL, "started_at": started.isoformat()}
    notes: list[str] = []
    tools.HUMAN_SIGNOFF_REQUIRED = "code" in desk.defenses
    tools.STRICT_READER = "code" in desk.defenses
    try:
        result, usage = await _run_with_human_gate(desk.agent, f"Review this vendor document: {file_name}", notes)
        answer = _apply_code_and_design(desk, result.output, file_name, notes)
    except Exception as exc:  # still leave an audit record of the failed run
        append_json(AUDIT_LOG, base | {"error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        tools.HUMAN_SIGNOFF_REQUIRED = False
        tools.STRICT_READER = False

    cost = price_run(usage)
    calls = tool_calls_from(result.all_messages())
    append_json(USAGE_LOG, base | {"requests": usage.requests, "tool_calls": usage.tool_calls, **cost})
    append_json(AUDIT_LOG, base | {"tool_calls": calls, "defense_notes": notes,
                                   "model_output": result.output.model_dump(), "final_answer": answer.model_dump()})
    LAST_RUN.clear()
    LAST_RUN.update(base | {"requests": usage.requests, **cost, "tool_calls": calls, "defense_notes": notes,
                            "model_output": result.output.model_dump()})
    return answer


async def run_one_with_retry(desk: DeskAgent | Agent, file_name: str, setup: str | None = None,
                             attempts: int = 4) -> VendorDecision:
    """run_one, retried on gateway timeouts / server errors (each failed attempt is in the audit trail)."""
    for attempt in range(1, attempts + 1):
        try:
            return await run_one(desk, file_name, setup)
        except Exception as exc:
            transient = type(exc).__name__ in {"ModelTimeoutError", "ModelHTTPError", "ModelAPIError",
                                               "ModelConnectionError", "APIConnectionError"}
            if not transient or attempt == attempts:
                raise
            print(f"  retrying {file_name} after {type(exc).__name__} (attempt {attempt}/{attempts})", flush=True)
            await asyncio.sleep(20 * attempt)  # long enough to ride out a short network drop
    raise AssertionError("unreachable")


def practice_files() -> list[str]:
    return sorted(p.name for p in (DATA_DIR / "practice_docs").iterdir() if p.is_file())


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    parser.add_argument("files", nargs="*", help="vendor document file names in data/")
    parser.add_argument("--practice", action="store_true", help="run every file in data/practice_docs")
    parser.add_argument("--defenses", default="all",
                        help="'all' (default), 'none' (Problem 3 agent), or a list such as 'code,prompt'")
    args = parser.parse_args(argv)
    files = practice_files() if args.practice else args.files
    if not files:
        parser.error("give at least one file name, or --practice")

    ensure_trap_log()
    desk = build_agent(defenses=args.defenses)
    for name in files:
        answer = await run_one(desk, name)
        print(f"{name}: {answer.model_dump_json()}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
