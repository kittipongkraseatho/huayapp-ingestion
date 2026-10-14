from pathlib import Path


def test_api_image_installs_ocr_fallback_for_all_lottery_cards():
    requirements = Path("huayapp-api/requirements.txt").read_text(encoding="utf-8")

    assert any(
        line.strip().lower().startswith("rapidocr-onnxruntime")
        for line in requirements.splitlines()
    ), "API image must install RapidOCR so non-primary lottery cards can be decoded"
