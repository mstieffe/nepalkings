# Audio Generation

Nepal Kings ships with a reproducible audio pipeline. Effects and fallback
music are synthesized by `scripts/assets/generate_sfx.py`; approved external
masters live under `scripts/assets/audio_sources/` and are converted into
compact runtime assets by the same script.

## Rebuild the shipped audio

Run from the repository root:

```bash
.venv/bin/python scripts/assets/generate_sfx.py
```

The script writes 22.05 kHz WAV runtime masters to `nepal_kings/sound/` and
uses FFmpeg to create matching OGG files for the browser client. Effects are
mono; approved music may remain stereo. Every filename in `utils/sound.py` and
`utils/music.py` must have both formats before release.

The active menu, kingdom, and battle themes are lossless excerpts from approved
Suno Pro masters. The script builds 60-second menu and kingdom loops plus a
45-second battle loop, each with a 6-second crossfade and background-safe gain.
Full exports are kept locally and Git-ignored; no source masters live in
`nepal_kings/sound/`, so they are not packaged for mobile.

Procedural loops remain as restrained fallbacks and are used automatically if
an approved source or FFmpeg is unavailable.

Selected spell, card, booster, construction, reward, progression, and battle
cues are derived from locally retained Mixkit WAV masters under
`scripts/assets/audio_sources/mixkit/`. The masters are Git-ignored; compact
mono runtime edits and their OGG companions are generated alongside the rest
of the sound set. If those masters are unavailable, the generator preserves
the procedural baseline and creates every required variant from its declared
fallback, so a clean checkout still produces a complete runtime sound set.

## Music generator prompts

Generate each loop as an instrumental stem with no vocals, spoken words,
recognizable melody, or copyrighted-style imitation. Ask for a clean loop and
leave headroom; normalize and convert only after the composition is approved.

### Menu theme

> Create a seamless 24-second instrumental loop for the main menu of a quiet medieval Himalayan strategy card game. Warm wooden plucks, a soft low drone, sparse hand-drum pulse, and very light bell-metal accents. Thoughtful, welcoming, mysterious, and premium; 80 BPM, D minor with gentle modal color. Minimal arrangement with plenty of silence for UI sounds. No vocals, choir, cinematic trailer hits, orchestral swells, or recognizable melody. Do not imitate sacred or specific traditional music. End must connect perfectly to the beginning.

### Kingdom theme

> Create a seamless 24-second instrumental exploration loop for viewing and managing a mountain kingdom map. Earthy wooden percussion, low frame drum, airy sustained texture, and restrained plucked-string motifs. Calm authority, distance, altitude, and careful planning; 80 BPM, modal minor. Subtle forward motion but never heroic or busy. No vocals, choir, modern synth lead, giant impacts, or recognizable melody. Do not imitate sacred or specific traditional music. Leave space for clicks, map movement, and notification sounds; perfect loop boundary.

### Battle theme

> Create a seamless 24-second instrumental tactical-battle loop for a three-round strategy card duel. Low drum heartbeat, dry wooden attacks, tense muted plucks, and a dark airy bed. Controlled pressure rather than action-movie intensity; 96 BPM, minor/modal harmony. Keep the midrange sparse so card reveals and result stingers remain clear. No vocals, choir, brass fanfare, EDM elements, giant impacts, or recognizable melody. Do not imitate sacred or specific traditional music. Perfectly loopable start and end.

## Sound-effect generator prompt

Generate one dry effect at a time, then audition it in context:

> Create a single short game sound effect for `[EVENT]` in a tactile medieval strategy card game. Palette: soft felt, dry wood, restrained bell metal, paper movement, and low frame drum. Duration `[DURATION]`; immediate readable transient, short controlled tail, no voice, no ambience bed, no cinematic boom, no arcade bleeps, no clipping, and no copyrighted source material. The effect must remain clear on a phone speaker and leave headroom for simultaneous UI sounds. Export isolated with silence trimmed.

Use 30-80 ms for taps, 100-250 ms for card/placement sounds, 350-650 ms for
spells and rewards, and up to 1.2 seconds for major result stingers. Create two
or three closely related variants for frequently repeated actions.

## Replacing a generated asset

Keep the existing filename and loudness role. Convert an approved source with
FFmpeg, then compare it against neighboring events in-game:

```bash
ffmpeg -i approved_source.wav -ar 22050 -ac 1 -c:a pcm_s16le nepal_kings/sound/event.wav
ffmpeg -i nepal_kings/sound/event.wav -ar 22050 -ac 1 -c:a libvorbis -q:a 4 nepal_kings/sound/event.ogg
```

Do not rerun the procedural generator after a manual replacement unless its
recipe has also been changed, because the generator is the current source of
truth.

## Licensing record

For commissioned, downloaded, or AI-generated replacements, record the source,
creator or model, generation date, prompt/job ID, license version, attribution
requirement, commercial-use permission, modification permission, and proof
that standalone redistribution and game distribution are allowed. Avoid
non-commercial licenses, unclear custom terms, Content ID restrictions, and
assets whose provenance cannot be documented. Add required credits to
`docs/legal/ATTRIBUTION.md` before shipping.
