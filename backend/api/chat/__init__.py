"""
Chat API router
"""
import traceback
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from datetime import datetime
from uuid import UUID
import uuid

from core.database.connection import get_db
from core.database.models import ChatSession, User, Scraper
from api.auth.dependencies import get_current_user
from api.chat.schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionListResponse,
    MessageCreate,
    ChatMessageResponse,
    Message
)
from agents.primary.agent import PrimaryAgent
from urllib.parse import urlparse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new chat session"""
    logger.info(f"[CREATE_SESSION] User {current_user.id} creating new chat session")
    logger.info(f"[CREATE_SESSION] Initial message: {session_data.initial_message}")

    # Create new chat session
    messages = []

    # If initial message provided, process it
    if session_data.initial_message:
        logger.info(f"[CREATE_SESSION] Processing initial message")
        # Create user message
        user_msg = {
            "role": "user",
            "content": session_data.initial_message,
            "timestamp": datetime.utcnow().isoformat()
        }
        messages.append(user_msg)

        # Get AI response
        agent = PrimaryAgent()
        try:
            agent_response = await agent.process_message(
                session_data.initial_message,
                [],  # Empty history for first message
                session_id=None  # Session ID will be set after creation
            )

            assistant_msg = {
                "role": "assistant",
                "content": agent_response["message"],
                "timestamp": datetime.utcnow().isoformat()
            }

            # Store tool calls if any
            if agent_response.get("tool_calls"):
                assistant_msg["tool_calls_made"] = agent_response["tool_calls"]

            messages.append(assistant_msg)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process message: {str(e)}"
            )

    # Create session in database
    new_session = ChatSession(
        id=uuid.uuid4(),
        user_id=current_user.id,
        messages=messages,
        status="active"
    )

    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return new_session


@router.get("/sessions", response_model=List[ChatSessionListResponse])
async def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all chat sessions for current user"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()

    # Transform to list response format
    response = []
    for session in sessions:
        messages = session.messages or []
        last_message = messages[-1]["content"] if messages else None

        response.append(ChatSessionListResponse(
            id=session.id,
            status=session.status,
            message_count=len(messages),
            last_message=last_message[:100] if last_message else None,  # Truncate
            created_at=session.created_at,
            updated_at=session.updated_at
        ))

    return response


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific chat session with full message history"""
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )

    return session


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    session_id: UUID,
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message in a chat session"""
    logger.info(f"[SEND_MESSAGE] User {current_user.id} sending message to session {session_id}")
    logger.info(f"[SEND_MESSAGE] Message content: {message_data.content}")

    # Get session
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        logger.error(f"[SEND_MESSAGE] Session {session_id} not found for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )

    # Get current messages
    messages = session.messages or []
    logger.info(f"[SEND_MESSAGE] Current message count: {len(messages)}")

    # Add user message
    user_msg = {
        "role": "user",
        "content": message_data.content,
        "timestamp": datetime.utcnow().isoformat()
    }
    messages.append(user_msg)
    logger.info(f"[SEND_MESSAGE] Added user message, new count: {len(messages)}")

    # Get AI response
    logger.info(f"[SEND_MESSAGE] Calling Primary Agent to process message")
    agent = PrimaryAgent()
    try:
        agent_response = await agent.process_message(
            message_data.content,
            messages[:-1],  # Pass history excluding current user message
            session_id=str(session_id)
        )
        logger.info(f"[SEND_MESSAGE] Agent response received")
        logger.info(f"[SEND_MESSAGE] Agent response: {agent_response.get('message', '')[:100]}...")

        # Create assistant message
        assistant_msg = {
            "role": "assistant",
            "content": agent_response["message"],
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store tool calls if any (for debugging/history)
        if agent_response.get("tool_calls"):
            assistant_msg["tool_calls_made"] = agent_response["tool_calls"]
            logger.info(f"[SEND_MESSAGE] Agent made {len(agent_response['tool_calls'])} tool calls")

        messages.append(assistant_msg)
        logger.info(f"[SEND_MESSAGE] Added assistant message, new count: {len(messages)}")

        # If a scraper was created, add it to the database
        created_scraper = None
        if agent_response.get("scraper_created"):
            logger.info(f"[SEND_MESSAGE] Agent created scraper, saving to database")
            scraper_data = agent_response["scraper_created"]

            # Extract domain from URL
            try:
                parsed_url = urlparse(scraper_data["target_url"])
                target_domain = parsed_url.netloc
            except Exception:
                target_domain = None

            # Create the scraper in the database
            new_scraper = Scraper(
                id=uuid.uuid4(),
                user_id=current_user.id,
                name=scraper_data["name"],
                target_url=scraper_data["target_url"],
                target_domain=target_domain,
                scraping_config=scraper_data["config"],
                schedule_cron=scraper_data.get("schedule_cron"),
                status="inactive"  # Will be 'active' after Secondary Agent generates code
            )

            db.add(new_scraper)

            # CRITICAL: Commit the scraper FIRST before linking to session
            # This prevents foreign key violations
            await db.commit()
            await db.refresh(new_scraper)
            logger.info(f"[SEND_MESSAGE] Scraper {new_scraper.id} committed to database")

            # Now link scraper to session (safe because scraper exists in DB)
            session.scraper_id = new_scraper.id
            created_scraper = new_scraper

            # Add system message about scraper creation
            system_msg = {
                "role": "system",
                "content": f"Scraper '{scraper_data['name']}' created with ID: {new_scraper.id}",
                "timestamp": datetime.utcnow().isoformat(),
                "scraper_id": str(new_scraper.id)
            }
            messages.append(system_msg)
            logger.info(f"[SEND_MESSAGE] Scraper linked to session, system message added")

    except Exception as e:
        logger.info(f"Error in send_message: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )

    # Update session
    logger.info(f"[SEND_MESSAGE] Updating session with {len(messages)} total messages")
    session.messages = messages
    session.updated_at = datetime.utcnow()

    # CRITICAL: Flag the JSONB field as modified so SQLAlchemy commits the change
    flag_modified(session, "messages")

    await db.commit()
    await db.refresh(session)
    logger.info(f"[SEND_MESSAGE] Session updated successfully with {len(session.messages)} messages")

    # Return the assistant's message and updated session
    response = ChatMessageResponse(
        message=Message(**assistant_msg),
        session=session
    )
    logger.info(f"[SEND_MESSAGE] Returning response with {len(session.messages)} messages in session")
    logger.info(f"[SEND_MESSAGE] Response message content: {assistant_msg['content'][:100]}...")
    return response


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a chat session"""
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )

    await db.delete(session)
    await db.commit()

    return None
