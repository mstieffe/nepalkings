#!/usr/bin/env python3
"""Capture Nepal Kings web UI screenshots under mobile-sized viewports.

This script intentionally uses only the Python standard library. It prepares a
review web root from the pygbag build output, serves it locally, launches Chrome
with the DevTools Protocol enabled, applies mobile emulation, waits for the game
runtime, then captures the rendered canvas/page.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "nepal_kings"
BUILD_WEB = APP_DIR / "build" / "web"
BUILD_CACHE = APP_DIR / "build" / "web-cache"
REVIEW_ROOT = ROOT / "artifacts" / "mobile-ui-review" / "web"
SCREENSHOT_DIR = ROOT / "artifacts" / "mobile-ui-review" / "screenshots"

CDN_BASE = "https://pygame-web.github.io/cdn/"
CDN_FILES = {
    "index-0.9.3-cp312.json": CDN_BASE + "index-0.9.3-cp312.json",
    "0.9.3/pythons.js": CDN_BASE + "0.9.3/pythons.js",
    # The pygbag 0.9.3 template points at pygame-web's browserfs path, but
    # that URL currently serves a 404 page. Use the BrowserFS package CDN for
    # the local review root so the WASM runtime can mount its filesystem.
    "0.9.3/browserfs.min.js": "https://cdn.jsdelivr.net/npm/browserfs@1.4.3/dist/browserfs.min.js",
    "0.9.3/cpython312/main.js": CDN_BASE + "0.9.3/cpython312/main.js",
    "0.9.3/cpython312/main.data": CDN_BASE + "0.9.3/cpython312/main.data",
    "0.9.3/cpython312/main.wasm": CDN_BASE + "0.9.3/cpython312/main.wasm",
    "0.9.3/cpythonrc.py": CDN_BASE + "0.9.3/cpythonrc.py",
    "0.9.3/empty.html": CDN_BASE + "0.9.3/empty.html",
    "0.9.3/empty.ogg": CDN_BASE + "0.9.3/empty.ogg",
    "cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl":
        CDN_BASE + "cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl",
    "vtx.js": CDN_BASE + "vtx.js",
    "vt/xterm.css": CDN_BASE + "vt/xterm.css",
    "vt/xterm.js": CDN_BASE + "vt/xterm.js",
    "vt/xterm-addon-image.js": CDN_BASE + "vt/xterm-addon-image.js",
}

DEFAULT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print("http:", fmt % args)


def md5_url(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def find_cached(url: str) -> Path | None:
    digest = md5_url(url)
    for suffix in (".data", ".js", ".css", ".wasm", ".py", ".ogg", ".png"):
        candidate = BUILD_CACHE / f"{digest}{suffix}"
        if candidate.exists():
            return candidate
    return None


def fetch_missing(url: str, dest: Path) -> None:
    print(f"fetching {url}")
    with urlopen(url, timeout=30) as response:
        dest.write_bytes(response.read())


def prepare_review_root(fetch_cdn: bool) -> None:
    if not (BUILD_WEB / "nepal_kings.tar.gz").exists():
        raise SystemExit(
            "Missing pygbag build output. Run: python -m pygbag --build nepal_kings"
        )

    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    for name in ("nepal_kings.tar.gz", "nepal_kings.apk", "favicon.png"):
        shutil.copy2(BUILD_WEB / name, REVIEW_ROOT / name)

    index_src = APP_DIR / "web" / "index.html"
    index = index_src.read_text(encoding="utf-8")
    index = index.replace("https://pygame-web.github.io/cdn/0.9.3/pythons.js", "/cdn/0.9.3/pythons.js")
    index = index.replace("https://pygame-web.github.io/cdn/0.9.3/", "/cdn/0.9.3/")
    index = index.replace("/cdn/0.9.3//browserfs.min.js", "/cdn/0.9.3/browserfs.min.js")
    (REVIEW_ROOT / "index.html").write_text(index, encoding="utf-8")

    for rel, url in CDN_FILES.items():
        dest = REVIEW_ROOT / "cdn" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        cached = find_cached(url)
        if cached:
            shutil.copy2(cached, dest)
        elif fetch_cdn:
            fetch_missing(url, dest)
        elif not dest.exists():
            raise SystemExit(
                f"Missing cached CDN file for {url}. "
                "Re-run with --fetch-cdn or build once with network access."
            )

    # The pygbag package index can contain absolute localhost:8000 package
    # URLs. The review server usually runs on a throwaway port, so rewrite
    # runtime fetch URLs back to the current local origin before fetch().
    pythons_js = REVIEW_ROOT / "cdn" / "0.9.3" / "pythons.js"
    js = pythons_js.read_text(encoding="utf-8")
    rewrite = (
        'if (typeof url === "string") {'
        'url = url.replace("https://pygame-web.github.io/cdn/", window.location.origin + "/cdn/");'
        'url = url.replace("http://localhost:8000/cdn/", window.location.origin + "/cdn/");'
        '}'
    )
    js = js.replace(
        "window.cross_file = function * cross_file(url, store, flags) {",
        "window.cross_file = function * cross_file(url, store, flags) {"
        + rewrite,
    )
    js = js.replace(
        "window.cross_dl = async function cross_dl(url, flags) {",
        "window.cross_dl = async function cross_dl(url, flags) {"
        + rewrite,
    )
    pythons_js.write_text(js, encoding="utf-8")


def start_server(port: int) -> http.server.ThreadingHTTPServer:
    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(REVIEW_ROOT), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    while n:
        chunk = sock.recv(n)
        if not chunk:
            raise ConnectionError("socket closed")
        chunks.append(chunk)
        n -= len(chunk)
    return b"".join(chunks)


def websocket_connect(ws_url: str) -> socket.socket:
    parsed = urlparse(ws_url)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    sock = socket.create_connection((parsed.hostname, parsed.port or 80), timeout=10)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}:{parsed.port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = sock.recv(4096)
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise ConnectionError(response.decode("latin1", errors="replace"))
    sock.settimeout(1.0)
    return sock


def ws_send(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = bytearray([0x81])
    if len(data) < 126:
        header.append(0x80 | len(data))
    elif len(data) < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", len(data)))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", len(data)))
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sock.sendall(bytes(header) + mask + masked)


def ws_recv(sock: socket.socket, timeout: float) -> dict[str, Any] | None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            first = recv_exact(sock, 2)
        except socket.timeout:
            continue
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        masked = bool(first[1] & 0x80)
        if length == 126:
            length = struct.unpack("!H", recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", recv_exact(sock, 8))[0]
        mask = recv_exact(sock, 4) if masked else b""
        payload = recv_exact(sock, length)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 8:
            return None
        if opcode == 1:
            return json.loads(payload.decode("utf-8"))
    return None


class Cdp:
    def __init__(self, ws_url: str):
        self.sock = websocket_connect(ws_url)
        self.next_id = 1
        self.events: list[dict[str, Any]] = []

    def command(self, method: str, params: dict[str, Any] | None = None, timeout: float = 10) -> Any:
        msg_id = self.next_id
        self.next_id += 1
        ws_send(self.sock, {"id": msg_id, "method": method, "params": params or {}})
        end = time.time() + timeout
        while time.time() < end:
            msg = ws_recv(self.sock, max(0.1, end - time.time()))
            if not msg:
                continue
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")
            if "method" in msg:
                self.events.append(msg)
        raise TimeoutError(method)

    def close(self) -> None:
        self.sock.close()


def get_json(url: str) -> Any:
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_target(debug_port: int) -> str:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            targets = get_json(f"http://127.0.0.1:{debug_port}/json/list")
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.2)
    raise TimeoutError("Chrome DevTools target not available")


def evaluate_probe(cdp: Cdp) -> dict[str, Any]:
    expression = """
