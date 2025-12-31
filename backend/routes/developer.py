from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import cloudinary.uploader
from middlewares.auth_required import get_user as get_current_user, auth_required
from config.db import db
from bson import ObjectId
from utils.serializers import serialize_doc,serialize_docs

router = APIRouter()

users_collection = db["users"]
events_collection = db["events"]
teams_collection = db["teams"]   
submissions_collection = db["submissions"] 


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



@router.get("/my-events")
async def my_events():
    cursor = events_collection.find({})
    events = await cursor.to_list(None)

    return {
        "success": True,
        "data": serialize_docs(events),
    }

@router.get("/registered")
async def registred_event():
    pass


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

@router.post("/events/{event_id}/teams/create")
async def create_team(event_id: str, teamName: str = Form(...), user=Depends(get_current_user)):
    # fetch event
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")
    # Load full user record from DB (auth returns only id/username/role)
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc.get("_id"))

    # Check max teams
    existing_team_count = await teams_collection.count_documents({"eventId": event_id})
    if existing_team_count >= event.get("maxTeams", 0):
        raise HTTPException(400, "Max teams reached")

    # Prevent duplicate registration
    existing = await teams_collection.find_one({
        "eventId": event_id,
        "members.userId": user_id
    })
    if existing:
        raise HTTPException(400, "You already registered in this event")

    team = {
        "eventId": event_id,
        "name": teamName,
        "members": [
            {
                "userId": user_id,
                "firstName": user_doc.get("firstName") or user_doc.get("firstname") or "",
                "lastName": user_doc.get("lastName") or user_doc.get("lastname") or "",
                "email": user_doc.get("email"),
            }
        ]
    }

    result = await teams_collection.insert_one(team)
    team["_id"] = result.inserted_id
    # add convenient fields
    team["teamId"] = str(result.inserted_id)
    team["teamName"] = teamName
    team["leaderId"] = user_id
    # update the inserted document with leaderId/teamId/teamName for consistency
    await teams_collection.update_one({"_id": result.inserted_id}, {"$set": {"teamId": team["teamId"], "teamName": teamName, "leaderId": user_id}})

    return {"success": True, "data": serialize_doc(team)}

@router.post("/events/{event_id}/teams/join")
async def join_team(event_id: str, teamId: str = Form(...), user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(teamId)})
    if not team:
        raise HTTPException(404, "Team not found")

    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")

    # Load full user record
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc.get("_id"))

    # Already registered?
    members = team.get("members", [])
    already = any(m.get("userId") == user_id for m in members)
    if already:
        raise HTTPException(400, "You already joined this team")

    # Check capacity
    if len(members) >= event.get("maxMembers", 0):
        raise HTTPException(400, "Team is full")

    # Add member
    await teams_collection.update_one(
        {"_id": ObjectId(teamId)},
        {"$push": {"members": {
            "userId": user_id,
            "firstName": user_doc.get("firstName") or user_doc.get("firstname") or "",
            "lastName": user_doc.get("lastName") or user_doc.get("lastname") or "",
            "email": user_doc.get("email"),
        }}}
    )

    updated = await teams_collection.find_one({"_id": ObjectId(teamId)})
    return {"success": True, "data": serialize_doc(updated)}


@router.delete("/events/{event_id}/teams/{team_id}")
async def delete_team(event_id: str, team_id: str, user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")

    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    user_id = str(user_doc.get("_id"))

    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    if user_id != leader:
        raise HTTPException(403, "Only team leader can delete the team")

    await teams_collection.delete_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": {"deleted": True}}


@router.post("/events/{event_id}/teams/{team_id}/members/add")
async def add_member(event_id: str, team_id: str, userId: str = Form(...), user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")

    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    caller_id = str(user_doc.get("_id"))

    # only leader can add
    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    if caller_id != leader:
        raise HTTPException(403, "Only team leader can add members")

    # check user to add exists
    new_user = await users_collection.find_one({"_id": ObjectId(userId)})
    if not new_user:
        raise HTTPException(404, "User to add not found")

    new_user_id = str(new_user.get("_id"))

    # already member?
    if any(m.get("userId") == new_user_id for m in (team.get("members") or [])):
        raise HTTPException(400, "User already a member")

    # check capacity via event
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")
    if len(team.get("members", [])) >= event.get("maxMembers", 0):
        raise HTTPException(400, "Team is full")

    await teams_collection.update_one({"_id": ObjectId(team_id)}, {"$push": {"members": {
        "userId": new_user_id,
        "firstName": new_user.get("firstName") or new_user.get("firstname") or "",
        "lastName": new_user.get("lastName") or new_user.get("lastname") or "",
        "email": new_user.get("email"),
    }}})

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}


@router.post("/events/{event_id}/teams/{team_id}/members/remove")
async def remove_member(event_id: str, team_id: str, userId: str = Form(...), user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")

    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    caller_id = str(user_doc.get("_id"))

    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    # allow leader or self removal
    if caller_id != leader and caller_id != userId:
        raise HTTPException(403, "Only leader can remove other members")

    await teams_collection.update_one({"_id": ObjectId(team_id)}, {"$pull": {"members": {"userId": userId}}})

    # fetch updated
    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    members = updated.get("members", [])

    # if removed leader and members remain, set new leader
    if leader == userId:
        if members:
            new_leader = members[0].get("userId")
            await teams_collection.update_one({"_id": ObjectId(team_id)}, {"$set": {"leaderId": new_leader}})
        else:
            # no members left, delete team
            await teams_collection.delete_one({"_id": ObjectId(team_id)})
            return {"success": True, "data": {"deleted": True}}

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}


@router.post("/events/{event_id}/teams/{team_id}/invite")
async def invite_member(event_id: str, team_id: str, email: str = Form(...), user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")

    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    caller_id = str(user_doc.get("_id"))

    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    if caller_id != leader:
        raise HTTPException(403, "Only team leader can invite members")

    from datetime import datetime
    invite = {"email": email, "status": "pending", "invitedBy": caller_id, "createdAt": datetime.utcnow()}

    await teams_collection.update_one({"_id": ObjectId(team_id)}, {"$push": {"invites": invite}})

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}

@router.get("/events/{event_id}/my-team")
async def my_team(event_id: str, user=Depends(get_current_user)):
    # Load full user to get consistent string id
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc.get("_id"))

    team = await teams_collection.find_one({
        "eventId": event_id,
        "members.userId": user_id
    })
    if not team:
        raise HTTPException(404, "Not registered")

    return {"success": True, "data": serialize_doc(team)}


