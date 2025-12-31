import io
import asyncio
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
import os

OPEN_AI_KEY = os.getenv("OPEN_AI_KEY")
if not OPEN_AI_KEY:
    raise RuntimeError("OPEN_AI_KEY missing")

client = OpenAI(api_key=OPEN_AI_KEY)


# -------------------------------
# MAIN FUNCTION: TEXT → MP3 AUDIO
# -------------------------------
async def text_to_speech_stream(text: str):
    """
    Converts text to speech (mp3) and streams it.
    The speech style is conversational Indian-English.
    """

    if not text or not text.strip():
        raise HTTPException(400, "Empty text for TTS")

    # Add Indian-style phrasing
    text = f"Please speak this in a natural Indian English accent: {text}"

    # Blocking call offloaded to thread
    def _call_tts():
        resp = client.audio.speech.create(
            model="tts-1",      # Fastest TTS model
            voice="alloy",      # Default voice (clear, neutral)
            format="mp3",
            input=text,
        )
        return resp.read()

    loop = asyncio.get_running_loop()
    audio_bytes = await loop.run_in_executor(None, _call_tts)

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg"
    )
