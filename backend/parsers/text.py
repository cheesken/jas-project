import os
from typing import List

from parsers.base import BaseParser, Chunk, ParseError

SUPPORTED_EXTENSIONS = {".txt"}
# utf-8-sig strips a BOM if present; latin-1 never fails, so it is the last resort.
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


class TXTParser(BaseParser):
    def parse(self, file_path: str) -> List[Chunk]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ParseError(f"Unsupported text file type: {file_path}")
        if not os.path.isfile(file_path):
            raise ParseError(f"Text file not found: {file_path}")

        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except OSError as e:
            raise ParseError(f"Failed to read text file: {file_path}") from e

        if b"\x00" in raw:
            raise ParseError(f"File looks binary, not text: {file_path}")

        text = self._decode(raw)
        # Normalize Windows/old-Mac line endings so chunk boundaries split on "\n".
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        if not text.strip():
            raise ParseError("TXT file contains no text")

        return self._chunk(text)

    @staticmethod
    def _decode(raw: bytes) -> str:
        for encoding in ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ParseError("Could not decode text file")


def parse_txt(file_path: str) -> List[Chunk]:
    return TXTParser().parse(file_path)
