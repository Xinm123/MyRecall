# MyRecall-v3 Reference Materials

This directory contains reference materials, external docs links, and analysis documents for MyRecall-v3 development.

---

## External Project References

### 1. screenpipe
- **Location**: `/Users/pyw/new/screenpipe/`
- **Documentation**: https://github.com/mediar-ai/screenpipe
- **Key Modules to Reference**:
  - Chat: `/Users/pyw/new/screenpipe/apps/screenpipe-app-tauri/app/chat/page.tsx`
  - Audio Pipeline: `/Users/pyw/new/screenpipe/crates/screenpipe-audio/src/core/run_record_and_transcribe.rs`
  - Database Schema: `/Users/pyw/new/screenpipe/crates/screenpipe-db/src/migrations/20240703111257_screenpipe.sql`
  - LLM Integration: `/Users/pyw/new/screenpipe/crates/screenpipe-core/src/llm.rs`

### 2. openclaw memory
- **Documentation**: https://docs.openclaw.ai/concepts/memory
- **Focus**: Memory architecture patterns, long-term context management

---

## Internal Analysis Documents

### MyRecall v2 Analysis
- **Location**: `/Users/pyw/new/MyRecall/v2/MyRecall_V2_Analysis.md`
- **Description**: Comprehensive bilingual (ZH/EN) analysis of existing MyRecall pipeline
- **Key Sections**:
  - Producer-Consumer architecture pattern
  - Three-tier storage (SQLite + FTS + LanceDB)
  - Hybrid search (vector + FTS + reranker)

### MyRecall vs screenpipe Comparison
- **Location**: `/Users/pyw/new/MyRecall/v2/MyRecall-vs-screenpipe.md`
- **Description**: Feature-by-feature comparison of the two systems

### Encryption Guide
- **Location**: `/Users/pyw/new/MyRecall/v2/encryption.md`
- **Description**: User guide for encrypted volume storage (BitLocker/LUKS/FileVault)

### Hardware Compatibility
- **Location**: `/Users/pyw/new/MyRecall/v2/hardware.md`
- **Description**: Hardware requirements and compatibility notes

---

## Technical References

### 1. FFmpeg Documentation
- **Official Docs**: https://ffmpeg.org/documentation.html
- **Key Commands for MyRecall**:
  - Desktop capture: `ffmpeg -f gdigrab -framerate 1 -i desktop -t 300 -c:v libx264 -crf 28 output.mp4`
  - Frame extraction: `ffmpeg -i video.mp4 -vf fps=1/5 -q:v 2 frame_%04d.jpg`

### 2. Whisper
- **faster-whisper**: https://github.com/guillaumekln/faster-whisper
- **openai-whisper**: https://github.com/openai/whisper
- **Model Cards**: https://huggingface.co/models?search=whisper

### 3. Speaker Diarization
- **pyannote-audio**: https://github.com/pyannote/pyannote-audio
- **Model**: https://huggingface.co/pyannote/speaker-diarization-3.1

### 4. LanceDB
- **Documentation**: https://lancedb.github.io/lancedb/
- **Python API**: https://lancedb.github.io/lancedb/python/

### 5. SQLite FTS5
- **Documentation**: https://www.sqlite.org/fts5.html
- **Best Practices**: https://www.sqlite.org/fts5.html#full_text_query_syntax

---

## Design Patterns

### 1. Producer-Consumer Pattern
- **Reference**: MyRecall existing implementation (`openrecall/client/recorder.py` + `openrecall/client/consumer.py`)
- **Pattern**: Decouples capture from upload, provides offline resilience

### 2. Hierarchical Timeline
- **Reference**: screenpipe's `video_chunks` → `frames` → `ocr_text` structure
- **Pattern**: Better temporal queries and chunk management than flat timestamps

