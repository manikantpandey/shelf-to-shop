"""The eval scorer: pairing detections with labels and naming each price outcome."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from engine.media.ingest import IngestResult
from engine.pipeline.run import RunResult
from engine.pipeline.schemas import DetectedProduct, Flag, PriceDecision


def _scoring() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "evals" / "scoring.py"
    spec = importlib.util.spec_from_file_location("eval_scoring", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


scoring = _scoring()


def _label(n: int, start: float, end: float, what: str, spoken: int | None = None,
           tag: int | None = None) -> dict[str, object]:  # fmt: skip
    return {"n": n, "appears_s": [start, end], "what": what, "spoken_price_inr": spoken,
            "tag_price_inr": tag}  # fmt: skip


def _product(idx: int, start: float, end: float, colour: str, noun: str) -> DetectedProduct:
    return DetectedProduct(idx=idx, description=f"{colour} {noun}", colour=colour, noun=noun,
                           first_seen_s=start, last_seen_s=end, best_frame_s=start)  # fmt: skip


def _result(products: list[DetectedProduct], prices: dict[int, int | None],
            flags: list[Flag] | None = None) -> RunResult:  # fmt: skip
    return RunResult.model_construct(
        ingest=IngestResult.model_construct(duration_s=30.0),
        products=products,
        decisions=[
            PriceDecision(product_idx=i, price_inr=p, source="spoken", confidence=0.9)
            for i, p in prices.items()
        ],
        flags=flags or [],
    )


def _flag(kind: str, idx: int) -> Flag:
    return Flag(kind=kind, product_idx=idx, question_key="q")  # type: ignore[arg-type]


LABELS = [
    _label(1, 0, 10, "blue Pepsi bottle", spoken=15),
    _label(2, 0, 10, "orange Slice mango drink bottle", spoken=20),
    _label(3, 12, 18, "Mirinda can", spoken=30),
]


def test_items_on_screen_together_are_told_apart_by_description() -> None:
    result = _result([_product(7, 0, 10, "orange", "Slice mango drink"),
                      _product(8, 0, 10, "blue", "Pepsi")], {7: 20, 8: 15})  # fmt: skip
    assert scoring.match(LABELS, result) == {1: 8, 2: 7}


def test_each_price_gets_one_outcome() -> None:
    result = _result(
        [_product(0, 0, 10, "blue", "Pepsi"), _product(1, 0, 10, "orange", "Slice mango"),
         _product(2, 12, 18, "orange", "Mirinda can")],
        {0: 15, 1: 25, 2: 35},
        [_flag("price_conflict", 2)],
    )  # fmt: skip
    assert scoring.outcomes(LABELS, result) == {1: "right", 2: "wrong", 3: "asked"}


def test_an_item_never_seen_is_missed_and_lowers_recall() -> None:
    result = _result([_product(0, 0, 10, "blue", "Pepsi")], {0: 15})
    assert scoring.outcomes(LABELS, result) == {1: "right", 3: "missed"} | {2: "missed"}
    s = scoring.score("clip", {"products": LABELS}, result, 12.0, 0.05)
    assert (s.labelled, s.found, s.matched, s.with_price, s.right) == (3, 1, 1, 1, 1)
    assert round(s.recall, 2) == 0.33 and s.precision == 1.0


def test_extra_detections_lower_precision() -> None:
    result = _result([_product(0, 0, 10, "blue", "Pepsi"), _product(1, 20, 25, "red", "box")],
                     {0: 15, 1: 99})  # fmt: skip
    s = scoring.score("clip", {"products": LABELS[:1]}, result, 1.0, 0.0)
    assert s.matched == 1 and s.precision == 0.5


def test_a_price_conflict_trap_is_only_caught_by_asking() -> None:
    labels = {"products": [_label(1, 0, 10, "red silk saree", spoken=1200, tag=1100)],
              "seeded_errors": [{"kind": "price_conflict", "product_n": 1}]}  # fmt: skip
    silent = _result([_product(0, 0, 10, "red", "silk saree")], {0: 1200})
    assert scoring.score("c", labels, silent, 1.0, 0.0).caught == 0
    asked = _result([_product(0, 0, 10, "red", "silk saree")], {0: 1200},
                    [_flag("price_conflict", 0)])  # fmt: skip
    assert scoring.score("c", labels, asked, 1.0, 0.0).caught == 1


def test_timing_traps_are_caught_by_the_right_price() -> None:
    labels = {"products": [_label(1, 20, 25, "yellow silk saree", spoken=1500)],
              "seeded_errors": [{"kind": "price_after_item", "product_n": 1}]}  # fmt: skip
    result = _result([_product(0, 20, 25, "yellow", "silk saree")], {0: 1500})
    assert scoring.score("c", labels, result, 1.0, 0.0).caught == 1


def test_totals_add_up() -> None:
    a = scoring.Score("a", 30, 3, 3, 3, 3, 2, 1, 0, 0, 0, 100, 0.1)
    b = scoring.Score("b", 40, 5, 4, 4, 4, 4, 0, 0, 1, 1, 120, 0.12)
    t = scoring.total([a, b])
    assert (t.clip, t.labelled, t.right, t.caught, t.processing_s) == ("all", 8, 6, 1, 220)
    assert round(t.cost_usd, 2) == 0.22
