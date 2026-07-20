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


def test_web_multi_request_can_start_json_post(monkeypatch):
    from utils import background_poller as module
    from utils import http_compat

    captured = []
    monkeypatch.setattr(module, '_IS_EMSCRIPTEN', True)
    monkeypatch.setattr(http_compat, 'start_async_get', lambda url, params=None: 2,
                        raising=False)

    def fake_post_json(url, payload=None):
        captured.append((url, payload))
        return 1

    monkeypatch.setattr(http_compat, 'start_async_post_json', fake_post_json,
                        raising=False)

    poller = module.BackgroundPoller(
        lambda: None,
        async_requests=[
            {'key': 'config', 'method': 'POST_JSON', 'url': '/draft/open',
             'json': {'land_id': 0}},
        ],
    )
    poller.poll(args=(7,))
    assert captured == [('/draft/open', {'land_id': 7})]


def test_web_polling_pauses_while_tab_is_hidden(monkeypatch):
    from utils import background_poller as module
    from utils import http_compat

    called = []
    monkeypatch.setattr(module, '_IS_EMSCRIPTEN', True)
    monkeypatch.setattr(http_compat, 'is_page_hidden', lambda: True,
                        raising=False)
    poller = module.BackgroundPoller(lambda: called.append(True))

    poller.poll()

    assert called == []
    assert poller.busy is False
