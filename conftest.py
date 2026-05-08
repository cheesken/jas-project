"""
Root-level conftest — loaded before any other conftest or test module.
Stubs heavy runtime dependencies so the test suite can run without
celery, redis, or sentence-transformers installed locally.

chromadb and pdfplumber ARE installed in the venv and are therefore not
stubbed here; tests that need the real library can import it directly.
"""
import functools
import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# NumPy 2.x compatibility — chromadb 0.4.24 uses aliases removed in NumPy 2.
# ---------------------------------------------------------------------------
if not hasattr(np, "float_"):
    np.float_ = np.float64
if not hasattr(np, "int_"):
    np.int_ = np.intp
if not hasattr(np, "uint"):
    np.uint = np.uintp
if not hasattr(np, "complex_"):
    np.complex_ = np.complex128
if not hasattr(np, "NaN"):
    np.NaN = np.nan


# ---------------------------------------------------------------------------
# Concrete exception stubs (must be real BaseException subclasses so that
# `except SomeError` and `pytest.raises(SomeError)` work correctly).
# ---------------------------------------------------------------------------

class _Retry(Exception):
    pass

class _SoftTimeLimitExceeded(Exception):
    pass

class _RedisError(Exception):
    pass


# ---------------------------------------------------------------------------
# Celery task wrapper — runs tasks synchronously so tests work without a
# running broker.  The `apply()` interface mirrors the real Celery API.
# ---------------------------------------------------------------------------

class _FakeTaskSelf:
    def retry(self, exc=None, **_):
        raise _Retry(str(exc) if exc else "retry")


class _FakeTaskWrapper:
    def __init__(self, func, bind: bool = False):
        self._func = func
        self._bind = bind
        functools.update_wrapper(self, func)

    def apply(self, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or {}
        try:
            if self._bind:
                result = self._func(_FakeTaskSelf(), *args, **kwargs)
            else:
                result = self._func(*args, **kwargs)
        except Exception:
            raise

        class _Result:
            def get(_self):
                return result
        return _Result()

    def apply_async(self, args=None, kwargs=None, **opts):
        return self.apply(args, kwargs)

    def __call__(self, *args, **kwargs):
        return self.apply(list(args), kwargs).get()


class _FakeCeleryConf:
    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeCeleryApp:
    def __init__(self):
        self.conf = _FakeCeleryConf()

    def task(self, *dec_args, bind=False, **_):
        if dec_args and callable(dec_args[0]):
            return _FakeTaskWrapper(dec_args[0], bind=False)

        def decorator(func):
            return _FakeTaskWrapper(func, bind=bind)

        return decorator


# ---------------------------------------------------------------------------
# Generic stub for packages that only need attribute access (returns mocks).
# ---------------------------------------------------------------------------

def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name

    def _getattr(attr):
        val = MagicMock(name=f"{name}.{attr}")
        setattr(mod, attr, val)
        return val

    mod.__getattr__ = _getattr
    return mod


# ---------------------------------------------------------------------------
# Apply all stubs.  Called once at startup and again before each test file is
# imported so that test modules that intentionally clear stubs (e.g.
# test_embedding.py) don't corrupt subsequent test files.
#
# NOTE: Python's fast-path import (when a module is already in sys.modules)
# skips the setattr(parent, child, module) step.  We must wire sub-modules
# as attributes on their parent explicitly so that `parent.child.Attr`
# attribute access returns the proper stub instead of hitting __getattr__.
# ---------------------------------------------------------------------------

def _apply_stubs() -> None:
    # celery — custom stub so @task decorators run eagerly in tests
    if "celery" not in sys.modules:
        celery_mod = types.ModuleType("celery")
        celery_mod.__path__ = []
        celery_mod.Celery = lambda *a, **kw: _FakeCeleryApp()
        sys.modules["celery"] = celery_mod
    else:
        celery_mod = sys.modules["celery"]

    if "celery.exceptions" not in sys.modules:
        exc_mod = types.ModuleType("celery.exceptions")
        exc_mod.Retry = _Retry
        exc_mod.SoftTimeLimitExceeded = _SoftTimeLimitExceeded
        sys.modules["celery.exceptions"] = exc_mod
    else:
        exc_mod = sys.modules["celery.exceptions"]
    celery_mod.exceptions = exc_mod

    # redis — provide a real RedisError so `except redis.exceptions.RedisError`
    # doesn't raise TypeError at runtime
    if "redis" not in sys.modules:
        redis_mod = _make_stub("redis")
        sys.modules["redis"] = redis_mod
    else:
        redis_mod = sys.modules["redis"]

    if "redis.exceptions" not in sys.modules:
        redis_exc = types.ModuleType("redis.exceptions")
        redis_exc.RedisError = _RedisError
        sys.modules["redis.exceptions"] = redis_exc
    else:
        redis_exc = sys.modules["redis.exceptions"]
    redis_mod.exceptions = redis_exc

    # sentence_transformers — lightweight MagicMock stub
    if "sentence_transformers" not in sys.modules:
        sys.modules["sentence_transformers"] = _make_stub("sentence_transformers")

    # Stub services.embedding so that importing services.query doesn't
    # pull in sentence_transformers transitively.  Tests that need a real
    # EmbeddingService patch it themselves.
    if "services.embedding" not in sys.modules:
        _emb = types.ModuleType("services.embedding")
        _emb.EmbeddingService = MagicMock(name="EmbeddingService")
        sys.modules["services.embedding"] = _emb


_apply_stubs()


# ---------------------------------------------------------------------------
# Custom Module collector — re-applies stubs just before each test file is
# imported.  This is necessary because test_embedding.py and test_parser.py
# intentionally remove certain stubs at module level so they can exercise the
# real library; without this hook subsequent files would see missing modules.
# ---------------------------------------------------------------------------

class _StubAwareModule(pytest.Module):
    def _getobj(self):
        _apply_stubs()
        return super()._getobj()


def pytest_pycollect_makemodule(module_path, parent):
    return _StubAwareModule.from_parent(parent, path=module_path)


# ---------------------------------------------------------------------------
# Auto-skip test_embedding.py when sentence_transformers is not installed.
# Those tests explicitly remove the stub to exercise the real library; without
# the real package they would fail with confusing MagicMock assertion errors.
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(items):
    import importlib.metadata
    # Check the pip registry, not sys.modules — a bare `import` would succeed
    # because the stub is already in sys.modules, giving a false positive.
    try:
        importlib.metadata.version("sentence-transformers")
        _has_st = True
    except importlib.metadata.PackageNotFoundError:
        _has_st = False

    if not _has_st:
        skip = pytest.mark.skip(reason="sentence_transformers not installed")
        for item in items:
            if item.fspath.basename == "test_embedding.py":
                item.add_marker(skip)
