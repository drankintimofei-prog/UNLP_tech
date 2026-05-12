# Architecture

## Overview

Single-service web app. FastAPI serves both the frontend (static HTML) and the API. Everything runs in one process — no separate frontend server, no database, no persistent storage.

---

## Project Structure

```
├── app/
│   ├── config.py           — environment variables, API client imports
│   ├── prompts.py          — EMCC system prompts for the LLM
│   ├── api.py              — FastAPI app, routes, SSE streaming
│   └── services/
│       ├── audio.py        — ffmpeg wrappers (extract, split, sample)
│       ├── transcription.py — Groq/OpenAI Whisper transcription
│       └── evaluation.py   — LLM evaluation and coaching validation
├── main.py                 — entry point (runs uvicorn)
├── index.html              — entire frontend (single file, no framework)
├── Dockerfile              — installs ffmpeg + Python deps, starts uvicorn
└── Procfile                — Railway start command
```

---

## Request Lifecycle

When a user uploads a video, this is what happens end to end:

```
Browser → POST /api/v1/process
         ↓
    [api.py] write file to /tmp
         ↓
    [audio.py] ffmpeg: extract + compress audio to 16kbps mono MP3
         ↓
    [transcription.py] send MP3 to Groq Whisper → text
         ↓
    [api.py] word count check (< 1000 words → reject)
         ↓
    [evaluation.py] validate_coaching_transcript → Groq LLM confirms coaching conversation
         ↓
    [evaluation.py] evaluate_transcript → Groq LLM produces EMCC JSON report
         ↓
    [api.py] parse JSON, stream "complete" event with report
         ↓
Browser renders report
```

Each step yields an SSE event to the browser so the user sees live progress. The temp directory (video + audio) is deleted automatically when the request finishes.

---

## Live Progress (SSE)

The `/api/v1/process` endpoint returns a `StreamingResponse` with `media_type="text/event-stream"`. The async generator inside it `yield`s events at each stage:

```python
yield format_sse({"stage": "uploading", "progress": 15, "message": "..."})
yield format_sse({"stage": "transcribing", "progress": 60, "message": "..."})
yield format_sse({"stage": "complete", "progress": 100, "report": {...}})
```

The browser reads these with `response.body.getReader()` and updates the UI on each event. No websockets, no polling.

---

## AI Services

### Transcription
- **Primary:** Groq hosting `whisper-large-v3`
- **Fallback:** OpenAI hosting `whisper-1` (triggers on Groq rate limit)

Files over 10MB are split into 10-minute segments and transcribed sequentially. Very long files (over `SAMPLE_TRANSCRIPTION_THRESHOLD_SECONDS`) use OpenAI's sampled approach — beginning, middle, and end — rather than the full audio.

### Evaluation
- **Primary:** Groq `llama-3.3-70b-versatile`
- **Fallback:** OpenAI `gpt-4o-mini` (triggers on Groq rate limit)

`response_format={"type": "json_object"}` is set on every LLM call to enforce JSON output. The system prompt in `prompts.py` also explicitly instructs the model to return only JSON.

Long transcripts are trimmed to ~10,000 characters by sampling the beginning, middle, and end before being sent to the LLM.

---

## Configuration

All settings live in `app/config.py` and are read from environment variables. Key ones:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | required | Groq transcription + evaluation |
| `OPENAI_API_KEY` | optional | Fallback for both transcription and evaluation |
| `MODE` | `production` | `production` uses full EMCC prompt; anything else uses compact prompt |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3` | Groq Whisper model |
| `MAX_TRANSCRIPTION_DURATION_SECONDS` | `7200` | Rejects audio longer than this |

---

## Guardrails

Three checks prevent garbage input from reaching the evaluator:

1. **File type** — validated client-side in `index.html` by extension and MIME type before upload
2. **Word count** — transcript must have at least 1000 words, otherwise rejected with a user-facing message
3. **Coaching validation** — first 3000 characters of the transcript are sent to the LLM with a strict prompt asking whether this is a real coaching conversation. Non-coaching content is rejected with the model's reason

---

## Frontend

`index.html` is a single self-contained file — no framework, no build step. It uses:
- Vanilla JS for all interactivity
- CSS custom properties for the design system (colours, spacing)
- `fetch` + `ReadableStream` for SSE consumption
- `localStorage` for basic job state persistence across page refreshes

The file is served directly by FastAPI via `FileResponse`. There is no separate frontend server.
