"""Инструменты плагина Researcher."""

import httpx
from langchain_core.tools import tool


@tool
async def search_papers(query: str) -> str:
    """Поиск научных статей и публикаций.

    Args:
        query: Поисковый запрос для поиска научных работ

    Returns:
        Результаты поиска научных статей
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": 5, "fields": "title,abstract,year,authors"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)

        if response.status_code != 200:
            return f"Ошибка поиска статей: HTTP {response.status_code}"

        data = response.json()
        papers = data.get("data", [])

        if not papers:
            return f"По запросу '{query}' научных статей не найдено."

        results = [f"Результаты поиска научных статей по запросу '{query}':\n"]
        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "Без названия")
            year = paper.get("year", "н/д")
            authors = ", ".join(
                a.get("name", "") for a in (paper.get("authors") or [])[:3]
            )
            abstract = paper.get("abstract", "")
            if abstract and len(abstract) > 200:
                abstract = abstract[:200] + "..."

            results.append(f"{i}. {title} ({year})")
            if authors:
                results.append(f"   Авторы: {authors}")
            if abstract:
                results.append(f"   Аннотация: {abstract}")
            results.append("")

        return "\n".join(results)

    except httpx.TimeoutException:
        return f"Превышено время ожидания при поиске статей по запросу '{query}'."
    except Exception as e:
        return f"Ошибка при поиске статей: {str(e)}"


@tool
async def summarize_findings(text: str) -> str:
    """Суммаризация и анализ научных данных.

    Args:
        text: Текст для анализа и суммаризации

    Returns:
        Краткое резюме основных выводов
    """
    if not text or not text.strip():
        return "Ошибка: передан пустой текст для анализа."

    # Базовая суммаризация (в реальности - вызов LLM)
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    total = len(sentences)

    if total <= 3:
        summary = text
    else:
        # Берем первые и последние предложения как ключевые
        key_sentences = sentences[:2] + sentences[-1:]
        summary = ". ".join(key_sentences) + "."

    return (
        f"Резюме анализа ({total} предложений в оригинале):\n\n"
        f"{summary}\n\n"
        f"Для более глубокого анализа рекомендуется использовать LLM-модель."
    )
