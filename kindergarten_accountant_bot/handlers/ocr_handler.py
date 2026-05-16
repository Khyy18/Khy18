"""OCR photo handler - scans documents and extracts structured data."""

import base64
import logging

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from kindergarten_accountant_bot.config import BACKEND_URL, BACKEND_TOKEN

logger = logging.getLogger(__name__)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photo messages: OCR and extract document data."""
    if not BACKEND_TOKEN:
        await update.message.reply_text(
            "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0431\u044d\u043a\u0435\u043d\u0434\u0430 \u043d\u0435 \u0437\u0430\u0434\u0430\u043d\u044b (BACKEND_TOKEN)."
        )
        return

    processing_msg = await update.message.reply_text(
        "\u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u044e \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442..."
    )

    try:
        # Get the largest photo version
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()

        # Base64 encode
        image_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")

        # Call backend OCR endpoint
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/ocr/process",
                json={"image_base64": image_b64, "filename": "photo.jpg"},
                headers={"Authorization": f"Bearer {BACKEND_TOKEN}"},
            )

        if response.status_code != 200:
            await processing_msg.edit_text(
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437."
            )
            return

        data = response.json()
        doc_type = data.get("doc_type", "unknown")
        fields = data.get("fields", {})

        # Store data in context for callback
        context.user_data["ocr_result"] = data

        # Format response message
        type_labels = {
            "invoice": "\u0421\u0447\u0451\u0442/\u041d\u0430\u043a\u043b\u0430\u0434\u043d\u0430\u044f",
            "timesheet": "\u0422\u0430\u0431\u0435\u043b\u044c",
            "receipt": "\u0427\u0435\u043a",
            "payslip": "\u0420\u0430\u0441\u0447\u0451\u0442\u043d\u044b\u0439 \u043b\u0438\u0441\u0442\u043e\u043a",
            "unknown": "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0442\u0438\u043f",
        }
        type_label = type_labels.get(doc_type, doc_type)

        lines = [f"\U0001f4c4 <b>\u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043e: {type_label}</b>\n"]
        if fields:
            for key, value in fields.items():
                lines.append(f"\u2022 <b>{key}:</b> {value}")
        else:
            lines.append("\u041f\u043e\u043b\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "\U0001f4e5 \u0421\u043a\u0430\u0447\u0430\u0442\u044c Excel",
                callback_data="ocr_excel",
            )]
        ])

        await processing_msg.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception as e:
        logger.error(f"OCR handler error: {e}")
        await processing_msg.edit_text(
            "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0435 \u0444\u043e\u0442\u043e. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435."
        )


async def ocr_excel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Download Excel' button press for OCR result."""
    query = update.callback_query
    await query.answer()

    ocr_data = context.user_data.get("ocr_result")
    if not ocr_data:
        await query.edit_message_text(
            "\u0414\u0430\u043d\u043d\u044b\u0435 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0432\u0430\u043d\u0438\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b. \u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0444\u043e\u0442\u043e \u0435\u0449\u0451 \u0440\u0430\u0437."
        )
        return

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/ocr/to-excel",
                json={
                    "doc_type": ocr_data.get("doc_type", "unknown"),
                    "fields": ocr_data.get("fields", {}),
                    "title": "\u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043d\u044b\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
                },
                headers={"Authorization": f"Bearer {BACKEND_TOKEN}"},
            )

        if response.status_code != 200:
            await query.edit_message_text(
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c Excel. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435."
            )
            return

        # Send the file
        filename = f"ocr_{ocr_data.get('doc_type', 'document')}.xlsx"
        await query.message.reply_document(
            document=response.content,
            filename=filename,
            caption="\U0001f4c4 \u0412\u0430\u0448 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043d\u044b\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
        )

        # Clean up stored OCR data
        context.user_data.pop("ocr_result", None)

    except Exception as e:
        logger.error(f"OCR Excel callback error: {e}")
        await query.edit_message_text(
            "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u0441\u043e\u0437\u0434\u0430\u043d\u0438\u0438 Excel. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435."
        )
