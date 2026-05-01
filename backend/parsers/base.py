from dataclasses import dataclass
from typing import Optional


class ParseError(Exception):
    pass


@dataclass
class Chunk:
    id: str
    content: str
    token_count: int
    chunk_index: int
    start_char: int
    end_char: int
    page_number: Optional[int] = None
