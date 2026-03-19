"""HTTP compatibility layer.

Desktop: re-exports from the ``requests`` library.
Web (pygbag/emscripten): synchronous XMLHttpRequest via embed.js().
"""
import sys as _sys

if _sys.platform == "emscripten":
    # ── Web: synchronous XHR executed through pygbag's JS bridge ───
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

    def _do_xhr(method, url, content_type=None, body_js="null"):
        """Run a synchronous XHR via pygbag's JS bridge; return _Response."""
        ct_line = ""
        if content_type:
            ct_line = f"x.setRequestHeader('Content-Type','{content_type}');"

        js = (
            f"(function(){{"
            f"var x=new XMLHttpRequest();"
            f"x.open('{method}','{_js_escape(url)}',false);"
            f"{ct_line}"
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

else:
    # ── Desktop: use requests ──────────────────────────────────────
    from requests import get, post, RequestException, HTTPError
