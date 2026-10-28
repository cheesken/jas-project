import os
import sqlite3

import pytest

from parsers.base import ParseError
from parsers.browser_history import (
    BrowserHistoryParser,
    parse_browser_history,
    webkit_to_iso,
)

# 2026-03-15T19:00:00Z as microseconds since 1601-01-01 (Chrome's epoch).
MAR_15_2026 = 13_418_074_800_000_000

CHROME_URLS_SCHEMA = """
    CREATE TABLE urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url LONGVARCHAR,
        title LONGVARCHAR,
        visit_count INTEGER DEFAULT 0 NOT NULL,
        typed_count INTEGER DEFAULT 0 NOT NULL,
        last_visit_time INTEGER NOT NULL,
        hidden INTEGER DEFAULT 0 NOT NULL
    )
"""


def _make_history(tmp_path, rows, name="History"):
    """rows: (url, title, visit_count, last_visit_time, hidden)"""
    path = tmp_path / name
    conn = sqlite3.connect(path)
    conn.execute(CHROME_URLS_SCHEMA)
    conn.executemany(
        "INSERT INTO urls (url, title, visit_count, last_visit_time, hidden) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return str(path)


def test_webkit_timestamp_conversion():
    assert webkit_to_iso(MAR_15_2026) == "2026-03-15T19:00:00+00:00"


def test_each_page_becomes_one_chunk_with_visit_metadata(tmp_path):
    path = _make_history(tmp_path, [
        ("https://www.yelp.com/biz/noosh-noshery-mountain-view",
         "Noosh Noshery - Menu - Yelp", 3, MAR_15_2026, 0),
    ])
    (chunk,) = parse_browser_history(path)
    assert chunk.content == "Noosh Noshery - Menu - Yelp · https://www.yelp.com/biz/noosh-noshery-mountain-view"
    assert chunk.chunk_index == 0
    assert chunk.metadata == {
        "last_modified": "2026-03-15T19:00:00+00:00",
        "url": "https://www.yelp.com/biz/noosh-noshery-mountain-view",
        "title": "Noosh Noshery - Menu - Yelp",
        "visit_count": 3,
        "browser_type": "chrome",
    }


def test_most_recent_visits_first_with_sequential_indexes(tmp_path):
    path = _make_history(tmp_path, [
        ("https://old.example.com/", "Old", 1, MAR_15_2026 - 10, 0),
        ("https://new.example.com/", "New", 1, MAR_15_2026, 0),
    ])
    chunks = parse_browser_history(path)
    assert [c.metadata["title"] for c in chunks] == ["New", "Old"]
    assert [c.chunk_index for c in chunks] == [0, 1]


def test_skips_hidden_unvisited_and_non_web_urls(tmp_path):
    path = _make_history(tmp_path, [
        ("https://kept.example.com/", "Kept", 1, MAR_15_2026, 0),
        ("https://hidden.example.com/", "Hidden", 1, MAR_15_2026, 1),
        ("https://never.example.com/", "Never", 0, 0, 0),
        ("chrome://settings/", "Settings", 5, MAR_15_2026, 0),
        ("file:///Users/jane/secret.pdf", "secret.pdf", 1, MAR_15_2026, 0),
    ])
    chunks = parse_browser_history(path)
    assert [c.metadata["url"] for c in chunks] == ["https://kept.example.com/"]


def test_same_title_on_same_site_is_collapsed_to_latest_visit(tmp_path):
    path = _make_history(tmp_path, [
        ("https://games.com/play?level=1", "Papa's Wingeria", 2, MAR_15_2026 - 20, 0),
        ("https://games.com/play?level=2", "Papa's  wingeria", 3, MAR_15_2026, 0),
        ("https://other.com/wingeria", "Papa's Wingeria", 1, MAR_15_2026 - 10, 0),
    ])
    chunks = parse_browser_history(path)
    assert [c.metadata["url"] for c in chunks] == [
        "https://games.com/play?level=2",
        "https://other.com/wingeria",
    ]
    assert chunks[0].metadata["visit_count"] == 5
    assert [c.chunk_index for c in chunks] == [0, 1]


def test_untitled_pages_are_not_collapsed(tmp_path):
    path = _make_history(tmp_path, [
        ("https://a.com/1", None, 1, MAR_15_2026, 0),
        ("https://a.com/2", "", 1, MAR_15_2026 - 1, 0),
    ])
    assert len(parse_browser_history(path)) == 2


def test_missing_title_falls_back_to_domain(tmp_path):
    path = _make_history(tmp_path, [("https://example.com/a/b", None, 1, MAR_15_2026, 0)])
    (chunk,) = parse_browser_history(path)
    assert chunk.content == "https://example.com/a/b"
    assert chunk.metadata["title"] == "example.com"


def test_title_whitespace_collapsed(tmp_path):
    path = _make_history(tmp_path, [("https://a.com/", "  Two\n  words  ", 1, MAR_15_2026, 0)])
    (chunk,) = parse_browser_history(path)
    assert chunk.metadata["title"] == "Two words"


def test_long_tracking_url_is_trimmed_in_content_but_kept_in_metadata(tmp_path):
    url = "https://ads.example.com/click?" + "x" * 5000
    path = _make_history(tmp_path, [(url, "Ad", 1, MAR_15_2026, 0)])
    chunks = parse_browser_history(path)
    assert len(chunks) == 1
    assert len(chunks[0].content) < 400
    assert chunks[0].metadata["url"] == url


def test_max_entries_limits_to_most_recent(tmp_path):
    path = _make_history(tmp_path, [
        (f"https://site{i}.com/", f"Site {i}", 1, MAR_15_2026 + i, 0) for i in range(10)
    ])
    chunks = BrowserHistoryParser(max_entries=3).parse(path)
    assert [c.metadata["title"] for c in chunks] == ["Site 9", "Site 8", "Site 7"]


def test_original_file_is_not_modified(tmp_path):
    path = _make_history(tmp_path, [("https://a.com/", "A", 1, MAR_15_2026, 0)])
    os.utime(path, (1, 1))
    before = open(path, "rb").read()
    parse_browser_history(path)
    assert open(path, "rb").read() == before
    assert os.path.getmtime(path) == 1
    assert sorted(os.listdir(tmp_path)) == ["History"]


def test_reads_while_another_connection_holds_a_write_lock(tmp_path):
    path = _make_history(tmp_path, [("https://a.com/", "A", 1, MAR_15_2026, 0)])
    chrome = sqlite3.connect(path)
    chrome.execute("BEGIN IMMEDIATE")
    try:
        assert len(parse_browser_history(path)) == 1
    finally:
        chrome.rollback()
        chrome.close()


def test_history_with_no_web_pages_raises(tmp_path):
    path = _make_history(tmp_path, [("chrome://newtab/", "New Tab", 1, MAR_15_2026, 0)])
    with pytest.raises(ParseError):
        parse_browser_history(path)


def test_non_sqlite_file_raises_parse_error(tmp_path):
    path = tmp_path / "History"
    path.write_bytes(b"definitely not sqlite" * 100)
    with pytest.raises(ParseError):
        parse_browser_history(str(path))


def test_sqlite_without_urls_table_raises_parse_error(tmp_path):
    path = tmp_path / "History"
    sqlite3.connect(path).close()
    with pytest.raises(ParseError):
        parse_browser_history(str(path))


def test_nonexistent_path_raises_parse_error():
    with pytest.raises(ParseError):
        parse_browser_history("/nonexistent/History")


# ------------------------------------------------------------------ Safari

from datetime import datetime, timezone  # noqa: E402
from unittest.mock import patch  # noqa: E402

from parsers.browser_history import SAFARI_PERMISSION_HINT, mac_absolute_to_iso  # noqa: E402

MAC_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
# 2026-03-15T19:00:00Z as seconds since 2001-01-01 (Safari's epoch).
SAFARI_MAR_15_2026 = (datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc) - MAC_EPOCH).total_seconds()

