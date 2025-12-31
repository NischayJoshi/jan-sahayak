from fastapi import APIRouter, Depends, HTTPException, Form,File, UploadFile
from middlewares.auth_required import get_user as get_current_user, auth_required
from config.db import db
import cloudinary.uploader
from bson import ObjectId
from typing import Optional
from graph.ppt_evaluator import analyze_ppt_endpoint,analyze_ppt_with_gpt
from utils.serializers import serialize_doc, serialize_docs
from datetime import datetime
from graph.github import *

router = APIRouter()

users_collection = db["users"]
events_collection = db["events"]
teams_collection = db["teams"]
submissions_collection = db["submissions"]


@router.get("/get-user")
async def get_user_route(user=Depends(auth_required)):
    return {"success": True, "data": user}


@router.get("/events/{event_id}")
async def get_event(event_id: str, user=Depends(get_current_user)):
    try:
        event = await events_collection.find_one({"_id": ObjectId(event_id)})
    except Exception:
        raise HTTPException(400, "Invalid event id")
    if not event:
        raise HTTPException(404, "Event not found")
    return {"success": True, "data": serialize_doc(event)}


@router.post("/events/{event_id}/teams/create")
async def create_team(event_id: str, teamName: str = Form(...), user=Depends(get_current_user)):
    try:
        event = await events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(400, "Invalid event id")

    if not event:
        raise HTTPException(404, "Event not found")

    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc["_id"])

    existing = await teams_collection.find_one({"eventId": event_id, "members.userId": user_id})
    if existing:
        raise HTTPException(400, "Already registered in a team for this event")

    team_data = {
        "eventId": event_id,
        "teamName": teamName,
        "leaderId": user_id,
        "members": [{
            "userId": user_id,
            "firstName": user_doc.get("firstName", ""),
            "lastName": user_doc.get("lastName", ""),
            "email": user_doc.get("email", "")
        }],
        "requests": [],
        "invites": [],
        "minSize": event.get("minMembers", 1),
        "maxSize": event.get("maxMembers", 1),
        "isActive": True if event.get("minMembers", 1) <= 1 else False,
        "createdAt": datetime.utcnow()
    }

    result = await teams_collection.insert_one(team_data)
    await teams_collection.update_one(
        {"_id": result.inserted_id},
        {"$set": {"teamId": str(result.inserted_id)}}
    )

    created = await teams_collection.find_one({"_id": result.inserted_id})
    return {"success": True, "data": serialize_doc(created)}


@router.post("/events/{event_id}/teams/{team_id}/requests/send")
async def send_request(event_id: str, team_id: str, user=Depends(get_current_user)):
    try:
        team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    except:
        raise HTTPException(400, "Invalid team id")

    if not team:
        raise HTTPException(404, "Team not found")

    if team.get("eventId") != event_id:
        raise HTTPException(400, "Team doesn't belong to event")

    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc["_id"])

    existing = await teams_collection.find_one({"eventId": event_id, "members.userId": user_id})
    if existing:
        raise HTTPException(400, "Already registered in another team")

    another_req = await teams_collection.find_one({
        "eventId": event_id,
        "requests": {"$elemMatch": {"userId": user_id, "status": "pending"}}
    })

    if another_req:
        raise HTTPException(400, "Already sent a pending request")

    req = {
        "requestId": str(ObjectId()),
        "userId": user_id,
        "firstName": user_doc.get("firstName", ""),
        "lastName": user_doc.get("lastName", ""),
        "email": user_doc.get("email", ""),
        "status": "pending",
        "createdAt": datetime.utcnow()
    }

    await teams_collection.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"requests": req}}
    )

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}


@router.get("/events/{event_id}/teams/open")
async def get_open(event_id: str):
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")

    max_members = int(event.get("maxMembers", 0))
    teams = await teams_collection.find({"eventId": event_id}).to_list(None)

    open_teams = []
    for t in teams:
        members_count = len(t.get("members", []))
        pending_count = len([x for x in t.get("requests", []) if x["status"] == "pending"])
        if members_count + pending_count < max_members:
            open_teams.append(t)

    return {"success": True, "data": serialize_docs(open_teams)}


