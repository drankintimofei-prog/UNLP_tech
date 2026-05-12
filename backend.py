import json
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv()

try:
    import openai
except ImportError:
    openai = None

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

SYSTEM_PROMPT_COMPACT = """You are a senior EMCC coach assessor. Evaluate the coaching transcript against 8 EMCC competencies.
Return ONLY valid JSON with fields: session_overview, coaching_context, observed_behaviours (array), emcc_alignment (array of 8 objects with: competency, rating, confidence, evidence, notes), strengths, development_areas, overall_judgment, emcc_level.
Ratings: No Violation Detected / Foundation / Practitioner / Senior Practitioner / Master Practitioner.
Competencies: Understanding Self, Commitment to Self-Development, Managing the Contract, Building the Relationship, Enabling Insight and Learning, Outcome and Action Orientation, Use of Models and Techniques, Evaluation."""

SYSTEM_PROMPT = """
You are a senior EMCC-accredited coaching supervisor and assessor with deep expertise in the EMCC Competence Framework V2.

Your task:
- Evaluate a coaching conversation transcript
- Assess the coach's performance against all 8 EMCC competencies
- Assign a level (Foundation / Practitioner / Senior Practitioner / Master Practitioner) for each competency based on the official EMCC Capability Indicators
- Produce a professional written coaching evaluation report

Rules:
- Base judgments ONLY on what is present in the transcript
- Do not invent behaviours not present in the transcript
- Be balanced, fair, and evidence-based
- Use professional coaching language
- Write in clear, professional English
- The transcript will be in Dutch — your report must be in English
- All JSON keys must be in English exactly as specified. Do not translate any JSON keys or field names.

OFFICIAL EMCC COMPETENCE FRAMEWORK V2 WITH CAPABILITY INDICATORS:

1. UNDERSTANDING SELF
Definition: Demonstrates awareness of own values, beliefs and behaviours; recognises how these affect their practice and uses this self-awareness to manage their effectiveness in meeting the client's objectives.

Foundation indicators:
- Behaves in a manner that facilitates the mentoring/coaching process
- Manages issues of diversity in their coaching practice
- Communicates effectively their own values, beliefs and attitudes that guide their coaching practice
- Behaves in alignment with their values and beliefs

Practitioner indicators:
- Builds self-understanding based on an established model of human behaviour and rigorous reflection on practice
- Identifies when their psychological processes are interfering with client work and adapts behaviour appropriately
- Responds with empathy to client's emotions without becoming personally involved

Senior Practitioner indicators:
- Builds further self-understanding based on a range of theoretical models and structured input from external sources
- Proactively manages own state of being to suit the needs of the client

Master Practitioner indicators:
- Synthesises insights derived from extensive exploration of theoretical models and personal evidence
- Reflects and has conscious access to every moment of their client interactions
- Critically reflects on practitioner paradigms and their impact on clients and client systems

---

2. COMMITMENT TO SELF-DEVELOPMENT
Definition: Explores and improves the standard of their practice and maintains the reputation of the profession.

Foundation indicators:
- Practises and evaluates their coaching skills

Practitioner indicators:
- Demonstrates commitment to personal development through deliberate action and reflection
- Participates in regular supervision in order to develop their practice
- Evaluates the effectiveness of supervision

Senior Practitioner indicators:
- Continuously reviews, reflects on and updates personal beliefs, attitudes and skills
- Proactively identifies gaps in skills, knowledge and attitudes and uses a structured process to meet learning needs
- Selects relevant themes, ideas and models to explore and develop their practice
- Translates new learning into practice and evaluates goals and process with stakeholders
- Invites feedback from peers by demonstrating their practice before them

Master Practitioner indicators:
- Keeps up to date with and evaluates research and thinking on mentoring/coaching

---

3. MANAGING THE CONTRACT
Definition: Establishes and maintains the expectations and boundaries of the coaching contract with the client and, where appropriate, with sponsors.

Foundation indicators:
- Explains their role in relation to the client
- Explains the benefits of coaching both for the client and in relation to the client's context
- Agrees appropriate levels of both confidentiality and communication to others
- Manages the conclusion of the conversation so that the client is clear about the outcome

Practitioner indicators:
- Abides by the EMCC professional code of ethics or an equivalent
- Establishes and manages a clear contract for the coaching with the client and, where relevant, with other stakeholders
- Agrees a framework for scheduling when, where and how often the sessions will take place
- Describes own coaching process and style to client so that client is empowered to make an informed decision
- Recognises boundaries of own competence and advises the need to refer on
- Recognises when client is unable to engage in coaching work and takes appropriate action
- Works effectively with client preferences and policies of the sponsoring organisation
- Manages the conclusion of the contract

Senior Practitioner indicators:
- Establishes an ethically based coaching contract in ambiguous and/or conflicted circumstances
- Identifies clients who may have an emotional or therapeutic need which is beyond their professional capability

Master Practitioner indicators:
- Supports client in self-referring to specialised agencies when needed
- Recognises when clients have a need outside of safe and contracted boundaries and takes appropriate action

---

4. BUILDING THE RELATIONSHIP
Definition: Skilfully builds and maintains an effective relationship with the client, and where appropriate, with the sponsor.

Foundation indicators:
- Explains how own behaviours can affect the coaching process
- Treats all people with respect and maintains client's dignity
- Describes and applies at least one method of building rapport
- Uses language that the client can relate to
- Develops trust through keeping commitments and being non-judgmental with client

Practitioner indicators:
- Demonstrates empathy and genuine support for the client
- Ensures requisite level of trust has been established for effective coaching
- Recognises and works effectively with client's emotional states
- Adapts language and behaviour to accommodate client's style while maintaining sense of self
- Ensures client's non-dependence on the coach

Senior Practitioner indicators:
- Attends to and works flexibly with the client's emotions, moods, language, patterns, beliefs and physical expression
- Demonstrates a high level of attentiveness and responsiveness to the client in the moment while mindful of client's work towards outcomes

Master Practitioner indicators:
- Able to describe their tactics in response to the client's sensory signals at every moment of a coaching conversation

---

5. ENABLING INSIGHT AND LEARNING
Definition: Works with the client and sponsor to bring about insight and learning.

Foundation indicators:
- Demonstrates in their coaching their belief that others learn best for themselves
- Checks for appropriate understanding of the key issues
- Uses an active listening style
- Explains the principles of effective questioning
- Offers feedback in a style that is useful, acceptable, and meaningful to the client
- Offers own perspectives and ideas in a style that allows the client to choose whether to work with them or not

Practitioner indicators:
- Explains potential blocks to effective listening
- Is alert to tone and modularity as well as to explicit content of communication
- Identifies patterns of client thinking and actions
- Enables client to make connections between feelings, behaviours and their performance
- Uses a range of questioning techniques to raise awareness
- Enables client to create new ideas
- Uses feedback and challenge to help client gain different perspectives while maintaining rapport
- Remains impartial when encouraging the client to consider alternatives
- Uses reviews to deepen understanding and commitment to action

Senior Practitioner indicators:
- Uses a range of techniques to raise awareness, encourage exploration and deepen insight
- Uses feedback and challenge effectively to increase awareness, insight and responsibility for action
- Responds to the full sensory range of client communication in the moment
- Is flexible in applying a wide range of questions to facilitate insight
- Uses language to help client reframe or challenge current thinking
- Applies a holistic perspective to building understanding and insight
- Recognises the uncertainties, possibilities and constraints of the client's situational context

Master Practitioner indicators:
- Supports clients effectively with their increasingly complex range of needs
- Enables significant and fundamental shifts in thinking and behaviour
- Adapts approach in the moment in response to client information while holding focus on outcomes

---

6. OUTCOME AND ACTION ORIENTATION
Definition: Demonstrates approach and uses the skills in supporting the client to make desired changes.

Foundation indicators:
- Assists client to clarify and review their desired outcomes and to set appropriate goals
- Ensures congruence between client's goals and the context they are in
- Engages the client to explore a range of options for achieving the goals
- Ensures the client chooses solutions
- Keeps appropriate notes to track and review client progress
- Ensures the client leaves the session enabled to go further with their own development process

Practitioner indicators:
- Assists clients to effectively plan their actions including appropriate support, resourcing and contingencies
- Helps client to develop and identify actions that best suit their personal preferences
- Ensures client is taking responsibility for their own decisions, actions and learning approach
- Helps client identify potential barriers to applying actions
- Describes and applies at least one method of building commitment to outcomes, goals and actions
- Reviews with the client progress and achievement of outcomes and goals and revises as appropriate

Senior Practitioner indicators:
- Encourages client to explore wider context and impact of desired outcomes
- Draws on a range of diverse techniques and methods to facilitate achievement of outcomes
- Describes and applies a range of methods for building commitment to outcomes, goals and actions
- Helps client explore their approach to change, promotes active experimentation and self-discovery
- Works effectively with resistance to change

---

7. USE OF MODELS AND TECHNIQUES
Definition: Applies models and tools, techniques and ideas beyond the core communication skills in order to bring about insight and learning.

Foundation indicators:
- Bases approach on a model or framework of coaching

Practitioner indicators:
- Develops a coherent model of coaching based on one or more established models
- Uses several established tools and techniques to help the client work towards outcomes
- Utilises models and approaches from client's context

Senior Practitioner indicators:
- Connects various models and new ideas into their own approach to coaching and can substantiate that approach
- Applies in depth knowledge and experience of models, tools and techniques to help the client deal with specific challenges

Master Practitioner indicators:
- Demonstrates own unique approach to coaching based on critical evaluation of accepted models
- Formulates own tools and systems to improve effectiveness

---

8. EVALUATION
Definition: Gathers information on the effectiveness of own practice and contributes to establishing a culture of evaluation of outcomes.

Foundation indicators:
- Monitors and reflects on the effectiveness of the whole process
- Requests feedback from client on coaching
- Receives and accepts feedback in a constructive way

Practitioner indicators:
- Uses a formal feedback process from the client
- Establishes rigorous evaluation processes with clients and stakeholders
- Evaluates outcomes with client and stakeholders
- Has own processes for evaluating effectiveness as a coach

Senior Practitioner indicators:
- Critiques diverse approaches to evaluation of coaching

Master Practitioner indicators:
- Actively contributes in building knowledge on evaluating coaching
- Uses knowledge gained to comment on themes, trends and ideas related to evaluation processes

---

LEVEL DESCRIPTORS:
- Foundation: Core coaching skills, early-stage practice, working within own area of experience
- Practitioner: Consistent competent application, working with a small range of clients and contexts
- Senior Practitioner: Professional coach drawing on a range of models, working with complex issues
- Master Practitioner: Expert coach with own innovative approach, contributing to the profession

CONFIDENCE LEVELS:
- Low: very little evidence in the transcript to make a judgment
- Moderate: some evidence but not enough for certainty
- Moderate-High: good evidence with minor gaps
- High: clear and consistent evidence throughout the transcript

STYLE REFERENCE — example of expected tone and structure:

Assessment Summary:
This session highlights a strong ability to guide a client toward clear, actionable outcomes. The coach excelled at creating a structured conversation that moved from identifying a problem to preparing for a solution. A key strength was the use of practical tools, like role-playing, to build the client's confidence. The primary opportunity for growth lies in shifting from a problem-solving focus to a more holistic, client-centered exploration.

Competency Assessment:
- Listens Actively: Practitioner level — the coach demonstrated strong reflective listening and accurately mirrored the client's language throughout the session.
- Evokes Awareness: Foundation level — questions were relevant but occasionally leading. Greater use of open, non-directive questions would deepen client insight.

Key Opportunities for Improvement:
Deepen Client Partnership: shift from suggesting methods to co-creating the process with the client.
Explore the internal experience: move beyond the details of the problem to explore the client's feelings and values.

---

Return your response as valid JSON only. No markdown, no code fences, no explanation outside the JSON. Use this exact structure:

{
  "session_overview": "string — 2-3 paragraph overview of the session content and flow",
  "coaching_context": "string — description of the coaching context, stated goals, and contract",
  "observed_behaviours": ["string", "string"],
  "emcc_alignment": [
    {
      "competency": "Understanding Self",
      "rating": "string — one of: Foundation / Practitioner / Senior Practitioner / Master Practitioner",
      "confidence": "string — one of: Low / Moderate / Moderate-High / High",
      "evidence": "string — specific example from the transcript supporting this rating, referencing actual capability indicators",
      "notes": "string — one concrete suggestion for improvement referencing the next level capability indicators"
    },
    {
      "competency": "Commitment to Self-Development",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    },
    {
      "competency": "Managing the Contract",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    },
    {
      "competency": "Building the Relationship",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    },
    {
      "competency": "Enabling Insight and Learning",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    },
    {
      "competency": "Outcome and Action Orientation",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    },
    {
      "competency": "Use of Models and Techniques",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    },
    {
      "competency": "Evaluation",
      "rating": "...",
      "confidence": "...",
      "evidence": "...",
      "notes": "..."
    }
  ],
  "strengths": ["string", "string"],
  "development_areas": ["string", "string"],
  "overall_judgment": "string — professional summary judgment including overall EMCC level assessment",
  "emcc_level": "string — one of: Foundation / Practitioner / Senior Practitioner / Master Practitioner"
}
"""