### 3. Tool-Calling for Chat
- **Reference**: OpenAI function calling docs (https://platform.openai.com/docs/guides/function-calling)
- **Pattern**: LLM decides when to query historical data, structured tool schema

### 4. Gradual Degradation
- **Reference**: FFmpeg watchdog, fallback to screenshot mode (Phase 1 plan)
- **Pattern**: System remains functional even when components fail

---

## API References

### 1. OpenAI API
- **Chat Completions**: https://platform.openai.com/docs/api-reference/chat
- **Function Calling**: https://platform.openai.com/docs/guides/function-calling
- **Models**: https://platform.openai.com/docs/models

### 2. Anthropic Claude API
- **Documentation**: https://docs.anthropic.com/claude/reference/
- **Tool Use**: https://docs.anthropic.com/claude/docs/tool-use

### 3. Ollama (Local LLM)
- **Documentation**: https://github.com/ollama/ollama
- **Python Library**: https://github.com/ollama/ollama-python

---

## Benchmarks & Datasets

### 1. OCR Accuracy
- **Tesseract Benchmark**: https://github.com/tesseract-ocr/tesseract/wiki/Data-Files
- **MyRecall Test Set**: TBD (create 100-frame curated dataset in Phase 1)

### 2. Audio Transcription (WER)
- **LibriSpeech**: https://www.openslr.org/12 (clean audio baseline)
- **AMI Corpus**: https://groups.inf.ed.ac.uk/ami/corpus/ (meeting recordings)

### 3. Speaker Diarization (DER)
- **AMI Corpus**: https://groups.inf.ed.ac.uk/ami/corpus/
- **VoxConverse**: https://www.robots.ox.ac.uk/~vgg/data/voxconverse/

### 4. Search Relevance
- **MyRecall Test Queries**: TBD (create 50-query test set with relevance judgments in Phase 3)

---

## Tools & Libraries

### Python Package Index
- **Core Dependencies**: See `/Users/pyw/new/MyRecall/requirements.txt`
- **New Dependencies for v3**:
  - `sounddevice` (audio capture)
  - `py-webrtcvad` (voice activity detection)
  - `faster-whisper` (transcription)
  - `pyannote-audio` (speaker diarization, optional Phase 2.1)
  - `dateparser` (natural language time parsing, Phase 4)

### Development Tools
- **pytest**: Testing framework
- **pytest-benchmark**: Performance benchmarking
- **black**: Code formatting
- **mypy**: Type checking
- **ruff**: Linting

---

## Deployment References

### 1. Docker
- **Dockerfile Reference**: https://docs.docker.com/engine/reference/builder/
- **Docker Compose**: https://docs.docker.com/compose/

### 2. Debian Server Setup
- **Debian Documentation**: https://www.debian.org/doc/
- **Systemd Service**: https://www.freedesktop.org/software/systemd/man/systemd.service.html

### 3. SSL/TLS (Let's Encrypt)
- **Certbot**: https://certbot.eff.org/
- **Let's Encrypt**: https://letsencrypt.org/

---

## Related Work (Inspirations)

### 1. Windows Recall
- **Blog Post**: https://support.microsoft.com/en-us/windows/retrace-your-steps-with-recall-aa03f8a0-a78b-4b3e-b0a1-2eb8ac48701c
- **Privacy Concerns**: https://www.wired.com/story/windows-recall-ai-privacy-security/

### 2. Rewind.ai
- **Website**: https://www.rewind.ai/
- **Approach**: macOS-only, proprietary, cloud-optional

### 3. Microsoft Viva Insights
- **Documentation**: https://support.microsoft.com/en-us/topic/viva-insights-introduction-9d2e7a29-be2f-4031-b318-43f1d8b0f875
- **Focus**: Work analytics, meeting summaries

---

## Standards & Specifications

### 1. ISO 8601 (Date/Time Format)
- **Specification**: https://www.iso.org/iso-8601-date-and-time-format.html
- **Usage in MyRecall**: All `timestamp` fields, API time range parameters

### 2. OpenAPI 3.0 (API Spec)
- **Specification**: https://spec.openapis.org/oas/v3.0.3
- **Usage**: Document MyRecall API endpoints (future enhancement)

### 3. WCAG 2.1 (Accessibility)
- **Specification**: https://www.w3.org/WAI/WCAG21/quickref/
- **Usage**: Web UI accessibility considerations (future enhancement)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-06 | Initial reference materials index |

---

## Contributing

To add a new reference:
1. Add link/location to appropriate section above
2. Briefly describe how it relates to MyRecall-v3 development
3. Update version history
