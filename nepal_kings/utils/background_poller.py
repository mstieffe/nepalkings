"""Lightweight background-thread wrapper for network polling.

Usage:

    poller = BackgroundPoller(my_fetch_function, args=(game_id,))
    # In your game loop:
    poller.poll()             # kicks off a thread if none is running
    if poller.has_result():   # non-blocking check
        data = poller.result  # latest result
"""
import threading


class BackgroundPoller:
    """Run a callable in a daemon thread; cache the latest result."""

    def __init__(self, func, args=(), kwargs=None):
        self._func = func
        self._args = args
        self._kwargs = kwargs or {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._result = None
        self._has_result = False
        self._busy = False

    # ── public api ──────────────────────────────────────────────

    def poll(self, args=None, kwargs=None):
        """Start a background fetch if one isn't already running.

        Optionally override *args* / *kwargs* for this invocation.
        """
        with self._lock:
            if self._busy:
                return  # previous fetch still in flight
            self._busy = True

        a = args if args is not None else self._args
        kw = kwargs if kwargs is not None else self._kwargs
        try:
            t = threading.Thread(target=self._run, args=(a, kw), daemon=True)
            t.start()
        except RuntimeError:
            # Threading unavailable (e.g. WASM/emscripten) — run synchronously
            self._run(a, kw)

    def has_result(self):
        """Return True if a new result is available since the last read."""
        return self._has_result

    @property
    def result(self):
        """Return the latest result and clear the *has_result* flag."""
        with self._lock:
            self._has_result = False
            return self._result

    @property
    def busy(self):
        return self._busy

    # ── internals ───────────────────────────────────────────────

    def _run(self, args, kwargs):
        try:
            res = self._func(*args, **kwargs)
            with self._lock:
                self._result = res
                self._has_result = True
        except Exception as e:
            print(f"[BackgroundPoller] {self._func.__name__}: {e}")
        finally:
            with self._lock:
                self._busy = False
