from __future__ import annotations

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str
    timestamp: int | None = None


class AddRequest(BaseModel):
    request_id: str
    messages: list[Message]
    user_id: str
    session_id: str


class AddResponse(BaseModel):
    success: bool = True
    request_id: str
    user_id: str
    session_id: str


class SearchRequest(BaseModel):
    query: str
    options: list[str] | None = None
    user_id: str
    session_id: str | None = None
    top_k: int = Field(default=100, ge=1, le=100)


class SearchResultItem(BaseModel):
    id: str
    content: str
    score: float | None = None
    created_at: str | None = None


class SearchResponse(BaseModel):
    data: list[SearchResultItem]
