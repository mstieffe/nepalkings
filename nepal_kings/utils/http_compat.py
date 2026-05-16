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
_auth_token = None


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


# ── Session-expired flag ─────────────────────────────────────────
_session_expired = False


def is_session_expired():
    """Return True if a 401 was received, indicating the token is stale."""
    return _session_expired


def clear_session_expired():
    """Reset the session-expired flag (e.g. after redirecting to login)."""
    global _session_expired
    _session_expired = False


def _check_auth_response(status_code):
    """If status is 401, mark session as expired and clear token."""
    global _session_expired, _auth_token
    if status_code == 401 and _auth_token is not None:
        _session_expired = True
        _auth_token = None

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

        __slots__ = ('status_code', 'text', '_json_cache', '_json_parsed')

        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text
            self._json_cache = None
            self._json_parsed = False

        def json(self):
            # Cache parsed JSON — multiple call sites (poller phase-1
            # transition + final assembly) used to re-parse the same body,
            # which is non-trivial on pygbag/emscripten for large figure
            # payloads.
            if not self._json_parsed:
                self._json_cache = _json.loads(self.text) if self.text else {}
                self._json_parsed = True
            return self._json_cache

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

    def _do_xhr(method, url, content_type=None, body_js="null"):
        """Run a synchronous XHR via pygbag's JS bridge; return _Response."""
        ct_line = ""
        if content_type:
            ct_line = f"x.setRequestHeader('Content-Type','{content_type}');"

        auth_line = ""
        if _auth_token:
            auth_line = f"x.setRequestHeader('Authorization','Bearer {_js_escape(_auth_token)}');"

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
        status = int(result["s"])
        _check_auth_response(status)
        return _Response(status, str(result["t"]))

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
        auth_js = ""
        if _auth_token:
            auth_js = f"x.setRequestHeader('Authorization','Bearer {_js_escape(_auth_token)}');"
        js = (
            f"(function(){{"
            f"window._axr=window._axr||{{}};"
            f"var x=new XMLHttpRequest();"
            f"x.open('GET','{full_url}',true);"
            f"{auth_js}"
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
        auth_js = ""
        if _auth_token:
            auth_js = f"x.setRequestHeader('Authorization','Bearer {_js_escape(_auth_token)}');"
        js = (
            f"(function(){{"
            f"window._axr=window._axr||{{}};"
            f"var x=new XMLHttpRequest();"
            f"x.open('POST','{full_url}',true);"
            f"x.setRequestHeader('Content-Type','application/x-www-form-urlencoded');"
            f"{auth_js}"
            f"x.onload=function(){{window._axr[{rid}]={{s:x.status,t:x.responseText||''}};}};"
            f"x.onerror=function(){{window._axr[{rid}]={{s:0,t:'network error'}};}};"
            f"x.send({body_js});"
            f"}})()"
        )
        _embed.js(js)
        return rid

    def start_async_post_json(url, payload=None):
        """Fire an async POST XHR with a JSON body; return request-id."""
        global _async_id_counter
        _async_id_counter += 1
        rid = _async_id_counter
        full_url = _js_escape(url)
        body_str = _json.dumps(payload or {})
        body_js = "'" + _js_escape(body_str) + "'"
        auth_js = ""
        if _auth_token:
            auth_js = f"x.setRequestHeader('Authorization','Bearer {_js_escape(_auth_token)}');"
        js = (
            f"(function(){{"
            f"window._axr=window._axr||{{}};"
            f"var x=new XMLHttpRequest();"
            f"x.open('POST','{full_url}',true);"
            f"x.setRequestHeader('Content-Type','application/json');"
            f"{auth_js}"
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
        status = int(result["s"])
        _check_auth_response(status)
        return _Response(status, str(result["t"]))

else:
    # ── Desktop: use requests with auto-injected auth ──────────────
    import requests as _requests

    RequestException = _requests.RequestException
    HTTPError = _requests.HTTPError

    def get(url, **kwargs):
        if _auth_token:
            headers = kwargs.pop('headers', {}) or {}
            headers.setdefault('Authorization', f'Bearer {_auth_token}')
            kwargs['headers'] = headers
        resp = _requests.get(url, **kwargs)
        _check_auth_response(resp.status_code)
        return resp

    def post(url, **kwargs):
        if _auth_token:
            headers = kwargs.pop('headers', {}) or {}
            headers.setdefault('Authorization', f'Bearer {_auth_token}')
            kwargs['headers'] = headers
        resp = _requests.post(url, **kwargs)
        _check_auth_response(resp.status_code)
        return resp
