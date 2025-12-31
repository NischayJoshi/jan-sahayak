from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
    Form,
    Body,
)
from fastapi.responses import StreamingResponse
from middlewares.auth_required import auth_required
from utils.pdf_reader import extract_pdf_text
from datetime import datetime
from bson import ObjectId
import cloudinary.uploader
import whisper
import tempfile
from config.db import db
from langchain_openai import ChatOpenAI
import os
import torch
from dotenv import load_dotenv
import asyncio
import re
import io
from openai import OpenAI

load_dotenv()

router = APIRouter(tags=["interview"])

OPEN_AI_KEY = os.getenv("OPEN_AI_KEY")
if not OPEN_AI_KEY:
    raise RuntimeError("OPEN_AI_KEY is not set")

client = OpenAI(api_key=OPEN_AI_KEY)

use_gpu = torch.cuda.is_available()

llm = ChatOpenAI(
    model_name="gpt-4o-mini",
    temperature=0.2,
    max_tokens=512,
    openai_api_key=OPEN_AI_KEY,
)

_whisper_model = None
_whisper_lock = asyncio.Lock()

submissions_collection = db["submissions"]
viva_sessions_collection = db["viva_sessions"]
teams_collection = db["teams"]


async def get_whisper_model():
    global _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            _whisper_model = whisper.load_model(
                "small",
                device="cuda" if use_gpu else "cpu",
            )
        return _whisper_model


async def transcribe_audio(path: str) -> str:
    model = await get_whisper_model()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: model.transcribe(
            path,
            fp16=use_gpu,
            temperature=0,
            beam_size=5,
            condition_on_previous_text=False,
        ),
    )
    text = (result.get("text") or "").strip()
    if not text:
        raise HTTPException(500, "Transcription failed.")
    return text


def parse_numbered_list(text: str, expected: int = 5) -> list[str]:
    lines = text.splitlines()
    items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\s*(\d+)[\.\)]\s*(.+)$", line)
        if m:
            items.append(m.group(2).strip())
    items = items[:expected]
    if len(items) != expected:
        raise HTTPException(500, "Failed to generate complete interview questions.")
    return items


def parse_score_feedback(text: str) -> dict:
    score = 0
    feedback = ""
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("score"):
            part = line.split(":", 1)[-1].strip()
            digits = re.findall(r"\d+", part)
            if digits:
                s = int(digits[0])
                if 0 <= s <= 10:
                    score = s
        elif line.lower().startswith("feedback"):
            feedback = line.split(":", 1)[-1].strip()
    if feedback == "":
        feedback = text.strip()
    return {"score": score, "feedback": feedback}


async def generate_interview_questions_from_pdf(pdf_text: str) -> list[str]:
    prompt = f"""
You are an expert technical interviewer.
Based on the following project description, generate EXACTLY 5 interview questions.

The first question MUST be:
1. Give your introduction.

Use clear, short, conversational Indian-English questions.

Project Description:
{pdf_text}

Return ONLY a numbered list in this format:
1. ...
2. ...
3. ...
4. ...
5. ...
"""
    response = await llm.apredict(prompt)
    return parse_numbered_list(response, expected=5)


async def evaluate_answer_with_llm(question: str, answer: str, pdf_text: str) -> dict:
    prompt = f"""
You are a strict but fair Indian technical interviewer.

Evaluate the candidate's answer based on clarity, technical correctness, relevance, and depth.
Ask Basic Easy Questions

PDF Summary:
{pdf_text}

Question:
{question}

Answer:
{answer}

Respond EXACTLY in this format:

Score: <0-10>
Feedback: <short, friendly, Indian-style feedback in 1-2 lines>
"""
    response = await llm.apredict(prompt)
    parsed = parse_score_feedback(response)
    return parsed


async def generate_viva_summary(pdf_text: str, questions: list[str], answers: list[str], scores: list[int]) -> str:
    qa_block_parts = []
    for q, a, s in zip(questions, answers, scores):
        qa_block_parts.append(
            f"### Question\n{q}\n\n### Answer\n{a}\n\n### Score: {s}/10\n"
        )
    qa_block = "\n\n---\n\n".join(qa_block_parts)
    prompt = f"""
You are an experienced Indian senior technical interviewer.

Generate a professional MARKDOWN summary for the candidate's viva performance.

Use a neutral Indian-English tone.

Include these sections:

## 📝 Overall Performance Summary
(2–3 lines)

## ✅ Strengths
- Bullet points

## ⚠️ Weaknesses
- Bullet points

## 🧠 Technical Depth Evaluation
(2–4 lines)

## 🏁 Final Recommendation
(Short conclusion)

Below is the interview transcript with scores:

{qa_block}

PDF Project Summary:
{pdf_text}

Write ONLY markdown. No extra explanation.
"""
    summary = await llm.apredict(prompt)
    return summary.strip()


async def synthesize_speech_bytes(text: str) -> bytes:
    if not text or not text.strip():
        raise HTTPException(400, "Empty text for TTS")

    def _call():
        resp = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            response_format="mp3",
            input=text,
        )
        return resp.read()

    loop = asyncio.get_running_loop()
    audio_bytes = await loop.run_in_executor(None, _call)
    return audio_bytes


@router.post("/tts", response_class=StreamingResponse)
async def tts_endpoint(payload: dict = Body(...)):
    text = (payload.get("text") or "").strip()
    audio_bytes = await synthesize_speech_bytes(text)
    return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")


