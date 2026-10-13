from __future__ import annotations

import re
from typing import Any, Mapping

from PIL import Image


class OCRUnavailableError(RuntimeError):
    pass


def accept_template_decode(
    payload: Mapping[str, Any] | None,
    *,
    expected_digits: int | None,
    min_score: float,
) -> str | None:
    """Accept only an unambiguous result returned by the browser glyph matcher."""
    if not payload:
        return None
    text = payload.get("text")
    scores = payload.get("scores")
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]+", text):
        return None
    if expected_digits is not None and len(text) != expected_digits:
        return None
    if not isinstance(scores, list) or len(scores) != len(text):
        return None
    try:
        if any(float(score) < min_score for score in scores):
            return None
    except (TypeError, ValueError):
        return None
    return text


class CanvasGlyphDecoder:
    """Decode digits by matching rendered browser glyphs, without reading data-val."""

    def __init__(self, *, min_score: float = 0.8):
        self.min_score = min_score

    def read(self, canvas_locator: Any, expected_digits: int | None = None) -> str | None:
        payload = canvas_locator.evaluate(_TEMPLATE_DECODER_SCRIPT)
        return accept_template_decode(
            payload,
            expected_digits=expected_digits,
            min_score=self.min_score,
        )

    def debug_read(self, canvas_locator: Any) -> dict[str, Any] | None:
        """Read a canvas and return full decoder diagnostics (font, transform,
        per-digit similarity scores). Production ``read`` is unaffected."""
        return canvas_locator.evaluate(_DEBUG_DECODER_SCRIPT)


_TEMPLATE_DECODER_SCRIPT = r"""canvas => {
  const ctx = canvas.getContext('2d');
  if (!ctx || !canvas.width || !canvas.height) return null;
  const width = canvas.width;
  const height = canvas.height;
  const source = ctx.getImageData(0, 0, width, height);

  function inkAt(data, index) {
    return data[index + 3] > 10 &&
      (data[index] < 245 || data[index + 1] < 245 || data[index + 2] < 245);
  }

  function maskFrom(imageData) {
    const data = imageData.data;
    const mask = new Uint8Array(imageData.width * imageData.height);
    for (let y = 0; y < imageData.height; y++) {
      for (let x = 0; x < imageData.width; x++) {
        const i = (y * imageData.width + x) * 4;
        mask[y * imageData.width + x] = inkAt(data, i) ? 1 : 0;
      }
    }
    return mask;
  }

  function normalizedRegion(sourceCanvas, sourceX, sourceY, sourceWidth, sourceHeight) {
    const crop = document.createElement('canvas');
    crop.width = sourceWidth;
    crop.height = sourceHeight;
    const cropCtx = crop.getContext('2d');
    cropCtx.drawImage(sourceCanvas, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);
    const cropData = cropCtx.getImageData(0, 0, sourceWidth, sourceHeight);
    const cropMask = maskFrom(cropData);
    let left = sourceWidth, top = sourceHeight, right = -1, bottom = -1;
    for (let y = 0; y < sourceHeight; y++) {
      for (let x = 0; x < sourceWidth; x++) {
        if (!cropMask[y * sourceWidth + x]) continue;
        left = Math.min(left, x); top = Math.min(top, y);
        right = Math.max(right, x); bottom = Math.max(bottom, y);
      }
    }
    if (right < left || bottom < top) return null;
    const normalized = document.createElement('canvas');
    normalized.width = 40;
    normalized.height = 60;
    normalized.getContext('2d').drawImage(
      crop, left, top, right - left + 1, bottom - top + 1,
      0, 0, normalized.width, normalized.height,
    );
    return maskFrom(normalized.getContext('2d').getImageData(0, 0, 40, 60));
  }

  const sourceMask = maskFrom(source);
  const groups = [];
  let start = null;
  for (let x = 0; x < width; x++) {
    let hasInk = false;
    for (let y = 0; y < height; y++) {
      if (sourceMask[y * width + x]) { hasInk = true; break; }
    }
    if (hasInk && start === null) start = x;
    if (!hasInk && start !== null) { groups.push([start, x - 1]); start = null; }
  }
  if (start !== null) groups.push([start, width - 1]);
  if (!groups.length || groups.length > 12) return null;

  const transform = ctx.getTransform ? ctx.getTransform() : null;
  if (!transform) return null;
  const logicalWidth = width / (transform.a || 1);
  const logicalHeight = height / (transform.d || 1);
  const templates = [];
  for (let digit = 0; digit <= 9; digit++) {
    const template = document.createElement('canvas');
    template.width = width;
    template.height = height;
    const tctx = template.getContext('2d');
    tctx.setTransform(transform);
    tctx.font = ctx.font;
    tctx.textAlign = ctx.textAlign;
    tctx.textBaseline = ctx.textBaseline;
    tctx.fillStyle = '#000';
    tctx.fillText(String(digit), logicalWidth / 2, logicalHeight / 2);
    templates.push(template);
  }

  function normalizedGroup(group) {
    const [left, right] = group;
    const groupWidth = right - left + 1;
    return normalizedRegion(canvas, left, 0, groupWidth, height);
  }

  function normalizedTemplate(template) {
    return normalizedRegion(template, 0, 0, width, height);
  }

  function similarity(left, right) {
    let intersection = 0;
    let union = 0;
    for (let i = 0; i < left.length; i++) {
      if (left[i] || right[i]) union++;
      if (left[i] && right[i]) intersection++;
    }
    return union ? intersection / union : 0;
  }

  const templateMasks = templates.map(normalizedTemplate);
  const text = [];
  const scores = [];
  for (const group of groups) {
    const glyph = normalizedGroup(group);
    let bestDigit = null;
    let bestScore = -1;
    for (let digit = 0; digit <= 9; digit++) {
      const score = glyph && templateMasks[digit] ? similarity(glyph, templateMasks[digit]) : 0;
      if (score > bestScore) { bestScore = score; bestDigit = digit; }
    }
    text.push(String(bestDigit));
    scores.push(bestScore);
  }
  return { text: text.join(''), scores };
}"""


