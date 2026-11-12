"""Structured output for the Campus Customs vendor desk agent.

The fields match section 13 of the shop handbook ("How the vendor desk agent should report").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VendorDecision(BaseModel):
    """One vendor document -> one purchasing recommendation."""

    vendor: str = Field(description="Vendor name exactly as the document gives it, e.g. 'Blue Hen Apparel'.")
    sku: str | None = Field(
        description="Campus Customs SKU the quote is for, e.g. 'CC-HD-006'. null if the document does not say."
    )
    unit_price: float | None = Field(
        description="Quoted price per unit in US dollars, e.g. 21.80. null if the document does not say."
    )
    lead_time_days: int | None = Field(
        description="Vendor lead time in days, as a whole number. null if the document does not say."
    )
    min_order: int | None = Field(
        description="Vendor minimum order in units, as a whole number. null if the document does not say."
    )
    decision: Literal["recommend", "do_not_recommend"] = Field(
        description="'recommend' only if all four purchasing checks pass; otherwise 'do_not_recommend'."
    )
    reason: str = Field(description="One sentence that names the purchasing check that decided it.")

    @field_validator("sku")
    @classmethod
    def _normalise_sku(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("reason")
    @classmethod
    def _one_sentence(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("reason must not be empty")
        body = value.rstrip(".!?")
        if any(f"{mark} " in body for mark in ".!?"):
            # Retried by PydanticAI: the model gets this message and fixes its answer.
            raise ValueError("reason must be exactly one sentence")
        return value
