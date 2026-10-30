"""Opt-in nested wall-time spans, without prompts, exceptions or credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import threading
import time
import uuid

PARENT = ContextVar("kcf_phase_parent", default=None)
LOCK = threading.Lock()
SESSION = uuid.uuid4().hex


def _write(path, event):
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
        handle.flush()


@contextmanager
def phase(name, *, target_id=None):
    destination = os.environ.get("KCF_PHASE_TRACE_PATH")
    if not destination:
        yield
        return
    from src.core.llm_client import TRACE_TARGET
    path = Path(destination)
    identity = uuid.uuid4().hex
    event = {"span_id": identity, "parent_span_id": PARENT.get(), "phase": name,
             "target_id": target_id if target_id is not None else TRACE_TARGET.get(),
             "stage": os.environ.get("KCF_EXPERIMENT_STAGE", "unspecified"),
             "session_id": SESSION, "pid": os.getpid(),
             "started_at": datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    _write(path, {**event, "event": "start"})
    token = PARENT.set(identity)
    status = "returned"
    try:
        yield
    except BaseException:
        status = "exception"
        raise
    finally:
        PARENT.reset(token)
        _write(path, {**event, "event": "end", "status": status,
                      "elapsed_seconds": time.monotonic() - started})


def measured(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with phase(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate
