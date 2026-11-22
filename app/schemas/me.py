# OfficerPath AI — PDF Engine (Phase 2, M3)
# Pydantic v2 schemas for the student profile endpoints (GAP-1).
# The profile is engine-DB data (doc 03 §2.1); Supabase Auth owns
# identity (email/password) and is never duplicated here. The
# user_id always comes from the verified JWT, never from the body.

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    preferred_exam: str | None = Field(default=None, max_length=64)
    education_level: str | None = Field(default=None, max_length=64)


class ProfileResponse(BaseModel):
    user_id: str
    email: str | None = None
    full_name: str
    phone: str | None = None
    preferred_exam: str | None = None
    education_level: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
