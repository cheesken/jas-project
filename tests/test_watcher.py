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
def test_main_runs_until_stopped_without_valid_dirs(monkeypatch, watch_dirs):
    import watcher.watcher as watcher_module

    monkeypatch.setenv("WATCH_DIRS", watch_dirs)
    monkeypatch.setattr(watcher_module.threading.Event, "wait", lambda self, *a, **k: self.set())
    with patch.object(watcher_module, "Observer") as mock_observer, \
         patch.object(watcher_module, "requests") as mock_requests, \
         patch.object(watcher_module.signal, "signal"):
        mock_requests.get.return_value.json.return_value = {"paths": []}
        watcher_module.main()
    mock_observer.return_value.start.assert_called_once()
    mock_observer.return_value.schedule.assert_not_called()
    mock_observer.return_value.stop.assert_called_once()


def test_sync_schedules_added_and_unschedules_removed(tmp_path):
    from watcher.watcher import sync_watches

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    observer = MagicMock()
    observer.schedule.side_effect = lambda handler, path, recursive: f"watch:{path}"
    watches = {}
    with patch("watcher.watcher._scan"):
        sync_watches(observer, MagicMock(), watches, {str(a), str(b)})
        assert set(watches) == {str(a), str(b)}
        sync_watches(observer, MagicMock(), watches, {str(b)})
    assert set(watches) == {str(b)}
    observer.unschedule.assert_called_once_with(f"watch:{a}")
    assert observer.schedule.call_count == 2


def test_sync_skips_missing_dirs(tmp_path):
    from watcher.watcher import sync_watches

    observer = MagicMock()
    watches = {}
    sync_watches(observer, MagicMock(), watches, {str(tmp_path / "missing")})
    assert watches == {}
    observer.schedule.assert_not_called()


def test_new_watch_scans_existing_supported_files(tmp_path):
    from watcher.watcher import sync_watches

    (tmp_path / "note.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "shot.PNG").write_bytes(b"x")
    (tmp_path / "skip.docx").write_text("x")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.pdf").write_text("x")
    handler = MagicMock()
    sync_watches(MagicMock(), handler, {}, {str(tmp_path)})
    fired = sorted(call.args for call in handler._fire.call_args_list)
    assert fired == [(str(tmp_path / "note.txt"), "txt"), (str(tmp_path / "sub" / "shot.PNG"), "image")]


@patch("watcher.watcher.requests")
def test_fetch_api_dirs_returns_paths(mock_requests):
    from watcher.watcher import _fetch_api_dirs

    mock_requests.get.return_value.json.return_value = {"paths": ["/x", "/y"]}
    assert _fetch_api_dirs(set()) == {"/x", "/y"}


def test_fetch_api_dirs_keeps_previous_when_api_down():
    import requests as real_requests
    from watcher.watcher import _fetch_api_dirs

    with patch("watcher.watcher.requests.get", side_effect=real_requests.exceptions.ConnectionError("down")):
        assert _fetch_api_dirs({"/kept"}) == {"/kept"}
