from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import cloudinary.uploader
from middlewares.auth_required import get_user as get_current_user, auth_required
from config.db import db
from bson import ObjectId
from utils.serializers import serialize_doc,serialize_docs

router = APIRouter()

@router.get("/test")
async def test():
    return {"msg": "dsfsf"}

users_collection = db["users"]
events_collection = db["events"]
teams_collection = db["teams"]          # NEW
submissions_collection = db["submissions"]  # NEW

@router.get("/profile")
async def profile(user=Depends(get_current_user)):
    """
    Returns full user profile from DB based on the user from token.
    """
    try:
        # user is dict from auth_required: {"_id": "...", "email": "...", "role": "..."}
        user_id = user.get("_id") or user.get("id")

        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid user payload")

        user_data = await users_collection.find_one({"_id": ObjectId(user_id)})

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Fix ObjectId in response
        user_data = serialize_doc(user_data)

        return {
            "success": True,
            "data": user_data,
        }

    except HTTPException:
        # Re-raise clean HTTP errors
        raise
    except Exception as e:
        # Log in real app; for now just expose
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-user")
async def get_user_route(user=Depends(auth_required)):
    """
    Returns the decoded user from token (without DB lookup).
    This is usually enough for basic dashboard header etc.
    """
    return {
        "success": True,
        "data": user,
    }

