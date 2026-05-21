"""Telegram-admin интеграция для управления фриланс-автоматизацией.

Позволяет отправлять уведомления об ошибках авторизации, показывать меню администратору
и принимать обновления cookies или динамической фильтрации.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import config
from logging_config import get_logger
from freelance_automation.config import (
    DYNAMIC_SETTINGS_PATH,
    ERROR_HISTORY_LIMIT,
    ERROR_STATE_PATH,
    FLRU_COOKIES_PATH,
    KWORK_COOKIES_PATH,
    SERVICE_RESTART_REQUEST_PATH,
)

log = get_logger(__name__)

TELEGRAM_ADMIN_STATE_PATH = os.getenv(
    "TELEGRAM_ADMIN_STATE_PATH", "telegram_admin_state.json"
)
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
ADMIN_CHAT_ID = config.TELEGRAM_CHAT_ID

ACTION_UPDATE_KWORK = "update_kwork_cookies"
ACTION_UPDATE_FLRU = "update_flru_cookies"
ACTION_UPDATE_FILTERS = "update_dynamic_filters"
ACTION_REFRESH_SETTINGS = "refresh_settings"
ACTION_SHOW_ERRORS = "show_last_errors"
ACTION_CLEAR_ERRORS = "clear_error_history"
ACTION_RESTART_SERVICE = "request_service_restart"
ACTION_CONFIRM_RESTART = "confirm_restart"
ACTION_FILE_SENT = "file_sent"
ACTION_SHOW_SETTINGS = "show_current_settings"
ACTION_CANCEL = "cancel"

ADMIN_CALLBACK_PREFIX = "admin:"


def _bot_url(method: str) -> str:
    return f"{config.TELEGRAM_API_URL}/bot{config.TELEGRAM_TOKEN}/{method}"


def _load_state() -> dict[str, dict[str, Any]]:
    try:
        with open(TELEGRAM_ADMIN_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def _save_state(state: dict[str, dict[str, Any]]) -> None:
    try:
        with open(TELEGRAM_ADMIN_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        log.warning("telegram_admin_state_save_failed", error=str(exc))


def _set_pending_action(chat_id: int, action: str) -> None:
    state = _load_state()
    state[str(chat_id)] = {
        "action": action,
        "requested_at": time.time(),
    }
    _save_state(state)


def _get_pending_action(chat_id: int) -> Optional[str]:
    state = _load_state()
    payload = state.get(str(chat_id))
    if isinstance(payload, dict):
        return payload.get("action")
    return None


def _clear_pending_action(chat_id: int) -> None:
    state = _load_state()
    state.pop(str(chat_id), None)
    _save_state(state)


async def _send_message(
    session: Any,
    chat_id: int,
    text: str,
    reply_markup: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    try:
        async with session.post(_bot_url("sendMessage"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_admin_send_failed", status=resp.status, chat_id=chat_id)
                return None
            return await resp.json()
    except (aiohttp.ClientError, Exception) as exc:
        log.error("telegram_admin_send_error", error=str(exc), chat_id=chat_id)
        return None


async def _answer_callback_query(
    session: Any,
    callback_query_id: str,
    text: str,
) -> None:
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": False,
    }
    try:
        async with session.post(_bot_url("answerCallbackQuery"), data=payload, timeout=15) as resp:
            if resp.status != 200:
                log.warning("telegram_admin_callback_failed", status=resp.status)
    except (aiohttp.ClientError, Exception) as exc:
        log.error("telegram_admin_callback_error", error=str(exc))


def _build_admin_menu() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Обновить cookies Kwork", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_UPDATE_KWORK},
                {"text": "Обновить cookies FL.ru", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_UPDATE_FLRU},
            ],
            [
                {"text": "Обновить фильтры заказов", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_UPDATE_FILTERS},
                {"text": "Перезагрузить настройки", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_REFRESH_SETTINGS},
            ],
            [
                {"text": "Показать текущие настройки", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_SHOW_SETTINGS},
                {"text": "Показать последние ошибки", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_SHOW_ERRORS},
            ],
            [
                {"text": "Очистить историю ошибок", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_CLEAR_ERRORS},
                {"text": "Запросить рестарт сервиса", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_RESTART_SERVICE},
            ],
            [
                {"text": "Отмена", "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_CANCEL},
            ],
        ]
    }


def _format_settings_text() -> str:
    dynamic = load_dynamic_settings()
    lines = [
        f"<b>Текущие настройки фриланс-автомата</b>",
        f"Kwork cookies: <code>{KWORK_COOKIES_PATH}</code>",
        f"FL.ru cookies: <code>{FLRU_COOKIES_PATH}</code>",
        f"Динамические фильтры: <code>{DYNAMIC_SETTINGS_PATH}</code>",
        "",
        f"<b>Постоянные переменные окружения</b>",
        f"FREELANCE_KEYWORDS = <code>{os.getenv('FREELANCE_KEYWORDS', '')}</code>",
        f"FREELANCE_CATEGORIES = <code>{os.getenv('FREELANCE_CATEGORIES', '')}</code>",
        "",
        f"<b>Динамические настройки</b>",
        f"keywords = <code>{dynamic.get('keywords', [])}</code>",
        f"categories = <code>{dynamic.get('categories', [])}</code>",
    ]
    restart_state = _load_restart_request()
    lines.extend([
        "",
        f"<b>Статус перезапуска</b>: <code>{'запрошен' if restart_state else 'не запрошен'}</code>",
    ])
    if restart_state:
        lines.append(f"Причина: <code>{restart_state.get('reason', 'не указана')}</code>")
    lines.append(f"Всего ошибок в истории: <code>{len(_load_error_history())}</code>")
    return "\n".join(lines)


def load_dynamic_settings() -> dict[str, Any]:
    try:
        with open(DYNAMIC_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def save_dynamic_settings(data: dict[str, Any]) -> bool:
    try:
        with open(DYNAMIC_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        log.warning("telegram_admin_save_dynamic_settings_failed", error=str(exc))
        return False


def _load_error_history() -> list[dict[str, Any]]:
    try:
        with open(ERROR_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _save_error_history(errors: list[dict[str, Any]]) -> None:
    try:
        with open(ERROR_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(errors[-ERROR_HISTORY_LIMIT:], f, ensure_ascii=False, indent=2)
    except OSError as exc:
        log.warning("telegram_admin_save_error_history_failed", error=str(exc))


def append_admin_error(source: str, message: str, details: Optional[str] = None) -> None:
    errors = _load_error_history()
    errors.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "message": message,
        "details": details or "",
    })
    _save_error_history(errors)


def _format_last_errors_text() -> str:
    errors = _load_error_history()
    if not errors:
        return "<b>Нет сохранённых ошибок.</b>"

    lines = ["<b>Последние ошибки фриланс-бота</b>"]
    for index, error in enumerate(errors[-10:], start=1):
        lines.append(
            f"{index}. <b>{error.get('source')}</b> — {error.get('message')}"
        )
        if error.get("details"):
            detail = str(error.get("details"))
            lines.append(f"<code>{detail}</code>")
    return "\n".join(lines)


def _is_restart_requested() -> bool:
    try:
        with open(SERVICE_RESTART_REQUEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return isinstance(data, dict)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def _load_restart_request() -> dict[str, Any] | None:
    try:
        with open(SERVICE_RESTART_REQUEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return None


def _request_service_restart(reason: str) -> bool:
    payload = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    try:
        with open(SERVICE_RESTART_REQUEST_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        log.warning("telegram_admin_save_restart_request_failed", error=str(exc))
        return False


def _clear_restart_request() -> None:
    try:
        os.remove(SERVICE_RESTART_REQUEST_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("telegram_admin_clear_restart_request_failed", error=str(exc))


def _clear_error_history() -> None:
    try:
        os.remove(ERROR_STATE_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("telegram_admin_clear_error_history_failed", error=str(exc))


async def watch_restart_request(shutdown_event: Any, poll_interval_sec: float = 5.0) -> None:
    while not shutdown_event.is_set():
        if _is_restart_requested():
            log.warning("restart_request_detected", path=SERVICE_RESTART_REQUEST_PATH)
            _clear_restart_request()
            shutdown_event.set()
            return
        await asyncio.sleep(poll_interval_sec)


def _save_cookies(platform: str, cookies: Any) -> bool:
    path = KWORK_COOKIES_PATH if platform == "kwork" else FLRU_COOKIES_PATH
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        log.warning("telegram_admin_save_cookies_failed", platform=platform, error=str(exc))
        return False


async def send_platform_login_failure_alert(
    platform: str,
    error: str | None = None,
) -> None:
    if not ADMIN_CHAT_ID or not config.TELEGRAM_TOKEN:
        log.warning("telegram_admin_no_chat_or_token", platform=platform)
        return

    import aiohttp

    async with aiohttp.ClientSession() as session:
        text_lines = [
            f"<b>Ошибка авторизации на {platform.upper()}</b>",
            f"Проверьте cookies файл: <code>{KWORK_COOKIES_PATH if platform == 'kwork' else FLRU_COOKIES_PATH}</code>",
        ]
        if error:
            text_lines.append(f"Ошибка: <code>{error}</code>")
        text_lines.append("")
        text_lines.append("Нажмите кнопку, чтобы отправить свежие cookies.")
        text = "\n".join(text_lines)

        await _send_message(
            session,
            ADMIN_CHAT_ID,
            text,
            reply_markup=_build_admin_menu(),
        )


async def send_manual_file_upload_alert(
    order_id: str,
    zip_path: str,
    platform: str,
) -> None:
    if not ADMIN_CHAT_ID or not config.TELEGRAM_TOKEN:
        log.warning("telegram_admin_no_chat_or_token", platform=platform)
        return

    import aiohttp

    async with aiohttp.ClientSession() as session:
        text_lines = [
            f"<b>Не удалось автоматически загрузить ZIP для заказа {order_id}</b>",
            f"Файл сохранён локально: <code>{zip_path}</code>",
            "Пожалуйста, отправьте этот файл вручную заказчику на платформе.",
            "Когда файл будет отправлен, нажмите кнопку ниже.",
        ]
        text = "\n".join(text_lines)

        markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "Файл отправлен",
                        "callback_data": ADMIN_CALLBACK_PREFIX + ACTION_FILE_SENT,
                    }
                ]
            ]
        }

        await _send_message(
            session,
            ADMIN_CHAT_ID,
            text,
            reply_markup=markup,
        )


async def _handle_callback_query(session: aiohttp.ClientSession, callback_query: dict[str, Any]) -> None:
    callback_id = callback_query.get("id", "")
    from_user = callback_query.get("from", {})
    chat_id = from_user.get("id")
    data = callback_query.get("data", "")

    if chat_id != ADMIN_CHAT_ID:
        await _answer_callback_query(session, callback_id, "Доступ запрещён.")
        return

    action = data.replace(ADMIN_CALLBACK_PREFIX, "")
    if action == ACTION_CANCEL:
        _clear_pending_action(chat_id)
        await _answer_callback_query(session, callback_id, "Действие отменено.")
        await _send_message(session, chat_id, "Отменено. Выберите следующее действие.", reply_markup=_build_admin_menu())
        return

    if action == ACTION_UPDATE_KWORK:
        _set_pending_action(chat_id, ACTION_UPDATE_KWORK)
        await _answer_callback_query(session, callback_id, "Готово.")
        await _send_message(
            session,
            chat_id,
            (
                "Отправьте в этом чате JSON cookies для Kwork.\n"
                "Пример: [ {\"name\":..., \"value\":..., ...} ]"
            ),
        )
        return

    if action == ACTION_UPDATE_FLRU:
        _set_pending_action(chat_id, ACTION_UPDATE_FLRU)
        await _answer_callback_query(session, callback_id, "Готово.")
        await _send_message(
            session,
            chat_id,
            (
                "Отправьте в этом чате JSON cookies для FL.ru.\n"
                "Пример: [ {\"name\":..., \"value\":..., ...} ]"
            ),
        )
        return

    if action == ACTION_UPDATE_FILTERS:
        _set_pending_action(chat_id, ACTION_UPDATE_FILTERS)
        await _answer_callback_query(session, callback_id, "Готово.")
        await _send_message(
            session,
            chat_id,
            (
                "Отправьте JSON с фильтрами.\n"
                "Пример: {\"keywords\": [\"telegram\", \"бот\"], \"categories\": [\"маркетинг\", \"web\"]}"
            ),
        )
        return

    if action == ACTION_REFRESH_SETTINGS:
        await _answer_callback_query(session, callback_id, "Настройки обновлены.")
        await _send_message(session, chat_id, _format_settings_text())
        return

    if action == ACTION_SHOW_ERRORS:
        await _answer_callback_query(session, callback_id, "Показываю последние ошибки.")
        await _send_message(session, chat_id, _format_last_errors_text())
        return

    if action == ACTION_CLEAR_ERRORS:
        _clear_error_history()
        await _answer_callback_query(session, callback_id, "История ошибок очищена.")
        await _send_message(session, chat_id, "История ошибок успешно очищена.")
        return

    if action == ACTION_RESTART_SERVICE:
        _set_pending_action(chat_id, ACTION_RESTART_SERVICE)
        await _answer_callback_query(session, callback_id, "Готово.")
        await _send_message(
            session,
            chat_id,
            "Отправьте /confirm_restart для подтверждения перезапуска сервиса.",
        )
        return

    if action == ACTION_SHOW_SETTINGS:
        await _answer_callback_query(session, callback_id, "Показываю настройки.")
        await _send_message(session, chat_id, _format_settings_text())
        return

    if action == ACTION_FILE_SENT:
        await _answer_callback_query(session, callback_id, "Отмечено как отправленное.")
        await _send_message(session, chat_id, "Спасибо! Файл отмечен как отправленный вручную.")
        return

    await _answer_callback_query(session, callback_id, "Неизвестная команда.")


async def _process_admin_message(session: aiohttp.ClientSession, chat_id: int, text: str) -> None:
    action = _get_pending_action(chat_id)
    if action is None:
        await _send_message(session, chat_id, "Введите /admin для управления настройками или используйте кнопки.")
        return

    if action in (ACTION_UPDATE_KWORK, ACTION_UPDATE_FLRU):
        try:
            cookies = json.loads(text)
            if not isinstance(cookies, list):
                raise ValueError("cookies must be a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            await _send_message(
                session,
                chat_id,
                (
                    f"Ошибка разбора JSON: {exc}.\n"
                    "Отправьте корректный JSON массив cookies еще раз."
                ),
            )
            return

        platform = "kwork" if action == ACTION_UPDATE_KWORK else "flru"
        if _save_cookies(platform, cookies):
            await _send_message(
                session,
                chat_id,
                f"Cookies для {platform.upper()} успешно сохранены в <code>{KWORK_COOKIES_PATH if platform == 'kwork' else FLRU_COOKIES_PATH}</code>.\n" 
                "Сервис нужно перезапустить для повторной авторизации.",
            )
            _clear_pending_action(chat_id)
        else:
            await _send_message(
                session,
                chat_id,
                "Не удалось сохранить cookies, проверьте права на файл и повторите.",
            )
        return

    if action == ACTION_UPDATE_FILTERS:
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("settings must be a JSON object")
            keywords = data.get("keywords")
            categories = data.get("categories")
            if keywords is not None and not isinstance(keywords, list):
                raise ValueError("keywords must be an array")
            if categories is not None and not isinstance(categories, list):
                raise ValueError("categories must be an array")
        except (json.JSONDecodeError, ValueError) as exc:
            await _send_message(
                session,
                chat_id,
                (
                    f"Ошибка разбора JSON: {exc}.\n"
                    "Отправьте корректный JSON со списком keywords и categories."
                ),
            )
            return

        update = {}
        if keywords is not None:
            update["keywords"] = [str(item) for item in keywords]
        if categories is not None:
            update["categories"] = [str(item) for item in categories]
        if save_dynamic_settings(update):
            await _send_message(
                session,
                chat_id,
                f"Фильтры сохранены в <code>{DYNAMIC_SETTINGS_PATH}</code>.\n"
                "Они будут применены при следующем сканировании.",
            )
            _clear_pending_action(chat_id)
        else:
            await _send_message(session, chat_id, "Не удалось сохранить настройки.")
        return

    if action == ACTION_RESTART_SERVICE:
        if text.strip().lower().startswith("/confirm_restart"):
            if _request_service_restart("admin_requested_restart"):
                await _send_message(
                    session,
                    chat_id,
                    "Перезапуск сервиса запрошен. Сервис остановится, после чего запустите его заново менеджером процессов.",
                )
                _clear_pending_action(chat_id)
            else:
                await _send_message(session, chat_id, "Не удалось записать запрос на перезапуск. Проверьте права на файл и повторите.")
        else:
            await _send_message(
                session,
                chat_id,
                "Для подтверждения перезапуска отправьте /confirm_restart.",
            )
        return

    await _send_message(session, chat_id, "Неизвестное действие, используйте /admin.")
    _clear_pending_action(chat_id)


async def handle_telegram_update(update: dict[str, Any], request: Any = None) -> None:
    callback_query = update.get("callback_query")
    message = update.get("message")

    if callback_query:
        async with aiohttp.ClientSession() as session:
            await _handle_callback_query(session, callback_query)
        return

    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id != ADMIN_CHAT_ID:
        return

    text = message.get("text", "").strip()
    if not text:
        return

    import aiohttp

    async with aiohttp.ClientSession() as session:
        if text.startswith("/admin") or text.startswith("/start"):
            await _send_message(session, chat_id, "Меню администрирования фриланс-бота:", reply_markup=_build_admin_menu())
            return
        if text.startswith("/status"):
            await _send_message(session, chat_id, _format_settings_text())
            return
        if text.startswith("/refresh") or text.startswith("/reload"):
            await _send_message(session, chat_id, _format_settings_text())
            return
        await _process_admin_message(session, chat_id, text)


def setup_routes(app: Any, secret_token: str | None = None) -> None:
    app["telegram_webhook_secret"] = secret_token or TELEGRAM_WEBHOOK_SECRET
    app.router.add_post("/webhook/telegram", _handle_update)


async def _handle_update(request: Any) -> Any:
    import aiohttp

    webhook_secret = request.app.get("telegram_webhook_secret", "")
    if webhook_secret:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_token != webhook_secret:
            return aiohttp.web.Response(status=403, text="forbidden")

    try:
        update = await request.json()
    except Exception:
        return aiohttp.web.Response(status=400, text="invalid json")

    await handle_telegram_update(update, request)
    return aiohttp.web.Response(status=200, text="ok")
