# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""Generate the game's runtime audio set plus web OGG companions.

Every runtime sound in nepal_kings/sound/ is built by this script. Most are
synthesized from project-owned recipes; approved source masters are converted
from scripts/assets/audio_sources/. Re-run after changing a recipe or source:

    python scripts/assets/generate_sfx.py

Design notes: 44.1 kHz avoids audible browser resampling and preserves the
detail in approved source recordings. Most short effects stay mono, while
music and spatial spell cues stay stereo. The OGG companions use a higher
quality setting than the original web pass and are used by the pygbag build
because browsers are more reliable with OGG than SDL WAV decoding. The
palette aims for soft felt, wood, bell metal, frame drum, and airy tones —
minimal and tactile rather than arcade-like.
"""

import array
import math
import os
import random
import shutil
import subprocess
import wave

SAMPLE_RATE = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '..', '..', 'nepal_kings', 'sound')
SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'audio_sources')
MIXKIT_SOURCE_DIR = os.path.join(SOURCE_DIR, 'mixkit')
WAV_OUTPUTS = []

EXTERNAL_MUSIC = {
    'menu': {
        'source': 'Menu Theme Source.flac',
        'source_duration': 66,
        'crossfade': 6,
        'gain_db': -8,
        'title': 'Nepal Kings Menu Theme',
        'asset_id': 'f3f9f88c-d579-4141-84ea-a9dc67c0aa08',
    },
    'kingdom': {
        'source': 'Kingdom Theme Source.flac',
        'source_duration': 66,
        'crossfade': 6,
        'gain_db': -8,
        'title': 'Nepal Kings Kingdom Theme',
        'asset_id': 'a0e07e8c-1d6d-4680-8d00-ff3a352623c4',
    },
    'battle': {
        'source': 'Battle Theme Source.flac',
        'source_duration': 51,
        'crossfade': 6,
        'gain_db': -8,
        'title': 'Nepal Kings Battle Theme',
        'asset_id': 'db9a709b-4806-4f4f-a04c-adb5340fd7ae',
    },
}

MIXKIT_EFFECTS = {
    'spell_cast': {
        'sources': ('mixkit-fast-magic-game-spell-883.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=1.6,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.25:d=0.35,volume=9dB,'
            'aresample=44100[out]'),
        'channels': 2,
    },
    'counter_spell': {
        'sources': ('mixkit-icicles-spell-whoosh-881.wav',),
        'filter': (
            '[0:a]atrim=start=0.1:end=2.25,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.8:d=0.35,volume=6dB,'
            'aresample=44100[out]'),
        'channels': 2,
    },
    'spell_heal': {
        'sources': ('mixkit-medium-healing-spell-880.wav',),
        'filter': (
            '[0:a]atrim=start=0.1:end=2.2,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.75:d=0.35,volume=5dB,'
            'aresample=44100[out]'),
        'channels': 2,
        'fallback': 'spell_cast.wav',
    },
    'spell_poison': {
        'sources': ('mixkit-heal-soft-water-spell-878.wav',),
        'filter': (
            '[0:a]atrim=start=0.05:end=1.7,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.35:d=0.35,volume=8dB,lowpass=f=4200,'
            'aresample=44100[out]'),
        'channels': 2,
        'fallback': 'spell_cast.wav',
    },
    'spell_reveal': {
        'sources': ('mixkit-light-spell-873.wav',),
        'filter': (
            '[0:a]atrim=start=0.05:end=1.7,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.35:d=0.35,volume=9dB,'
            'aresample=44100[out]'),
        'channels': 2,
        'fallback': 'spell_cast.wav',
    },
    'spell_cards': {
        'sources': ('mixkit-spell-waves-874.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=1.55,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.2:d=0.35,volume=-2dB,'
            'aresample=44100[out]'),
        'channels': 2,
        'fallback': 'spell_cast.wav',
    },
    'spell_explosion': {
        'sources': (
            'mixkit-fireball-spell-1347.wav',
            'mixkit-explosion-spell-1685.wav',
        ),
        'filter': (
            '[0:a]atrim=start=0:end=1.55,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.2:d=0.35,volume=-6dB[cast];'
            '[1:a]atrim=start=0:end=1.25,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.95:d=0.3,volume=-9dB,'
            'adelay=420:all=1[impact];'
            '[cast][impact]amix=inputs=2:duration=longest:normalize=0,'
            'alimiter=limit=0.7:attack=5:release=50,'
            'aresample=44100[out]'),
        'channels': 2,
        'fallback': 'spell_cast.wav',
    },
    'card_slide_4': {
        'sources': ('mixkit-poker-card-flick-2002.wav',),
        'filter': (
            '[0:a]atrim=start=0.035:end=0.335,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.22:d=0.08,volume=10dB,'
            'alimiter=limit=0.7:attack=2:release=20,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
        'fallback': 'card_slide.wav',
    },
    'card_place_3': {
        'sources': ('mixkit-poker-card-placement-2001.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=0.18,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.12:d=0.06,volume=6dB,'
            'alimiter=limit=0.7:attack=2:release=20,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
        'fallback': 'card_place.wav',
    },
    'coin_3': {
        'sources': ('mixkit-space-coin-win-notification-271.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=0.38,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.30:d=0.08,volume=-3dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
        'fallback': 'coin.wav',
    },
    'booster_open': {
        'sources': ('mixkit-cards-deck-hits-1994.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=0.82,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.68:d=0.14,volume=8dB,'
            'alimiter=limit=0.7:attack=2:release=25,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'booster_open_2': {
        'sources': ('mixkit-thin-metal-card-deck-shuffle-3175.wav',),
        'filter': (
            '[0:a]atrim=start=0.25:end=1.0,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.62:d=0.13,volume=9dB,'
            'alimiter=limit=0.7:attack=2:release=25,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
        'fallback': 'booster_open.wav',
    },
    'rare_card_reveal': {
        'sources': ('mixkit-ethereal-fairy-win-sound-2019.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=2.38,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=2.08:d=0.30,volume=-1.5dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'reward_reveal': {
        'sources': ('mixkit-game-loot-win-2013.wav',),
        'filter': (
            '[0:a]atrim=start=0.10:end=1.03,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.78:d=0.15,volume=2dB,'
            'alimiter=limit=0.7:attack=3:release=30,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'quest_claim': {
        'sources': ('mixkit-achievement-bell-600.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=1.25,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.0:d=0.25,volume=-2dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'craft_success': {
        'sources': ('mixkit-metal-medieval-construction-818.wav',),
        'filter': (
            '[0:a]atrim=start=0.10:end=1.40,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.10:d=0.20,volume=-1dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'figure_place_2': {
        'sources': ('mixkit-metal-hammer-hit-833.wav',),
        'filter': (
            '[0:a]atrim=start=0.08:end=0.55,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.35:d=0.12,volume=12dB,'
            'alimiter=limit=0.7:attack=2:release=25,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
        'fallback': 'figure_place.wav',
    },
    'map_gain': {
        'sources': ('mixkit-unlock-game-notification-253.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=0.95,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.72:d=0.18,volume=6dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'round_win': {
        'sources': ('mixkit-quick-win-video-game-notification-269.wav',),
        'filter': (
            '[0:a]atrim=start=0.08:end=0.98,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=0.70:d=0.20,volume=-3dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'battle_total': {
        'sources': ('mixkit-arcade-score-interface-217.wav',),
        'filter': (
            '[0:a]atrim=start=0.10:end=1.65,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.30:d=0.25,volume=-1dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'battle_win': {
        'sources': ('mixkit-winning-notification-2018.wav',),
        'filter': (
            '[0:a]atrim=start=0:end=1.50,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.20:d=0.25,volume=-1.5dB,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
    'battle_lose': {
        'sources': ('mixkit-losing-drums-2023.wav',),
        'filter': (
            '[0:a]atrim=start=0.06:end=2.15,asetpts=PTS-STARTPTS,'
            'afade=t=out:st=1.75:d=0.30,'
            'pan=mono|c0=0.5*c0+0.5*c1,aresample=44100[out]'),
    },
}

random.seed(42)  # deterministic noise → reproducible files


# ── DSP helpers (lists of floats in [-1, 1]) ───────────────────────

def silence(duration):
    return [0.0] * int(duration * SAMPLE_RATE)


def tone(duration, f0, f1=None, partials=((1.0, 1.0),), decay=6.0,
         attack=0.004):
    """Exponentially decaying tone with optional pitch glide and partials.

    partials: iterable of (frequency multiplier, amplitude).
    """
    n = int(duration * SAMPLE_RATE)
    f1 = f1 if f1 is not None else f0
    out = [0.0] * n
    for mult, amp in partials:
        phase = 0.0
        for i in range(n):
            t = i / n
            freq = (f0 + (f1 - f0) * t) * mult
            phase += 2 * math.pi * freq / SAMPLE_RATE
            env = math.exp(-decay * t)
            if i < attack * SAMPLE_RATE:
                env *= i / max(1, attack * SAMPLE_RATE)
            out[i] += amp * env * math.sin(phase)
    return out


def noise(duration, decay=8.0, lowpass=0.25, highpass=0.0, attack=0.002):
    """Filtered white noise burst. lowpass/highpass are one-pole coefficients
    in (0, 1]; smaller lowpass = darker, larger highpass = thinner."""
    n = int(duration * SAMPLE_RATE)
    out = [0.0] * n
    lp = 0.0
    prev = prev_lp = 0.0
    for i in range(n):
        t = i / n
        white = random.uniform(-1.0, 1.0)
        lp += lowpass * (white - lp)          # one-pole lowpass
        sample = lp
        if highpass > 0.0:                     # one-pole highpass
            hp = sample - prev_lp + (1.0 - highpass) * prev
            prev_lp, prev = sample, hp
            sample = hp
        env = math.exp(-decay * t)
        if i < attack * SAMPLE_RATE:
            env *= i / max(1, attack * SAMPLE_RATE)
        out[i] = sample * env
    return out


def mix(*layers):
    n = max(len(l) for l in layers)
    out = [0.0] * n
    for layer in layers:
        for i, s in enumerate(layer):
            out[i] += s
    return out


def seq(*parts):
    """Concatenate (sound, offset_seconds) pairs onto one timeline."""
    total = 0
    placed = []
    for sound, offset in parts:
        start = int(offset * SAMPLE_RATE)
        placed.append((sound, start))
        total = max(total, start + len(sound))
    out = [0.0] * total
    for sound, start in placed:
        for i, s in enumerate(sound):
            out[start + i] += s
    return out


def gain(sound, g):
    return [s * g for s in sound]


def echo(sound, delay=0.07, amount=0.28, repeats=2):
    """Add a short, quiet delay tail without requiring external DSP tools."""
    delay_samples = max(1, int(delay * SAMPLE_RATE))
    out = list(sound) + [0.0] * (delay_samples * repeats)
    for repeat in range(1, repeats + 1):
        scale = amount ** repeat
        offset = delay_samples * repeat
        for i, sample in enumerate(sound):
            out[i + offset] += sample * scale
    return out


def pad_tone(duration, frequency, partials=((1.0, 1.0), (2.0, 0.18)),
             attack=0.8, release=0.9, tremolo_hz=0.12):
    """Slow sustained tone for quiet music beds."""
    n = int(duration * SAMPLE_RATE)
    out = [0.0] * n
    attack_n = max(1, int(attack * SAMPLE_RATE))
    release_n = max(1, int(release * SAMPLE_RATE))
    phases = [0.0 for _ in partials]
    for i in range(n):
        env = min(1.0, i / attack_n, (n - 1 - i) / release_n)
        env = max(0.0, env)
        tremolo = 0.88 + 0.12 * math.sin(
            2 * math.pi * tremolo_hz * i / SAMPLE_RATE)
        for idx, (mult, amp) in enumerate(partials):
            phases[idx] += 2 * math.pi * frequency * mult / SAMPLE_RATE
            out[i] += amp * env * tremolo * math.sin(phases[idx])
    return out


def finalize(sound, peak=0.65):
    """Normalize to peak, soft-clip, and fade the last 10 ms."""
    m = max(1e-9, max(abs(s) for s in sound))
    scaled = [s / m * peak for s in sound]
    out = [math.tanh(1.5 * s) for s in scaled]
    fade = int(0.010 * SAMPLE_RATE)
    n = len(out)
    for i in range(min(fade, n)):
        out[n - 1 - i] *= i / fade
    return out


def finalize_loop(sound, peak=0.30):
    """Normalize a music loop and pin its final sample to its first."""
    m = max(1e-9, max(abs(s) for s in sound))
    out = [math.tanh(1.25 * (s / m * peak)) for s in sound]
    if out:
        out[-1] = out[0]
    return out


def write_wav(name, sound, channels=1):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    pcm = array.array('h', (
        int(max(-1.0, min(1.0, sample)) * 32767)
        for sample in sound
        for _channel in range(channels)
    ))
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    WAV_OUTPUTS.append(path)
    kb = os.path.getsize(path) / 1024
    print(f'  {name:<22} {len(sound) / SAMPLE_RATE * 1000:5.0f} ms  {kb:5.1f} KB')


def write_ogg_companions():
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        print('Skipping web OGG companions: ffmpeg not found.')
        return

    print('Writing web OGG companions...')
    for wav_path in WAV_OUTPUTS:
        ogg_path = os.path.splitext(wav_path)[0] + '.ogg'
        quality = '7' if os.path.basename(wav_path).startswith('music_') else '6'
        with wave.open(wav_path, 'rb') as wf:
            channels = wf.getnchannels()
        subprocess.run([
            ffmpeg,
            '-y',
            '-loglevel', 'error',
            '-i', wav_path,
            '-ar', str(SAMPLE_RATE),
            '-ac', str(channels),
            '-c:a', 'libvorbis',
            '-q:a', quality,
            ogg_path,
        ], check=True)
        name = os.path.basename(ogg_path)
        kb = os.path.getsize(ogg_path) / 1024
        print(f'  {name:<22} web        {kb:5.1f} KB')


def write_external_music_loop(track_name):
    """Derive a compact loop from an approved lossless music excerpt."""
    spec = EXTERNAL_MUSIC[track_name]
    source = os.path.join(SOURCE_DIR, spec['source'])
    ffmpeg = shutil.which('ffmpeg')
    if not os.path.exists(source):
        return False
    if not ffmpeg:
        print(f'{spec["source"]} found but ffmpeg is unavailable; '
              f'using procedural {track_name} music.')
        return False

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'music_{track_name}.wav')
    duration = spec['source_duration']
    crossfade = spec['crossfade']
    tail_start = duration - crossfade
    # The output starts after the source head and ends with a tail-to-head
    # crossfade. Its final instant meets the same source point as its first.
    filter_graph = (
        '[0:a]asplit=3[midin][tailin][headin];'
        f'[midin]atrim=start={crossfade}:end={tail_start},'
        'asetpts=PTS-STARTPTS[mid];'
        f'[tailin]atrim=start={tail_start}:end={duration},'
        'asetpts=PTS-STARTPTS,'
        f'afade=t=out:st=0:d={crossfade}:curve=tri[tail];'
        f'[headin]atrim=start=0:end={crossfade},asetpts=PTS-STARTPTS,'
        f'afade=t=in:st=0:d={crossfade}:curve=tri[head];'
        '[tail][head]amix=inputs=2:duration=first:'
        'dropout_transition=0:normalize=0[xfade];'
        f'[mid][xfade]concat=n=2:v=0:a=1,volume={spec["gain_db"]}dB,'
        'aresample=44100[out]'
    )
    subprocess.run([
        ffmpeg,
        '-y',
        '-loglevel', 'error',
        '-i', source,
        '-filter_complex', filter_graph,
        '-map', '[out]',
        '-c:a', 'pcm_s16le',
        '-ar', str(SAMPLE_RATE),
        '-ac', '2',
        '-metadata', f'title={spec["title"]} (Runtime Edit)',
        '-metadata', 'artist=Nepal Kings',
        '-metadata', f'comment=Suno Pro source id {spec["asset_id"]}',
        path,
    ], check=True)
    WAV_OUTPUTS.append(path)
    kb = os.path.getsize(path) / 1024
    with wave.open(path, 'rb') as wf:
        duration = wf.getnframes() / wf.getframerate()
    print(f'  {os.path.basename(path):<22} {duration * 1000:5.0f} ms  {kb:5.1f} KB')
    return True


def write_mixkit_effect(name, spec):
    """Create one compact runtime cue from ignored Mixkit masters."""
    ffmpeg = shutil.which('ffmpeg')
    sources = [os.path.join(MIXKIT_SOURCE_DIR, filename)
               for filename in spec['sources']]
    if not ffmpeg or not all(os.path.exists(path) for path in sources):
        return False

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f'{name}.wav')
    channels = int(spec.get('channels', 1))
    command = [ffmpeg, '-y', '-loglevel', 'error']
    for source in sources:
        command.extend(['-i', source])
    command.extend([
        '-filter_complex', spec['filter'],
        '-map', '[out]',
        '-c:a', 'pcm_s16le',
        '-ar', str(SAMPLE_RATE),
        '-ac', str(channels),
        '-metadata', f'title=Nepal Kings {name} runtime edit',
        '-metadata', 'artist=Mixkit / Nepal Kings edit',
        '-metadata', 'comment=Derived under the Mixkit Sound Effects Free License',
        path,
    ])
    subprocess.run(command, check=True)
    if path not in WAV_OUTPUTS:
        WAV_OUTPUTS.append(path)
    kb = os.path.getsize(path) / 1024
    with wave.open(path, 'rb') as wf:
        duration = wf.getnframes() / wf.getframerate()
    print(f'  {os.path.basename(path):<22} {duration * 1000:5.0f} ms  {kb:5.1f} KB')
    return True


def write_mixkit_effects():
    """Build licensed cues while retaining deterministic fallbacks."""
    for name, spec in MIXKIT_EFFECTS.items():
        if write_mixkit_effect(name, spec):
            continue
        fallback_name = spec.get('fallback')
        if fallback_name is None:
            continue
        fallback = os.path.join(OUT_DIR, fallback_name)
        path = os.path.join(OUT_DIR, f'{name}.wav')
        shutil.copyfile(fallback, path)
        if path not in WAV_OUTPUTS:
            WAV_OUTPUTS.append(path)
        print(f'  {os.path.basename(path):<22} fallback')


# ── Note helper ────────────────────────────────────────────────────

def note(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def pluck_pattern(notes, beat, total_beats, *, offset=0.0,
                  length=0.48, level=1.0, partials=None):
    """Place one decaying pluck per beat, cycling over ``notes``."""
    parts = []
    palette = partials or PLUCK
    for beat_index in range(total_beats):
        midi = notes[beat_index % len(notes)]
        if midi is None:
            continue
        parts.append((gain(tone(length, note(midi), decay=7.5,
                                partials=palette), level),
                      offset + beat_index * beat))
    return seq(*parts) if parts else []


def soft_drum_pattern(beat, total_beats, hits, *, level=1.0):
    parts = []
    for beat_index in hits:
        if beat_index >= total_beats:
            continue
        drum = mix(
            tone(0.22, 105, 62, decay=13,
                 partials=((1.0, 1.0), (1.5, 0.18))),
            gain(noise(0.08, decay=35, lowpass=0.09), 0.35),
        )
        parts.append((gain(drum, level), beat_index * beat))
    return seq(*parts) if parts else []


PLUCK = ((1.0, 1.0), (2.0, 0.35), (3.0, 0.12), (4.7, 0.05))
WOOD = ((1.0, 1.0), (2.76, 0.4), (5.4, 0.15))


# ── Recipes ────────────────────────────────────────────────────────

def build_all():
    WAV_OUTPUTS[:] = []
    random.seed(42)
    print(f'Writing SFX to {os.path.relpath(OUT_DIR)}/')

    # Soft fingertip tick for any UI button.
    write_wav('ui_click.wav', finalize(mix(
        tone(0.045, 1750, 1500, decay=60),
        gain(noise(0.030, decay=70, lowpass=0.6), 0.5),
    ), peak=0.40))
    write_wav('ui_click_2.wav', finalize(mix(
        tone(0.047, 1620, 1430, decay=58),
        gain(noise(0.032, decay=68, lowpass=0.55), 0.48),
    ), peak=0.39))
    write_wav('ui_click_3.wav', finalize(mix(
        tone(0.043, 1880, 1570, decay=64),
        gain(noise(0.027, decay=74, lowpass=0.62), 0.44),
    ), peak=0.38))

    # Slightly lower tick for back / cancel / close.
    write_wav('ui_back.wav', finalize(mix(
        tone(0.050, 950, 800, decay=55),
        gain(noise(0.030, decay=70, lowpass=0.5), 0.4),
    ), peak=0.35))

    # Felt slide for picking a card up.
    write_wav('card_slide.wav', finalize(
        noise(0.14, decay=14, lowpass=0.18, highpass=0.05), peak=0.35))
    write_wav('card_slide_2.wav', finalize(
        noise(0.13, decay=13, lowpass=0.15, highpass=0.04), peak=0.33))
    write_wav('card_slide_3.wav', finalize(
        noise(0.15, decay=15, lowpass=0.21, highpass=0.06), peak=0.32))

    # Soft thump + tap for putting a card down.
    write_wav('card_place.wav', finalize(mix(
        tone(0.09, 210, 150, decay=35, partials=WOOD),
        gain(noise(0.04, decay=50, lowpass=0.5), 0.5),
    ), peak=0.50))
    write_wav('card_place_2.wav', finalize(mix(
        tone(0.10, 235, 165, decay=32, partials=WOOD),
        gain(noise(0.035, decay=54, lowpass=0.46), 0.46),
    ), peak=0.48))

    # Small metallic ping for gold gained / purchases.
    write_wav('coin.wav', finalize(mix(
        tone(0.22, 2520, decay=16),
        gain(tone(0.22, 3780, decay=20), 0.55),
        gain(tone(0.10, 1900, decay=30), 0.3),
    ), peak=0.45))
    write_wav('coin_2.wav', finalize(mix(
        tone(0.21, 2730, decay=17),
        gain(tone(0.21, 4095, decay=22), 0.50),
        gain(tone(0.09, 2050, decay=32), 0.28),
    ), peak=0.43))

    # Paper riser + pop for opening a booster pack.
    write_wav('booster_open.wav', finalize(seq(
        (noise(0.28, decay=4, lowpass=0.10, highpass=0.04), 0.0),
        (tone(0.28, 280, 880, decay=4), 0.0),
        (mix(tone(0.06, 760, 620, decay=40, partials=WOOD),
             gain(noise(0.04, decay=55, lowpass=0.6), 0.7)), 0.27),
    ), peak=0.55))

    # Three staggered sparkle pings for the card reveal.
    write_wav('booster_reveal.wav', finalize(seq(
        (tone(0.18, note(88), decay=14, partials=PLUCK), 0.00),
        (gain(tone(0.18, note(92), decay=14, partials=PLUCK), 0.8), 0.07),
        (gain(tone(0.26, note(95), decay=12, partials=PLUCK), 0.7), 0.14),
    ), peak=0.45))

    # A wider, slower shimmer reserved for genuinely rare card moments.
    write_wav('rare_card_reveal.wav', finalize(echo(seq(
        (tone(0.28, note(84), decay=10, partials=PLUCK), 0.00),
        (gain(tone(0.34, note(91), decay=9, partials=PLUCK), 0.82), 0.10),
        (gain(tone(0.55, note(96), decay=7, partials=PLUCK), 0.68), 0.23),
    ), delay=0.085, amount=0.24, repeats=2), peak=0.46))

    # Reward/quest cues are related but distinct: reveal opens upward,
    # while claim resolves with a grounded final note.
    write_wav('reward_reveal.wav', finalize(seq(
        (tone(0.20, note(74), note(81), decay=8, partials=PLUCK), 0.00),
        (gain(tone(0.28, note(86), decay=9, partials=PLUCK), 0.82), 0.13),
    ), peak=0.43))
    write_wav('quest_claim.wav', finalize(seq(
        (tone(0.18, note(69), decay=10, partials=WOOD), 0.00),
        (gain(tone(0.34, note(76), decay=8, partials=PLUCK), 0.88), 0.10),
        (gain(tone(0.42, note(81), decay=7, partials=PLUCK), 0.64), 0.20),
    ), peak=0.46))

    # Ceremonial, compact success cue for crafting a Maharaja.
    write_wav('craft_success.wav', finalize(echo(seq(
        (tone(0.26, note(62), decay=9, partials=WOOD), 0.00),
        (tone(0.28, note(69), decay=8, partials=PLUCK), 0.10),
        (tone(0.55, note(74), decay=5, partials=PLUCK), 0.22),
        (gain(tone(0.50, note(78), decay=5, partials=PLUCK), 0.7), 0.22),
    ), delay=0.10, amount=0.20, repeats=2), peak=0.52))

    # Wooden knock for placing a figure on the field.
    write_wav('figure_place.wav', finalize(mix(
        tone(0.12, 320, 240, decay=28, partials=WOOD),
        gain(noise(0.03, decay=60, lowpass=0.55), 0.6),
    ), peak=0.55))

    write_wav('land_select.wav', finalize(mix(
        tone(0.13, 410, 335, decay=24, partials=WOOD),
        gain(tone(0.18, note(67), decay=15, partials=PLUCK), 0.28),
    ), peak=0.43))

    write_wav('map_gain.wav', finalize(seq(
        (tone(0.20, note(62), decay=10, partials=WOOD), 0.00),
        (gain(tone(0.32, note(69), decay=8, partials=PLUCK), 0.8), 0.12),
    ), peak=0.44))

    write_wav('defence_set.wav', finalize(seq(
        (mix(tone(0.15, 185, 135, decay=20, partials=WOOD),
             gain(noise(0.04, decay=48, lowpass=0.42), 0.4)), 0.00),
        (gain(tone(0.30, note(62), decay=9, partials=PLUCK), 0.52), 0.10),
    ), peak=0.52))

    # Spell cues share an airy body but move in opposite pitch directions.
    write_wav('spell_cast.wav', finalize(echo(mix(
        tone(0.42, note(67), note(86), decay=5, partials=PLUCK),
        gain(noise(0.32, decay=7, lowpass=0.11, highpass=0.03), 0.36),
    ), delay=0.075, amount=0.25, repeats=2), peak=0.46), channels=2)
    write_wav('counter_spell.wav', finalize(echo(seq(
        (mix(tone(0.22, note(86), note(74), decay=8, partials=PLUCK),
             gain(noise(0.16, decay=12, lowpass=0.14), 0.28)), 0.00),
        (gain(tone(0.32, note(79), decay=8, partials=WOOD), 0.72), 0.12),
    ), delay=0.065, amount=0.22, repeats=2), peak=0.47), channels=2)
    write_wav('attack_launch.wav', finalize(seq(
        (tone(0.30, 95, 62, decay=9,
              partials=((1.0, 1.0), (1.5, 0.22))), 0.00),
        (gain(noise(0.24, decay=8, lowpass=0.10), 0.45), 0.00),
        (gain(tone(0.25, note(62), note(69), decay=8,
                   partials=WOOD), 0.48), 0.16),
    ), peak=0.60))

    # Low drum + breath of noise when a battle begins.
    write_wav('battle_start.wav', finalize(mix(
        tone(0.45, 130, 70, decay=9, partials=((1.0, 1.0), (1.5, 0.3))),
        gain(noise(0.35, decay=9, lowpass=0.12), 0.5),
    ), peak=0.65))

    write_wav('round_win.wav', finalize(seq(
        (tone(0.16, note(72), decay=11, partials=WOOD), 0.00),
        (gain(tone(0.28, note(79), decay=9, partials=PLUCK), 0.75), 0.08),
    ), peak=0.43))
    write_wav('round_loss.wav', finalize(seq(
        (tone(0.17, note(62), decay=11, partials=WOOD), 0.00),
        (gain(tone(0.27, note(57), decay=9, partials=WOOD), 0.75), 0.09),
    ), peak=0.40))
    write_wav('battle_total.wav', finalize(mix(
        tone(0.40, 92, 68, decay=8,
             partials=((1.0, 1.0), (2.0, 0.22))),
        gain(tone(0.40, note(62), note(74), decay=6,
                  partials=PLUCK), 0.42),
    ), peak=0.50))

    # Rising major arpeggio that resolves onto a held major chord — a
    # fuller, more rewarding "battle won".
    win_notes = [note(72), note(76), note(79), note(84)]
    win_chord = mix(
        tone(0.9, note(72), decay=3.2, partials=PLUCK),
        gain(tone(0.9, note(76), decay=3.2, partials=PLUCK), 0.8),
        gain(tone(0.9, note(79), decay=3.0, partials=PLUCK), 0.8),
        gain(tone(0.9, note(84), decay=2.8, partials=PLUCK), 0.7),
    )
    write_wav('battle_win.wav', finalize(seq(
        *(((gain(tone(0.26, f, decay=10, partials=PLUCK), 0.9 - 0.08 * i)),
           0.075 * i) for i, f in enumerate(win_notes)),
        (gain(win_chord, 0.9), 0.075 * len(win_notes)),
    ), peak=0.58))

    # Three falling notes over a low drone — a clearer, more melancholic
    # "battle lost".
    write_wav('battle_lose.wav', finalize(seq(
        (tone(0.34, note(59), decay=8, partials=PLUCK), 0.00),
        (gain(tone(0.40, note(55), decay=7, partials=PLUCK), 0.95), 0.16),
        (gain(tone(0.70, note(51), decay=5, partials=PLUCK), 0.9), 0.34),
        (gain(tone(0.9, note(39), decay=3.0,
                   partials=((1.0, 1.0), (2.0, 0.3))), 0.5), 0.30),
    ), peak=0.52))

    # Bigger triumphant fanfare for conquering a land: rising arpeggio,
    # a held octave-stacked major chord, and a soft swell.
    conquer_chord = mix(
        tone(1.1, note(79), decay=2.6, partials=PLUCK),
        gain(tone(1.1, note(83), decay=2.6, partials=PLUCK), 0.8),
        gain(tone(1.1, note(86), decay=2.4, partials=PLUCK), 0.8),
        gain(tone(1.1, note(91), decay=2.4), 0.4),
    )
    write_wav('conquer_win.wav', finalize(seq(
        (tone(0.30, note(67), decay=8, partials=PLUCK), 0.00),
        (tone(0.30, note(72), decay=8, partials=PLUCK), 0.09),
        (tone(0.34, note(76), decay=7, partials=PLUCK), 0.18),
        (tone(0.34, note(79), decay=7, partials=PLUCK), 0.27),
        (gain(conquer_chord, 0.95), 0.37),
        (gain(noise(0.6, decay=5, lowpass=0.09), 0.22), 0.34),
    ), peak=0.62))

    # Gentle two-note "it's your turn" notify.
    write_wav('your_turn.wav', finalize(seq(
        (tone(0.16, note(79), decay=12, partials=PLUCK), 0.00),
        (gain(tone(0.30, note(84), decay=10, partials=PLUCK), 0.9), 0.12),
    ), peak=0.45))

    # Muted low buzz for invalid actions.
    write_wav('error.wav', finalize(mix(
        tone(0.13, 160, 140, decay=18, partials=((1.0, 1.0), (2.0, 0.5),
                                                 (3.0, 0.25))),
        gain(noise(0.05, decay=40, lowpass=0.3), 0.2),
    ), peak=0.40))

    # Low felt-drum riser for the round-reveal HOLD tension beat.
    write_wav('reveal_hold.wav', finalize(mix(
        tone(0.30, 110, 185, decay=5, partials=((1.0, 1.0), (2.0, 0.25))),
        gain(noise(0.30, decay=6, lowpass=0.10), 0.35),
    ), peak=0.40))

    # Tiny wooden tick for the round-diff tally count-up.
    write_wav('tally_tick.wav', finalize(mix(
        tone(0.030, 1150, 1000, decay=80, partials=WOOD),
        gain(noise(0.02, decay=90, lowpass=0.5), 0.35),
    ), peak=0.32))

    write_wav('tally_tick_2.wav', finalize(mix(
        tone(0.032, 1250, 1060, decay=84, partials=WOOD),
        gain(noise(0.019, decay=94, lowpass=0.46), 0.32),
    ), peak=0.30))

    # Replace selected procedural cues and add authored variants when the
    # ignored Mixkit masters are available locally. Every entry has a stable
    # procedural fallback so a clean checkout can still rebuild all assets.
    write_mixkit_effects()

    # Background loops: 16 beats each. These are intentionally sparse and
    # quiet; SFX and player decisions remain the foreground.
    menu_beat = 0.75
    menu_beats = 16
    menu_duration = menu_beat * menu_beats
    if not write_external_music_loop('menu'):
        menu_music = mix(
            silence(menu_duration),
            gain(pad_tone(menu_duration, note(38), tremolo_hz=0.08), 0.46),
            gain(pad_tone(menu_duration, note(45), tremolo_hz=0.10), 0.24),
            pluck_pattern([62, None, 65, None, 69, None, 67, None],
                          menu_beat, menu_beats, length=0.58, level=0.62),
            gain(pluck_pattern([74, None, None, None, 72, None, None, None],
                               menu_beat, menu_beats, offset=0.18,
                               length=0.42, level=0.42), 0.72),
            gain(soft_drum_pattern(menu_beat, menu_beats, [0, 8]), 0.34),
        )
        write_wav('music_menu.wav', finalize_loop(menu_music, peak=0.28))

    kingdom_beat = 0.75
    kingdom_beats = 16
    kingdom_duration = kingdom_beat * kingdom_beats
    if not write_external_music_loop('kingdom'):
        kingdom_music = mix(
            silence(kingdom_duration),
            gain(pad_tone(kingdom_duration, note(36), tremolo_hz=0.07), 0.42),
            gain(pad_tone(kingdom_duration, note(43), tremolo_hz=0.09), 0.25),
            pluck_pattern([55, 62, None, 60, 58, None, 55, None],
                          kingdom_beat, kingdom_beats, length=0.54,
                          level=0.68, partials=WOOD),
            gain(pluck_pattern([67, None, 70, None, 69, None, 65, None],
                               kingdom_beat, kingdom_beats, offset=0.12,
                               length=0.45, level=0.44), 0.78),
            gain(soft_drum_pattern(kingdom_beat, kingdom_beats,
                                   [0, 4, 8, 12]), 0.46),
        )
        write_wav('music_kingdom.wav', finalize_loop(kingdom_music, peak=0.29))

    battle_beat = 0.625
    battle_beats = 16
    battle_duration = battle_beat * battle_beats
    if not write_external_music_loop('battle'):
        battle_music = mix(
            silence(battle_duration),
            gain(pad_tone(battle_duration, note(34), tremolo_hz=0.16), 0.38),
            pluck_pattern([50, None, 50, 53, 57, None, 55, 53],
                          battle_beat, battle_beats, length=0.38,
                          level=0.56, partials=WOOD),
            gain(pluck_pattern([62, 65, 69, 67], battle_beat * 2,
                               battle_beats // 2, offset=0.08,
                               length=0.52, level=0.48), 0.72),
            gain(soft_drum_pattern(battle_beat, battle_beats,
                                   [0, 2, 4, 6, 8, 10, 12, 14]), 0.62),
        )
        write_wav('music_battle.wav', finalize_loop(battle_music, peak=0.30))

    write_ogg_companions()


if __name__ == '__main__':
    build_all()
    print('Done.')