@router.post("/interview-data")
async def get_interview_data(
    file: UploadFile = File(...),
    user: dict = Depends(auth_required),
):
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF allowed.")

    upload = cloudinary.uploader.upload(file.file, resource_type="raw")
    pdf_url = upload.get("secure_url")
    if not pdf_url:
        raise HTTPException(500, "Failed to upload PDF.")

    pdf_text = await extract_pdf_text(pdf_url)
    if not pdf_text:
        raise HTTPException(500, "Failed to extract PDF text.")

    submission_doc = {
        "userId": str(user["id"]),
        "pdfUrl": pdf_url,
        "pdfText": pdf_text,
        "roundId": "viva",
        "submittedAt": datetime.utcnow(),
    }

    await submissions_collection.update_one(
        {"userId": str(user["id"]), "roundId": "viva"},
        {"$set": submission_doc},
        upsert=True,
    )

    questions = await generate_interview_questions_from_pdf(pdf_text)

    session_doc = {
        "userId": str(user["id"]),
        "pdfUrl": pdf_url,
        "pdfText": pdf_text,
        "questions": questions,
        "answers": [],
        "scores": [],
        "feedbacks": [],
        "currentIndex": 0,
        "totalScore": 0,
        "maxQuestions": 5,
        "isFinished": False,
        "createdAt": datetime.utcnow(),
    }

    result = await viva_sessions_collection.insert_one(session_doc)
    session_id = str(result.inserted_id)

    return {
        "success": True,
        "sessionId": session_id,
        "question": questions[0],
        "questionIndex": 0,
        "totalQuestions": 5,
    }


@router.get("/session/{session_id}")
async def get_session_state(
    session_id: str,
    user: dict = Depends(auth_required),
):
    try:
        obj_id = ObjectId(session_id)
    except Exception:
        raise HTTPException(400, "Invalid sessionId.")

    session = await viva_sessions_collection.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(404, "Session not found.")

    if str(session["userId"]) != str(user["id"]):
        raise HTTPException(403, "Unauthorized session access.")

    idx = session.get("currentIndex", 0)
    max_q = session.get("maxQuestions", 5)
    questions = session.get("questions") or []

    current_question = None
    if not session.get("isFinished") and 0 <= idx < len(questions):
        current_question = questions[idx]

    return {
        "success": True,
        "sessionId": session_id,
        "question": current_question,
        "questionIndex": idx,
        "totalQuestions": max_q,
        "answeredCount": len(session.get("answers", [])),
        "totalScore": session.get("totalScore", 0),
        "done": session.get("isFinished", False),
    }


@router.post("/answer-audio")
async def answer_audio(
    sessionId: str = Form(...),
    eventId: str | None = Form(None),
    questionIndex: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(auth_required),
):
    try:
        obj_id = ObjectId(sessionId)
    except Exception:
        raise HTTPException(400, "Invalid sessionId.")

    session = await viva_sessions_collection.find_one({"_id": obj_id})
    if not session:
        raise HTTPException(404, "Session not found.")

    if str(session["userId"]) != str(user["id"]):
        raise HTTPException(403, "Unauthorized session access.")

    if session.get("isFinished"):
        raise HTTPException(400, "Interview already completed.")

    if questionIndex != session.get("currentIndex", 0):
        raise HTTPException(400, "Invalid question index.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    transcript = await transcribe_audio(tmp_path)

    try:
        os.remove(tmp_path)
    except Exception:
        pass

    questions = session.get("questions") or []
    if questionIndex >= len(questions):
        raise HTTPException(400, "Question index out of range.")

    question = questions[questionIndex]
    eval_result = await evaluate_answer_with_llm(question, transcript, session.get("pdfText", ""))

    score = int(eval_result.get("score", 0))
    if score < 0:
        score = 0
    if score > 10:
        score = 10
    feedback = eval_result.get("feedback", "").strip()

    answers = session.get("answers", []) + [transcript]
    scores = session.get("scores", []) + [score]
    feedbacks = session.get("feedbacks", []) + [feedback]

    next_index = questionIndex + 1
    max_questions = session.get("maxQuestions", 5)
    finished = next_index >= max_questions
    total_score = sum(scores)

    await viva_sessions_collection.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "currentIndex": next_index,
                "isFinished": finished,
                "totalScore": total_score,
                "answers": answers,
                "scores": scores,
                "feedbacks": feedbacks,
            }
        },
    )

    if finished:
        viva_summary = await generate_viva_summary(
            session.get("pdfText", ""),
            questions,
            answers,
            scores,
        )

        team_name = "N/A"
        team_id_str = None

        if eventId:
            team_data = await teams_collection.find_one(
                {"eventId": eventId, "members.userId": str(user["id"])}
            )
            if team_data:
                team_name = team_data.get("teamName", "N/A")
                team_id_str = str(team_data["_id"])

        await submissions_collection.update_one(
            {"userId": str(user["id"]), "roundId": "viva"},
            {
                "$set": {
                    "eventId": eventId,
                    "teamName": team_name,
                    "teamId": team_id_str,
                    "aiResult": {
                        "vivaScore": total_score,
                        "vivaSummary": viva_summary,
                        "vivaAnswers": answers,
                        "vivaScores": scores,
                        "vivaFeedbacks": feedbacks,
                    },
                    "completedAt": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    next_question = None if finished else questions[next_index]

    return {
        "success": True,
        "transcript": transcript,
        "score": score,
        "feedback": feedback,
        "nextQuestion": next_question,
        "nextIndex": next_index,
        "done": finished,
        "totalScore": total_score,
        "answeredCount": len(answers),
        "totalQuestions": max_questions,
    }
