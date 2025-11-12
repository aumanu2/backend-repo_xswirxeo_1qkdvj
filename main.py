import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="SkillSwap API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Utility ----------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

# ---------- Request Models ----------

class UserCreate(BaseModel):
    name: str
    email: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    teach_skills: List[str] = []
    learn_skills: List[str] = []
    location: Optional[str] = None
    availability: Optional[str] = None

class SwipeAction(BaseModel):
    user_id: str
    target_id: str
    action: str  # 'like' or 'pass'

class SessionCreate(BaseModel):
    match_id: str
    topic: Optional[str] = None
    scheduled_time: Optional[str] = None
    mode: str = "chat"  # 'chat' or 'video'

# ---------- Core Endpoints ----------

@app.get("/")
def read_root():
    return {"message": "SkillSwap Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# Users
@app.post("/api/users")
def create_or_get_user(payload: UserCreate):
    existing = db["userprofile"].find_one({"email": payload.email})
    if existing:
        existing["id"] = str(existing.pop("_id"))
        return existing
    doc_id = create_document("userprofile", payload.model_dump())
    user = db["userprofile"].find_one({"_id": ObjectId(doc_id)})
    user["id"] = str(user.pop("_id"))
    return user

@app.get("/api/users")
def list_users():
    users = list(db["userprofile"].find())
    for u in users:
        u["id"] = str(u.pop("_id"))
    return users

# Recommendations (AI Matching heuristic)
@app.get("/api/recommendations")
def recommendations(user_id: str, limit: int = 20):
    me = db["userprofile"].find_one({"_id": oid(user_id)})
    if not me:
        raise HTTPException(404, "User not found")

    # Simple heuristic: score by mutual interest overlap
    candidates = list(db["userprofile"].find({"_id": {"$ne": oid(user_id)}}))
    scored = []
    my_teach = set(map(str.lower, me.get("teach_skills", [])))
    my_learn = set(map(str.lower, me.get("learn_skills", [])))

    for c in candidates:
        teach = set(map(str.lower, c.get("teach_skills", [])))
        learn = set(map(str.lower, c.get("learn_skills", [])))
        score = 0
        # I can teach what they want to learn
        score += len(my_teach & learn) * 3
        # They can teach what I want to learn
        score += len(teach & my_learn) * 3
        # general interest overlap
        score += len((my_teach | my_learn) & (teach | learn))
        if score > 0:
            c_copy = dict(c)
            c_copy["id"] = str(c_copy.pop("_id"))
            c_copy["score"] = score
            scored.append(c_copy)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

# Swipes and Matches
@app.post("/api/swipe")
def swipe(payload: SwipeAction):
    if payload.action not in ("like", "pass"):
        raise HTTPException(400, "Invalid action")

    # record swipe
    create_document("swipe", payload.model_dump())

    if payload.action == "like":
        # check mutual like
        mutual = db["swipe"].find_one({
            "user_id": payload.target_id,
            "target_id": payload.user_id,
            "action": "like",
        })
        if mutual:
            # ensure match not already exists
            existing = db["match"].find_one({
                "$or": [
                    {"user_a": payload.user_id, "user_b": payload.target_id},
                    {"user_a": payload.target_id, "user_b": payload.user_id},
                ]
            })
            if not existing:
                match_id = create_document("match", {
                    "user_a": payload.user_id,
                    "user_b": payload.target_id,
                    "status": "active",
                })
                return {"status": "matched", "match_id": match_id}
            else:
                return {"status": "matched", "match_id": str(existing["_id"])}

    return {"status": "recorded"}

@app.get("/api/matches")
def get_matches(user_id: str):
    ms = list(db["match"].find({
        "$or": [{"user_a": user_id}, {"user_b": user_id}],
        "status": "active",
    }))
    enriched = []
    for m in ms:
        other_id = m["user_b"] if m["user_a"] == user_id else m["user_a"]
        other = db["userprofile"].find_one({"_id": oid(other_id)})
        if other:
            other["id"] = str(other.pop("_id"))
        enriched.append({
            "id": str(m["_id"]),
            "other": other,
        })
    return enriched

# Sessions
@app.post("/api/sessions")
def create_session(payload: SessionCreate):
    match = db["match"].find_one({"_id": oid(payload.match_id)})
    if not match:
        raise HTTPException(404, "Match not found")
    session_id = create_document("session", {
        "match_id": payload.match_id,
        "host_id": match["user_a"],
        "guest_id": match["user_b"],
        "topic": payload.topic,
        "scheduled_time": payload.scheduled_time,
        "mode": payload.mode,
        "status": "scheduled",
    })
    return {"id": session_id}

@app.post("/api/sessions/{session_id}/complete")
def complete_session(session_id: str):
    s = db["session"].find_one({"_id": oid(session_id)})
    if not s:
        raise HTTPException(404, "Session not found")
    db["session"].update_one({"_id": s["_id"]}, {"$set": {"status": "completed"}})

    # Reward both users with SkillCoins
    reward = 10
    for uid in [s["host_id"], s["guest_id"]]:
        db["rewardtransaction"].insert_one({
            "user_id": uid,
            "amount": reward,
            "reason": f"Completed session {session_id}",
        })
        db["userprofile"].update_one({"_id": oid(uid)}, {"$inc": {"skillcoins": reward}})
    return {"status": "completed", "skillcoins_awarded": reward}

@app.get("/api/skillcoins")
def get_skillcoins(user_id: str):
    u = db["userprofile"].find_one({"_id": oid(user_id)})
    if not u:
        raise HTTPException(404, "User not found")
    return {"balance": int(u.get("skillcoins", 0))}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
