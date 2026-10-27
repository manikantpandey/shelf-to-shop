"""What the pipeline needs from model providers; Meta implementations and fakes satisfy it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

import numpy as np
from pydantic import BaseModel

from engine.agents.structured import Effort, StructuredResult
from engine.pipeline.schemas import Box, DetectedProduct, Transcript
from engine.runlog import CallContext

M = TypeVar("M", bound=BaseModel)


class VideoUnderstanding(Protocol):
    async def analyse(
        self, ctx: CallContext, video: Path, width: int, height: int, duration_s: float
    ) -> list[DetectedProduct]: ...


class Transcriber(Protocol):
    async def transcribe(
        self,
        ctx: CallContext,
        wav: Path,
        duration_s: float,
        speech_spans: list[tuple[float, float]],
    ) -> Transcript: ...


@dataclass(frozen=True)
class MaskResult:
    mask: np.ndarray
    confidence: float | None
    method: str


class Segmenter(Protocol):
    async def cutout(
        self, ctx: CallContext, frame: Path, box: Box | None, noun: str
    ) -> MaskResult | None: ...


class ImageGen(Protocol):
    async def backdrop(self, ctx: CallContext, prompt: str) -> bytes: ...


class StructuredLLM(Protocol):
    async def run(
        self,
        ctx: CallContext,
        *,
        output: type[M],
        instructions: str,
        content: list[dict[str, Any]],
        estimate_input_tokens: int,
        effort: Effort = "low",
        max_output_tokens: int = 4096,
        inputs_summary: dict[str, Any] | None = None,
    ) -> StructuredResult[M]: ...


@dataclass
class Providers:
    video: VideoUnderstanding
    transcriber: Transcriber
    segmenter: Segmenter
    images: ImageGen
    text: StructuredLLM
