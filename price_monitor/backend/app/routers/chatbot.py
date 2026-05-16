"""Chatbot router - AI chatbot with product search."""
from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.chat import ChatMessageIn, ChatMessageOut, ChatResponse
from app.services.chatbot_service import chatbot_service

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def send_message(
    data: ChatMessageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send a message to the AI chatbot."""

    # Save user message
    user_msg = ChatMessage(user_id=user.id, role="user", content=data.message)
    db.add(user_msg)
    await db.commit()

    # Get AI response
    result = await chatbot_service.answer(data.message, db)

    # Save assistant message
    assistant_msg = ChatMessage(user_id=user.id, role="assistant", content=result["reply"])
    db.add(assistant_msg)
    await db.commit()

    return ChatResponse(reply=result["reply"], product_ids=result["product_ids"])

@router.get("/history", response_model=list[ChatMessageOut])
async def get_chat_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get chat history for the current user."""
    from sqlalchemy import select

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        ChatMessageOut(
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in reversed(messages)
    ]
