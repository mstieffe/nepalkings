# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.

import tarfile
import zipfile

from scripts.report_web_bundle import inspect_bundle, main


def _bundle(tmp_path, size=32):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'main.py').write_bytes(b'x' * size)

    with tarfile.open(tmp_path / 'nepal_kings.tar.gz', 'w:gz') as archive:
        archive.add(assets / 'main.py', arcname='assets/main.py')
    with zipfile.ZipFile(
        tmp_path / 'nepal_kings.apk', 'w', zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr('assets/main.py', b'x' * size)
    audio = tmp_path / 'audio'
    audio.mkdir()
    (audio / 'cue.ogg').write_bytes(b'audio')


def test_report_inspects_both_runtime_archives(tmp_path):
    _bundle(tmp_path)
    report = inspect_bundle(tmp_path)

    assert report['external_audio_files'] == 1
    assert report['external_audio_bytes'] == 5
    assert report['top_uncompressed_archive_files'][0] == {
        'path': 'assets/main.py',
        'bytes': 32,
    }
    assert report['top_uncompressed_apk_files'][0] == {
        'path': 'assets/main.py',
        'bytes': 32,
    }


def test_report_fails_an_explicit_tiny_budget(tmp_path):
    _bundle(tmp_path, size=4096)

    result = main([
        str(tmp_path),
        '--max-archive-mib',
        '0.000001',
        '--max-audio-mib',
        '1',
    ])

    assert result == 1