(() => {
  const canvas = document.getElementById('canvas');
  const loader = document.getElementById('nk-loader');
  const rect = canvas ? canvas.getBoundingClientRect() : null;
  return {
    href: location.href,
    readyState: document.readyState,
    title: document.title,
    bodyText: (document.body && document.body.innerText || '').slice(0, 300),
    canvas: canvas ? {
      width: canvas.width,
      height: canvas.height,
      cssWidth: rect.width,
      cssHeight: rect.height,
      visible: getComputedStyle(canvas).visibility,
      display: getComputedStyle(canvas).display
    } : null,
    loaderDisplay: loader ? getComputedStyle(loader).display : null,
    loaderOpacity: loader ? getComputedStyle(loader).opacity : null
  };
})()
"""
    result = cdp.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    return result.get("result", {}).get("value", {})


def drain_cdp_events(cdp: Cdp) -> None:
    while True:
        event = ws_recv(cdp.sock, 0.05)
        if not event:
            break
        if "method" not in event:
            continue
        cdp.events.append(event)
        if event.get("method") == "Page.javascriptDialogOpening":
            try:
                cdp.command("Page.handleJavaScriptDialog", {"accept": True}, timeout=2)
            except Exception:
                pass


def launch_chrome(chrome: str, debug_port: int, profile: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-component-update",
            "--mute-audio",
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def parse_viewport(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="login")
    parser.add_argument("--path", default="/")
    parser.add_argument("--viewport", default="932x430")
    parser.add_argument("--wait", type=float, default=25.0)
    parser.add_argument("--server-port", type=int, default=8011)
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--fetch-cdn", action="store_true")
    parser.add_argument("--skip-prepare", action="store_true")
    args = parser.parse_args()

    if not args.skip_prepare:
        prepare_review_root(fetch_cdn=args.fetch_cdn)

    width, height = parse_viewport(args.viewport)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    server = start_server(args.server_port)
    profile = Path(tempfile.mkdtemp(prefix="nk-mobile-cdp-"))
    chrome = launch_chrome(args.chrome, args.debug_port, profile)
    cdp = None
    try:
        ws_url = wait_for_target(args.debug_port)
        cdp = Cdp(ws_url)
        cdp.command("Page.enable")
        cdp.command("Runtime.enable")
        cdp.command("Emulation.setUserAgentOverride", {"userAgent": DEFAULT_UA})
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 3,
                "mobile": True,
                "screenOrientation": {"type": "landscapePrimary", "angle": 90},
            },
        )
        url = f"http://localhost:{args.server_port}{args.path}"
        cdp.command("Page.navigate", {"url": url})
        deadline = time.time() + args.wait
        probe = {}
        audio_gate_tapped = False
        while time.time() < deadline:
            time.sleep(1)
            try:
                probe = evaluate_probe(cdp)
                drain_cdp_events(cdp)
                if (not audio_gate_tapped
                        and "Tap to start" in (probe.get("bodyText") or "")):
                    # The production shell intentionally waits for a real
                    # user gesture before unlocking Web Audio. CDP input is a
                    # trusted gesture, unlike element.click(), so let the
                    # screenshot harness pass the same gate a player sees.
                    for event_type in ("mousePressed", "mouseReleased"):
                        cdp.command(
                            "Input.dispatchMouseEvent",
                            {
                                "type": event_type,
                                "x": width / 2,
                                "y": height / 2,
                                "button": "left",
                                "clickCount": 1,
                            },
                        )
                    audio_gate_tapped = True
                    continue
                canvas = probe.get("canvas") or {}
                if canvas.get("width", 0) > 1 and probe.get("loaderDisplay") == "none":
                    break
            except Exception as exc:
                probe = {"probeError": repr(exc)}
                drain_cdp_events(cdp)
        out = SCREENSHOT_DIR / f"{args.name}-{width}x{height}.png"
        meta = SCREENSHOT_DIR / f"{args.name}-{width}x{height}.json"
        probe["events"] = cdp.events[-80:]
        try:
            screenshot = cdp.command(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
                timeout=60,
            )
            png = base64.b64decode(screenshot["data"])
            out.write_bytes(png)
            print(out)
        except Exception as exc:
            probe["screenshotError"] = repr(exc)
        meta.write_text(json.dumps(probe, indent=2), encoding="utf-8")
        print(meta)
        return 0
    finally:
        if cdp:
            try:
                cdp.command("Browser.close", timeout=2)
            except Exception:
                pass
            cdp.close()
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