# Debug variant of the decoder that returns every field needed to diagnose
# why a canvas is being rejected. The production ``_TEMPLATE_DECODER_SCRIPT``
# is intentionally minimal; this one is only called by ``debug_read``.
_DEBUG_DECODER_SCRIPT = r"""canvas => {
  const ctx = canvas.getContext('2d');
  if (!ctx || !canvas.width || !canvas.height) {
    return {
      error: 'no_2d_context_or_zero_size',
      canvas_width: canvas.width,
      canvas_height: canvas.height,
    };
  }
  const width = canvas.width;
  const height = canvas.height;
  const source = ctx.getImageData(0, 0, width, height);

  function inkAt(data, index) {
    return data[index + 3] > 10 &&
      (data[index] < 245 || data[index + 1] < 245 || data[index + 2] < 245);
  }

  function maskFrom(imageData) {
    const data = imageData.data;
    const mask = new Uint8Array(imageData.width * imageData.height);
    let inkCount = 0;
    for (let y = 0; y < imageData.height; y++) {
      for (let x = 0; x < imageData.width; x++) {
        const i = (y * imageData.width + x) * 4;
        const ink = inkAt(data, i) ? 1 : 0;
        mask[y * imageData.width + x] = ink;
        if (ink) inkCount++;
      }
    }
    return { mask, inkCount };
  }

  function normalizedRegion(sourceCanvas, sourceX, sourceY, sourceWidth, sourceHeight) {
    const crop = document.createElement('canvas');
    crop.width = sourceWidth;
    crop.height = sourceHeight;
    const cropCtx = crop.getContext('2d');
    cropCtx.drawImage(sourceCanvas, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);
    const cropData = cropCtx.getImageData(0, 0, sourceWidth, sourceHeight);
    const cropResult = maskFrom(cropData);
    let left = sourceWidth, top = sourceHeight, right = -1, bottom = -1;
    for (let y = 0; y < sourceHeight; y++) {
      for (let x = 0; x < sourceWidth; x++) {
        if (!cropResult.mask[y * sourceWidth + x]) continue;
        left = Math.min(left, x); top = Math.min(top, y);
        right = Math.max(right, x); bottom = Math.max(bottom, y);
      }
    }
    if (right < left || bottom < top) return null;
    const normalized = document.createElement('canvas');
    normalized.width = 40;
    normalized.height = 60;
    normalized.getContext('2d').drawImage(
      crop, left, top, right - left + 1, bottom - top + 1,
      0, 0, normalized.width, normalized.height,
    );
    return maskFrom(normalized.getContext('2d').getImageData(0, 0, 40, 60));
  }

  const sourceResult = maskFrom(source);
  const sourceMask = sourceResult.mask;

  const groups = [];
  let start = null;
  for (let x = 0; x < width; x++) {
    let hasInk = false;
    for (let y = 0; y < height; y++) {
      if (sourceMask[y * width + x]) { hasInk = true; break; }
    }
    if (hasInk && start === null) start = x;
    if (!hasInk && start !== null) { groups.push([start, x - 1]); start = null; }
  }
  if (start !== null) groups.push([start, width - 1]);

  const transform = ctx.getTransform ? ctx.getTransform() : null;
  const effectiveScale = transform ? (transform.a || 1) : 1;
  const logicalWidth = width / effectiveScale;
  const logicalHeight = height / (transform ? (transform.d || 1) : 1);

  let glyphs = null;
  let templateError = null;

  if (!groups.length || groups.length > 12) {
    templateError = groups.length === 0
      ? 'no_groups_detected'
      : 'too_many_groups_' + groups.length;
  } else if (!transform) {
    templateError = 'no_transform';
  } else {
    const templates = [];
    for (let digit = 0; digit <= 9; digit++) {
      const template = document.createElement('canvas');
      template.width = width;
      template.height = height;
      const tctx = template.getContext('2d');
      tctx.setTransform(transform);
      tctx.font = ctx.font;
      tctx.textAlign = ctx.textAlign;
      tctx.textBaseline = ctx.textBaseline;
      tctx.fillStyle = '#000';
      tctx.fillText(String(digit), logicalWidth / 2, logicalHeight / 2);
      templates.push(template);
    }

    function normalizedGroup(group) {
      const [left, right] = group;
      const groupWidth = right - left + 1;
      return normalizedRegion(canvas, left, 0, groupWidth, height);
    }

    function normalizedTemplate(template) {
      return normalizedRegion(template, 0, 0, width, height);
    }

    function similarity(left, right) {
      let intersection = 0;
      let union = 0;
      for (let i = 0; i < left.length; i++) {
        if (left[i] || right[i]) union++;
        if (left[i] && right[i]) intersection++;
      }
      return union ? intersection / union : 0;
    }

    const templateMasks = templates.map(normalizedTemplate);
    glyphs = [];
    for (const group of groups) {
      const glyph = normalizedGroup(group);
      const allScores = [];
      let bestDigit = null;
      let bestScore = -1;
      for (let digit = 0; digit <= 9; digit++) {
        const score = glyph && templateMasks[digit] ? similarity(glyph, templateMasks[digit]) : 0;
        allScores.push(Number(score.toFixed(4)));
        if (score > bestScore) { bestScore = score; bestDigit = digit; }
      }
      glyphs.push({
        best_digit: bestDigit,
        best_score: Number(bestScore.toFixed(4)),
        all_scores: allScores,
      });
    }
  }

  return {
    canvas_width: width,
    canvas_height: height,
    font: ctx.font || null,
    text_align: ctx.textAlign || null,
    text_baseline: ctx.textBaseline || null,
    fill_style: ctx.fillStyle || null,
    transform: transform ? {
      a: transform.a, b: transform.b, c: transform.c,
      d: transform.d, e: transform.e, f: transform.f,
    } : null,
    effective_scale: effectiveScale,
    logical_width: logicalWidth,
    logical_height: logicalHeight,
    ink_pixel_count: sourceResult.inkCount,
    group_count: groups.length,
    group_ranges: groups.map(g => ({ start: g[0], end: g[1], width: g[1] - g[0] + 1 })),
    template_error: templateError,
    glyphs,
  };
}"""