SAFARI_SCHEMA = """
    CREATE TABLE history_items (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE,
        domain_expansion TEXT NULL, visit_count INTEGER NOT NULL);
    CREATE TABLE history_visits (id INTEGER PRIMARY KEY AUTOINCREMENT, history_item INTEGER NOT NULL,
        visit_time REAL NOT NULL, title TEXT NULL, load_successful BOOLEAN NOT NULL DEFAULT 1,
        redirect_source INTEGER NULL, redirect_destination INTEGER NULL);
"""


def _make_safari_history(tmp_path, pages):
    """pages: (url, visit_count, [(visit_time, title), ...])"""
    path = tmp_path / "Safari" / "History.db"
    path.parent.mkdir()
    conn = sqlite3.connect(path)
    conn.executescript(SAFARI_SCHEMA)
    for url, count, visits in pages:
        item = conn.execute("INSERT INTO history_items (url, visit_count) VALUES (?, ?)", (url, count)).lastrowid
        conn.executemany("INSERT INTO history_visits (history_item, visit_time, title) VALUES (?, ?, ?)",
                         [(item, t, title) for t, title in visits])
    conn.commit()
    conn.close()
    return str(path)


def test_mac_absolute_timestamp_conversion():
    assert mac_absolute_to_iso(SAFARI_MAR_15_2026) == "2026-03-15T19:00:00+00:00"