@router.post("/create")
async def create_event(
    user = Depends(get_current_user),

    name: str = Form(...),
    summary: str = Form(""),
    description: str = Form(""),
    date: str = Form(...),
    registrationDeadline: str = Form(...),  # NEW FIELD
    prize: str = Form(""),
    maxTeams: int = Form(...),
    minMembers: int = Form(...),
    maxMembers: int = Form(...),
    rounds: str = Form("[]"),

    bannerFile: UploadFile = File(None),
    logoFile: UploadFile = File(None),
):
    try:
        from datetime import datetime

        deadline_dt = datetime.fromisoformat(registrationDeadline)
        event_dt = datetime.fromisoformat(date)

        if deadline_dt > event_dt:
            raise HTTPException(
                status_code=400,
                detail="Registration deadline must be before event date."
            )


        import json
        try:
            rounds_data = json.loads(rounds)
        except:
            rounds_data = []

        banner_url = None
        if bannerFile:
            upload_res = cloudinary.uploader.upload(bannerFile.file)
            banner_url = upload_res["secure_url"]

        logo_url = None
        if logoFile:
            upload_res = cloudinary.uploader.upload(logoFile.file)
            logo_url = upload_res["secure_url"]

        event_obj = {
            "name": name,
            "summary": summary,
            "description": description,
            "date": date,
            "registrationDeadline": registrationDeadline,  # NEW FIELD
            "prize": prize,
            "maxTeams": maxTeams,
            "minMembers": minMembers,
            "maxMembers": maxMembers,
            "rounds": rounds_data,
            "banner": banner_url,
            "logo": logo_url,
            "organizerId": ObjectId(user["id"]),
            "createdAt": datetime.utcnow(),
        }

        result = await events_collection.insert_one(event_obj)
        event_obj["_id"] = result.inserted_id

        return {
            "success": True,
            "data": serialize_doc(event_obj),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my-events")
async def my_events(user = Depends(get_current_user)):
    cursor = events_collection.find({"organizerId": ObjectId(user["id"])})
    events = await cursor.to_list(None)

    return {
        "success": True,
        "data": serialize_docs(events),
    }

@router.get("/events/{event_id}")
async def get_single_event(event_id: str, user=Depends(get_current_user)):
    try:
        event = await events_collection.find_one({"_id": ObjectId(event_id)})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        return {
            "success": True,
            "data": serialize_doc(event),
        }
    except:
        raise HTTPException(status_code=400, detail="Invalid event ID")

@router.get("/events/{event_id}/responses")
async def event_responses(event_id: str, user=Depends(get_current_user)):
    try:
        # Check event belongs to organizer
        event = await events_collection.find_one(
            {"_id": ObjectId(event_id), "organizerId": ObjectId(user["id"])}
        )
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        # Fetch teams of this event
        teams = await teams_collection.find({"eventId": event_id}).to_list(None)
        teams_map = {str(t["_id"]): serialize_doc(t) for t in teams}

        # Fetch all submissions of all rounds
        subs = await submissions_collection.find({"eventId": event_id}).to_list(None)

        # Group submissions by roundId
        rounds_data = []
        for round_item in event.get("rounds", []):
            r_id = round_item["id"]

            round_submissions = []
            for s in subs:
                if s["roundId"] == r_id:
                    tid = str(s["teamId"])
                    round_submissions.append({
                        "teamId": tid,
                        "teamName": teams_map[tid]["teamName"] if tid in teams_map else "Unknown Team",
                        "submissionUrl": s.get("submissionUrl"),
                        "score": s.get("score"),
                    })

            rounds_data.append({
                "id": r_id,
                "name": round_item.get("description") or r_id,
                "submissions": round_submissions,
            })

        return {
            "success": True,
            "data": {
                "teamsCount": len(teams),
                "rounds": rounds_data
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/events/{event_id}/rounds/{round_id}/submissions/{team_id}")
async def update_score(event_id: str, round_id: str, team_id: str, payload: dict,
                       user=Depends(get_current_user)):

    score = payload.get("score")
    if score is None:
        raise HTTPException(status_code=400, detail="Score missing")

    # Verify event belongs to organizer
    event = await events_collection.find_one(
        {"_id": ObjectId(event_id), "organizerId": ObjectId(user["id"])}
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Update submission score
    await submissions_collection.update_one(
        {
            "eventId": event_id,
            "teamId": team_id,
            "roundId": round_id,
        },
        {
            "$set": {"score": score}
        },
        upsert=True
    )

    return {"success": True, "message": "Score updated"}

@router.get("/get-teams/{event_id}")
async def get_teams(event_id: str, user=Depends(get_current_user)):

    teams = teams_collection.find({"eventId": event_id})
    team_docs = await teams.to_list(None)

    result = []

    for t in team_docs:
        leader = await users_collection.find_one({"_id": ObjectId(t["leaderId"])})
        members = []

        for m in t.get("members", []):
            user_doc = await users_collection.find_one({"_id": ObjectId(m.get("userId"))})
            if user_doc:
                members.append({
                    "name": user_doc.get("name"),
                    "email": user_doc.get("email"),
                    "userId": str(user_doc["_id"])
                })

        result.append({
            "teamId": str(t["_id"]),
            "teamName": t["teamName"],
            "leader": {
                "name": leader.get("name") if leader else None,
                "email": leader.get("email") if leader else None,
                "userId": t["leaderId"]
            },
            "members": members,
            "eventId": t["eventId"]
        })

    return {"success": True, "data": result}


@router.delete("/delete-team/{team_id}")
async def delete_team(team_id: str, user=Depends(get_current_user)):

    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    await teams_collection.delete_one({"_id": ObjectId(team_id)})

    # Delete from all rounds submissions also
    await db["rounds"].update_many(
        {},
        {"$pull": {"submissions": {"teamId": team_id}}}
    )

    return {"success": True, "message": "Team deleted"}

@router.get("/events/{event_id}/submissions")
async def get_all_submissions(event_id: str, user=Depends(get_current_user)):

    # Get all submissions for this event
    cursor = submissions_collection.find({"eventId": event_id})
    submissions = await cursor.to_list(None)

    results = []

    for sub in submissions:

        team_id = sub.get("teamId")
        team = await teams_collection.find_one({"_id": ObjectId(team_id)})

        if not team:
            continue  # skip broken entries

        # Extract leader name
        leader_id = team.get("leaderId")
        leader_obj = next((m for m in team.get("members", []) if m["userId"] == leader_id), None)

        leader_name = f"{leader_obj.get('firstName','')} {leader_obj.get('lastName','')}".strip() if leader_obj else "Unknown"

        # Build unified shape
        item = {
            "submissionId": str(sub["_id"]),
            "eventId": sub["eventId"],
            "teamId": team_id,
            "teamName": team.get("teamName"),
            "leaderName": leader_name,
            "roundId": sub.get("roundId"),
            "submittedAt": sub.get("submittedAt"),

            # round-specific fields (safe defaults)
            "fileUrl": sub.get("fileUrl"),
            "repo": sub.get("repo"),
            "video": sub.get("video"),
        }

        results.append(item)

    # Group by round
    grouped = {
        "ppt": [s for s in results if s["roundId"] == "ppt"],
        "repo": [s for s in results if s["roundId"] == "repo"],
        "viva": [s for s in results if s["roundId"] == "viva"],
    }

    return {
        "success": True,
        "data": grouped
    }