from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import smoke_duel_concurrency as smoke


def test_staging_gold_bootstrap_refuses_non_synthetic_user(monkeypatch) -> None:
    called = False

    def unexpected_run(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(smoke.subprocess, "run", unexpected_run)

    with pytest.raises(RuntimeError, match="non-synthetic"):
        smoke._bootstrap_staging_gold(
            ["real_player", "nkduel_b_0720110032_ba33"],
            ssh_identity=Path("/tmp/identity"),
            known_hosts=Path("/tmp/known-hosts"),
        )

    assert called is False


def test_staging_gold_bootstrap_updates_exact_generated_users(
    monkeypatch,
) -> None:
    captured = {}

    def successful_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="UPDATE 2\n",
            stderr="",
        )

    monkeypatch.setattr(smoke.subprocess, "run", successful_run)
    smoke._bootstrap_staging_gold(
        [
            "nkduel_a_0720110032_5588",
            "nkduel_b_0720110032_ba33",
        ],
        ssh_identity=Path("/tmp/identity"),
        known_hosts=Path("/tmp/known-hosts"),
    )

    command = captured["command"]
    assert command[:2] == ["ssh", "-i"]
    assert "UserKnownHostsFile=/tmp/known-hosts" in command
    remote_command = command[-1]
    assert "nkduel_a_0720110032_5588" in remote_command
    assert "nkduel_b_0720110032_ba33" in remote_command
    assert "SET gold = 100" in remote_command
    assert "staging.env" in remote_command
    assert "password" not in remote_command.lower()