@router.post("/events/{event_id}/teams/{team_id}/requests/{request_id}/accept")
async def accept_request(event_id, team_id, request_id, user=Depends(get_current_user)):

    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if str(user["id"]) != team["leaderId"]:
        raise HTTPException(403, "Only leader can accept")

    req = next((r for r in team["requests"] if r["requestId"] == request_id and r["status"] == "pending"), None)

    if not req:
        raise HTTPException(404, "Request not pending")

    member_doc = {
        "userId": req["userId"],
        "firstName": req.get("firstName", ""),
        "lastName": req.get("lastName", ""),
        "email": req.get("email", "")
    }

    await teams_collection.update_one(
        {"_id": ObjectId(team_id)},
        {
            "$push": {"members": member_doc},
            "$pull": {"requests": {"requestId": request_id}}
        }
    )

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}


@router.post("/events/{event_id}/teams/{team_id}/requests/{request_id}/reject")
async def reject_request(event_id, team_id, request_id, user=Depends(get_current_user)):

    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if str(user["id"]) != team["leaderId"]:
        raise HTTPException(403, "Only leader can reject")

    await teams_collection.update_one(
        {"_id": ObjectId(team_id)},
        {"$pull": {"requests": {"requestId": request_id}}}
    )

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}


@router.post("/events/{event_id}/teams/{team_id}/members/remove")
async def remove_member(event_id, team_id, userId: str = Form(...), user=Depends(get_current_user)):

    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    caller = str(user["id"])
    leader = team["leaderId"]

    if caller != leader and caller != userId:
        raise HTTPException(403, "Not allowed")

    await teams_collection.update_one(
        {"_id": ObjectId(team_id)},
        {"$pull": {"members": {"userId": userId}}}
    )

    updated = await teams_collection.find_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": serialize_doc(updated)}


@router.delete("/events/{event_id}/teams/{team_id}")
async def delete_team(event_id, team_id, user=Depends(get_current_user)):
    team = await teams_collection.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(404, "Team not found")

    if str(user["id"]) != team["leaderId"]:
        raise HTTPException(403, "Only leader can delete team")

    await teams_collection.delete_one({"_id": ObjectId(team_id)})
    return {"success": True, "data": {"deleted": True}}


@router.get("/events/{event_id}/my-team")
async def my_team(event_id: str, user=Depends(get_current_user)):
    team = await teams_collection.find_one({
        "eventId": event_id,
        "members.userId": str(user["id"])
    })
    if not team:
        return {"success": True, "data": None}

    return {"success": True, "data": serialize_doc(team)}

from pydantic import BaseModel
class PPTAnalysisInput(BaseModel):
    topic: str
    file_url: Optional[str] = None


async def run_ppt_analysis(topic: str, file_url: str):
    state = {
        "content": topic,
        "file_path": file_url,
    }
    result_state = await analyze_ppt_with_gpt(state)
    return result_state["output"]




@router.post("/events/{event_id}/submit/ppt")
async def submit_ppt(
    event_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    # fetch event
    event = await events_collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(404, "Event not found")

    topic = event.get("description") or "PPT Submission"

    # fetch user
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc["_id"])

    # fetch team
    team = await teams_collection.find_one({"eventId": event_id, "members.userId": user_id})
    if not team:
        raise HTTPException(400, "You are not part of any team")

    # no duplicate submissions
    existing = await submissions_collection.find_one({
        "eventId": event_id,
        "teamId": str(team["_id"]),
        "roundId": "ppt",
    })
    if existing:
        raise HTTPException(400, "PPT already submitted for this round")

    # upload file
    try:
        upload = cloudinary.uploader.upload(file.file, resource_type="auto")
        file_url = upload.get("secure_url")
    except Exception as e:
        raise HTTPException(500, str(e))

    # run AI analysis
    ai_result = await run_ppt_analysis(topic, file_url)

    # save submission
    submission = {
        "eventId": event_id,
        "teamId": str(team["_id"]),
        "roundId": "ppt",
        "topic": topic,
        "fileUrl": file_url,
        "aiResult": ai_result,
        "submittedAt": datetime.utcnow()
    }

    result = await submissions_collection.insert_one(submission)
    submission["_id"] = str(result.inserted_id)

    return {"success": True, "data": submission}



