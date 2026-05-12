# UNLP CoachAI

A web tool that watches a coaching session recording and produces a detailed professional evaluation — automatically, in seconds.

Upload a video or audio file of a coaching conversation, and the tool will transcribe it, analyse the coach's performance across all 8 EMCC competencies, and return a structured report with ratings, evidence, and concrete tips for improvement.

---

## What it does

1. **You upload a recording** — any common video or audio format works (.mp4, .mov, .mkv, .wav, .mp3, and more)
2. **The audio is extracted and transcribed** — the speech is converted to text automatically
3. **The transcript is validated** — the tool checks that it's actually a coaching conversation before proceeding
4. **An EMCC evaluation is generated** — an AI assessor reviews the transcript against the full EMCC Competence Framework V2 and produces a report

The whole process takes a few minutes depending on the length of the recording.

---

## The report includes

- **Session overview** — a plain-language summary of what happened in the session
- **EMCC competency ratings** — each of the 8 competencies rated from Foundation to Master Practitioner, with evidence pulled directly from the transcript
- **Tip for Improvement** — a concrete, actionable suggestion for each competency
- **Strengths** — what the coach did well
- **Development areas** — where there is room to grow
- **Final conclusion** — an overall professional judgment and EMCC level assessment

---

## EMCC competencies covered

1. Understanding Self
2. Commitment to Self-Development
3. Managing the Contract
4. Building the Relationship
5. Enabling Insight and Learning
6. Outcome and Action Orientation
7. Use of Models and Techniques
8. Evaluation

---

## A few things to know

- Sessions should be in **Dutch** — the report is always produced in English
- The recording should be at least **5 minutes** of actual coaching conversation
- Files up to **5GB** are supported
- Long recordings are automatically split and processed in segments
- If the primary AI service is busy, the tool silently switches to a backup provider — you won't notice the difference

---

## Running it locally

You need Python 3.11+ and ffmpeg installed on your machine.

**1. Clone the repository**
```
git clone https://github.com/drankintimofei-prog/UNLP_tech.git
cd UNLP_tech
```

**2. Install Python dependencies**
```
pip install -r requirements.txt
```

**3. Create a `.env` file** in the project folder with your API keys:
```
GROQ_API_KEY=your_groq_key_here
OPENAI_API_KEY=your_openai_key_here
MODE=production
```

**4. Start the server**
```
uvicorn backend:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in your browser.

---

## API keys you need

| Key | Where to get it | Used for |
|-----|----------------|---------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Transcription and evaluation (primary) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Fallback when Groq rate limits are hit |

---

## Tech stack

- **Backend** — Python, FastAPI, uvicorn
- **Transcription** — Groq Whisper / OpenAI Whisper
- **Evaluation** — Groq Llama 3.3 70B / OpenAI GPT-4o Mini
- **Audio processing** — ffmpeg
- **Frontend** — plain HTML, CSS, JavaScript (no framework)
- **Hosting** — Railway
