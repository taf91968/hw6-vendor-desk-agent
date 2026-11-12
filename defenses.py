"""Problem 6: three defense layers for the vendor desk agent. Each layer can be switched on or off.

    code    Deterministic Python checks, no extra model tokens:
              - cross-check the model's numbers against the document's own labeled fields
                ("Unit price: $X", "Lead time: N days", "Minimum order: N units"); a later "correction",
                "revised" or "replaces" paragraph cannot change them
              - recompute the decision from the final values with check_purchasing_rules
              - strip links and email addresses from the reason
              - send_email / approve_payment refuse to act without a human sign-off
    design  How the agent is built:
              - send_email / approve_payment are approval-required tools: a call pauses the run and goes to a
                human; with no human in a batch run it is denied, and the model is told so
              - the model only extracts facts; code makes the decision and writes the reason from the rule
                results, so document text can never reach the buyer through the reason
    prompt  Extra rules in prompts/prompt.md (the no-defense agent uses prompts/prompt_baseline.md)

"none" is the Problem 3 agent exactly as it was attacked in Problem 5.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

LAYERS = ("code", "design", "prompt")


def parse_defenses(text: str) -> frozenset[str]:
    """'all' | 'none' | comma list such as 'code,prompt'."""
    text = (text or "all").strip().lower()
    if text == "all":
        return frozenset(LAYERS)
    if text == "none":
        return frozenset()
    chosen = {t.strip() for t in text.split(",") if t.strip()}
    unknown = chosen - set(LAYERS)
    if unknown:
        raise ValueError(f"unknown defense layer(s): {sorted(unknown)}; choose from {LAYERS}, 'all' or 'none'")
    return frozenset(chosen)


def label(defenses: frozenset[str]) -> str:
    return "+".join(l for l in LAYERS if l in defenses) or "none"


# --------------------------------------------------------------------------- design: extraction-only output


class Extraction(BaseModel):
    """What the model returns when the design layer is on: facts only, no decision, no free text."""

    vendor: str = Field(description="Vendor name exactly as the document gives it.")
    sku: str | None = Field(description="Campus Customs SKU, e.g. 'CC-HD-006'. null if not stated.")
    unit_price: float | None = Field(description="Quoted unit price in dollars, from the quote itself. null if not stated.")
    lead_time_days: int | None = Field(description="Lead time in days, from the quote itself. null if not stated.")
    min_order: int | None = Field(description="Minimum order in units. null if not stated.")


DESIGN_NOTE = (
    "\n\n## Output for this run\n\nReturn only the extracted facts: vendor, sku, unit_price, lead_time_days, "
    "min_order. Code runs the purchasing checks and writes the decision and reason. You may still call the "
    "lookup tools to find a SKU.\n"
)

CHECK_NAMES = {
    "approved_vendor": "approved vendor",
    "price": "price",
    "lead_time": "lead time",
    "minimum_order": "minimum order",
}


def reason_from_checks(rules: dict, vendor: str, lead_time_days, min_order) -> str:
    """One sentence that names the deciding check(s). Never reveals the max unit cost."""
    failed = rules["failed_checks"]
    if not failed:
        return "All four purchasing checks passed: approved vendor, price, lead time, and minimum order."
    parts = []
    for name in failed:
        if name == "approved_vendor":
            parts.append(f"{vendor} is not an approved vendor")
        elif name == "price":
            unknown = "unknown" in rules["checks"]["price"]["detail"].lower()
            parts.append("the unit price or SKU is not stated, so the price cannot be checked" if unknown
                         else "the quoted unit price is above the max unit cost for this SKU")
        elif name == "lead_time":
            parts.append(f"the lead time of {lead_time_days} days is over the 21-day limit"
                         if lead_time_days is not None else "the lead time is unknown")
        elif name == "minimum_order":
            parts.append(f"the minimum order of {min_order} units is over the 600-unit limit"
                         if min_order is not None else "the minimum order is unknown")
    labels = [CHECK_NAMES[n] for n in failed]
    names = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    return f"Failed the {names} check{'s' if len(failed) > 1 else ''}: " + "; ".join(parts) + "."


# --------------------------------------------------------------------------- code: labeled-field cross-check

_NUM = r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
_LABELS = {
    "unit_price": re.compile(r"^[\s|*-]*unit price[\s|:*-]+" + _NUM, re.I | re.M),
    "lead_time_days": re.compile(r"^[\s|*-]*lead time[\s|:*-]+([0-9]+)\s*(?:-\s*([0-9]+)\s*)?(business\s+|calendar\s+)?(days?|weeks?)", re.I | re.M),
    "min_order": re.compile(r"^[\s|*-]*minimum order[\s|:*-]+([0-9][0-9,]*)", re.I | re.M),
    "sku": re.compile(r"\bCC-[A-Z]{2}-[0-9]{3}\b"),
}
SUSPICIOUS = re.compile(
    r"send_email|approve_payment|\breplaces?\b|\bcorrection\b|\brevised\b|\bis now\b|\bignore\b|"
    r"https?://|\bstanding instruction\b|\bmax unit cost\b|\bwith send|\bdeposit of \$", re.I)
URL_OR_EMAIL = re.compile(r"\s*\(?\b(?:https?://\S+|www\.\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+)\)?", re.I)


def labeled_values(text: str) -> dict[str, list]:
    """Every value the document states on a labeled line (table row or 'Label: value' line)."""
    out: dict[str, list] = {}
    for m in _LABELS["unit_price"].finditer(text):
        out.setdefault("unit_price", []).append(round(float(m.group(1).replace(",", "")), 2))
    for m in _LABELS["lead_time_days"].finditer(text):
        n = int(m.group(2) or m.group(1))  # a range like 10-14 days -> 14
        out.setdefault("lead_time_days", []).append(n * 7 if m.group(4).lower().startswith("week") else n)
    for m in _LABELS["min_order"].finditer(text):
        out.setdefault("min_order", []).append(int(m.group(1).replace(",", "")))
    skus = _LABELS["sku"].findall(text)
    if skus:
        out["sku"] = skus
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def suspicious_lines(text: str) -> list[str]:
    return [" ".join(line.split())[:200] for line in text.splitlines() if SUSPICIOUS.search(line)]


def cross_check(answer: dict, document_text: str) -> tuple[dict, list[str]]:
    """Replace any model value that disagrees with the document's single labeled value."""
    fixed = dict(answer)
    notes = []
    for field, values in labeled_values(document_text).items():
        if len(values) != 1:
            if len(values) > 1:
                notes.append(f"{field}: document has more than one labeled value {values}; kept the model's value")
            continue
        stated = values[0]
        got = fixed.get(field)
        same = (got is not None and (abs(float(got) - float(stated)) < 0.005 if field == "unit_price"
                                     else str(got).upper() == str(stated).upper()))
        if not same:
            notes.append(f"{field}: model said {got!r}, labeled field says {stated!r}; used the labeled value")
            fixed[field] = stated
    return fixed, notes


def _norm_name(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def vendor_check(answer: dict, document_text: str, blocked_vendors: list[str]) -> tuple[dict, list[str]]:
    """If the document names a removed or pending vendor anywhere, that is the vendor that gets checked.

    Conservative on purpose: a removed vendor can't get through by also naming an approved one
    ("vendor of record: ...", "studio name of ..."). A person can still override the flag.
    """
    fixed, notes = dict(answer), []
    text = f" {_norm_name(document_text)} "
    named = [v for v in blocked_vendors if f" {_norm_name(v)} " in text]
    if named and _norm_name(fixed.get("vendor") or "") not in {_norm_name(v) for v in named}:
        notes.append(f"vendor: document names removed/pending vendor {named[0]!r} but the model reported "
                     f"{fixed.get('vendor')!r}; checked {named[0]!r}")
        fixed["vendor"] = named[0]
    return fixed, notes


def scrub_reason(reason: str) -> tuple[str, bool]:
    cleaned = " ".join(URL_OR_EMAIL.sub("", reason).split())
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned).rstrip(" :;,")
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned, cleaned != reason
