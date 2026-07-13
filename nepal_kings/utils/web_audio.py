# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Small Python bridge to the browser-native Web Audio manager."""

import json
import sys


_IS_WEB = sys.platform == 'emscripten'


def _invoke(function_name, *args):
    if not _IS_WEB:
        return False
    try:
        import embed
        payload = ','.join(json.dumps(arg, separators=(',', ':'))
                           for arg in args)
        return bool(embed.js(
            f"window.{function_name}&&window.{function_name}({payload})"
        ))
    except Exception:
        return False


def play_sfx(filename, volume):
    return _invoke('nk_audio_play_sfx', filename, float(volume))


def play_music(filename, volume, fade_ms):
    return _invoke(
        'nk_audio_play_music', filename, float(volume), int(fade_ms))


def stop_music(fade_ms):
    return _invoke('nk_audio_stop_music', int(fade_ms))
