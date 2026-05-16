"""Support router - AI customer support chatbot."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.services.support_bot import support_bot

router = APIRouter(prefix="/support", tags=["support"])


class SupportMessageIn(BaseModel):
    message: str


class SupportMessageOut(BaseModel):
    reply: str


@router.post("/chat", response_model=SupportMessageOut)
async def support_chat(
    data: SupportMessageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send a message to the AI support bot."""
    # Load last 10 messages for context
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    past_messages = result.scalars().all()
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(past_messages)
    ]

    # Get AI response
    reply = await support_bot.answer(data.message, history=history)

    # Save user message
    user_msg = ChatMessage(user_id=user.id, role="user", content=data.message)
    db.add(user_msg)

    # Save bot reply
    bot_msg = ChatMessage(user_id=user.id, role="assistant", content=reply)
    db.add(bot_msg)

    await db.commit()

    return SupportMessageOut(reply=reply)
