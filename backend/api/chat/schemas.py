"""
Chat API request/response schemas
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID


class MessageCreate(BaseModel):
    """Schema for creating a new message"""
    content: str = Field(..., min_length=1, max_length=10000)


class Message(BaseModel):
    """Schema for a chat message"""
    role: str = Field(..., description="user or assistant")
    content: str
    timestamp: datetime


class ChatSessionCreate(BaseModel):
    """Schema for creating a new chat session"""
    initial_message: Optional[str] = Field(None, description="Optional first message")


class ChatSessionResponse(BaseModel):
    """Schema for chat session response"""
    id: UUID
    user_id: UUID
    scraper_id: Optional[UUID] = None
    messages: List[Message] = []
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatSessionListResponse(BaseModel):
    """Schema for listing chat sessions"""
    id: UUID
    status: str
    message_count: int
    last_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    """Schema for message response after sending"""
    message: Message
    session: ChatSessionResponse
