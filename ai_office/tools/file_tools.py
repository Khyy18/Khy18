"""Инструменты для работы с файлами (PDF, CSV, отчёты)."""

import csv
import io
import logging
import os
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

ALLOWED_FILE_DIR = "/tmp/ai_office_files"

# Создаём директорию если не существует
os.makedirs(ALLOWED_FILE_DIR, exist_ok=True)


def _validate_file_path(file_path: str) -> str | None:
    """Проверить что путь к файлу находится в разрешённой директории.

    Returns:
        None если путь валиден, иначе сообщение об ошибке.
    """
    resolved = Path(file_path).resolve()
    allowed = Path(ALLOWED_FILE_DIR).resolve()
    if not str(resolved).startswith(str(allowed) + os.sep) and resolved != allowed:
        return "Ошибка: доступ к файлу запрещён"
    return None


@tool
async def parse_pdf(file_path: str) -> str:
    """Извлечь текст из PDF файла.

    Args:
        file_path: Путь к PDF файлу

    Returns:
        Извлечённый текст или сообщение об ошибке
    """
    error = _validate_file_path(file_path)
    if error:
        return error

    path = Path(file_path)
    if not path.exists():
        return f"Ошибка: файл не найден: {file_path}"

    if not path.suffix.lower() == ".pdf":
        return f"Ошибка: файл не является PDF: {file_path}"

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        text_parts = []

        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Страница {i + 1} ---\n{page_text}")

        if not text_parts:
            return "PDF файл не содержит извлекаемого текста."

        result = "\n\n".join(text_parts)
        # Ограничиваем размер выходного текста
        if len(result) > 10000:
            result = result[:10000] + "\n\n... (текст обрезан, слишком большой файл)"

        return result

    except ImportError:
        return "Ошибка: библиотека PyPDF2 не установлена"
    except Exception as e:
        logger.error("Ошибка парсинга PDF: %s", str(e))
        return f"Ошибка при чтении PDF: {str(e)}"


@tool
async def parse_csv(file_path: str) -> str:
    """Прочитать и отформатировать CSV файл.

    Args:
        file_path: Путь к CSV файлу

    Returns:
        Содержимое CSV в текстовом формате
    """
    error = _validate_file_path(file_path)
    if error:
        return error

    path = Path(file_path)
    if not path.exists():
        return f"Ошибка: файл не найден: {file_path}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            # Определяем диалект
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel

            reader = csv.reader(f, dialect)
            rows = []
            for i, row in enumerate(reader):
                if i >= 100:  # Ограничение на 100 строк
                    rows.append(f"... (ещё строки, всего > {i})")
                    break
                rows.append(" | ".join(row))

        if not rows:
            return "CSV файл пуст."

        # Первая строка - заголовки
        header = rows[0]
        separator = "-" * min(len(header), 80)
        result = f"{header}\n{separator}\n" + "\n".join(rows[1:])

        return f"Содержимое CSV ({len(rows)} строк):\n\n{result}"

    except UnicodeDecodeError:
        return "Ошибка: не удалось прочитать файл (некорректная кодировка)"
    except Exception as e:
        logger.error("Ошибка парсинга CSV: %s", str(e))
        return f"Ошибка при чтении CSV: {str(e)}"


@tool
async def generate_report(title: str, content: str, format: str = "text") -> str:
    """Сгенерировать отчёт в указанном формате.

    Args:
        title: Заголовок отчёта
        content: Содержимое отчёта
        format: Формат отчёта (text, markdown, html)

    Returns:
        Сформированный отчёт
    """
    if not title.strip():
        return "Ошибка: заголовок отчёта не может быть пустым"

    if format == "markdown":
        report = f"# {title}\n\n{content}\n\n---\n*Отчёт сгенерирован AI Office*\n"
    elif format == "html":
        report = (
            f"<html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1>"
            f"<div>{content}</div>"
            f"<hr><p><em>Отчёт сгенерирован AI Office</em></p>"
            f"</body></html>"
        )
    else:
        report = (
            f"{'=' * 60}\n"
            f"  {title}\n"
            f"{'=' * 60}\n\n"
            f"{content}\n\n"
            f"{'-' * 60}\n"
            f"Отчёт сгенерирован AI Office\n"
        )

    return report


@tool
async def analyze_document(file_path: str, question: str) -> str:
    """Анализ документа с ответом на вопрос.

    Извлекает текст из файла и формирует контекст для анализа.

    Args:
        file_path: Путь к документу (PDF или текстовый файл)
        question: Вопрос по содержимому документа

    Returns:
        Ответ на вопрос или извлечённый контекст
    """
    error = _validate_file_path(file_path)
    if error:
        return error

    path = Path(file_path)
    if not path.exists():
        return f"Ошибка: файл не найден: {file_path}"

    if not question.strip():
        return "Ошибка: вопрос не может быть пустым"

    # Извлекаем текст в зависимости от типа файла
    text = ""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(path))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            text = "\n".join(text_parts)
        except ImportError:
            return "Ошибка: библиотека PyPDF2 не установлена"
        except Exception as e:
            return f"Ошибка чтения PDF: {str(e)}"
    elif suffix in (".txt", ".md", ".csv", ".json", ".log"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read(50000)  # Ограничение на 50KB
        except Exception as e:
            return f"Ошибка чтения файла: {str(e)}"
    else:
        return f"Неподдерживаемый формат файла: {suffix}"

    if not text.strip():
        return "Документ пуст или не содержит текста."

    # Ограничиваем контекст
    if len(text) > 5000:
        text = text[:5000] + "..."

    return (
        f"Контекст документа ({path.name}):\n\n"
        f"{text}\n\n"
        f"Вопрос: {question}\n\n"
        f"Для полного анализа передайте этот контекст LLM-агенту."
    )
