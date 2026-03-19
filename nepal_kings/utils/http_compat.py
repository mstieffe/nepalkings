"""HTTP compatibility layer.

Desktop: re-exports from the ``requests`` library.
Web (pygbag/emscripten): synchronous XMLHttpRequest via JS interop.
"""
import sys as _sys

if _sys.platform == "emscripten":
    # ── Web: synchronous XMLHttpRequest ────────────────────────────
    import json as _json
    from platform import window as _window  # pygbag JS interop

    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        pass

    class _Response:
        """Mimics a ``requests.Response`` backed by an XMLHttpRequest."""

        def __init__(self, xhr):
            self.status_code = xhr.status
            self.text = xhr.responseText or ""

        def json(self):
            return _json.loads(self.text) if self.text else {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise HTTPError(
                    f"HTTP {self.status_code}: {self.text[:200]}"
                )

    def _encode_params(params):
        """URL-encode a dict of query parameters."""
        if not params:
            return ""
        parts = []
        for k, v in params.items():
            # Minimal percent-encoding for common chars
            parts.append(f"{k}={v}")
        return "?" + "&".join(parts)

    def _encode_form(data):
        """URL-encode a dict as application/x-www-form-urlencoded body."""
        if not data:
            return ""
        parts = []
        for k, v in data.items():
            parts.append(f"{k}={v}")
        return "&".join(parts)

    def get(url, params=None, timeout=None, **kwargs):
        try:
            full_url = url + _encode_params(params)
            xhr = _window.XMLHttpRequest.new()
            xhr.open("GET", full_url, False)  # synchronous
            xhr.send(None)
            return _Response(xhr)
        except Exception as exc:
            raise RequestException(str(exc)) from exc

    def post(url, data=None, json=None, timeout=None, **kwargs):
        try:
            xhr = _window.XMLHttpRequest.new()
            xhr.open("POST", url, False)  # synchronous
            if json is not None:
                xhr.setRequestHeader("Content-Type", "application/json")
                xhr.send(_json.dumps(json))
            elif data is not None:
                xhr.setRequestHeader(
                    "Content-Type", "application/x-www-form-urlencoded"
                )
                xhr.send(_encode_form(data))
            else:
                xhr.send(None)
            return _Response(xhr)
        except Exception as exc:
            raise RequestException(str(exc)) from exc

else:
    # ── Desktop: use requests ──────────────────────────────────────
    from requests import get, post, RequestException, HTTPError
