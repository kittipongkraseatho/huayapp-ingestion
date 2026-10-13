from PIL import Image

from huayapp_scraper.ocr import (
    CanvasGlyphDecoder,
    CanvasOCR,
    _DEBUG_DECODER_SCRIPT,
    accept_template_decode,
)


class FakeBackend:
    """Stand-in for the RapidBackend that returns ``(x, text, confidence)``
    triples — same shape as the production backend after the multi-region
    fix."""

    def __init__(self, text, confidence, x=0.0):
        self.text = text
        self.confidence = confidence
        self.x = x

    def recognize(self, image):
        return [(self.x, self.text, self.confidence)]


def test_canvas_ocr_preserves_leading_zeroes():
    reader = CanvasOCR(backend=FakeBackend("007", 0.99), min_confidence=0.8)

    assert reader.read(Image.new("RGB", (20, 20)), expected_digits=3) == "007"


class MultiRegionBackend:
    def __init__(self, regions):
        self.regions = regions  # list of (x, text, confidence)

    def recognize(self, image):
        return sorted(self.regions, key=lambda r: r[0])


def test_canvas_ocr_concatenates_multi_regions_in_left_to_right_order():
    backend = MultiRegionBackend(
        [
            (50.0, "8", 0.6),  # rightmost digit first
            (10.0, "5", 0.7),
            (30.0, "7", 0.55),
        ]
    )
    reader = CanvasOCR(backend=backend, min_confidence=0.5)

    assert reader.read(Image.new("RGB", (20, 20)), expected_digits=3) == "578"


def test_canvas_ocr_drops_below_threshold_regions_but_keeps_above():
    backend = MultiRegionBackend(
        [
            (10.0, "5", 0.7),
            (30.0, "noise", 0.4),  # below 0.5 threshold, dropped
            (50.0, "7", 0.6),
        ]
    )
    reader = CanvasOCR(backend=backend, min_confidence=0.5)

    assert reader.read(Image.new("RGB", (20, 20)), expected_digits=2) == "57"


def test_canvas_ocr_returns_none_when_no_region_meets_threshold():
    backend = MultiRegionBackend(
        [
            (10.0, "5", 0.4),
            (30.0, "7", 0.3),
        ]
    )
    reader = CanvasOCR(backend=backend, min_confidence=0.5)

    assert reader.read(Image.new("RGB", (20, 20))) is None


def test_canvas_ocr_rejects_non_numeric_regions():
    backend = MultiRegionBackend(
        [
            (10.0, "abc", 0.9),  # digits-only filter rejects
            (30.0, "12", 0.9),
        ]
    )
    reader = CanvasOCR(backend=backend, min_confidence=0.5)

    assert reader.read(Image.new("RGB", (20, 20))) == "12"


def test_canvas_ocr_length_filter_applies_to_combined_regions():
    backend = MultiRegionBackend(
        [
            (10.0, "57", 0.7),
            (50.0, "821", 0.6),
        ]
    )
    reader = CanvasOCR(backend=backend, min_confidence=0.5)

    # combined length 5 — different from per-region length 2 or 3
    assert reader.read(Image.new("RGB", (20, 20)), expected_digits=5) == "57821"
    assert reader.read(Image.new("RGB", (20, 20)), expected_digits=3) is None


def test_canvas_ocr_rejects_low_confidence_and_wrong_digit_count():
    image = Image.new("RGB", (20, 20))
    assert CanvasOCR(FakeBackend("701", 0.79), min_confidence=0.8).read(image, 3) is None
    assert CanvasOCR(FakeBackend("70", 0.99), min_confidence=0.8).read(image, 3) is None
    assert CanvasOCR(FakeBackend("7O1", 0.99), min_confidence=0.8).read(image, 3) is None


def test_template_decode_accepts_exact_rendered_glyph_scores():
    payload = {"text": "402701", "scores": [1.0, 0.988, 1.0, 0.985, 0.972, 0.963]}

    assert accept_template_decode(payload, expected_digits=6, min_score=0.9) == "402701"


def test_template_decode_rejects_ambiguous_rendered_glyphs():
    assert accept_template_decode(
        {"text": "402701", "scores": [1.0, 0.988, 0.79, 0.985, 0.972, 0.963]},
        expected_digits=6,
        min_score=0.9,
    ) is None


def test_debug_decoder_script_includes_diagnostic_fields():
    # The debug variant must expose enough state for a human to diagnose
    # why a canvas was rejected. Lock in the schema so silent regressions
    # are caught during refactors.
    for marker in (
        "font",
        "transform",
        "effective_scale",
        "ink_pixel_count",
        "group_count",
        "all_scores",
        "template_error",
    ):
        assert marker in _DEBUG_DECODER_SCRIPT, f"debug script missing {marker}"


def test_debug_read_delegates_to_evaluate_with_debug_script():
    class FakeLocator:
        def __init__(self):
            self.calls = []

        def evaluate(self, script):
            self.calls.append(script)
            return {"canvas_width": 0, "canvas_height": 0}

    locator = FakeLocator()
    decoder = CanvasGlyphDecoder(min_score=0.7)

    result = decoder.debug_read(locator)

    assert result == {"canvas_width": 0, "canvas_height": 0}
    assert locator.calls == [_DEBUG_DECODER_SCRIPT]


def test_debug_read_min_score_does_not_affect_decode():
    # debug_read must not enforce the production min_score — we want the
    # raw similarity values to surface even when below threshold.
    class FakeLocator:
        def evaluate(self, script):
            return {
                "canvas_width": 10,
                "canvas_height": 10,
                "template_error": None,
                "glyphs": [{"best_digit": 5, "best_score": 0.55, "all_scores": [0.5] * 10}],
            }

    decoder = CanvasGlyphDecoder(min_score=0.99)
    result = decoder.debug_read(FakeLocator())

    assert result["glyphs"][0]["best_score"] == 0.55  # not filtered out