def test_safari_page_uses_latest_visit_title_and_time(tmp_path):
    path = _make_safari_history(tmp_path, [
        ("https://www.yelp.com/biz/noosh-noshery", 4, [
            (SAFARI_MAR_15_2026 - 86400, "Old title"),
            (SAFARI_MAR_15_2026, "Noosh Noshery - Menu - Yelp"),
        ]),
    ])
    (chunk,) = parse_browser_history(path)
    assert chunk.content == "Noosh Noshery - Menu - Yelp · https://www.yelp.com/biz/noosh-noshery"
    assert chunk.metadata == {
        "last_modified": "2026-03-15T19:00:00+00:00",
        "url": "https://www.yelp.com/biz/noosh-noshery",
        "title": "Noosh Noshery - Menu - Yelp",
        "visit_count": 4,
        "browser_type": "safari",
    }


def test_safari_newest_first_skips_non_web_and_merges_duplicates(tmp_path):
    path = _make_safari_history(tmp_path, [
        ("https://old.example.com/", 1, [(SAFARI_MAR_15_2026 - 50, "Old")]),
        ("https://new.example.com/", 1, [(SAFARI_MAR_15_2026, "New")]),
        ("file:///Users/jane/notes.pdf", 1, [(SAFARI_MAR_15_2026, "notes.pdf")]),
        ("https://games.com/play?l=1", 2, [(SAFARI_MAR_15_2026 - 20, "Puzzle")]),
        ("https://games.com/play?l=2", 3, [(SAFARI_MAR_15_2026 - 10, "Puzzle")]),
    ])
    chunks = parse_browser_history(path)
    assert [c.metadata["title"] for c in chunks] == ["New", "Puzzle", "Old"]
    assert chunks[1].metadata["visit_count"] == 5
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_chrome_files_are_still_detected_as_chrome(tmp_path):
    path = _make_history(tmp_path, [("https://a.com/", "A", 1, MAR_15_2026, 0)])
    (chunk,) = parse_browser_history(path)
    assert chunk.metadata["browser_type"] == "chrome"


def test_safari_permission_denied_explains_full_disk_access(tmp_path):
    path = _make_safari_history(tmp_path, [("https://a.com/", 1, [(SAFARI_MAR_15_2026, "A")])])
    with patch("parsers.browser_history.shutil.copyfile", side_effect=PermissionError("denied")):
        with pytest.raises(ParseError, match="Full Disk Access"):
            parse_browser_history(path)


def test_other_permission_errors_name_the_file(tmp_path):
    path = _make_history(tmp_path, [("https://a.com/", "A", 1, MAR_15_2026, 0)])
    with patch("parsers.browser_history.shutil.copyfile", side_effect=PermissionError("denied")):
        with pytest.raises(ParseError, match="Permission denied reading browser history"):
            parse_browser_history(path)
