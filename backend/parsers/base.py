import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

import tiktoken


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


def _lookup_page(start_char: int, page_breaks: Optional[List[Tuple[int, int]]]) -> Optional[int]:
    if page_breaks is None:
        return None
    result = None
    for char_offset, page_number in page_breaks:
        if char_offset <= start_char:
            result = page_number
        else:
            break
    return result


class BaseParser(ABC):
    chunk_size: int = 400
    overlap: int = 50

    @abstractmethod
    def parse(self, file_path: str) -> List[Chunk]:
        ...

    def _chunk(self, text: str, page_breaks: Optional[List[Tuple[int, int]]] = None) -> List[Chunk]:
        encoding = tiktoken.get_encoding("cl100k_base")
        encoded = encoding.encode(text)
        chunks: List[Chunk] = []
        i = 0
        chunk_index = 0

        while i < len(encoded):
            end = min(i + self.chunk_size, len(encoded))
            chunk_tokens = encoded[i:end]
            chunk_text = encoding.decode(chunk_tokens)

            start_char = len(encoding.decode(encoded[:i]))
            end_char = len(encoding.decode(encoded[:end]))

            # Refine split point: look in the last 100 tokens for a natural break
            if end < len(encoded) and len(chunk_tokens) == self.chunk_size:
                search_start = max(0, len(chunk_tokens) - 100)
                search_text = encoding.decode(chunk_tokens[search_start:])
                best_pos = -1
                for delimiter in ["\n\n", "\n", ". ", " "]:
                    pos = search_text.rfind(delimiter)
                    if pos != -1:
                        # Calculate how many characters from the start of the chunk
                        # to this split point
                        prefix_before_search = encoding.decode(chunk_tokens[:search_start])
                        split_char_offset = len(prefix_before_search) + pos + len(delimiter)
                        # Re-encode the truncated text to find the token boundary
                        truncated_text = encoding.decode(chunk_tokens)[:split_char_offset]
                        new_token_count = len(encoding.encode(truncated_text))
                        if new_token_count > 0:
                            chunk_tokens = encoded[i:i + new_token_count]
                            end = i + new_token_count
                            chunk_text = encoding.decode(chunk_tokens)
                            end_char = len(encoding.decode(encoded[:end]))
                        best_pos = pos
                        break

            chunks.append(Chunk(
                id=str(uuid.uuid4()),
                content=chunk_text,
                token_count=len(chunk_tokens),
                chunk_index=chunk_index,
                start_char=start_char,
                end_char=end_char,
                page_number=_lookup_page(start_char, page_breaks),
            ))
            chunk_index += 1
            if end >= len(encoded):
                break
            i = end - self.overlap

        # Final-chunk merge: if last chunk < 50 tokens, merge into previous
        if len(chunks) >= 2 and chunks[-1].token_count < 50:
            last = chunks.pop()
            prev = chunks[-1]
            prev.content = text[prev.start_char:last.end_char]
            prev.end_char = last.end_char
            prev.token_count = len(encoding.encode(prev.content))

        return chunks