class CanvasOCR:
    """Read rendered digit canvases through an injectable OCR backend.

    For canvases where multiple digit regions are detected (e.g. the 5-digit
    ``เลขบน`` canvas on Huayapp's foreign lottery cards), a single
    candidate can lose digits to a higher-confidence neighbour. The
    backend now returns ``(start_x, text, confidence)`` triples so we can
    sort by left-to-right position and rebuild the digit string from every
    region that survives the confidence threshold.
    """

    def __init__(self, backend: Any | None = None, *, min_confidence: float = 0.8):
        self.backend = backend or self._load_default_backend()
        self.min_confidence = min_confidence

    @staticmethod
    def _load_default_backend() -> Any:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise OCRUnavailableError(
                "No OCR backend is installed. Use Python 3.11/3.12 with requirements-ocr.txt."
            ) from exc

        class RapidBackend:
            def __init__(self):
                self.engine = RapidOCR()

            def recognize(self, image: Image.Image):
                """Return ``[(start_x, text, confidence), ...]`` sorted by ``x``."""
                import numpy as np

                result, _ = self.engine(np.asarray(image.convert("RGB")))
                if not result:
                    return []
                regions = []
                for item in result:
                    bbox, text, confidence = item
                    # bbox is [[x1, y1], [x2, y2], [x3, y3], [x4, y4]] in pixels
                    xs = [point[0] for point in bbox]
                    regions.append((min(xs), text, float(confidence)))
                regions.sort(key=lambda r: r[0])
                return regions

        return RapidBackend()

    def read(self, image: Image.Image, expected_digits: int | None = None) -> str | None:
        regions = self.backend.recognize(image)
        if not regions:
            return None
        kept: list[tuple[str, float]] = []
        for _, text, confidence in regions:
            if confidence < self.min_confidence:
                continue
            if not re.fullmatch(r"[0-9\s]+", text or ""):
                continue
            kept.append((text, confidence))
        if not kept:
            return None
        combined = "".join(re.sub(r"\s+", "", text) for text, _ in kept)
        if expected_digits is not None and len(combined) != expected_digits:
            return None
        return combined
