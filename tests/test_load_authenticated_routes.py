from scripts.load_authenticated_routes import (
    Sample,
    _nearest_rank,
    _route_path,
    _summarize,
)


def test_nearest_rank_percentile() -> None:
    values = [100, 200, 300, 400, 500]
    assert _nearest_rank(values, 0.50) == 300
    assert _nearest_rank(values, 0.95) == 500
    assert _nearest_rank([], 0.95) == 0


def test_route_paths_are_scoped_to_synthetic_viewer() -> None:
    assert _route_path("collection", "nkload_test", 42) == "/collection/cards"
    assert _route_path(
        "conquer_config",
        "nkload_test",
        42,
    ) == "/kingdom/conquer/config?land_id=42"
    assert _route_path(
        "game_list",
        "nkload_test",
        42,
    ) == "/games/get_games?username=nkload_test"
    assert _route_path("kingdom_map", "nkload_test", 42) == "/kingdom/map"


def test_summary_enforces_latency_and_error_budgets() -> None:
    passing = [
        Sample(
            bytes=100,
            elapsed_ms=100,
            error="",
            route="collection",
            status=200,
            virtual_user=index,
        )
        for index in range(100)
    ]
    report = _summarize(
        passing,
        duration_seconds=10,
        max_p95_ms=800,
        max_map_p95_ms=1500,
        max_error_rate=0.005,
    )
    assert report["ok"] is True
    assert report["requests_per_second"] == 10

    failing = passing + [
        Sample(
            bytes=0,
            elapsed_ms=900,
            error="HTTP 503",
            route="collection",
            status=503,
            virtual_user=101,
        )
    ]
    report = _summarize(
        failing,
        duration_seconds=10,
        max_p95_ms=800,
        max_map_p95_ms=1500,
        max_error_rate=0.005,
    )
    assert report["ok"] is False
    assert "error rate" in report["failures"][0]


def test_summary_uses_explicit_heavy_map_budget() -> None:
    samples = [
        Sample(
            bytes=3_341_221,
            elapsed_ms=1600,
            error="",
            route="kingdom_map",
            status=200,
            virtual_user=index,
        )
        for index in range(10)
    ]
    report = _summarize(
        samples,
        duration_seconds=10,
        max_p95_ms=800,
        max_map_p95_ms=1500,
        max_error_rate=0.005,
    )
    assert report["ok"] is False
    assert "kingdom_map p95" in report["failures"][0]
