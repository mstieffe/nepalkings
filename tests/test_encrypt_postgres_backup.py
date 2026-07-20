from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.encrypt_postgres_backup import main


OPENSSL = shutil.which("openssl")


def _certificate(tmp_path: Path) -> tuple[Path, Path]:
    if not OPENSSL:
        pytest.skip("OpenSSL is not installed")
    private_key = tmp_path / "private.pem"
    certificate = tmp_path / "recipient-cert.pem"
    subprocess.run(
        [
            OPENSSL,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
            "-subj",
            "/CN=nepalkings-backup-test",
            "-days",
            "1",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, private_key


def test_create_round_trip_manifest_and_remove_source(tmp_path: Path) -> None:
    certificate, private_key = _certificate(tmp_path)
    source = tmp_path / "production.dump"
    source.write_bytes((b"postgres-custom-format-test\0" * 400) + b"end")
    plaintext_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "production.dump.cms"

    assert (
        main(
            [
                "create",
                str(source),
                str(output),
                "--recipient-cert",
                str(certificate),
                "--private-key",
                str(private_key),
                "--expected-sha256",
                plaintext_sha256,
                "--source-label",
                "/remote/production.dump",
                "--remove-source-after-verify",
            ]
        )
        == 0
    )

    manifest_path = tmp_path / "production.dump.cms.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not source.exists()
    assert output.is_file()
    assert output.stat().st_mode & 0o777 == 0o600
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert manifest["plaintext_sha256"] == plaintext_sha256
    assert manifest["round_trip_verified"] is True
    assert manifest["source_label"] == "/remote/production.dump"

    assert (
        main(
            [
                "verify",
                str(output),
                "--recipient-cert",
                str(certificate),
                "--private-key",
                str(private_key),
                "--expected-sha256",
                plaintext_sha256,
            ]
        )
        == 0
    )


def test_sha_mismatch_preserves_source_and_creates_no_output(
    tmp_path: Path,
) -> None:
    certificate, private_key = _certificate(tmp_path)
    source = tmp_path / "production.dump"
    source.write_bytes(b"backup")
    output = tmp_path / "production.dump.cms"

    assert (
        main(
            [
                "create",
                str(source),
                str(output),
                "--recipient-cert",
                str(certificate),
                "--private-key",
                str(private_key),
                "--expected-sha256",
                "0" * 64,
                "--remove-source-after-verify",
            ]
        )
        == 1
    )

    assert source.read_bytes() == b"backup"
    assert not output.exists()
