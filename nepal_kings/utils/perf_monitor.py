import os
import sys
import time
from contextlib import contextmanager, nullcontext


_ACTIVE_MONITOR = None


def perf_enabled():
    return os.environ.get('NK_PERF') == '1'


class PerfMonitor:
    def __init__(self, *, enabled=None, publish_interval_ms=500, max_events=240):
        self.enabled = perf_enabled() if enabled is None else bool(enabled)
        self.publish_interval_ms = int(publish_interval_ms)
        self.max_events = int(max_events)
        self.frame_count = 0
        self.last_publish_ms = 0
        self.frame_started_at = None
        self.section_started_at = {}
        self.sections = {}
        self.frames = []
        self.slow_events = []
        self.context = {}

    @staticmethod
    def _now_ms():
        return time.perf_counter() * 1000.0

    def frame_start(self, context=None):
        global _ACTIVE_MONITOR
        if not self.enabled:
            return
        _ACTIVE_MONITOR = self
        self.frame_started_at = self._now_ms()
        self.context = dict(context or {})

    def frame_end(self):
        global _ACTIVE_MONITOR
        if not self.enabled or self.frame_started_at is None:
            return
        elapsed = self._now_ms() - self.frame_started_at
        self.frame_started_at = None
        self.frame_count += 1
        self.frames.append(round(elapsed, 3))
        if len(self.frames) > self.max_events:
            self.frames = self.frames[-self.max_events:]
        if elapsed >= 33.0:
            self.slow_events.append({
                'frame': self.frame_count,
                'ms': round(elapsed, 3),
                'context': dict(self.context),
            })
            if len(self.slow_events) > self.max_events:
                self.slow_events = self.slow_events[-self.max_events:]
        self.publish_if_due()
        _ACTIVE_MONITOR = None

    def begin(self, name):
        if self.enabled:
            self.section_started_at[name] = self._now_ms()

    def end(self, name):
        if not self.enabled:
            return
        started = self.section_started_at.pop(name, None)
        if started is None:
            return
        elapsed = self._now_ms() - started
        stats = self.sections.setdefault(name, {
            'count': 0,
            'total_ms': 0.0,
            'max_ms': 0.0,
            'slow': [],
        })
        stats['count'] += 1
        stats['total_ms'] += elapsed
        stats['max_ms'] = max(stats['max_ms'], elapsed)
        if elapsed >= 16.0:
            stats['slow'].append({
                'frame': self.frame_count + 1,
                'ms': round(elapsed, 3),
                'context': dict(self.context),
            })
            if len(stats['slow']) > 40:
                stats['slow'] = stats['slow'][-40:]

    @contextmanager
    def section(self, name):
        self.begin(name)
        try:
            yield
        finally:
            self.end(name)

    def summary(self):
        frames = list(self.frames)
        sections = {}
        for name, stats in self.sections.items():
            count = max(1, stats['count'])
            sections[name] = {
                'count': stats['count'],
                'avg_ms': round(stats['total_ms'] / count, 3),
                'max_ms': round(stats['max_ms'], 3),
                'slow': list(stats['slow']),
            }
        sorted_frames = sorted(frames)
        p95 = 0.0
        if sorted_frames:
            p95 = sorted_frames[min(len(sorted_frames) - 1,
                                    int(len(sorted_frames) * 0.95))]
        return {
            'enabled': self.enabled,
            'frame_count': self.frame_count,
            'context': dict(self.context),
            'work': {
                'samples': len(frames),
                'avg_ms': round(sum(frames) / len(frames), 3) if frames else 0.0,
                'p95_ms': round(p95, 3),
                'max_ms': round(max(frames), 3) if frames else 0.0,
            },
            'sections': sections,
            'slow_events': list(self.slow_events),
        }

    def publish_if_due(self, *, force=False):
        if not self.enabled or sys.platform != 'emscripten':
            return
        now = int(time.perf_counter() * 1000)
        if not force and now - self.last_publish_ms < self.publish_interval_ms:
            return
        self.last_publish_ms = now
        try:
            import json
            import embed
            payload = json.dumps(self.summary(), separators=(',', ':'))
            embed.js(
                "(function(){window.NK_PERF=" + payload + ";return 1;})()"
            )
        except Exception:
            pass


def perf_section(name):
    monitor = _ACTIVE_MONITOR
    if monitor is None or not monitor.enabled:
        return nullcontext()
    return monitor.section(name)