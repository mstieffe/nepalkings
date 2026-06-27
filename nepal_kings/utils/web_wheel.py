"""Raw browser wheel-event bridge for pygbag builds."""

import sys

import pygame


_IS_WEB = sys.platform == 'emscripten'
_installed = False

_MIN_PIXEL_WHEEL_UNIT = 0.08
_PIXELS_PER_WHEEL_UNIT = 100.0
_LINES_PER_WHEEL_UNIT = 3.0


def init():
    """Install the browser-side wheel listener once on web builds."""
    global _installed
    if not _IS_WEB or _installed:
        return
    try:
        import embed as _embed
        ok = bool(_embed.js("""
(function(){
    if (window.__nkWheelBridgeInstalled) return true;
    window.__nkWheelBridgeInstalled = true;
    window.__nkWheelQueue = window.__nkWheelQueue || [];

    function install(){
        if (window.__nkWheelBridgeListenerInstalled) return true;
        var canvas = document.getElementById('canvas');
        if (!canvas) return false;
        canvas.addEventListener('wheel', function(ev){
            var rect = canvas.getBoundingClientRect();
            var cssW = rect.width || canvas.clientWidth || canvas.width || 1;
            var cssH = rect.height || canvas.clientHeight || canvas.height || 1;
            var canvasW = canvas.width || cssW || 1;
            var canvasH = canvas.height || cssH || 1;
            var x = Math.round((ev.clientX - rect.left) * canvasW / cssW);
            var y = Math.round((ev.clientY - rect.top) * canvasH / cssH);
            x = Math.max(0, Math.min(canvasW, x));
            y = Math.max(0, Math.min(canvasH, y));
            window.__nkWheelQueue.push({
                dx: ev.deltaX || 0,
                dy: ev.deltaY || 0,
                mode: ev.deltaMode || 0,
                x: x,
                y: y
            });
            if (window.__nkWheelQueue.length > 64) {
                window.__nkWheelQueue.splice(
                    0, window.__nkWheelQueue.length - 64);
            }
            ev.preventDefault();
            ev.stopPropagation();
            if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();
        }, {capture: true, passive: false});
        window.__nkWheelBridgeListenerInstalled = true;
        return true;
    }

    if (!install()) {
        var tries = 0;
        var timer = window.setInterval(function(){
            tries += 1;
            if (install() || tries > 100) window.clearInterval(timer);
        }, 100);
    }
    return true;
})()
"""))
        _installed = ok
    except Exception:
        _installed = False


def merge_events(events):
    """Return *events* with raw web wheel samples appended as pygame events."""
    synthetic = drain_events()
    if not synthetic:
        return events
    filtered = [event for event in events if not _is_native_wheel_event(event)]
    return filtered + synthetic


def drain_events():
    """Drain pending raw browser wheel samples as pygame MOUSEWHEEL events."""
    if not _IS_WEB:
        return []
    init()
    if not _installed:
        return []
    try:
        import embed as _embed
        samples = _embed.js("""
(function(){
    var q = window.__nkWheelQueue || [];
    if (!q.length) return [];
    window.__nkWheelQueue = [];
    return q;
})()
""")
    except Exception:
        return []
    return _events_from_samples(samples or [])


def _is_native_wheel_event(event):
    if event.type == pygame.MOUSEWHEEL:
        return True
    return (event.type == pygame.MOUSEBUTTONDOWN
            and getattr(event, 'button', None) in (4, 5))


def _events_from_samples(samples):
    events = []
    for sample in samples:
        try:
            wheel_y = _wheel_units(sample.get('dy', 0), sample.get('mode', 0))
            if not wheel_y:
                continue
            pos = (int(round(float(sample.get('x', 0) or 0))),
                   int(round(float(sample.get('y', 0) or 0))))
        except Exception:
            continue
        y = 1 if wheel_y >= 1.0 else -1 if wheel_y <= -1.0 else 0
        events.append(pygame.event.Event(
            pygame.MOUSEWHEEL,
            {'x': 0, 'y': y, 'precise_y': wheel_y, 'pos': pos},
        ))
    return events


def _wheel_units(delta_y, delta_mode):
    delta_y = float(delta_y or 0)
    if not delta_y:
        return 0.0
    delta_mode = int(delta_mode or 0)
    if delta_mode == 1:
        units = -delta_y / _LINES_PER_WHEEL_UNIT
    elif delta_mode == 2:
        units = -delta_y
    else:
        units = -delta_y / _PIXELS_PER_WHEEL_UNIT
        if 0 < abs(units) < _MIN_PIXEL_WHEEL_UNIT:
            units = _MIN_PIXEL_WHEEL_UNIT if units > 0 else -_MIN_PIXEL_WHEEL_UNIT
    return max(-1.0, min(1.0, units))