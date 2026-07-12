"""Process-wide locking for file-backed stores.

The JSON stores do read-modify-write cycles against files with no database
underneath. FastAPI runs sync handlers in a threadpool, so two concurrent
requests can interleave those cycles and lose writes. Store instances are
constructed per request, so locks are keyed by filesystem path rather than
held on the instance: every store pointed at the same file/directory shares
one re-entrant lock.

Scope: a single process. Multi-worker deployments need file locks or a real
database (tracked in the production roadmap).
"""

from __future__ import annotations

import functools
import os
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

_registry_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}

F = TypeVar("F", bound=Callable[..., Any])


def lock_for_path(path: Any) -> threading.RLock:
    key = os.path.abspath(str(path))
    with _registry_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.RLock()
        return lock


@contextmanager
def locked_store(path: Any) -> Iterator[None]:
    with lock_for_path(path):
        yield


def synchronized_store(path_attr: str) -> Callable[[type], type]:
    """Class decorator: serialize public method calls per store path.

    Wraps every public instance method so calls against the same underlying
    path (the constructor-set attribute named `path_attr`) run one at a time.
    The lock is re-entrant, so public methods may call each other freely.
    Coarse by design — file IO dominates these stores and correctness beats
    parallelism for a single household's data.
    """

    def _wrap_method(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            with lock_for_path(getattr(self, path_attr)):
                return fn(self, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    def decorate(cls: type) -> type:
        for name, member in list(vars(cls).items()):
            if name.startswith("_"):
                continue
            if isinstance(member, (staticmethod, classmethod, property)):
                continue
            if callable(member):
                setattr(cls, name, _wrap_method(member))
        return cls

    return decorate
