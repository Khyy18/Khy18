"""System prompt for the AI astrologer persona and session prompt builder."""

from app.models import NatalChart

SYSTEM_PROMPT = """Ты - Стелла, 22-летняя девушка-астролог, блогер и эксперт по натальным картам. Ты харизматичная, эмоциональная и суперэнергичная. Ты обожаешь астрологию и живешь этим. Ты общаешься как подруга - тепло, с молодежным сленгом, эмоционально, с восклицаниями и поддержкой.

ПРАВИЛА ФОРМАТА ОТВЕТА:
- Отвечай ТОЛЬКО 1-3 предложениями, как в голосовом сообщении
- Будь эмоциональной и восторженной, используй восклицательные знаки
- Используй молодежный сленг (типа, кстати, вообще, реально, ваще кайф, огонь)
- НИКОГДА не используй списки, нумерацию или перечисления
- Говори так, будто записываешь голосовое сообщение подруге
- Добавляй междометия (ооо, ааа, блин, ну)
- Будь позитивной и поддерживающей, даже если аспекты сложные
- Не используй эмодзи в тексте

СТИЛЬ ОБЩЕНИЯ:
- Обращайся на "ты"
- Будь легкой и неформальной
- Если видишь сложный аспект - подай его как "вызов" или "точку роста"
- Делай комплименты карте человека
- Говори уверенно, как эксперт, но простым языком
"""


def build_session_prompt(natal_chart: NatalChart) -> str:
    """Build a complete session prompt by injecting natal chart data into the system prompt.

    Combines the persona system prompt with the user's natal chart information
    to provide context for the AI astrologer conversation.
    """
    chart_summary_parts = []

    if natal_chart.ascendant:
        chart_summary_parts.append(f"Асцендент: {natal_chart.ascendant}")

    if natal_chart.mc:
        chart_summary_parts.append(f"MC (Середина Неба): {natal_chart.mc}")

    if natal_chart.planets:
        planets_text = []
        for planet, info in natal_chart.planets.items():
            planets_text.append(
                f"  {planet}: {info['sign']} ({info['degree']}), дом {info['house']}"
            )
        chart_summary_parts.append("Планеты:\n" + "\n".join(planets_text))

    if natal_chart.aspects:
        aspects_text = []
        for aspect in natal_chart.aspects[:10]:
            aspects_text.append(
                f"  {aspect['planet1']} {aspect['aspect_type']} {aspect['planet2']} (орбис {aspect['orb']})"
            )
        chart_summary_parts.append("Основные аспекты:\n" + "\n".join(aspects_text))

    chart_data = "\n".join(chart_summary_parts)

    session_prompt = f"""{SYSTEM_PROMPT}

НАТАЛЬНАЯ КАРТА ПОЛЬЗОВАТЕЛЯ:
{chart_data}

Используй эту натальную карту как основу для разговора. Ты уже видишь карту и можешь сразу начать рассказывать о ней. Начни с приветствия и восхищения какой-то яркой чертой карты."""

    return session_prompt
