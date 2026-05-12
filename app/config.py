import os
from dotenv import load_dotenv

load_dotenv()

try:
    import openai
except ImportError:
    openai = None

try:
    from groq import Groq
except ImportError as exc:
    raise ImportError("groq package is required: pip install groq") from exc

try:
    import anthropic
except ImportError:
    anthropic = None

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODE = os.getenv("MODE", "production").lower()
TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3")
MAX_TRANSCRIPTION_DURATION_SECONDS = int(os.getenv("MAX_TRANSCRIPTION_DURATION_SECONDS", "7200"))
ENABLE_OPENAI_TRANSCRIPTION_FALLBACK = os.getenv("ENABLE_OPENAI_TRANSCRIPTION_FALLBACK", "true").lower() in ("1", "true", "yes")
SAMPLE_TRANSCRIPTION_SEGMENT_SECONDS = int(os.getenv("SAMPLE_TRANSCRIPTION_SEGMENT_SECONDS", "300"))
SAMPLE_TRANSCRIPTION_THRESHOLD_SECONDS = int(os.getenv("SAMPLE_TRANSCRIPTION_THRESHOLD_SECONDS", "3600"))

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is required in environment variables")
