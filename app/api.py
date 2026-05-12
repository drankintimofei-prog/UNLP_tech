import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.services.audio import extract_audio
from app.services.evaluation import evaluate_transcript, validate_coaching_transcript
from app.services.transcription import transcribe_audio

BASE_DIR = Path(__file__).parent.parent

app = FastAPI(title="UNLP CoachAI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def format_sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/", include_in_schema=False)
def serve_frontend():
    return FileResponse(BASE_DIR / "index.html", media_type="text/html")


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "UNLP CoachAI", "version": "1.0.0"}


@app.post("/api/v1/process")
async def process_video(file: UploadFile = File(...)):
    async def event_stream():
        try:
            yield format_sse({"stage": "uploading", "progress": 15, "message": "File received..."})

            with tempfile.TemporaryDirectory() as tmpdir:
                upload_path = Path(tmpdir) / "upload_video"
                audio_path = Path(tmpdir) / "extracted_audio.mp3"

                content = await file.read()
                upload_path.write_bytes(content)

                yield format_sse({"stage": "extracting", "progress": 35, "message": "Extracting audio..."})
                await extract_audio(upload_path, audio_path)
                print(f"[DEBUG] Compressed audio file size: {audio_path.stat().st_size} bytes")

                yield format_sse({"stage": "transcribing", "progress": 60, "message": "Transcribing session..."})
                transcript = await transcribe_audio(audio_path)

                if len(transcript.split()) < 1000:
                    yield format_sse({
                        "stage": "error",
                        "message": "The audio contains too little speech. Please upload a coaching session of at least 5 minutes.",
                    })
                    return

                yield format_sse({"stage": "validating", "progress": 70, "message": "Validating content..."})
                validation_result = await validate_coaching_transcript(transcript)
                if not validation_result.get("is_coaching", False):
                    reason = validation_result.get("reason", "The content does not appear to be a coaching conversation.")
                    yield format_sse({
                        "stage": "error",
                        "message": f"This does not appear to be a coaching session: {reason}. Please upload a video of a real coaching conversation between a coach and client.",
                    })
                    return

                yield format_sse({"stage": "evaluating", "progress": 85, "message": "Generating EMCC evaluation..."})
                report_text = await evaluate_transcript(transcript)

                try:
                    report_data = json.loads(report_text.strip())
                except json.JSONDecodeError:
                    raise RuntimeError("Unable to parse JSON from model output")

                yield format_sse({"stage": "complete", "progress": 100, "report": report_data})

        except Exception as e:
            import traceback
            error_details = f"{str(e)}\n\n{traceback.format_exc()}"
            yield format_sse({"stage": "error", "message": f"Error: {str(e)}", "details": error_details})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
