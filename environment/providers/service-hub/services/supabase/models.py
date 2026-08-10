"""Request bodies for the Supabase routes.

Only bodies are modelled. Responses stay as plain dicts because the point of a
simulator is to return the *upstream's* shapes byte-for-byte -- PostgREST's bare
arrays, Storage's ``{"name": ...}`` on create, the ``signedURL`` casing -- and a
response model would quietly normalise exactly the details an agent is meant to
encounter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BucketCreateBody(BaseModel):
    id: str = Field(..., description="Bucket id, unique within the project", examples=["exports"])
    name: Optional[str] = Field(None, description="Display name; defaults to the id")
    public: Optional[bool] = Field(False, description="Public buckets are readable by anon")
    file_size_limit: Optional[int] = Field(None, description="Per-object byte cap")
    allowed_mime_types: Optional[List[str]] = None


class ObjectListBody(BaseModel):
    prefix: Optional[str] = Field("", description="Path prefix filter, e.g. 'invoices/'")
    limit: Optional[int] = 100
    offset: Optional[int] = 0


class SignBody(BaseModel):
    expiresIn: Optional[int] = Field(3600, description="Seconds until the signed URL expires")


class BroadcastMessage(BaseModel):
    topic: str = Field(..., description="Channel name, e.g. 'room:orbit-standup'")
    event: Optional[str] = "broadcast"
    payload: Optional[Dict[str, Any]] = None


class BroadcastBody(BaseModel):
    messages: List[BroadcastMessage]
