import json

from app.config import GROQ_API_KEY, OPENAI_API_KEY, MODE, Groq, openai
from app.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_COMPACT

_RATE_LIMIT_KEYWORDS = ("rate_limit_exceeded", "Rate limit", "tokens per day", "429")


async def evaluate_transcript(transcript: str) -> str:
    max_chars = 10000
    if len(transcript) > max_chars:
        section_size = max_chars // 3
        middle_start = len(transcript) // 2 - section_size // 2
        truncated = (
            transcript[:section_size]
            + "\n\n[... session continues ...]\n\n"
            + transcript[middle_start: middle_start + section_size]
            + "\n\n[... session continues ...]\n\n"
            + transcript[-section_size:]
        )
    else:
        truncated = transcript

    user_prompt = f"COACHING TRANSCRIPT (Dutch):\n{truncated}\n\nGenerate the EMCC evaluation report as JSON."
    system_prompt = SYSTEM_PROMPT if MODE == "production" else SYSTEM_PROMPT_COMPACT

    print(f"[DEBUG] Mode: {MODE} | System prompt size: {len(system_prompt)} chars")
    print(f"[DEBUG] User prompt size: {len(user_prompt)} chars")
    print(f"[DEBUG] Total size: {len(system_prompt) + len(user_prompt)} chars")
    print(f"[DEBUG] Transcript section size: {len(truncated)} chars")
    print(f"[DEBUG] Last 200 chars of transcript: ...{truncated[-200:]}")

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
        if any(kw in str(exc) for kw in _RATE_LIMIT_KEYWORDS):
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
    trimmed = transcript[:3000]
    system_prompt = """You are a content validator. Answer only with JSON.
Determine if this transcript contains a real coaching or mentoring conversation.

A valid coaching session requires ALL of these:
- At least two people speaking
- One person acting as coach (asking questions, facilitating)
- One person acting as client (reflecting, exploring goals or challenges)
- A clear helping and exploratory dynamic

Return: {"is_coaching": true or false, "reason": "one sentence in English explaining why not"}
"""
    print(f"[DEBUG] Validation system prompt size: {len(system_prompt)} chars")
    print(f"[DEBUG] Validation transcript size: {len(trimmed)} chars")

    val_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trimmed},
    ]

    client = Groq(api_key=GROQ_API_KEY)
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=val_messages,
            temperature=0,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if any(kw in str(exc) for kw in _RATE_LIMIT_KEYWORDS):
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
                try:
                    return json.loads(oa_response.choices[0].message.content)
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
            content = message.get("content") if isinstance(message, dict) else choice.get("content", str(choice))
        if content:
            try:
                return json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return {"is_coaching": False, "reason": "Unable to parse validation response"}

    raise RuntimeError("Unexpected validation model response format")
