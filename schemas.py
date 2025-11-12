"""
Database Schemas for SkillSwap

Each Pydantic model corresponds to a MongoDB collection. The collection name
is the lowercase of the class name.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class Userprofile(BaseModel):
    """
    Collection: userprofile
    Represents a SkillSwap user profile with teach/learn skills and meta info.
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Unique email")
    bio: Optional[str] = Field(None, description="Short bio")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")
    teach_skills: List[str] = Field(default_factory=list, description="Skills user can teach")
    learn_skills: List[str] = Field(default_factory=list, description="Skills user wants to learn")
    location: Optional[str] = Field(None, description="City/Country or timezone")
    availability: Optional[str] = Field(None, description="Availability text, e.g., evenings/weekends")
    skillcoins: int = Field(0, description="Reward balance")

class Swipe(BaseModel):
    """
    Collection: swipe
    Records a swipe action (like or pass) from a user to another user.
    """
    user_id: str
    target_id: str
    action: Literal["like", "pass"]

class Match(BaseModel):
    """
    Collection: match
    Represents a mutual like between two users.
    """
    user_a: str
    user_b: str
    status: Literal["pending", "active", "blocked"] = "pending"

class Session(BaseModel):
    """
    Collection: session
    Represents a scheduled learning session between matched users.
    """
    match_id: str
    host_id: str
    guest_id: str
    topic: Optional[str] = None
    scheduled_time: Optional[str] = None  # ISO string for simplicity
    mode: Literal["chat", "video"] = "chat"
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"

class Rewardtransaction(BaseModel):
    """
    Collection: rewardtransaction
    Ledger of SkillCoin adjustments.
    """
    user_id: str
    amount: int
    reason: str
