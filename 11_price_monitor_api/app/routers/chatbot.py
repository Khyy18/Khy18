"""AI chatbot router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db.models import Product, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.routers.deals import _product_to_deal
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chatbot_service import ChatbotService

router = APIRouter(tags=["chat"])

_chatbot = ChatbotService()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Process a chat message and return AI response with product recommendations."""
    result = await _chatbot.answer(data.message, db)

    products = None
    if result["products"]:
        products = [_product_to_deal(p) for p in result["products"]]

    return ChatResponse(reply=result["reply"], products=products)
