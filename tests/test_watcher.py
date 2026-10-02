import time
from unittest.mock import MagicMock, patch

import pytest

# Skip (not error) when watchdog isn't installed: the conftest skip hook only runs
# after collection, too late to stop this module's import from failing.
pytest.importorskip("watchdog")

from watcher.watcher import DebouncedIngestHandler, _get_file_type


def test_get_file_type_supported():
    assert _get_file_type("/path/to/doc.pdf") == "pdf"
    assert _get_file_type("/path/to/notes.txt") == "txt"
    assert _get_file_type("/path/to/photo.png") == "image"
    assert _get_file_type("/path/to/photo.jpg") == "image"
    assert _get_file_type("/path/to/photo.jpeg") == "image"


def test_get_file_type_unsupported():
    assert _get_file_type("/path/to/file.docx") is None
    assert _get_file_type("/path/to/file.xlsx") is None
    assert _get_file_type("/path/to/file") is None


def test_get_file_type_case_insensitive():
    assert _get_file_type("/path/to/DOC.PDF") == "pdf"
    assert _get_file_type("/path/to/image.JPG") == "image"


def test_handler_ignores_unsupported_extensions():
    handler = DebouncedIngestHandler()
    event = MagicMock()
    event.is_directory = False
    event.src_path = "/watched/dir/file.docx"
    handler.on_created(event)
    assert len(handler._pending) == 0


def test_handler_ignores_directory_events():
    handler = DebouncedIngestHandler()
    event = MagicMock()
    event.is_directory = True
    event.src_path = "/watched/dir/subdir"
    handler.on_created(event)
    assert len(handler._pending) == 0


@patch("watcher.watcher.DEBOUNCE_SECONDS", 0.1)
@patch("watcher.watcher.requests")
def test_handler_posts_to_ingest_after_debounce(mock_requests, tmp_path):
    test_file = tmp_path / "test.pdf"
    test_file.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"job_id": "abc"}
    mock_requests.post.return_value = mock_response

    handler = DebouncedIngestHandler()
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(test_file)
    handler.on_created(event)

    time.sleep(0.3)

    mock_requests.post.assert_called_once()
    call_args = mock_requests.post.call_args
    assert call_args[1]["json"]["file_path"] == str(test_file)
    assert call_args[1]["json"]["file_type"] == "pdf"


@patch("watcher.watcher.DEBOUNCE_SECONDS", 0.1)
@patch("watcher.watcher.requests")
def test_handler_debounces_rapid_events(mock_requests, tmp_path):
    test_file = tmp_path / "test.pdf"
    test_file.write_bytes(b"%PDF-1.4")

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"job_id": "abc"}
    mock_requests.post.return_value = mock_response

    handler = DebouncedIngestHandler()
    for _ in range(3):
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(test_file)
        handler.on_modified(event)
        time.sleep(0.02)

    time.sleep(0.3)

    # Rapid events for the same file should coalesce into one POST
    mock_requests.post.assert_called_once()


@patch("watcher.watcher.DEBOUNCE_SECONDS", 0.1)
@patch("watcher.watcher.requests")
def test_handler_handles_409_gracefully(mock_requests, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")

    mock_response = MagicMock()
    mock_response.status_code = 409
    mock_requests.post.return_value = mock_response

    handler = DebouncedIngestHandler()
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(test_file)
    handler.on_created(event)

    time.sleep(0.3)

    # Should not raise — 409 is handled gracefully
    mock_requests.post.assert_called_once()


@patch("watcher.watcher.DEBOUNCE_SECONDS", 0.1)
@patch("watcher.watcher.requests")
def test_handler_skips_disappeared_file(mock_requests, tmp_path):
    missing = str(tmp_path / "gone.pdf")

    handler = DebouncedIngestHandler()
    event = MagicMock()
    event.is_directory = False
    event.src_path = missing
    handler.on_created(event)

    time.sleep(0.3)

    # File doesn't exist when timer fires, so no POST
    mock_requests.post.assert_not_called()


@pytest.mark.parametrize("watch_dirs", ["", "/nonexistent/dir-a,/nonexistent/dir-b"])
def test_main_idles_instead_of_exiting_without_valid_dirs(monkeypatch, watch_dirs):
    import watcher.watcher as watcher_module

    monkeypatch.setenv("WATCH_DIRS", watch_dirs)
    waited = []
    monkeypatch.setattr(watcher_module.threading.Event, "wait", lambda self, *a, **k: waited.append(True))
    with patch.object(watcher_module, "Observer") as mock_observer, \
         patch.object(watcher_module.signal, "signal"):
        watcher_module.main()  # must return normally, not raise SystemExit
    assert waited == [True]
    mock_observer.assert_not_called()
