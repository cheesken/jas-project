import logging
import os
import signal
import threading
import time
from typing import Dict, Set

import requests
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

EXTENSION_MAP = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
}

DEBOUNCE_SECONDS = float(os.environ.get("WATCHER_DEBOUNCE", "2.0"))
API_URL = os.environ.get("API_URL", "http://api:8000")
POLL_SECONDS = float(os.environ.get("WATCH_POLL_SECONDS", "5.0"))


def _get_file_type(path: str):
    """Return the ingest file_type for the given path, or None if unsupported."""
    ext = os.path.splitext(path)[1].lower()
    return EXTENSION_MAP.get(ext)


class DebouncedIngestHandler(FileSystemEventHandler):
    """Watches for new/modified files and POSTs them to /ingest after debouncing."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._pending: Dict[str, float] = {}
        self._timers: Dict[str, threading.Timer] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory and hasattr(event, "dest_path"):
            self._schedule(event.dest_path)

    def _schedule(self, path: str) -> None:
        file_type = _get_file_type(path)
        if file_type is None:
            return

        with self._lock:
            self._pending[path] = time.time()
            if path in self._timers:
                self._timers[path].cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, self._fire, args=[path, file_type])
            timer.daemon = True
            timer.start()
            self._timers[path] = timer

    def _fire(self, path: str, file_type: str) -> None:
        with self._lock:
            self._pending.pop(path, None)
            self._timers.pop(path, None)

        if not os.path.isfile(path):
            logger.debug("File disappeared before ingest: %s", path)
            return

        logger.info("Ingesting watched file: %s (type=%s)", path, file_type)
        try:
            resp = requests.post(
                f"{API_URL}/ingest",
                json={"file_path": path, "file_type": file_type},
                timeout=10,
            )
            if resp.status_code == 201:
                logger.info("Ingest accepted: %s -> job %s", path, resp.json().get("job_id"))
            elif resp.status_code == 409:
                logger.info("File already ingested (409): %s", path)
            else:
                logger.warning("Ingest returned %d for %s: %s", resp.status_code, path, resp.text)
        except requests.exceptions.RequestException as e:
            logger.error("Failed to POST ingest for %s: %s", path, e)


def _fetch_api_dirs(previous: Set[str]) -> Set[str]:
    try:
        resp = requests.get(f"{API_URL}/settings/watch", timeout=5)
        resp.raise_for_status()
        return set(resp.json().get("paths", []))
    except (requests.exceptions.RequestException, ValueError):
        return previous


def _scan(handler: DebouncedIngestHandler, directory: str) -> None:
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            path = os.path.join(root, name)
            file_type = _get_file_type(path)
            if file_type:
                handler._fire(path, file_type)


def sync_watches(observer, handler: DebouncedIngestHandler, watches: Dict[str, object], desired: Set[str]) -> None:
    for d in set(watches) - desired:
        observer.unschedule(watches.pop(d))
        logger.info("Stopped watching: %s", d)
    for d in sorted(desired - set(watches)):
        if not os.path.isdir(d):
            logger.debug("Watch directory does not exist, skipping: %s", d)
            continue
        watches[d] = observer.schedule(handler, d, recursive=True)
        logger.info("Watching directory: %s", d)
        _scan(handler, d)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [watcher] %(message)s",
    )

    env_dirs = {d.strip() for d in os.environ.get("WATCH_DIRS", "").split(",") if d.strip()}
    for d in sorted(env_dirs):
        if not os.path.isdir(d):
            logger.warning("Watch directory does not exist, skipping: %s", d)

    stop_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down watcher...", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    handler = DebouncedIngestHandler()
    observer = Observer()
    observer.start()
    logger.info("File watcher started; checking %s/settings/watch every %.0fs.", API_URL, POLL_SECONDS)

    watches: Dict[str, object] = {}
    api_dirs: Set[str] = set()
    try:
        while not stop_event.is_set():
            api_dirs = _fetch_api_dirs(api_dirs)
            sync_watches(observer, handler, watches, env_dirs | api_dirs)
            stop_event.wait(POLL_SECONDS)
    finally:
        observer.stop()
        observer.join()
        logger.info("File watcher stopped.")


if __name__ == "__main__":
    main()