@router.get("/registered")
async def registred_event(user=Depends(get_current_user)):
    # Return events the current user has registered for (via teams)
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc.get("_id"))

    # find all teams where this user is a member
    cursor = teams_collection.find({"members.userId": user_id})
    teams = await cursor.to_list(None)
    event_ids = list({t.get("eventId") for t in teams if t.get("eventId")})

    # fetch events
    events = []
    for eid in event_ids:
        try:
            ev = await events_collection.find_one({"_id": ObjectId(eid)})
            if ev:
                events.append(ev)
        except Exception:
            # skip invalid ids
            continue

    return {"success": True, "data": serialize_docs(events)}

from fastapi import APIRouter, Depends, HTTPException, Form
from datetime import datetime
from bson import ObjectId
from middlewares.auth_required import get_user as get_current_user, auth_required



@router.post("/events/{event_id}/teams/{team_id}/requests/send")
async def send_join_request(event_id: str, team_id: str, user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")
    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    user_id = str(user_doc.get("_id"))
    if any(m.get("userId") == user_id for m in (team.get("members") or [])):
        raise HTTPException(400, "You are already a member")
    if any(r.get("userId") == user_id and r.get("status") == "pending" for r in (team.get("requests") or [])):
        raise HTTPException(400, "Request already pending")
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")
    if len(team.get("members", [])) >= event.get("maxMembers", 0):
        raise HTTPException(400, "Team is full")
    request_obj = {
        "requestId": str(ObjectId()),
        "userId": user_id,
        "firstName": user_doc.get("firstName") or user_doc.get("firstname") or "",
        "lastName": user_doc.get("lastName") or user_doc.get("lastname") or "",
        "email": user_doc.get("email"),
        "status": "pending",
        "createdAt": datetime.utcnow(),
    }
    await teams_collection.update_one({"_id": ObjectId(team_id)}, {"$push": {"requests": request_obj}})
    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}

@router.get("/events/{event_id}/teams/open")
async def list_open_teams(event_id: str):
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")
    cursor = teams_collection.find({
        "eventId": event_id,
        "$expr": {"$lt": [{"$size": {"$ifNull": ["$members", []]}}, event.get("maxMembers", 0)]}
    })
    teams = await cursor.to_list(None)
    return {"success": True, "data": serialize_docs(teams)}

@router.get("/events/{event_id}/teams/{team_id}/requests")
async def get_team_requests(event_id: str, team_id: str, user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")
    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    caller_id = str(user_doc.get("_id"))
    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    if caller_id != leader:
        raise HTTPException(403, "Only team leader can view requests")
    requests = team.get("requests", []) or []
    return {"success": True, "data": requests}

@router.post("/events/{event_id}/teams/{team_id}/requests/{request_id}/accept")
async def accept_join_request(event_id: str, team_id: str, request_id: str, user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")
    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    caller_id = str(user_doc.get("_id"))
    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    if caller_id != leader:
        raise HTTPException(403, "Only team leader can accept requests")
    req = None
    for r in team.get("requests", []):
        if r.get("requestId") == request_id and r.get("status") == "pending":
            req = r
            break
    if not req:
        raise HTTPException(404, "Request not found or not pending")
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")
    if len(team.get("members", [])) >= event.get("maxMembers", 0):
        raise HTTPException(400, "Team is full")
    await teams_collection.update_one({"_id": ObjectId(team_id)}, {"$push": {"members": {
        "userId": req["userId"],
        "firstName": req.get("firstName", ""),
        "lastName": req.get("lastName", ""),
        "email": req.get("email", ""),
    }}})
    await teams_collection.update_one({"_id": ObjectId(team_id), "requests.requestId": request_id}, {"$set": {"requests.$.status": "accepted"}})
    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}

@router.post("/events/{event_id}/teams/{team_id}/requests/{request_id}/reject")
async def reject_join_request(event_id: str, team_id: str, request_id: str, reason: str = Form(None), user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")
    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team does not belong to this event")
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")
    caller_id = str(user_doc.get("_id"))
    leader = team.get("leaderId") or (team.get("members") or [])[0].get("userId")
    if caller_id != leader:
        raise HTTPException(403, "Only team leader can reject requests")
    found = False
    for r in team.get("requests", []):
        if r.get("requestId") == request_id and r.get("status") == "pending":
            found = True
            break
    if not found:
        raise HTTPException(404, "Request not found or not pending")
    update = {"requests.$.status": "rejected"}
    if reason:
        update["requests.$.reason"] = reason
    await teams_collection.update_one({"_id": ObjectId(team_id), "requests.requestId": request_id}, {"$set": update})
    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}
