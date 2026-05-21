"""
WebSocket обработчик видеозвонка.

Управляет жизненным циклом сессии:
connecting -> active -> ending -> closed

Принимает:
- Binary frames: аудио-чанки от клиента (PCM/opus)
- JSON frames: управляющие сообщения (mute, unmute, end_call)

Отправляет:
- JSON: статусы, текстовые дельты от LLM
- Binary: аудио/видео от AI pipeline
"""

import asyncio
import json
import logging
import enum

from fastapi import WebSocket, WebSocketDisconnect, Query

from app.auth.jwt import verify_token
from app.call.pipeline import AIPipeline
from app.models.database import async_session_factory, Session, SessionStatus

logger = logging.getLogger(__name__)


class CallState(str, enum.Enum):
    connecting = "connecting"
    active = "active"
    ending = "ending"
    closed = "closed"


async def _get_redis():
    """Получаем Redis для подписки на force_end от биллинга (shared singleton)."""
    from app.redis_client import get_redis
    return await get_redis()


async def websocket_call(websocket: WebSocket, session_id: str, token: str = Query(...)):
    """
    WebSocket endpoint для видеозвонка.

    Параметры:
    - session_id: ID сессии (из URL path)
    - token: JWT токен (из query param)
    """
    # Верификация JWT
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Принимаем WebSocket соединение
    await websocket.accept()

    # Проверяем ownership сессии
    try:
        async with async_session_factory() as db_session:
            from sqlalchemy import select as sa_select
            result = await db_session.execute(
                sa_select(Session).where(Session.id == session_id)
            )
            session_row = result.scalar_one_or_none()
            if not session_row or session_row.user_id != user_id:
                await websocket.send_json({
                    "type": "error",
                    "message": "Session does not belong to user",
                })
                await websocket.close(code=4003, reason="Session does not belong to user")
                return
    except Exception as e:
        logger.error(f"Session ownership check failed: {e}")
        await websocket.close(code=4003, reason="Session does not belong to user")
        return

    state = CallState.connecting

    # Инициализируем AI pipeline
    pipeline = AIPipeline(session_id=session_id)

    # Подписываемся на Redis pubsub для получения force_end от биллинга
    redis = await _get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"call:{session_id}")

    async def listen_billing():
        """
        Слушаем канал Redis для сигналов от BillingWorker.
        Обрабатывает force_end и JSON-сообщения (balance_warning).
        """
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    if data == "force_end":
                        await websocket.send_json({
                            "type": "status",
                            "state": "ending",
                            "reason": "balance_depleted",
                            "message": "Баланс исчерпан. Сессия завершается.",
                        })
                        return True
                    elif data.startswith("{"):
                        # JSON-сообщение (например balance_warning)
                        try:
                            parsed = json.loads(data)
                            await websocket.send_json(parsed)
                        except (json.JSONDecodeError, Exception) as e:
                            logger.error(f"Failed to parse billing message: {e}")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
        return False

    # Запускаем слушатель биллинга в фоне
    billing_task = asyncio.create_task(listen_billing())

    try:
        # Переходим в активное состояние
        state = CallState.active
        await websocket.send_json({
            "type": "status",
            "state": state.value,
            "session_id": session_id,
        })

        while state == CallState.active:
            # Проверяем сигнал от биллинга
            if billing_task.done():
                state = CallState.ending
                break

            try:
                # Ждем сообщения от клиента с таймаутом
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                state = CallState.closed
                break

            # Обработка бинарных аудио-данных
            if "bytes" in message and message["bytes"]:
                await pipeline.process_audio_chunk(message["bytes"])

                # Проверяем готовность ответа и стримим
                async for response_chunk in pipeline.get_response_stream():
                    if response_chunk["type"] == "text_delta":
                        await websocket.send_json({
                            "type": "text_delta",
                            "content": response_chunk["content"],
                        })
                    elif response_chunk["type"] == "audio":
                        await websocket.send_bytes(response_chunk["data"])

            # Обработка JSON управляющих сообщений
            elif "text" in message and message["text"]:
                try:
                    control = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                action = control.get("action")

                if action == "end_call":
                    state = CallState.ending
                    break
                elif action == "speech_end":
                    # Frontend VAD detected end of speech - trigger transcription
                    await pipeline.force_transcribe()
                elif action == "mute":
                    await websocket.send_json({
                        "type": "status",
                        "muted": True,
                    })
                elif action == "unmute":
                    await websocket.send_json({
                        "type": "status",
                        "muted": False,
                    })

    except WebSocketDisconnect:
        state = CallState.closed
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        state = CallState.closed
    finally:
        # Завершаем сессию
        state = CallState.closed
        billing_task.cancel()
        await pubsub.unsubscribe(f"call:{session_id}")

        # Останавливаем per-session billing task
        try:
            from app.billing.instance import billing_worker
            await billing_worker.stop_session_billing(session_id)
        except Exception as e:
            logger.error(f"Failed to stop session billing for {session_id}: {e}")

        # Update session status to finished in the database
        try:
            async with async_session_factory() as db_session:
                from sqlalchemy import select as sa_select
                result = await db_session.execute(
                    sa_select(Session).where(Session.id == session_id)
                )
                session_row = result.scalar_one_or_none()
                if session_row and session_row.status == SessionStatus.active:
                    from datetime import datetime
                    session_row.status = SessionStatus.finished
                    session_row.ended_at = datetime.utcnow()
                    await db_session.commit()
        except Exception as e:
            logger.error(f"Failed to finalize session {session_id}: {e}")

        # Отправляем финальный статус если соединение еще открыто
        try:
            await websocket.send_json({
                "type": "status",
                "state": "closed",
            })
            await websocket.close()
        except Exception:
            pass

        logger.info(f"WebSocket session {session_id} closed for user {user_id}")
