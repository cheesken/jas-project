import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlsplit

from parsers.base import BaseParser, Chunk, ParseError

# Chrome stores timestamps as microseconds since 1601-01-01 UTC (WebKit epoch).
WEBKIT_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
MAX_ENTRIES = int(os.environ.get("BROWSER_HISTORY_MAX_ENTRIES", "5000"))
MAX_TITLE_CHARS = 300
# Tracking URLs can run to thousands of characters; the full URL stays in metadata.
MAX_URL_CHARS = 300
ALLOWED_SCHEMES = ("http://", "https://")

# Chrome keeps a rollback journal or WAL next to the History file; copy whichever
# exists so the snapshot includes visits that have not been checkpointed yet.
SIDECAR_SUFFIXES = ("-journal", "-wal")

QUERY = """
    SELECT url, title, visit_count, last_visit_time
    FROM urls
    WHERE hidden = 0 AND last_visit_time > 0
    ORDER BY last_visit_time DESC
    LIMIT ?
"""


def webkit_to_iso(timestamp: int) -> str:
    return (WEBKIT_EPOCH + timedelta(microseconds=timestamp)).isoformat()


class BrowserHistoryParser(BaseParser):
    browser_type = "chrome"

    def __init__(self, max_entries: Optional[int] = None) -> None:
        self.max_entries = max_entries or MAX_ENTRIES

    def parse(self, file_path: str) -> List[Chunk]:
        if not os.path.isfile(file_path):
            raise ParseError(f"Browser history not found: {file_path}")

        # Chrome holds a lock on History while running, and the user's home is
        # mounted read-only in Docker, so read from a private temp copy.
        with tempfile.TemporaryDirectory(prefix="history-") as tmp_dir:
            snapshot = os.path.join(tmp_dir, "History")
            try:
                shutil.copyfile(file_path, snapshot)
                for suffix in SIDECAR_SUFFIXES:
                    if os.path.isfile(file_path + suffix):
                        shutil.copyfile(file_path + suffix, snapshot + suffix)
            except OSError as e:
                raise ParseError(f"Failed to copy browser history: {file_path}") from e

            rows = self._read_rows(snapshot, file_path)

        chunks: List[Chunk] = []
        for url, title, visit_count, last_visit_time in self._dedupe(rows):
            chunks.extend(self._entry_chunks(url, title, visit_count, last_visit_time, len(chunks)))

        if not chunks:
            raise ParseError("Browser history contains no web pages")
        return chunks

    @staticmethod
    def _dedupe(rows: list) -> list:
        """Drop non-web URLs and collapse pages that share a site and title.

        Chrome stores one row per distinct URL, so a single page reached with
        different query strings (search results, games, tracking params) would
        otherwise fill the results with identical cards. Rows arrive newest
        first, so the kept row is the most recent visit; visit counts are summed.
        """
        kept: dict = {}
        for url, title, visit_count, last_visit_time in rows:
            if not url or not url.startswith(ALLOWED_SCHEMES):
                continue
            norm_title = " ".join((title or "").split()).lower()
            key = (urlsplit(url).netloc, norm_title) if norm_title else url
            if key in kept:
                kept[key][2] += int(visit_count or 0)
            else:
                kept[key] = [url, title, int(visit_count or 0), last_visit_time]
        return list(kept.values())

    def _read_rows(self, snapshot: str, file_path: str) -> list:
        try:
            conn = sqlite3.connect(snapshot)
        except sqlite3.Error as e:
            raise ParseError(f"Failed to open browser history: {file_path}") from e
        try:
            conn.execute("PRAGMA query_only = ON")
            return conn.execute(QUERY, (self.max_entries,)).fetchall()
        except sqlite3.DatabaseError as e:
            raise ParseError(f"Not a Chrome history database: {file_path}") from e
        finally:
            conn.close()

    def _entry_chunks(
        self,
        url: str,
        title: Optional[str],
        visit_count: int,
        last_visit_time: int,
        next_index: int,
    ) -> List[Chunk]:
        title = " ".join((title or "").split())[:MAX_TITLE_CHARS]
        domain = urlsplit(url).netloc
        display_title = title or domain or url
        shown_url = url if len(url) <= MAX_URL_CHARS else url[:MAX_URL_CHARS] + "…"
        content = f"{title} · {shown_url}" if title else shown_url

        metadata = {
            "last_modified": webkit_to_iso(last_visit_time),
            "url": url,
            "title": display_title,
            "visit_count": int(visit_count or 0),
            "browser_type": self.browser_type,
        }

        # One chunk per page keeps results precise; with the caps above, _chunk
        # never needs to split an entry.
        chunks = self._chunk(content)
        for offset, chunk in enumerate(chunks):
            chunk.chunk_index = next_index + offset
            chunk.metadata = dict(metadata)
        return chunks


def parse_browser_history(file_path: str) -> List[Chunk]:
    return BrowserHistoryParser().parse(file_path)
