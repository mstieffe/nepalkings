# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""HTTP compatibility layer.

Desktop: re-exports from the ``requests`` library.
Web (pygbag/emscripten): synchronous XMLHttpRequest via embed.js(),
plus async XHR helpers for non-blocking background polling.

Auth token: call ``set_auth_token(token)`` after login so that all
subsequent requests automatically include ``Authorization: Bearer <token>``.
"""
import sys as _sys

# ── Auth token store (shared across both platforms) ──────────────────
_auth_token = None  # type: str | None


def set_auth_token(token):
    """Store the Bearer token to be sent with every request."""
    global _auth_token
    _auth_token = token


def clear_auth_token():
    """Remove the stored Bearer token (e.g. on logout)."""
    global _auth_token
    _auth_token = None


def get_auth_token():
    """Return the currently stored Bearer token, or None."""
    return _auth_token


if _sys.platform == "emscripten":
    # ── Web: XHR executed through pygbag's JS bridge ───────────
    import json as _json
    import embed as _embed

    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        pass

    class _Response:
        """Mimics ``requests.Response``."""

        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

        def json(self):
            return _json.loads(self.text) if self.text else {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise HTTPError(f"HTTP {self.status_code}: {self.text[:200]}")

    # -- helpers ------------------------------------------------

    def _js_escape(s):
        """Escape a Python string for safe embedding in a JS '…' literal."""
        return (
            str(s)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    def _encode_params(params):
        """Build a query string with percent-encoding."""
        if not params:
            return ""
        parts = []
        for k, v in params.items():
            ek = str(k).replace("%", "%25").replace("&", "%26").replace("=", "%3D").replace("+", "%2B").replace(" ", "%20")
            ev = str(v).replace("%", "%25").replace("&", "%26").replace("=", "%3D").replace("+", "%2B").replace(" ", "%20")
            parts.append(f"{ek}={ev}")
        return "?" + "&".join(parts)

    def _form_body_js(data):
        """Return a JS *expression* that evaluates to a form-encoded string."""
        if not data:
            return "null"
        pieces = []
        for k, v in data.items():
            ek = _js_escape(str(k))
            ev = _js_escape(str(v))
            pieces.append(
                f"encodeURIComponent('{ek}')+'='+encodeURIComponent('{ev}')"
            )
        # Join with '&' separators:  expr1 + '&' + expr2 + '&' + expr3
        return ("+'&'+".join(pieces))

    def _auth_header_js():
        """Return JS snippet to set the Authorization header if a token is stored."""
        if _auth_token:
            return f"x.setRequestHeader('Authorization','Bearer {_js_escape(_auth_token)}');"
        return ""

    def _do_xhr(method, url, content_type=None, body_js="null"):
        """Run a synchronous XHR via pygbag's JS bridge; return _Response."""
        ct_line = ""
        if content_type:
            ct_line = f"x.setRequestHeader('Content-Type','{content_type}');"

        auth_line = _auth_header_js()

        js = (
            f"(function(){{"
            f"var x=new XMLHttpRequest();"
            f"x.open('{method}','{_js_escape(url)}',false);"
            f"{ct_line}"
            f"{auth_line}"
            f"x.send({body_js});"
            f"return {{s:x.status,t:x.responseText||''}};"
            f"}})()"
        )
        result = _embed.js(js)
        if result is None:
            raise RequestException("XHR: embed.js() returned None")
        return _Response(int(result["s"]), str(result["t"]))

    # -- public API (matches requests.get / requests.post) ------

    def get(url, params=None, timeout=None, **kwargs):
        try:
            return _do_xhr("GET", url + _encode_params(params))
        except RequestException:
            raise
        except Exception as exc:
            raise RequestException(str(exc)) from exc

    def post(url, data=None, json=None, timeout=None, **kwargs):
        try:
            if json is not None:
                body = "'" + _js_escape(_json.dumps(json)) + "'"
                return _do_xhr("POST", url, "application/json", body)
            elif data is not None:
                return _do_xhr(
                    "POST", url,
                    "application/x-www-form-urlencoded",
                    _form_body_js(data),
                )
            else:
                return _do_xhr("POST", url)
        except RequestException:
            raise
        except Exception as exc:
            raise RequestException(str(exc)) from exc

    # ── Async XHR helpers (non-blocking, for background polling) ──

    _async_id_counter = 0

    def start_async_get(url, params=None):
        """Fire an async GET XHR; return an integer request-id."""
        global _async_id_counter
        _async_id_counter += 1
        rid = _async_id_counter
        full_url = _js_escape(url + _encode_params(params))
        auth_line = _auth_header_js()
        js = (
            f"(function(){{"
            f"window._axr=window._axr||{{}};"
            f"var x=new XMLHttpRequest();"
            f"x.open('GET','{full_url}',true);"
            f"{auth_line}"
            f"x.onload=function(){{window._axr[{rid}]={{s:x.status,t:x.responseText||''}};}};"
            f"x.onerror=function(){{window._axr[{rid}]={{s:0,t:'network error'}};}};"
            f"x.send();"
            f"}})()"
        )
        _embed.js(js)
        return rid

    def start_async_post(url, data=None):
        """Fire an async POST XHR with form-encoded data; return request-id."""
        global _async_id_counter
        _async_id_counter += 1
        rid = _async_id_counter
        full_url = _js_escape(url)
        body_js = _form_body_js(data)
        auth_line = _auth_header_js()
        js = (
            f"(function(){{"
            f"window._axr=window._axr||{{}};"
            f"var x=new XMLHttpRequest();"
            f"x.open('POST','{full_url}',true);"
            f"x.setRequestHeader('Content-Type','application/x-www-form-urlencoded');"
            f"{auth_line}"
            f"x.onload=function(){{window._axr[{rid}]={{s:x.status,t:x.responseText||''}};}};"
            f"x.onerror=function(){{window._axr[{rid}]={{s:0,t:'network error'}};}};"
            f"x.send({body_js});"
            f"}})()"
        )
        _embed.js(js)
        return rid

    def check_async(rid):
        """Check if async request *rid* finished.  Returns _Response or None."""
        js = (
            f"(function(){{"
            f"var r=(window._axr||{{}})[{rid}];"
            f"if(!r)return null;"
            f"delete window._axr[{rid}];"
            f"return r;"
            f"}})()"
        )
        result = _embed.js(js)
        if result is None:
            return None
        return _Response(int(result["s"]), str(result["t"]))

else:
    # ── Desktop: wrap requests to auto-inject Authorization header ─────
    import requests as _requests

    RequestException = _requests.exceptions.RequestException
    HTTPError = _requests.exceptions.HTTPError

    def _auth_headers():
        """Return dict with Authorization header if a token is set."""
        if _auth_token:
            return {'Authorization': f'Bearer {_auth_token}'}
        return {}

    def get(url, params=None, timeout=None, headers=None, **kwargs):
        h = {**_auth_headers(), **(headers or {})}
        return _requests.get(url, params=params, timeout=timeout, headers=h, **kwargs)

    def post(url, data=None, json=None, timeout=None, headers=None, **kwargs):
        h = {**_auth_headers(), **(headers or {})}
        return _requests.post(url, data=data, json=json, timeout=timeout, headers=h, **kwargs)
