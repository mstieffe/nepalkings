from __future__ import annotations

from typing import Any

from scripts import probe_launch_endpoints as probe


RELEASE = "9" * 40


def _result(endpoint: str, payload: dict[str, Any]) -> probe.RequestResult:
    return probe.RequestResult(
        endpoint=endpoint,
        latency_ms=42.0,
        status=200,
        payload=payload,
        error=None,
    )


def test_probe_cycle_accepts_launch_contract(monkeypatch) -> None:
    payloads = {
        "/healthz": {
            "environment": "production",
            "release_sha": RELEASE,
            "status": "ok",
            "success": True,
        },
        "/readyz": {
            "database": "postgresql",
            "environment": "production",
            "release_sha": RELEASE,
            "schema_version": 17,
            "status": "ready",
            "success": True,
        },
        "/legal/versions": {
            "documents": {"privacy": "/legal/privacy", "terms": "/legal/terms"},
            "privacy_version": "2026-06-12",
            "success": True,
            "terms_version": "2026-06-12",
        },
    }
    monkeypatch.setattr(
        probe,
        "_request_json",
        lambda _base_url, endpoint, _timeout: _result(
            endpoint, payloads[endpoint]
        ),
    )

    report = probe.probe_cycle(
        [("production", "https://example.invalid")],
        samples=3,
        timeout=1,
        max_p95_ms=100,
        minimum_schema_version=17,
    )

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["targets"][0]["release_sha"] == RELEASE


def test_probe_cycle_rejects_wrong_environment_schema_and_release(
    monkeypatch,
) -> None:
    payloads = {
        "/healthz": {
            "environment": "staging",
            "release_sha": "a" * 40,
            "status": "ok",
            "success": True,
        },
        "/readyz": {
            "database": "sqlite",
            "environment": "production",
            "release_sha": "b" * 40,
            "schema_version": 16,
            "status": "ready",
            "success": True,
        },
        "/legal/versions": {"documents": {}, "success": True},
    }
    monkeypatch.setattr(
        probe,
        "_request_json",
        lambda _base_url, endpoint, _timeout: _result(
            endpoint, payloads[endpoint]
        ),
    )

    report = probe.probe_cycle(
        [("production", "https://example.invalid")],
        samples=1,
        timeout=1,
        max_p95_ms=100,
        minimum_schema_version=17,
    )

    assert report["ok"] is False
    errors = "\n".join(report["errors"])
    assert "expected environment" in errors
    assert "database is not postgresql" in errors
    assert "schema version is below 17" in errors
    assert "release mismatch" in errors
    assert "terms_version is missing" in errors


def test_probe_cycle_rejects_latency_ceiling(monkeypatch) -> None:
    def slow_result(_base_url, endpoint, _timeout):
        payload = {
            "success": True,
            "environment": "production",
            "release_sha": RELEASE,
        }
        if endpoint == "/healthz":
            payload["status"] = "ok"
        elif endpoint == "/readyz":
            payload.update(
                status="ready",
                database="postgresql",
                schema_version=17,
            )
        else:
            payload = {
                "documents": {
                    "privacy": "/legal/privacy",
                    "terms": "/legal/terms",
                },
                "privacy_version": "2026-06-12",
                "success": True,
                "terms_version": "2026-06-12",
            }
        result = _result(endpoint, payload)
        return probe.RequestResult(
            endpoint=result.endpoint,
            latency_ms=501.0,
            status=result.status,
            payload=result.payload,
            error=result.error,
        )

    monkeypatch.setattr(probe, "_request_json", slow_result)
    report = probe.probe_cycle(
        [("production", "https://example.invalid")],
        samples=3,
        timeout=1,
        max_p95_ms=500,
        minimum_schema_version=17,
    )

    assert report["ok"] is False
    assert "exceeds 500.0 ms" in "\n".join(report["errors"])
