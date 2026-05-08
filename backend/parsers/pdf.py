from typing import List, Tuple

import pdfplumber

from parsers.base import BaseParser, Chunk, ParseError


class PDFParser(BaseParser):
    _lib = pdfplumber

    def parse(self, file_path: str) -> List[Chunk]:
        try:
            pdf = pdfplumber.open(file_path)
        except Exception as e:
            raise ParseError(f"Failed to parse PDF: {file_path}") from e

        page_texts: List[str] = []
        page_breaks: List[Tuple[int, int]] = []
        char_offset = 0

        try:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                page_breaks.append((char_offset, page_num))
                page_texts.append(text)
                # Account for the text length plus the "\n\n" separator
                char_offset += len(text) + 2  # +2 for "\n\n"
        finally:
            pdf.close()

        full_text = "\n\n".join(page_texts)

        if not full_text.strip():
            raise ParseError("PDF contains no extractable text")

        return self._chunk(full_text, page_breaks)


def parse_pdf(file_path: str) -> List[Chunk]:
    return PDFParser().parse(file_path)
