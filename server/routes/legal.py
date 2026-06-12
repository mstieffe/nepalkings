# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Public legal-document routes."""
from pathlib import Path

from flask import Blueprint, Response, jsonify

import server_settings as settings

legal = Blueprint('legal', __name__)

_DOC_ROOT = Path(__file__).resolve().parents[2] / 'docs' / 'legal'
_DOCS = {
    'terms': 'TERMS.md',
    'privacy': 'PRIVACY.md',
    'community-guidelines': 'COMMUNITY_GUIDELINES.md',
    'attribution': 'ATTRIBUTION.md',
}


def _markdown_response(filename):
    path = _DOC_ROOT / filename
    if not path.exists():
        return jsonify({'success': False, 'message': 'Document not found'}), 404
    return Response(
        path.read_text(encoding='utf-8'),
        mimetype='text/plain; charset=utf-8',
    )


@legal.route('/terms', methods=['GET'])
def terms():
    return _markdown_response(_DOCS['terms'])


@legal.route('/privacy', methods=['GET'])
def privacy():
    return _markdown_response(_DOCS['privacy'])


@legal.route('/community-guidelines', methods=['GET'])
def community_guidelines():
    return _markdown_response(_DOCS['community-guidelines'])


@legal.route('/attribution', methods=['GET'])
def attribution():
    return _markdown_response(_DOCS['attribution'])


@legal.route('/versions', methods=['GET'])
def versions():
    return jsonify({
        'success': True,
        'terms_version': settings.LEGAL_TERMS_VERSION,
        'privacy_version': settings.LEGAL_PRIVACY_VERSION,
        'documents': {
            key: f'/legal/{key}'
            for key in _DOCS
        },
    })