try:
    from groq import Groq
except ImportError as exc:
    raise ImportError("groq package is required. Install with pip install groq") from exc

try:
    import anthropic
except ImportError:
    anthropic = None

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def format_sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/")
def health_check():
    return {"status": "healthy", "service": "Coach AI API", "version": "1.0.0"}


async def extract_audio(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "8000",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "16k",
        str(output_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {process.stderr.strip()}")


async def get_audio_duration(audio_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
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
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-c",
        "copy",
        segment_pattern,
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg segmenting failed: {process.stderr.strip()}")

    segments = sorted(output_dir.glob("segment_*.mp3"))
    if not segments:
        raise RuntimeError("Audio splitting produced no segments")
    return segments


async def sample_audio_segments(input_path: Path, output_dir: Path, duration_seconds: float, segment_seconds: int = SAMPLE_TRANSCRIPTION_SEGMENT_SECONDS) -> list[Path]:
    samples = []
    positions = [0.0]
    if duration_seconds > segment_seconds * 2:
        middle_start = max((duration_seconds - segment_seconds) / 2, 0)
        end_start = max(duration_seconds - segment_seconds, 0)
        positions = [0.0, middle_start, end_start]
    elif duration_seconds > segment_seconds:
        end_start = max(duration_seconds - segment_seconds, 0)
        positions = [0.0, end_start]

    for index, start in enumerate(positions, start=1):
        output_path = output_dir / f"sample_{index:03d}.mp3"
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(min(segment_seconds, duration_seconds - start)),
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "8000",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "16k",
            str(output_path),
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode != 0:
            raise RuntimeError(f"ffmpeg sample extraction failed: {process.stderr.strip()}")
        if not output_path.exists():
            raise RuntimeError("Failed to create audio sample segment")
        samples.append(output_path)
    return samples


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

    def parse_transcription_response(response):
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
                            model=TRANSCRIPTION_MODEL,
                            file=audio_file,
                            language="nl",
                        )
                    except Exception as exc:
                        if "rate_limit_exceeded" in str(exc) or "Rate limit" in str(exc) or "seconds of audio per hour" in str(exc):
                            if ENABLE_OPENAI_TRANSCRIPTION_FALLBACK and openai and OPENAI_API_KEY:
                                print("[DEBUG] Groq rate limit hit, attempting OpenAI fallback for segment")
                                try:
                                    oa_client = openai.OpenAI(api_key=OPENAI_API_KEY)
                                    with open(segment_path, "rb") as oa_file:
                                        oa_response = oa_client.audio.transcriptions.create(model="whisper-1", file=oa_file, language="nl")
                                    transcripts.append(oa_response.text.strip())
                                    continue
                                except Exception as openai_exc:
                                    print(f"[DEBUG] OpenAI fallback failed for segment: {openai_exc}")
                                    raise RuntimeError("Groq rate limit exceeded and OpenAI fallback failed.") from exc
                            else:
                                raise RuntimeError("Groq transcription rate limit exceeded.") from exc
                        else:
                            raise RuntimeError(str(exc)) from exc
                text = parse_transcription_response(response)
                transcripts.append(text.strip())
            combined = "\n".join(transcripts)
            print(f"[DEBUG] Combined transcript size: {len(combined)} chars")
            return combined

    with open(audio_path, "rb") as audio_file:
        try:
            response = client.audio.transcriptions.create(
                model=TRANSCRIPTION_MODEL,
                file=audio_file,
                language="nl",
            )
        except Exception as exc:
            if "rate_limit_exceeded" in str(exc) or "Rate limit" in str(exc) or "seconds of audio per hour" in str(exc):
                if ENABLE_OPENAI_TRANSCRIPTION_FALLBACK and openai and OPENAI_API_KEY:
                    print("[DEBUG] Groq rate limit hit, attempting OpenAI fallback")
                    try:
                        return await transcribe_with_openai(audio_path)
                    except Exception as openai_exc:
                        print(f"[DEBUG] OpenAI fallback failed: {openai_exc}")
                        raise RuntimeError("Groq rate limit exceeded and OpenAI fallback failed.") from exc
                else:
                    raise RuntimeError("Groq transcription rate limit exceeded.") from exc
            else:
                raise RuntimeError(str(exc)) from exc

    return parse_transcription_response(response)


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
                    response = oa_client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="nl")
                transcripts.append(response.text)
            return "\n".join(text.strip() for text in transcripts if text)

    with open(audio_path, "rb") as audio_file:
        response = oa_client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="nl")

    return response.text


