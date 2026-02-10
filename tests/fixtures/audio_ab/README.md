# Audio A/B Benchmark Fixtures

This directory documents the expected layout for optional real-audio samples used by:

```bash
python -m openrecall.server.audio.ab_benchmark --dataset hybrid --real-samples-dir <dir>
```

## Layout

```text
audio_ab/
  manifest.json
  real_sample_1.wav
  real_sample_2.wav
```

## Manifest Schema

`manifest.json` should contain either:

1. an object with `samples` array, or
2. a raw array of sample objects.

Each sample object supports:

- `sample_id`: unique identifier string
- `path`: relative or absolute WAV file path
- `has_speech`: boolean ground-truth label

See `manifest.example.json` for a complete example.
