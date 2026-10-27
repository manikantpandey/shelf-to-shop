"""Matcher and verifier, replaying the spike outputs for the synthetic clip (synth_a)."""

from __future__ import annotations

import pytest

from engine.pipeline.align import align_chunks, place_turns
from engine.pipeline.colours import colours_in
from engine.pipeline.match import match_prices
from engine.pipeline.schemas import (
    Cutout,
    DetectedProduct,
    TimedChunk,
    TimedMention,
    Transcript,
)
from engine.pipeline.verify import verify

# What Muse Spark returned (spike 1b) and what the ASR + pause detector produced (spike 3).
PRODUCTS = [
    (1, "blue", 0.0, 5.0, 1200, None),
    (2, "red and gold", 4.5, 11.5, 1200, 1100),
    (3, "green", 11.0, 16.0, 850, None),
    (4, "light blue", 15.5, 20.5, 900, None),
    (5, "yellow and maroon", 20.0, 25.0, None, None),
    (6, "pink", 24.5, 32.0, None, None),
]
TURNS = [
    (
        0.70,
        14.94,
        "ये नीला वाला, बड़ा सा, ये लाल लाल सिल्क वाली, एक हजार दो सौ, सादे आठ सौ, अगला हरा वाला,",
    ),
    (15.98, 19.58, "ये भी नीला, हल्का वाला, वाला, नौ सौ,"),
    (25.02, 27.66, "पीच वाला पीला, दस हजार"),
    (28.22, 31.50, "और ये गुलाबी वाला भी देख लीजिए,"),
]
SPANS = [
    (1.0, 2.3), (2.46, 3.5), (5.4, 6.98), (7.12, 8.68), (9.2, 10.56), (10.72, 12.02),
    (16.2, 17.34), (17.54, 18.58), (18.74, 19.58), (25.3, 26.6), (26.74, 27.8), (28.5, 31.14),
]  # fmt: skip


def products() -> list[DetectedProduct]:
    return [
        DetectedProduct(
            idx=idx,
            description=f"{colour} saree",
            colour=colour,
            noun="saree",
            first_seen_s=a,
            last_seen_s=b,
            best_frame_s=(a + b) / 2,
            spark_price_inr=spark,
            tag_price_inr=tag,
            tag_text=f"Rs {tag}" if tag else None,
        )
        for idx, colour, a, b, spark, tag in PRODUCTS
    ]


def transcript() -> Transcript:
    chunks, mentions, timing = place_turns(TURNS, SPANS)
    return Transcript(text=" ".join(t for *_, t in TURNS), chunks=chunks, mentions=mentions,
                      timing=timing)  # type: ignore[arg-type]  # fmt: skip


def test_turn_chunks_align_to_pause_spans() -> None:
    tr = transcript()
    assert tr.timing == "aligned"
    by_value = {m.value_inr: m.t_s for m in tr.mentions}
    assert by_value[1200] == pytest.approx(7.12, abs=0.05)  # labelled 7.11
    assert by_value[850] == pytest.approx(9.2, abs=0.05)  # labelled 9.20
    assert by_value[900] == pytest.approx(18.74, abs=0.3)  # labelled 18.73
    assert by_value[10000] == pytest.approx(26.74, abs=0.3)  # misheard "dedh hazaar"


def test_alignment_gives_up_cleanly() -> None:
    assert align_chunks([], [(0, 1)]) is None
    assert align_chunks(["a"], []) is None


def test_colour_words_in_both_scripts() -> None:
    assert colours_in("अगला हरा वाला") == {"green"}
    assert colours_in("ye neela wala") == {"blue"}
    assert colours_in("light blue cotton") >= {"sky", "blue"}
    assert colours_in("yellow and maroon") == {"yellow", "maroon"}
    assert colours_in("dekh lijiye") == set()


