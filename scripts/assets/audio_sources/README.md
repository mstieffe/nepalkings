# Audio Sources

Source masters in this directory are not copied into the game or web bundle.
`scripts/assets/generate_sfx.py` creates compact runtime assets from them.

## Active Suno Pro themes

All three tracks were generated on 2026-07-13 while the creator's Suno account
had an active Pro subscription. Commercial game use was confirmed by the
creator on 2026-07-13.

| Use | Production source | Full-master excerpt | Suno asset ID | Runtime |
| --- | --- | --- | --- | --- |
| Menu | `Menu Theme Source.flac` | 12-78s | `f3f9f88c-d579-4141-84ea-a9dc67c0aa08` | 60s |
| Kingdom | `Kingdom Theme Source.flac` | 24-90s | `a0e07e8c-1d6d-4680-8d00-ff3a352623c4` | 60s |
| Battle | `Battle Theme Source.flac` | 0-51s | `db9a709b-4806-4f4f-a04c-adb5340fd7ae` | 45s |

Each runtime edit uses a 6-second tail-to-head crossfade, -8 dB gain, and
44.1 kHz stereo output. Web OGG companions use Vorbis quality 7; this keeps
the generated files compact without discarding the upper half of the audible
band. The generated files are
`nepal_kings/sound/music_<use>.wav` and `.ogg`.

The original 48 kHz WAV exports are retained locally as `Menu Suno Master.wav`,
`Kingdom Suno Master.wav`, and `Battle Suno Master.wav`. They are Git-ignored
and excluded from every game bundle.

## Archived alternate

`Kora Gate Menu Source.flac` is the lossless production excerpt for the former
Kora Gate menu edit (Suno asset ID
`b368419a-9c46-4221-be7c-5c77ced1c396`). Its full 5:43 WAV and MP3 exports are
also retained locally and Git-ignored. It was generated under the same active
Suno Pro account and is cleared for future commercial game use.
