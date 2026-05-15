"""FastAPI приложение REST API AI-агентства для B2B-клиентов."""

import asyncio
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel

import config
import database
import billing
import pipeline
import pricing
from api.auth import get_current_client
from models import OrderStatus, ServiceType

app = FastAPI(title="AI Agency REST API", version="1.0.0")


# --- Request/Response модели ---

class OrderCreateRequest(BaseModel):
    """Запрос на создание заказа."""
    service_type: str
    input_text: str
    urgent: bool = False


class OrderCreateResponse(BaseModel):
    """Ответ на создание заказа."""
    order_id: int
    status: str
    price: float


class OrderStatusResponse(BaseModel):
    """Ответ со статусом заказа."""
    order_id: int
    status: str
    service_type: str
    created_at: str
    price: float


class OrderResultResponse(BaseModel):
    """Ответ с результатом заказа."""
    order_id: int
    result_text: str


# --- Background task ---

async def _process_order_background(order_id: int, service_type: ServiceType, input_text: str) -> None:
    """Фоновая обработка заказа через pipeline."""
    try:
        await database.update_order_status(order_id, OrderStatus.PROCESSING.value)
        result, variant_id = await pipeline.process_order(service_type, input_text)
        if result:
            await database.update_order_status(
                order_id, OrderStatus.COMPLETED.value, output_text=result
            )
            if variant_id is not None:
                await database.update_order_ab_variant(order_id, variant_id)
        else:
            await database.update_order_status(order_id, OrderStatus.FAILED.value)
    except Exception:
        await database.update_order_status(order_id, OrderStatus.FAILED.value)


# --- Endpoints ---

@app.post("/api/orders", response_model=OrderCreateResponse)
async def create_order(
    request: OrderCreateRequest,
    background_tasks: BackgroundTasks,
    client: dict = Depends(get_current_client),
) -> OrderCreateResponse:
    """
    Создать новый заказ.

    Принимает тип услуги, текст и флаг срочности.
    Запускает обработку в фоне, возвращает ID заказа и цену.
    """
    # Валидация service_type
    try:
        service_type = ServiceType(request.service_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service_type: {request.service_type}",
        )

    # Расчет цены
    price = pricing.calculate_price(
        request.service_type, len(request.input_text), urgent=request.urgent
    )

    # Проверка баланса и списание средств
    can_order = await billing.check_can_order(client["client_id"], price)
    if not can_order:
        raise HTTPException(
            status_code=402,
            detail="Insufficient funds or subscription limit exceeded",
        )

    charged = await billing.charge_or_use_subscription(client["client_id"], price)
    if not charged:
        raise HTTPException(
            status_code=402,
            detail="Insufficient funds",
        )

    # Создаем заказ в БД
    order_id = await database.create_order(
        client_id=client["client_id"],
        service_type=request.service_type,
        input_text=request.input_text,
        price=price,
    )

    # Запускаем обработку в фоне
    background_tasks.add_task(
        _process_order_background, order_id, service_type, request.input_text
    )

    return OrderCreateResponse(
        order_id=order_id,
        status=OrderStatus.PENDING.value,
        price=price,
    )


@app.get("/api/orders/{order_id}", response_model=OrderStatusResponse)
async def get_order_status(
    order_id: int,
    client: dict = Depends(get_current_client),
) -> OrderStatusResponse:
    """
    Получить статус заказа.

    Возвращает статус, тип услуги, дату создания и цену.
    Проверяет принадлежность заказа клиенту.
    """
    order = await database.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Проверяем принадлежность заказа клиенту
    if order["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Order not found")

    return OrderStatusResponse(
        order_id=order["id"],
        status=order["status"],
        service_type=order["service_type"],
        created_at=order["created_at"],
        price=order["price"],
    )


@app.get("/api/orders/{order_id}/result", response_model=OrderResultResponse)
async def get_order_result(
    order_id: int,
    client: dict = Depends(get_current_client),
) -> OrderResultResponse:
    """
    Получить результат заказа.

    Доступен только для завершенных заказов.
    Проверяет принадлежность заказа клиенту.
    """
    order = await database.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Проверяем принадлежность заказа клиенту
    if order["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Order not found")

    # Результат доступен только для завершенных заказов
    if order["status"] != OrderStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Order not completed yet",
        )

    result_text = order.get("output_text") or ""
    return OrderResultResponse(
        order_id=order["id"],
        result_text=result_text,
    )
