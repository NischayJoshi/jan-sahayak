from fastapi import APIRouter, Depends, HTTPException
from middlewares.auth_required import get_user as get_current_user
from config.db import db
from bson import ObjectId
from utils.serializers import serialize_doc, serialize_docs

router = APIRouter()

users_collection = db["users"]
events_collection = db["events"]
teams_collection = db["teams"]
submissions_collection = db["submissions"]


@router.get("/is-registered/{event_id}")
async def is_registered(
    event_id: str,
    user=Depends(get_current_user)
):
    # Validate event ID
    if not ObjectId.is_valid(event_id):
        raise HTTPException(400, "Invalid event ID")

    # Ensure event exists (event _id is ObjectId)
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")

    # Team eventId is stored as string, so DO NOT use ObjectId here
    team = await teams_collection.find_one({
        "eventId": event_id,              # <--- FIXED
        "members.userId": user["id"]      # stored as string
    })

    if not team:
        raise HTTPException(403, "User is not registered for this event")

    return {
        "registered": True,
        "team": serialize_doc(team)
    }
