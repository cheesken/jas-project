from typing import List

from parsers.base import Chunk


def parse_pdf(file_path: str) -> List[Chunk]:
    raise NotImplementedError("parse_pdf is owned by the parser module — provide the implementation before invoking the worker")
