import os
import shutil
from unittest.mock import patch

import pytest
from PIL import Image

from parsers.base import Chunk, ParseError
from parsers.image import NO_TEXT_PLACEHOLDER, ImageParser, parse_image

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TEXT_PNG = os.path.join(FIXTURES, "text.png")
TEXT_JPG = os.path.join(FIXTURES, "text.jpg")
BLANK_PNG = os.path.join(FIXTURES, "blank.png")

requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


@requires_tesseract
def test_png_with_text_returns_chunks():
    chunks = parse_image(TEXT_PNG)
    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)
    combined = " ".join(c.content for c in chunks)
    assert "Tara" in combined
    assert "Reservation" in combined


@requires_tesseract
def test_jpeg_with_text_returns_chunks():
    chunks = parse_image(TEXT_JPG)
    assert len(chunks) >= 1
    combined = " ".join(c.content for c in chunks)
    assert "Invoice" in combined
    assert "48213" in combined


@requires_tesseract
def test_blank_png_returns_placeholder_with_real_ocr():
    chunks = parse_image(BLANK_PNG)
    assert len(chunks) == 1
    assert chunks[0].content == NO_TEXT_PLACEHOLDER


@pytest.mark.parametrize("ocr_output", ["", "   \n\t  "])
def test_no_text_returns_single_placeholder_chunk(ocr_output):
    with patch("parsers.image.pytesseract.image_to_string", return_value=ocr_output):
        chunks = parse_image(BLANK_PNG)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.content == NO_TEXT_PLACEHOLDER
    assert chunk.chunk_index == 0
    assert chunk.token_count == 0
    assert chunk.page_number is None
    assert chunk.id


def test_nonexistent_path_raises_parse_error():
    with pytest.raises(ParseError):
        parse_image("/nonexistent/screenshot.png")


def test_unsupported_extension_raises_parse_error(tmp_path):
    path = tmp_path / "image.gif"
    Image.new("RGB", (10, 10), "white").save(path)
    with pytest.raises(ParseError):
        parse_image(str(path))


def test_corrupt_image_raises_parse_error(tmp_path):
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"not an image")
    with pytest.raises(ParseError):
        parse_image(str(path))


def test_ocr_failure_raises_parse_error():
    import pytesseract

    with patch(
        "parsers.image.pytesseract.image_to_string",
        side_effect=pytesseract.TesseractError(1, "boom"),
    ):
        with pytest.raises(ParseError):
            parse_image(TEXT_PNG)


@pytest.mark.parametrize("ext", [".PNG", ".JPG", ".Jpeg"])
def test_extension_is_case_insensitive(tmp_path, ext):
    path = tmp_path / f"shot{ext}"
    fmt = "PNG" if ext.lower() == ".png" else "JPEG"
    Image.new("RGB", (50, 50), "white").save(path, format=fmt)
    with patch("parsers.image.pytesseract.image_to_string", return_value=""):
        chunks = parse_image(str(path))
    assert chunks[0].content == NO_TEXT_PLACEHOLDER


def test_long_text_chunks_within_token_limit():
    long_text = " ".join(f"Sentence number {i} about the quarterly report." for i in range(600))
    with patch("parsers.image.pytesseract.image_to_string", return_value=long_text):
        chunks = parse_image(TEXT_PNG)
    assert len(chunks) > 1
    assert all(c.token_count <= 400 for c in chunks)


def test_small_image_is_upscaled():
    img = Image.new("RGB", (100, 80), "white")
    out = ImageParser()._preprocess(img)
    assert out.size == (200, 160)


def test_large_image_is_not_upscaled():
    img = Image.new("RGB", (800, 600), "white")
    out = ImageParser()._preprocess(img)
    assert out.size == (800, 600)


def test_transparent_png_is_flattened_onto_white():
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    out = ImageParser()._preprocess(img)
    assert out.mode == "RGB"
    assert out.getpixel((10, 10)) == (255, 255, 255)