def test_synthetic_clip_prices_and_flags() -> None:
    prods = products()
    result = match_prices(prods, transcript())
    by_idx = {d.product_idx: d for d in result.decisions}

    # Heard "बड़ा सा" instead of "barah sau": vision pairing supplies the price.
    assert (by_idx[1].price_inr, by_idx[1].source) == (1200, "vision_pairing")
    # Speech and vision agree.
    assert (by_idx[2].price_inr, by_idx[2].confidence) == (1200, 0.95)
    # Said while item 2 was on screen, but "agla hara wala" + vision put it on item 3.
    assert (by_idx[3].price_inr, by_idx[3].source) == (850, "spoken")
    assert by_idx[4].price_inr == 900
    assert by_idx[6].price_inr is None
    assert all(d.evidence for d in result.decisions if d.price_inr is not None)

    flags = verify(prods, result.decisions, [], result.flags)
    kinds = {(f.kind, f.product_idx) for f in flags}
    assert ("price_conflict", 2) in kinds  # tag 1100 vs spoken 1200
    assert ("missing_price", 6) in kinds
    # "dedh hazaar" misheard as 10,000 must never pass silently: either item 5 gets it and is
    # flagged as implausible, or the seller is asked which item it belongs to.
    if by_idx[5].price_inr == 10000:
        assert ("implausible_price", 5) in kinds
    else:
        assert any(f.kind == "ambiguous_price" and 10000 in f.options for f in flags)
    tag_flag = next(f for f in flags if f.kind == "price_conflict" and f.product_idx == 2)
    assert tag_flag.question_key == "flag.price_conflict.tag"
    assert tag_flag.options == [1200, 1100]


def _single_mention(t: float, value: int, text: str = "x") -> Transcript:
    return Transcript(
        text=text,
        chunks=[TimedChunk(start_s=t, end_s=t + 1, text=text, turn=0)],
        mentions=[TimedMention(value_inr=value, t_s=t, words=str(value), chunk=0, confidence=0.9)],
    )


def _plain(idx: int, a: float, b: float, colour: str = "red") -> DetectedProduct:
    return DetectedProduct(
        idx=idx,
        description=f"{colour} item",
        colour=colour,
        noun="saree",
        first_seen_s=a,
        last_seen_s=b,
        best_frame_s=a,
    )


def test_near_tie_becomes_a_question_not_a_guess() -> None:
    prods = [_plain(1, 0, 5), _plain(2, 4, 9)]  # both on screen at t=4.5
    result = match_prices(prods, _single_mention(4.5, 700))
    assert all(d.price_inr is None for d in result.decisions)
    [flag] = result.flags
    assert flag.kind == "ambiguous_price"
    assert sorted(flag.candidates) == [1, 2]
    assert flag.options == [700]
    # verify() must not also ask "missing price" for the same items.
    assert [f.kind for f in verify(prods, result.decisions, [], result.flags)] == [
        "ambiguous_price"
    ]


def test_direction_word_breaks_the_tie() -> None:
    prods = [_plain(1, 0, 5), _plain(2, 4.6, 9)]  # item 2 appears just after the price
    result = match_prices(prods, _single_mention(4.5, 700, "agla wala saat sau"))
    assert {d.product_idx: d.price_inr for d in result.decisions} == {1: None, 2: 700}


def test_colour_word_breaks_the_tie() -> None:
    prods = [_plain(1, 0, 5, "red"), _plain(2, 4, 9, "green")]
    result = match_prices(prods, _single_mention(4.5, 700, "ye hara wala"))
    assert {d.product_idx: d.price_inr for d in result.decisions} == {1: None, 2: 700}


def test_prices_far_from_any_item_are_unplaced() -> None:
    result = match_prices([_plain(1, 0, 5)], _single_mention(30.0, 500))
    assert result.unplaced and result.decisions[0].price_inr is None


def test_two_different_spoken_prices_for_one_item() -> None:
    tr = Transcript(
        text="x",
        chunks=[TimedChunk(start_s=1, end_s=2, text="a", turn=0),
                TimedChunk(start_s=3, end_s=4, text="b", turn=0)],
        mentions=[TimedMention(value_inr=500, t_s=1, words="500", chunk=0, confidence=0.9),
                  TimedMention(value_inr=450, t_s=3, words="450", chunk=1, confidence=0.9)],
    )  # fmt: skip
    result = match_prices([_plain(1, 0, 5)], tr)
    assert any(f.question_key == "flag.price_conflict.multiple" for f in result.flags)


def test_duplicates_and_weak_masks_are_flagged(tmp_path: object) -> None:
    from pathlib import Path

    prods = [_plain(1, 0, 6, "blue"), _plain(2, 1, 6, "blue")]
    cut = Cutout(product_idx=1, frame=Path("f.jpg"), mask=Path("m.png"), confidence=0.4,
                 coverage=0.3, method="point")  # fmt: skip
    flags = verify(prods, [], [cut], [])
    assert {f.kind for f in flags} == {"duplicate", "low_conf_mask"}
