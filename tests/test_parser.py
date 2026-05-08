import sys

# Remove conftest stubs and any cached imports so real pdfplumber/tiktoken are used
for _mod in list(sys.modules):
    if _mod in ("pdfplumber", "tiktoken") or _mod.startswith(
        ("pdfplumber.", "tiktoken.", "parsers.")
    ):
        del sys.modules[_mod]

import pytest
import tiktoken
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from parsers.base import ParseError, Chunk
from parsers.pdf import PDFParser, parse_pdf


@pytest.fixture
def single_page_pdf(tmp_path):
    path = tmp_path / "single.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "The capstone project is advised by Gopinath Vinodh.")
    c.save()
    return str(path)


@pytest.fixture
def multi_page_pdf(tmp_path):
    path = tmp_path / "multi.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "Page one: Introduction to the project.")
    c.showPage()
    c.drawString(72, 720, "Page two: Methodology and approach.")
    c.showPage()
    c.drawString(72, 720, "Page three: Results and conclusions.")
    c.save()
    return str(path)


@pytest.fixture
def long_text_pdf(tmp_path):
    """Generate a PDF with ~2000 cl100k_base tokens of text."""
    path = tmp_path / "long.pdf"
    enc = tiktoken.get_encoding("cl100k_base")
    # Build text that is roughly 2000 tokens
    sentence = "The quick brown fox jumps over the lazy dog. "
    tokens_per_sentence = len(enc.encode(sentence))
    repeat_count = (2000 // tokens_per_sentence) + 1
    long_text = sentence * repeat_count

    c = canvas.Canvas(str(path), pagesize=letter)
    # Write in chunks of ~80 chars per line across multiple pages
    y = 750
    for i in range(0, len(long_text), 80):
        line = long_text[i:i + 80]
        c.drawString(72, y, line)
        y -= 14
        if y < 72:
            c.showPage()
            y = 750
    c.save()
    return str(path)


@pytest.fixture
def corrupted_pdf(tmp_path):
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"not a pdf")
    return str(path)


@pytest.fixture
def empty_pdf(tmp_path):
    path = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    # One page, no text drawn
    c.showPage()
    c.save()
    return str(path)


# Test 1: Single-page PDF
def test_single_page_pdf(single_page_pdf):
    chunks = parse_pdf(single_page_pdf)
    assert len(chunks) >= 1
    assert "Gopinath Vinodh" in chunks[0].content
    assert chunks[0].page_number == 1


# Test 2: Multi-page PDF
def test_multi_page_pdf(multi_page_pdf):
    chunks = parse_pdf(multi_page_pdf)
    all_content = " ".join(c.content for c in chunks)
    assert "Page one" in all_content
    assert "Page two" in all_content
    assert "Page three" in all_content
    page_numbers = {c.page_number for c in chunks}
    assert page_numbers.issubset({1, 2, 3})
    assert len(page_numbers) >= 1


# Test 3: Long-text chunking produces multiple chunks, each <= 400 tokens
def test_long_text_chunking(long_text_pdf):
    chunks = parse_pdf(long_text_pdf)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 400


# Test 4: Overlap preservation between consecutive chunks
def test_overlap_preservation(long_text_pdf):
    enc = tiktoken.get_encoding("cl100k_base")
    chunks = parse_pdf(long_text_pdf)
    assert len(chunks) >= 2

    for i in range(len(chunks) - 1):
        tokens_i = enc.encode(chunks[i].content)
        tokens_next = enc.encode(chunks[i + 1].content)
        trailing = enc.decode(tokens_i[-50:])
        leading = enc.decode(tokens_next[:50])
        assert trailing == leading


# Test 5: Final-chunk merge logic
def test_final_chunk_merge():
    enc = tiktoken.get_encoding("cl100k_base")
    # Build text of exactly 105 tokens in a tiktoken-version-agnostic way.
    # Word-repetition is unreliable because BPE merges the trailing space of
    # each word with the leading bytes of the next, giving fewer tokens than
    # tokens_per_word * repeat_count.  Instead, build a token pool from a long
    # sentence and search for a prefix length whose decode round-trips cleanly.
    filler = "The quick brown fox jumped over the lazy dog. " * 50
    pool = enc.encode(filler)
    text = None
    for n in range(105, 125):
        candidate = enc.decode(pool[:n])
        if len(enc.encode(candidate)) == 105:
            text = candidate
            break
    assert text is not None, "Could not build a 105-token string with this tiktoken version"

    # Create a parser with chunk_size=100, overlap=10
    class SmallParser(PDFParser):
        chunk_size = 100
        overlap = 10

    parser = SmallParser()
    chunks = parser._chunk(text)
    # First chunk: [0, 100), second: [90, 105) = 15 tokens < 50 → merged
    assert len(chunks) == 1
    assert chunks[0].content == text


# Test 6: Corrupted PDF raises ParseError
def test_corrupted_pdf(corrupted_pdf):
    with pytest.raises(ParseError):
        parse_pdf(corrupted_pdf)


# Test 7: Empty PDF raises ParseError
def test_empty_pdf(empty_pdf):
    with pytest.raises(ParseError, match="PDF contains no extractable text"):
        parse_pdf(empty_pdf)
