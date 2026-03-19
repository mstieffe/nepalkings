"""HTTP compatibility layer.

Desktop: re-exports from the ``requests`` library.
Web (pygbag/emscripten): provides stubs so modules import cleanly.
Phase 2 will replace the stubs with browser ``fetch()`` wrappers.
"""
import sys as _sys

if _sys.platform == "emscripten":
    # ── Web stubs ──────────────────────────────────────────────────
    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        pass

    class _StubResponse:
        status_code = 503
        text = "Network not available (web stub)"

        def json(self):
            return {}

        def raise_for_status(self):
            raise HTTPError(self.text)

    def get(*args, **kwargs):
        return _StubResponse()

    def post(*args, **kwargs):
        return _StubResponse()

else:
    # ── Desktop: use requests ──────────────────────────────────────
    from requests import get, post, RequestException, HTTPError
