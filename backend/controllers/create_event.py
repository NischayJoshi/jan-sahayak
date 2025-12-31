from langchain_core.chat_models import ChatGroq
from dotenv import load_dotenv
import asyncio
import os

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
llm = ChatGroq(api_key=groq_api_key, model="groq-alpha-001")

async def create_event_summary(event_details: str) -> str:
    prompt = (
        "Generate a concise and engaging summary for the following event:\n\n"
        f"{event_details}\n\n"
        "Summary:"
    )
    return await llm.apredict(prompt)

