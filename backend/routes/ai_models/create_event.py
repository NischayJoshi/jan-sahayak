from langchain_groq import ChatGroq
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import os

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
llm = ChatGroq(api_key=groq_api_key, model="llama-3.1-8b-instant")

router = APIRouter(tags=["AI Models"])

class EventDetails(BaseModel):
    event_details: str


# -------------------------------------------------------
# 1) Generate short summary
# -------------------------------------------------------
@router.post("/create-event-summary")
async def create_event_summary(data: EventDetails):
    if not data.event_details.strip():
        raise HTTPException(status_code=400, detail="event_details cannot be empty")

    prompt = f"""
    You are an expert event copywriter.
    Create a concise, engaging 1–2 sentence summary for this event:

    {data.event_details}

    Summary:
    """

    summary = await llm.apredict(prompt)
    return {"summary": summary.strip()}


# -------------------------------------------------------
# 2) Generate full event object (JSON)
# -------------------------------------------------------
@router.post("/create-event-ai")
async def create_event_ai(data: EventDetails):
    if not data.event_details.strip():
        raise HTTPException(status_code=400, detail="event_details cannot be empty")

    prompt = f"""
    You are an expert event planner and technical content writer.
    Read the following event details:

    {data.event_details}

    Now generate a COMPLETE event configuration in VALID JSON ONLY.
    Do NOT add comments. Do NOT add text outside JSON.

    Use this EXACT structure:

    {{
      "name": "",
      "summary": "",
      "description": "",
      "date": "",
      "registrationDeadline": "",
      "prize": "",
      "maxTeams": 0,
      "minMembers": 0,
      "maxMembers": 0
    }}

    STRICT RULES:
    - Description MUST be long, structured, and professional (minimum 150–250 words)
    - Description should include:
        • Event mission & objective  
        • Participation guidelines  
        • Overview of rounds  
        • What judges will evaluate  
        • Why teams should participate  
    - "date" must be ISO format YYYY-MM-DD  
    - "registrationDeadline" must be BEFORE "date"  
    - "prize" must be numeric string (e.g., "5000")  
    - Names must sound premium and branded  
    - Keep summary short around 1–2 sentences, but description very detailed  

    Return ONLY the JSON.
    """

    raw = await llm.apredict(prompt)

    try:
        parsed = json.loads(raw)
    except:
        cleaned = raw.strip().replace("```json", "").replace("```", "")
        try:
            parsed = json.loads(cleaned)
        except:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON from model: {raw}"
            )

    return {"event": parsed}
