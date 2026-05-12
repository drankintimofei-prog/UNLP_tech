import json
import tempfile
from pathlib import Path

from app.config import (
    GROQ_API_KEY,
    OPENAI_API_KEY,
    TRANSCRIPTION_MODEL,
    MAX_TRANSCRIPTION_DURATION_SECONDS,
    ENABLE_OPENAI_TRANSCRIPTION_FALLBACK,
    SAMPLE_TRANSCRIPTION_THRESHOLD_SECONDS,
    Groq,
    openai,
)
from app.services.audio import get_audio_duration, sample_audio_segments, split_audio_segments


def _parse_transcription_response(response) -> str:
    if isinstance(response, dict):
        if response.get("error"):
            error = response["error"]
            raise RuntimeError(
                f"Groq transcription error: {error.get('message') if isinstance(error, dict) else error}"
            )
        return response.get("text") or response.get("transcript") or json.dumps(response)
    if hasattr(response, "text"):
        return response.text
    if hasattr(response, "content"):
        return response.content
    raise RuntimeError("Unexpected transcription response format")


async def transcribe_audio(audio_path: Path) -> str:
    file_size = audio_path.stat().st_size
    duration_seconds = await get_audio_duration(audio_path)
    print(f"[DEBUG] Audio file size: {file_size} bytes")
    print(f"[DEBUG] Audio duration: {duration_seconds:.1f} seconds")

    if duration_seconds > MAX_TRANSCRIPTION_DURATION_SECONDS:
        raise RuntimeError(
            f"Audio duration is {duration_seconds / 60:.1f} minutes, which likely exceeds your Groq transcription quota. "
            "Please upload a shorter coaching session or retry after your quota resets."
        )

    client = Groq(api_key=GROQ_API_KEY)

    if file_size > 10_000_000:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            segments = await split_audio_segments(audio_path, tmpdir_path, segment_seconds=600)
            print(f"[DEBUG] Split into {len(segments)} audio segments")
            transcripts = []
            for index, segment_path in enumerate(segments, start=1):
                segment_size = segment_path.stat().st_size
                print(f"[DEBUG] Transcribing segment {index}/{len(segments)} size: {segment_size} bytes")
                with open(segment_path, "rb") as audio_file:
                    try:
                        response = client.audio.transcriptions.create(
                            model=TRANSCRIPTION_MODEL, file=audio_file, language="nl",
                        )
                    except Exception as exc:
                        if any(kw in str(exc) for kw in ("rate_limit_exceeded", "Rate limit", "seconds of audio per hour")):
                            if ENABLE_OPENAI_TRANSCRIPTION_FALLBACK and openai and OPENAI_API_KEY:
                                print("[DEBUG] Groq rate limit hit, attempting OpenAI fallback for segment")
                                try:
                                    oa_client = openai.OpenAI(api_key=OPENAI_API_KEY)
                                    with open(segment_path, "rb") as oa_file:
                                        oa_response = oa_client.audio.transcriptions.create(
                                            model="whisper-1", file=oa_file, language="nl"
                                        )
                                    transcripts.append(oa_response.text.strip())
                                    continue
                                except Exception as openai_exc:
                                    print(f"[DEBUG] OpenAI fallback failed for segment: {openai_exc}")
                                    raise RuntimeError("Groq rate limit exceeded and OpenAI fallback failed.") from exc
                            raise RuntimeError("Groq transcription rate limit exceeded.") from exc
                        raise RuntimeError(str(exc)) from exc
                transcripts.append(_parse_transcription_response(response).strip())
            combined = "\n".join(transcripts)
            print(f"[DEBUG] Combined transcript size: {len(combined)} chars")
            return combined

    with open(audio_path, "rb") as audio_file:
        try:
            response = client.audio.transcriptions.create(
                model=TRANSCRIPTION_MODEL, file=audio_file, language="nl",
            )
        except Exception as exc:
            if any(kw in str(exc) for kw in ("rate_limit_exceeded", "Rate limit", "seconds of audio per hour")):
                if ENABLE_OPENAI_TRANSCRIPTION_FALLBACK and openai and OPENAI_API_KEY:
                    print("[DEBUG] Groq rate limit hit, attempting OpenAI fallback")
                    try:
                        return await transcribe_with_openai(audio_path)
                    except Exception as openai_exc:
                        print(f"[DEBUG] OpenAI fallback failed: {openai_exc}")
                        raise RuntimeError("Groq rate limit exceeded and OpenAI fallback failed.") from exc
                raise RuntimeError("Groq transcription rate limit exceeded.") from exc
            raise RuntimeError(str(exc)) from exc

    return _parse_transcription_response(response)


async def transcribe_with_openai(audio_path: Path) -> str:
    if openai is None or not OPENAI_API_KEY:
        raise RuntimeError("OpenAI transcription fallback is not available")

    oa_client = openai.OpenAI(api_key=OPENAI_API_KEY)
    duration_seconds = await get_audio_duration(audio_path)

    if duration_seconds > SAMPLE_TRANSCRIPTION_THRESHOLD_SECONDS:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            segments = await sample_audio_segments(audio_path, tmpdir_path, duration_seconds)
            transcripts = []
            for index, segment_path in enumerate(segments, start=1):
                print(f"[DEBUG] OpenAI fallback transcribing segment {index}/{len(segments)} size: {segment_path.stat().st_size} bytes")
                with open(segment_path, "rb") as audio_file:
                    response = oa_client.audio.transcriptions.create(
                        model="whisper-1", file=audio_file, language="nl"
                    )
                transcripts.append(response.text)
            return "\n".join(text.strip() for text in transcripts if text)

    with open(audio_path, "rb") as audio_file:
        response = oa_client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="nl"
        )
    return response.text
