"""Regression tests for web async polling behaviour."""


def test_web_async_result_checks_are_throttled(monkeypatch):
    from utils import background_poller as module
    from utils import http_compat

    current_time = [0.0]
    calls = []

    monkeypatch.setattr(module, '_IS_EMSCRIPTEN', True)
    monkeypatch.setattr(module._time, 'monotonic', lambda: current_time[0])

    def fake_check_async(rid):
        calls.append(rid)
        return None

    monkeypatch.setattr(http_compat, 'check_async', fake_check_async,
                        raising=False)

    poller = module.BackgroundPoller(lambda: None)
    poller._simple_rid = 123
    poller._busy = True

    assert poller.has_result() is False
    assert calls == [123]

    assert poller.has_result() is False
    assert calls == [123]

    current_time[0] = 0.099
    assert poller.has_result() is False
    assert calls == [123]

    current_time[0] = 0.100
    assert poller.has_result() is False
    assert calls == [123, 123]