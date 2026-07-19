# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression checks for the production API baked into released clients."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_API = 'https://api-nepalkingz.eu.pythonanywhere.com'
LEGACY_API = 'https://nepalkings.pythonanywhere.com'


def test_all_release_entry_points_use_the_production_api():
    release_files = (
        ROOT / 'nepal_kings' / 'main.py',
        ROOT / 'nepal_kings' / 'config' / 'server_settings.py',
        ROOT / 'run_remote.sh',
        ROOT / 'build_installer.sh',
        ROOT / '.github' / 'workflows' / 'build.yml',
    )

    for path in release_files:
        text = path.read_text(encoding='utf-8')
        assert PRODUCTION_API in text, f'{path} does not use the production API'
        assert LEGACY_API not in text, f'{path} still bakes in the legacy API'


def test_pages_deployment_still_requires_main():
    workflow = (
        ROOT / '.github' / 'workflows' / 'deploy-web.yml'
    ).read_text(encoding='utf-8')

    assert 'branches: [main]' in workflow
    assert 'branches: [develop]' not in workflow
