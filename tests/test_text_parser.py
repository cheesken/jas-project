import pytest

from parsers.base import Chunk, ParseError
from parsers.text import TXTParser, parse_txt


def _write(tmp_path, data: bytes, name="notes.txt"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_short_txt_returns_single_chunk(tmp_path):
    path = _write(tmp_path, b"Tara recommended Noosh Noshery on Castro St.")
    chunks = parse_txt(path)
    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].content == "Tara recommended Noosh Noshery on Castro St."
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number is None
    assert chunks[0].metadata == {}


def test_long_txt_is_chunked_within_token_limit(tmp_path):
    text = " ".join(f"Sentence number {i} about the quarterly report." for i in range(600))
    chunks = parse_txt(_write(tmp_path, text.encode()))
    assert len(chunks) > 1
    assert all(c.token_count <= 400 for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_utf8_bom_is_stripped(tmp_path):
    chunks = parse_txt(_write(tmp_path, b"\xef\xbb\xbfhello caf\xc3\xa9"))
    assert chunks[0].content == "hello café"


def test_non_utf8_falls_back_to_cp1252(tmp_path):
    chunks = parse_txt(_write(tmp_path, "smart “quotes” café".encode("cp1252")))
    assert chunks[0].content == "smart “quotes” café"


def test_crlf_line_endings_normalized(tmp_path):
    chunks = parse_txt(_write(tmp_path, b"line one\r\nline two\rline three"))
    assert chunks[0].content == "line one\nline two\nline three"


@pytest.mark.parametrize("data", [b"", b"   \n\t  "])
def test_empty_txt_raises_parse_error(tmp_path, data):
    with pytest.raises(ParseError):
        parse_txt(_write(tmp_path, data))


def test_binary_file_raises_parse_error(tmp_path):
    with pytest.raises(ParseError):
        parse_txt(_write(tmp_path, b"\x89PNG\r\n\x1a\n\x00\x00\x00"))


def test_nonexistent_path_raises_parse_error():
    with pytest.raises(ParseError):
        parse_txt("/nonexistent/notes.txt")


def test_unsupported_extension_raises_parse_error(tmp_path):
    with pytest.raises(ParseError):
        parse_txt(_write(tmp_path, b"hello", name="notes.md"))


def test_extension_is_case_insensitive(tmp_path):
    chunks = TXTParser().parse(_write(tmp_path, b"hello", name="NOTES.TXT"))
    assert chunks[0].content == "hello"
