# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""Generate the game's SFX set as small mono WAV files plus web OGG companions.

Every sound in nepal_kings/sound/ is synthesized by this script, so the
whole set is license-clean, reproducible, and tweakable in one place.
Re-run after changing any recipe:

    python scripts/assets/generate_sfx.py

Design notes: 22.05 kHz mono 16-bit keeps each WAV in the 10–60 KB range
(~0.5 MB total). The OGG companions are used by the pygbag web build because
browsers are more reliable with OGG than SDL WAV decoding. The palette aims
for soft, felt-and-wood UI sounds with a few short musical stingers —
minimal, not arcade-y.
"""

import array
import math
import os
import random
import shutil
import subprocess
import wave

SAMPLE_RATE = 22050
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '..', '..', 'nepal_kings', 'sound')
WAV_OUTPUTS = []

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


def write_wav(name, sound):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    pcm = array.array('h', (int(max(-1.0, min(1.0, s)) * 32767) for s in sound))
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
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
        subprocess.run([
            ffmpeg,
            '-y',
            '-loglevel', 'error',
            '-i', wav_path,
            '-ar', str(SAMPLE_RATE),
            '-ac', '1',
            '-c:a', 'libvorbis',
            '-q:a', '4',
            ogg_path,
        ], check=True)
        name = os.path.basename(ogg_path)
        kb = os.path.getsize(ogg_path) / 1024
        print(f'  {name:<22} web        {kb:5.1f} KB')


# ── Note helper ────────────────────────────────────────────────────

def note(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


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

    # Slightly lower tick for back / cancel / close.
    write_wav('ui_back.wav', finalize(mix(
        tone(0.050, 950, 800, decay=55),
        gain(noise(0.030, decay=70, lowpass=0.5), 0.4),
    ), peak=0.35))

    # Felt slide for picking a card up.
    write_wav('card_slide.wav', finalize(
        noise(0.14, decay=14, lowpass=0.18, highpass=0.05), peak=0.35))

    # Soft thump + tap for putting a card down.
    write_wav('card_place.wav', finalize(mix(
        tone(0.09, 210, 150, decay=35, partials=WOOD),
        gain(noise(0.04, decay=50, lowpass=0.5), 0.5),
    ), peak=0.50))

    # Small metallic ping for gold gained / purchases.
    write_wav('coin.wav', finalize(mix(
        tone(0.22, 2520, decay=16),
        gain(tone(0.22, 3780, decay=20), 0.55),
        gain(tone(0.10, 1900, decay=30), 0.3),
    ), peak=0.45))

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

    # Wooden knock for placing a figure on the field.
    write_wav('figure_place.wav', finalize(mix(
        tone(0.12, 320, 240, decay=28, partials=WOOD),
        gain(noise(0.03, decay=60, lowpass=0.55), 0.6),
    ), peak=0.55))

    # Low drum + breath of noise when a battle begins.
    write_wav('battle_start.wav', finalize(mix(
        tone(0.45, 130, 70, decay=9, partials=((1.0, 1.0), (1.5, 0.3))),
        gain(noise(0.35, decay=9, lowpass=0.12), 0.5),
    ), peak=0.65))

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

    write_ogg_companions()


if __name__ == '__main__':
    build_all()
    print('Done.')