@router.post("/events/{event_id}/submit/repo")
async def submit_repo(
    event_id: str,
    repo: str = Form(...),
    video: str = Form(...),
    user=Depends(get_current_user)
):
    # ---------- USER / TEAM VALIDATION ----------
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc["_id"])

    team = await teams_collection.find_one({
        "eventId": event_id,
        "members.userId": user_id
    })
    if not team:
        raise HTTPException(400, "You are not part of any team")

    existing = await submissions_collection.find_one({
        "eventId": event_id,
        "teamId": str(team["_id"]),
        "roundId": "repo",
    })
    if existing:
        raise HTTPException(400, "Repository already submitted for this round")

    # ---------- INSERT INITIAL SUBMISSION ----------
    submission = {
        "eventId": event_id,
        "teamId": str(team["_id"]),
        "roundId": "repo",
        "repo": repo,
        "video": video,
        "submittedAt": datetime.utcnow(),
        "evaluation": None,     
        "status": "processing"
    }

    result = await submissions_collection.insert_one(submission)
    submission_id = result.inserted_id

    # ---------- RUN THE EVALUATOR ----------
    loop = asyncio.get_event_loop()

    try:
        # 1. Clone + static analysis (sync)
        repo_path, chunks, radon_raw, pylint_score, plag, structure = \
            await loop.run_in_executor(
                executor,
                evaluate_repo_blocking,
                repo,
                ""            # description optional
            )

        # 2. LLM scoring (async)
        logic, rel, style, llm_fb = await llm_code_rating("", chunks)

        # 3. Code smells + scores
        code_smells = detect_code_smells(radon_raw, pylint_score, plag, structure)
        risk_score = compute_risk_score(plag, pylint_score, code_smells, structure)
        final_score = compute_final_score(plag, logic, rel, style, pylint_score, structure)
        rubric = rubric_from_score(final_score)

        # 4. Mentor + rewrite
        mentor_md = await generate_markdown_mentor("", {
            "final_score": final_score,
            "rubric": rubric,
            "risk_score": risk_score,
            "structure": structure,
            "plagiarism": plag,
            "logic": logic,
            "relevance": rel,
            "style": style,
            "pylint_score": pylint_score,
            "code_smells": code_smells,
            "files_analyzed": len(chunks),
        })

        rewrite_md = await generate_rewrite_suggestions("", chunks, code_smells)

        # 5. PDF
        pdf_bytes = generate_pdf_report({
            "final_score": final_score,
            "rubric": rubric,
            "risk_score": risk_score,
            "structure": structure,
            "plagiarism": plag,
            "logic": logic,
            "relevance": rel,
            "style": style,
            "pylint_score": pylint_score,
            "code_smells": code_smells,
            "files_analyzed": len(chunks),
        })

        report_pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # ---------- FINAL AI EVALUATION JSON ----------
        evaluation = {
            "final_score": final_score,
            "rubric": rubric,
            "risk_score": risk_score,
            "structure": structure,
            "plagiarism": plag,
            "logic": logic,
            "relevance": rel,
            "style": style,
            "pylint_score": pylint_score,
            "code_smells": code_smells,
            "llm_feedback": llm_fb,
            "mentor_summary_markdown": mentor_md,
            "rewrite_suggestions_markdown": rewrite_md,
            "report_pdf_base64": report_pdf_base64,
            "files_analyzed": len(chunks),
        }

        # ---------- SAVE RESULT INTO SAME SUBMISSION ----------
        await submissions_collection.update_one(
            {"_id": submission_id},
            {
                "$set": {
                    "evaluation": evaluation,
                    "status": "completed"
                }
            }
        )

        return {
            "success": True,
            "message": "Repository submitted and evaluation completed",
            "submissionId": str(submission_id),
            "evaluation": evaluation
        }

    except Exception as e:
        await submissions_collection.update_one(
            {"_id": submission_id},
            {"$set": {"status": "error", "error": str(e)}}
        )
        raise HTTPException(500, f"Evaluation failed: {str(e)}")


