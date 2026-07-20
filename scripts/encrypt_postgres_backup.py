#!/usr/bin/env python3
"""Encrypt and verify a PostgreSQL custom-format backup for off-site storage.

The source dump is encrypted as CMS EnvelopedData with AES-256-GCM.  A
successful create operation decrypts the archive again and compares the
plaintext SHA-256 before it writes the manifest or removes the source.

Example:

    python scripts/encrypt_postgres_backup.py create \
      /private/tmp/production.dump \
      backups/off-provider/production/production.dump.cms \
      --recipient-cert ~/.config/nepalkings/backup-encryption/recipient-cert.pem \
      --private-key ~/.config/nepalkings/backup-encryption/private.pem \
      --expected-sha256 <sha256> \
      --source-label /home/nepalkingz/backups/postgres-production/production.dump \
      --remove-source-after-verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


BUFFER_SIZE = 1024 * 1024


class BackupEncryptionError(RuntimeError):
    """Raised when encryption or verification cannot be completed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _run_checked(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise BackupEncryptionError(f"{Path(command[0]).name} failed: {detail}")
    return result


def _certificate_fingerprint(openssl: str, certificate: Path) -> str:
    result = _run_checked(
        [
            openssl,
            "x509",
            "-in",
            str(certificate),
            "-noout",
            "-fingerprint",
            "-sha256",
        ]
    )
    _, separator, fingerprint = result.stdout.strip().partition("=")
    if not separator or not fingerprint:
        raise BackupEncryptionError("OpenSSL returned no certificate fingerprint")
    return fingerprint.upper()


def _decrypted_sha256(
    openssl: str,
    encrypted: Path,
    recipient_cert: Path,
    private_key: Path,
) -> str:
    digest = hashlib.sha256()
    with tempfile.TemporaryFile() as error_output:
        process = subprocess.Popen(
            [
                openssl,
                "cms",
                "-decrypt",
                "-binary",
                "-inform",
                "DER",
                "-in",
                str(encrypted),
                "-recip",
                str(recipient_cert),
                "-inkey",
                str(private_key),
            ],
            stdout=subprocess.PIPE,
            stderr=error_output,
        )
        assert process.stdout is not None
        while chunk := process.stdout.read(BUFFER_SIZE):
            digest.update(chunk)
        process.stdout.close()
        return_code = process.wait()
        if return_code != 0:
            error_output.seek(0)
            detail = error_output.read().decode("utf-8", errors="replace").strip()
            raise BackupEncryptionError(
                f"OpenSSL decryption failed: {detail or 'unknown error'}"
            )
    return digest.hexdigest()


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def create_backup(args: argparse.Namespace) -> int:
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    recipient_cert = args.recipient_cert.expanduser().resolve()
    private_key = args.private_key.expanduser().resolve()
    manifest = (
        args.manifest.expanduser().resolve()
        if args.manifest
        else output.with_name(f"{output.name}.manifest.json")
    )

    for required in (source, recipient_cert, private_key):
        if not required.is_file():
            raise BackupEncryptionError(f"Required file is missing: {required}")
    if output.exists() and not args.overwrite:
        raise BackupEncryptionError(
            f"Output already exists (pass --overwrite to replace it): {output}"
        )

    openssl = shutil.which(args.openssl)
    if not openssl:
        raise BackupEncryptionError(f"OpenSSL executable not found: {args.openssl}")

    plaintext_sha256 = _sha256(source)
    if (
        args.expected_sha256
        and plaintext_sha256.lower() != args.expected_sha256.lower()
    ):
        raise BackupEncryptionError(
            "Source SHA-256 does not match --expected-sha256; refusing to encrypt"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_output = Path(temporary_name)
    try:
        _run_checked(
            [
                openssl,
                "cms",
                "-encrypt",
                "-binary",
                "-aes-256-gcm",
                "-in",
                str(source),
                "-outform",
                "DER",
                "-out",
                str(temporary_output),
                str(recipient_cert),
            ]
        )
        os.chmod(temporary_output, 0o600)
        decrypted_sha256 = _decrypted_sha256(
            openssl,
            temporary_output,
            recipient_cert,
            private_key,
        )
        if decrypted_sha256 != plaintext_sha256:
            raise BackupEncryptionError(
                "Decrypted SHA-256 differs from the source; refusing to publish backup"
            )

        encrypted_sha256 = _sha256(temporary_output)
        encrypted_size = temporary_output.stat().st_size
        os.replace(temporary_output, output)
        os.chmod(output, 0o600)

        payload: dict[str, object] = {
            "created_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "encryption": "CMS EnvelopedData with AES-256-GCM",
            "encrypted_file": output.name,
            "encrypted_sha256": encrypted_sha256,
            "encrypted_size_bytes": encrypted_size,
            "format_version": 1,
            "plaintext_sha256": plaintext_sha256,
            "plaintext_size_bytes": source.stat().st_size,
            "recipient_certificate_sha256_fingerprint": _certificate_fingerprint(
                openssl, recipient_cert
            ),
            "round_trip_verified": True,
            "source_file": source.name,
            "source_label": args.source_label or source.name,
        }
        _write_manifest(manifest, payload)

        if args.remove_source_after_verify:
            source.unlink()

        print(
            json.dumps(
                {
                    "encrypted_backup": str(output),
                    "manifest": str(manifest),
                    "plaintext_sha256": plaintext_sha256,
                    "encrypted_sha256": encrypted_sha256,
                    "round_trip_verified": True,
                    "source_removed": bool(args.remove_source_after_verify),
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        temporary_output.unlink(missing_ok=True)


def verify_backup(args: argparse.Namespace) -> int:
    encrypted = args.encrypted.expanduser().resolve()
    recipient_cert = args.recipient_cert.expanduser().resolve()
    private_key = args.private_key.expanduser().resolve()
    for required in (encrypted, recipient_cert, private_key):
        if not required.is_file():
            raise BackupEncryptionError(f"Required file is missing: {required}")

    openssl = shutil.which(args.openssl)
    if not openssl:
        raise BackupEncryptionError(f"OpenSSL executable not found: {args.openssl}")

    plaintext_sha256 = _decrypted_sha256(
        openssl,
        encrypted,
        recipient_cert,
        private_key,
    )
    if (
        args.expected_sha256
        and plaintext_sha256.lower() != args.expected_sha256.lower()
    ):
        raise BackupEncryptionError(
            "Decrypted SHA-256 does not match --expected-sha256"
        )
    print(
        json.dumps(
            {
                "encrypted_backup": str(encrypted),
                "encrypted_sha256": _sha256(encrypted),
                "plaintext_sha256": plaintext_sha256,
                "verified": True,
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create", help="encrypt, round-trip verify, and manifest a dump"
    )
    create.add_argument("source", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--recipient-cert", type=Path, required=True)
    create.add_argument("--private-key", type=Path, required=True)
    create.add_argument("--expected-sha256")
    create.add_argument("--source-label")
    create.add_argument("--manifest", type=Path)
    create.add_argument("--openssl", default="openssl")
    create.add_argument("--overwrite", action="store_true")
    create.add_argument("--remove-source-after-verify", action="store_true")
    create.set_defaults(handler=create_backup)

    verify = subparsers.add_parser(
        "verify", help="decrypt to a hash stream and verify an encrypted dump"
    )
    verify.add_argument("encrypted", type=Path)
    verify.add_argument("--recipient-cert", type=Path, required=True)
    verify.add_argument("--private-key", type=Path, required=True)
    verify.add_argument("--expected-sha256")
    verify.add_argument("--openssl", default="openssl")
    verify.set_defaults(handler=verify_backup)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except BackupEncryptionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
