import subprocess
import tempfile
from pathlib import Path

from app.config import SAMPLE_TRANSCRIPTION_SEGMENT_SECONDS


async def extract_audio(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vn", "-ac", "1", "-ar", "8000",
        "-codec:a", "libmp3lame", "-b:a", "16k",
        str(output_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {process.stderr.strip()}")


async def get_audio_duration(audio_path: Path) -> float:
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {process.stderr.strip()}")
    try:
        return float(process.stdout.strip())
    except ValueError:
        raise RuntimeError("Unable to determine audio duration from extracted audio")


async def split_audio_segments(input_path: Path, output_dir: Path, segment_seconds: int = 600) -> list[Path]:
    segment_pattern = str(output_dir / "segment_%03d.mp3")
    command = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-f", "segment", "-segment_time", str(segment_seconds),
        "-c", "copy", segment_pattern,
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg segmenting failed: {process.stderr.strip()}")
    segments = sorted(output_dir.glob("segment_*.mp3"))
    if not segments:
        raise RuntimeError("Audio splitting produced no segments")
    return segments


async def sample_audio_segments(
    input_path: Path,
    output_dir: Path,
    duration_seconds: float,
    segment_seconds: int = SAMPLE_TRANSCRIPTION_SEGMENT_SECONDS,
) -> list[Path]:
    positions = [0.0]
    if duration_seconds > segment_seconds * 2:
        positions = [
            0.0,
            max((duration_seconds - segment_seconds) / 2, 0),
            max(duration_seconds - segment_seconds, 0),
        ]
    elif duration_seconds > segment_seconds:
        positions = [0.0, max(duration_seconds - segment_seconds, 0)]

    samples = []
    for index, start in enumerate(positions, start=1):
        output_path = output_dir / f"sample_{index:03d}.mp3"
        command = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(min(segment_seconds, duration_seconds - start)),
            "-i", str(input_path),
            "-ac", "1", "-ar", "8000",
            "-codec:a", "libmp3lame", "-b:a", "16k",
            str(output_path),
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode != 0:
            raise RuntimeError(f"ffmpeg sample extraction failed: {process.stderr.strip()}")
        if not output_path.exists():
            raise RuntimeError("Failed to create audio sample segment")
        samples.append(output_path)
    return samples