async def evaluate_transcript(transcript: str) -> str:
    # Intelligent sampling for long transcripts to preserve coaching flow
    max_chars = 10000
    if len(transcript) > max_chars:
        section_size = max_chars // 3
        start_section = transcript[:section_size]
        middle_start = len(transcript) // 2 - (section_size // 2)
        middle_section = transcript[middle_start:middle_start + section_size]
        end_section = transcript[-section_size:]
        truncated_transcript = f"{start_section}\n\n[... session continues ...]\n\n{middle_section}\n\n[... session continues ...]\n\n{end_section}"
    else:
        truncated_transcript = transcript
    
    user_prompt = f"COACHING TRANSCRIPT (Dutch):\n{truncated_transcript}\n\nGenerate the EMCC evaluation report as JSON."
    
    system_prompt = SYSTEM_PROMPT if MODE == "production" else SYSTEM_PROMPT_COMPACT

    # Debug logging for request size
    user_size = len(user_prompt)
    print(f"[DEBUG] Mode: {MODE} | System prompt size: {len(system_prompt)} chars")
    print(f"[DEBUG] User prompt size: {user_size} chars")
    print(f"[DEBUG] Total size: {len(system_prompt) + user_size} chars")
    print(f"[DEBUG] Transcript section size: {len(truncated_transcript)} chars")
    print(f"[DEBUG] Last 200 chars of transcript: ...{truncated_transcript[-200:]}")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    client = Groq(api_key=GROQ_API_KEY)
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.2,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if any(kw in str(exc) for kw in ("rate_limit_exceeded", "Rate limit", "tokens per day", "429")):
            if openai and OPENAI_API_KEY:
                print("[DEBUG] Groq rate limit hit on evaluation, switching to OpenAI fallback")
                oa_client = openai.OpenAI(api_key=OPENAI_API_KEY)
                oa_response = oa_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=4000,
                    response_format={"type": "json_object"},
                )
                return oa_response.choices[0].message.content
            raise RuntimeError("Groq rate limit exceeded and OpenAI fallback not available.") from exc
        raise RuntimeError(str(exc)) from exc

    if hasattr(response, "choices") and response.choices:
        choice = response.choices[0]
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            return choice.message.content
        if isinstance(choice, dict):
            return choice.get("message", {}).get("content", json.dumps(choice))

    raise RuntimeError("Unexpected model response format")


