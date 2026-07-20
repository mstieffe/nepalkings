#!/usr/bin/env python3
# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Report and enforce the public web bundle's pragmatic beta budgets."""

from __future__ import annotations

import argparse
import json
import tarfile
import zipfile
from pathlib import Path


MIB = 1024 * 1024


def _top_tar_files(path, limit=15):
    with tarfile.open(path, 'r:gz') as archive:
        rows = [
            {'path': item.name, 'bytes': item.size}
            for item in archive.getmembers()
            if item.isfile()
        ]
    return sorted(rows, key=lambda row: row['bytes'], reverse=True)[:limit]


def _top_zip_files(path, limit=15):
    with zipfile.ZipFile(path) as archive:
        rows = [
            {'path': item.filename, 'bytes': item.file_size}
            for item in archive.infolist()
            if not item.is_dir()
        ]
    return sorted(rows, key=lambda row: row['bytes'], reverse=True)[:limit]


def inspect_bundle(directory):
    directory = Path(directory)
    tar_path = directory / 'nepal_kings.tar.gz'
    apk_path = directory / 'nepal_kings.apk'
    if not tar_path.is_file() or not apk_path.is_file():
        raise FileNotFoundError(
            'Expected nepal_kings.tar.gz and nepal_kings.apk in '
            f'{directory}')
    audio_dir = directory / 'audio'
    audio_files = [
        path for path in audio_dir.rglob('*')
        if path.is_file()
    ] if audio_dir.is_dir() else []
    return {
        'directory': str(directory),
        'github_pages_archive_bytes': tar_path.stat().st_size,
        'itch_archive_bytes': apk_path.stat().st_size,
        'external_audio_bytes': sum(
            path.stat().st_size for path in audio_files),
        'external_audio_files': len(audio_files),
        'top_uncompressed_archive_files': _top_tar_files(tar_path),
        'top_uncompressed_apk_files': _top_zip_files(apk_path),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument(
        '--max-archive-mib',
        type=float,
        default=52.0,
        help='Maximum for each initial archive (default: 52 MiB)',
    )
    parser.add_argument(
        '--max-audio-mib',
        type=float,
        default=15.0,
        help='Maximum separately-loaded Web Audio tree (default: 15 MiB)',
    )
    parser.add_argument('--output')
    args = parser.parse_args(argv)

    report = inspect_bundle(args.directory)
    report['budgets'] = {
        'archive_mib': args.max_archive_mib,
        'external_audio_mib': args.max_audio_mib,
    }
    violations = []
    archive_limit = int(args.max_archive_mib * MIB)
    for key in (
        'github_pages_archive_bytes',
        'itch_archive_bytes',
    ):
        if report[key] > archive_limit:
            violations.append(
                f'{key} is {report[key] / MIB:.2f} MiB '
                f'(limit {args.max_archive_mib:.2f} MiB)')
    audio_limit = int(args.max_audio_mib * MIB)
    if report['external_audio_bytes'] > audio_limit:
        violations.append(
            'external_audio_bytes is '
            f"{report['external_audio_bytes'] / MIB:.2f} MiB "
            f'(limit {args.max_audio_mib:.2f} MiB)')
    report['passed'] = not violations
    report['violations'] = violations

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + '\n', encoding='utf-8')
    return 0 if not violations else 1


if __name__ == '__main__':
    raise SystemExit(main())