@router.get("/events/{event_id}/my-submissions")
async def my_submissions(event_id: str, user=Depends(get_current_user)):
    print( "Fetching submissions for user:", user)
    user_doc = await users_collection.find_one({"_id": ObjectId(user["id"])})
    if not user_doc:
        raise HTTPException(404, "User not found")

    user_id = str(user_doc["_id"])
    print( "User ID:", user_id)
    team = await teams_collection.find_one({"eventId": event_id, "members.userId": user_id})
    if not team:
        return {"success": True, "data": {}}

    subs = await submissions_collection.find({
        "eventId": event_id,
        "teamId": str(team["_id"])
    }).to_list(None)

    serialized = serialize_docs(subs)
    indexed = {s["roundId"]: s for s in serialized}

    return {"success": True, "data": indexed}

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/events/{event_id}/leaderboard")
async def event_leaderboard(event_id: str,user=Depends(get_current_user)):
    n = 0
    submissions_1 = await submissions_collection.find({
        "eventId": event_id,
        "roundId": "ppt"
    }).to_list(None)
    submissions_2 = await submissions_collection.find({
        "eventId": event_id,
        "roundId": "repo",
        "status": "completed"
    }).to_list(None)
    submissions_3 = await submissions_collection.find({
        "eventId": event_id,
        "roundId": "viva",
    }).to_list(None)

    leaderboard_1 = []
    for sub in submissions_1:
        team = await teams_collection.find_one({"_id": ObjectId(sub["teamId"])})
        if not team:
            continue
        n+=1
        score = sub.get("aiResult", {}).get("score", {}).get("overall_score", 0)
        leaderboard_1.append({
            "teamName": team["teamName"],
            "teamId": str(team["_id"]),
            "score": score,
            "roundId": "ppt"
        })
    leaderboard_2 = []
    for sub in submissions_2:
        team = await teams_collection.find_one({"_id": ObjectId(sub["teamId"])})
        if not team:
            continue
        evaluation = sub.get("evaluation", {})
        score = evaluation.get("final_score", 0)
        n+=1
        leaderboard_2.append({
            "teamName": team["teamName"],
            "teamId": str(team["_id"]),
            "score": score,
            "roundId": "repo"
        })
    
    leaderboard_3 = []
    for sub in submissions_3:
        team = await teams_collection.find_one({"_id": ObjectId(sub["teamId"])})
        if not team:
            continue
        n+=1
        score = sub.get("aiResult", {}).get("vivaScore", 0)
        leaderboard_3.append({
            "teamName": team["teamName"],
            "teamId": str(team["_id"]),
            "score": score,
            "roundId": "viva"
        })
    combined_scores = {}
    for entry in leaderboard_1 + leaderboard_2+leaderboard_3:
        team_id = entry["teamId"]
        if team_id not in combined_scores:
            combined_scores[team_id] = {
                "teamName": entry["teamName"],
                "teamId": team_id,
                "totalScore": 0
            }
        combined_scores[team_id]["totalScore"] += entry["score"]
        combined_scores[team_id]["totalScore"] /= n if n > 0 else 1  



    return {"success": True, "data": {
        "ppt_leaderboard": sorted(leaderboard_1, key=lambda x: x["score"], reverse=True),
        "repo_leaderboard": sorted(leaderboard_2, key=lambda x: x["score"], reverse=True),
        "overall_leaderboard": sorted(combined_scores.values(), key=lambda x: x["totalScore"], reverse=True)
    }}