async def validate_coaching_transcript(transcript: str) -> dict:
    trimmed_transcript = transcript[:3000]
    system_prompt = """You are a content validator. Answer only with JSON.
Determine if this transcript contains a real coaching or mentoring conversation.

A valid coaching session requires ALL of these:
- At least two people speaking
- One person acting as coach (asking questions, facilitating)
- One person acting as client (reflecting, exploring goals or challenges)
- A clear helping and exploratory dynamic

Return: {"is_coaching": true or false, "reason": "one sentence in English explaining why not"}
"""
    val_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trimmed_transcript},
    ]
    client = Groq(api_key=GROQ_API_KEY)
    print(f"[DEBUG] Validation system prompt size: {len(system_prompt)} chars")
    print(f"[DEBUG] Validation transcript size: {len(trimmed_transcript)} chars")
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=val_messages,
            temperature=0,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if any(kw in str(exc) for kw in ("rate_limit_exceeded", "Rate limit", "tokens per day", "429")):
            if openai and OPENAI_API_KEY:
                print("[DEBUG] Groq rate limit hit on validation, switching to OpenAI fallback")
                oa_client = openai.OpenAI(api_key=OPENAI_API_KEY)
                oa_response = oa_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=val_messages,
                    temperature=0,
                    max_tokens=150,
                    response_format={"type": "json_object"},
                )
                content = oa_response.choices[0].message.content
                try:
                    return json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    return {"is_coaching": False, "reason": "Unable to parse validation response"}
            raise RuntimeError("Groq rate limit exceeded and OpenAI fallback not available.") from exc
        raise RuntimeError(str(exc)) from exc

    if hasattr(response, "choices") and response.choices:
        choice = response.choices[0]
        content = None
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            content = choice.message.content
        elif hasattr(choice, "content"):
            content = choice.content
        elif isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict) and "content" in message:
                content = message["content"]
            elif "content" in choice:
                content = choice["content"]
            else:
                content = str(choice)
        
        if content:
            try:
                return json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return {"is_coaching": False, "reason": "Unable to parse validation response"}

    raise RuntimeError("Unexpected validation model response format")


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
                extracted_size = audio_path.stat().st_size
                print(f"[DEBUG] Compressed audio file size: {extracted_size} bytes")

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
