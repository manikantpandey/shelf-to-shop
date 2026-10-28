"""Data passed between pipeline stages. Every stage input and output is a pydantic model."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Box(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    def centre(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2


class DetectedProduct(BaseModel):
    """One item seen in the video (Muse Spark), with its own opinion of the spoken price."""

    idx: int
    description: str
    colour: str
    noun: str = Field(description="short noun phrase for the item, e.g. 'saree', 'sandal'")
    first_seen_s: float
    last_seen_s: float
    best_frame_s: float
    box: Box | None = None
    tag_text: str | None = None
    tag_price_inr: int | None = None
    spark_price_inr: int | None = None
    spark_price_words: str | None = None


class TimedChunk(BaseModel):
    """A stretch of transcript text placed on the audio timeline."""

    start_s: float
    end_s: float
    text: str
    turn: int


class TimedMention(BaseModel):
    value_inr: int
    t_s: float
    words: str
    chunk: int  # index into the transcript's chunks
    confidence: float


class Transcript(BaseModel):
    text: str
    chunks: list[TimedChunk]
    mentions: list[TimedMention]
    timing: Literal["aligned", "interpolated", "none"] = "aligned"


EvidenceKind = Literal["speech", "vision_pairing", "tag", "seller"]


class Evidence(BaseModel):
    kind: EvidenceKind
    value_inr: int | None
    t_s: float | None = None
    snippet: str | None = None


class PriceDecision(BaseModel):
    product_idx: int
    price_inr: int | None
    # The printed price when the item sells below it (MRP on packed goods).
    mrp_inr: int | None = None
    source: Literal["spoken", "vision_pairing", "tag", "seller", "none"]
    confidence: float
    evidence: list[Evidence] = Field(default_factory=list)


FlagKind = Literal[
    "missing_price",
    "price_conflict",
    "ambiguous_price",
    "implausible_price",
    "uncertain_price",
    "duplicate",
    "low_conf_mask",
]


class Flag(BaseModel):
    kind: FlagKind
    product_idx: int | None
    # i18n key + params; the UI renders the question in the seller's language.
    question_key: str
    params: dict[str, str | int] = Field(default_factory=dict)
    options: list[int] = Field(default_factory=list, description="suggested prices in rupees")
    candidates: list[int] = Field(default_factory=list, description="products the flag may concern")


class Cutout(BaseModel):
    product_idx: int
    frame: Path
    mask: Path
    confidence: float | None
    coverage: float
    method: Literal["point", "concept", "box_fallback"]


class Enriched(BaseModel):
    product_idx: int
    title_en: str
    title_hi: str
    description_en: str
    description_hi: str
    brand: str | None = None
    category: str
    colour: str
    material: str | None
    pattern: str | None


class FinalImage(BaseModel):
    product_idx: int
    path: Path
    ai_background: bool
