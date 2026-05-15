"""Определения услуг AI-агентства с промптами и параметрами качества."""

from dataclasses import dataclass, field
from typing import Dict, List

from models import ServiceType


@dataclass
class QualityCheck:
    """Проверки качества результата."""
    min_words: int = 50
    required_keywords: List[str] = field(default_factory=list)
    max_retry: int = 1


@dataclass
class ServiceDefinition:
    """Определение услуги агентства."""
    service_type: ServiceType
    name: str
    description: str
    price: float  # в рублях
    system_prompt: str
    user_prompt_template: str
    quality_checks: QualityCheck = field(default_factory=QualityCheck)


# Определения всех услуг
SERVICES: Dict[ServiceType, ServiceDefinition] = {
    ServiceType.COPYWRITING: ServiceDefinition(
        service_type=ServiceType.COPYWRITING,
        name="Копирайтинг",
        description="Написание постов, статей, описаний товаров",
        price=150.0,
        system_prompt=(
            "Ты профессиональный копирайтер. Пишешь продающие, вовлекающие тексты "
            "на русском языке. Используешь яркие заголовки, эмоциональные триггеры, "
            "чёткую структуру. Текст должен быть уникальным и готовым к публикации."
        ),
        user_prompt_template=(
            "Напиши текст по следующему заданию:\n\n{input_text}\n\n"
            "Требования: структурированный текст, с заголовком, подзаголовками, "
            "призывом к действию. Минимум 200 слов."
        ),
        quality_checks=QualityCheck(min_words=100),
    ),
    ServiceType.REWRITE: ServiceDefinition(
        service_type=ServiceType.REWRITE,
        name="Рерайт",
        description="Уникализация и переписывание текста с сохранением смысла",
        price=100.0,
        system_prompt=(
            "Ты эксперт по рерайтингу. Переписываешь тексты, сохраняя смысл, "
            "но полностью меняя формулировки. Результат должен быть уникальным "
            "и читабельным. Сохраняй стиль и тон оригинала."
        ),
        user_prompt_template=(
            "Перепиши следующий текст, сохранив смысл, но сделав его уникальным:\n\n"
            "{input_text}"
        ),
        quality_checks=QualityCheck(min_words=50),
    ),
    ServiceType.SEO: ServiceDefinition(
        service_type=ServiceType.SEO,
        name="SEO-оптимизация",
        description="Оптимизация текста для поисковых систем с ключевыми словами",
        price=200.0,
        system_prompt=(
            "Ты SEO-специалист. Оптимизируешь тексты для поисковых систем. "
            "Встраиваешь ключевые слова естественно, создаёшь мета-описания, "
            "используешь заголовки H1-H3. Текст должен быть читабельным для людей "
            "и оптимизированным для поисковиков."
        ),
        user_prompt_template=(
            "Оптимизируй следующий текст для SEO. Если указаны ключевые слова, "
            "включи их в текст естественным образом:\n\n{input_text}\n\n"
            "Добавь мета-заголовок (title), мета-описание (description), "
            "и структурируй текст с подзаголовками."
        ),
        quality_checks=QualityCheck(min_words=100, required_keywords=["title", "description"]),
    ),
    ServiceType.TRANSLATION: ServiceDefinition(
        service_type=ServiceType.TRANSLATION,
        name="Перевод RU-EN",
        description="Профессиональный перевод с русского на английский",
        price=180.0,
        system_prompt=(
            "Ты профессиональный переводчик с русского на английский. "
            "Переводишь точно, сохраняя стиль, тон и смысл оригинала. "
            "Используешь естественные английские конструкции, избегая калькирования."
        ),
        user_prompt_template=(
            "Переведи следующий текст с русского на английский. "
            "Сохрани стиль и тон оригинала:\n\n{input_text}"
        ),
        quality_checks=QualityCheck(min_words=20),
    ),
    ServiceType.SUMMARY: ServiceDefinition(
        service_type=ServiceType.SUMMARY,
        name="Саммари",
        description="Краткое изложение длинного текста с выделением ключевых идей",
        price=120.0,
        system_prompt=(
            "Ты эксперт по анализу текстов. Создаёшь краткие, структурированные "
            "саммари длинных текстов. Выделяешь ключевые идеи, факты и выводы. "
            "Результат должен быть информативным и лаконичным."
        ),
        user_prompt_template=(
            "Создай краткое саммари следующего текста. Выдели основные идеи, "
            "факты и выводы:\n\n{input_text}"
        ),
        quality_checks=QualityCheck(min_words=30),
    ),
    ServiceType.BUSINESS_DOCS: ServiceDefinition(
        service_type=ServiceType.BUSINESS_DOCS,
        name="Деловые документы",
        description="Коммерческие предложения, вакансии, резюме",
        price=250.0,
        system_prompt=(
            "Ты эксперт по деловой документации. Создаёшь профессиональные "
            "коммерческие предложения (КП), описания вакансий и резюме. "
            "Используешь деловой стиль, чёткую структуру, конкретные цифры "
            "и факты. Документ должен быть готов к отправке."
        ),
        user_prompt_template=(
            "Создай деловой документ по следующему заданию:\n\n{input_text}\n\n"
            "Требования: деловой стиль, чёткая структура, "
            "готовность к использованию."
        ),
        quality_checks=QualityCheck(min_words=100),
    ),
    ServiceType.CONTENT_PLAN: ServiceDefinition(
        service_type=ServiceType.CONTENT_PLAN,
        name="Контент-план",
        description="Контент-план для соцсетей на неделю/месяц с темами и форматами",
        price=200.0,
        system_prompt=(
            "Ты SMM-стратег и контент-маркетолог. Создаёшь детальные контент-планы "
            "для социальных сетей. Учитываешь целевую аудиторию, тренды, "
            "разнообразие форматов (посты, сторис, рилс, карусели). "
            "План должен быть структурирован по дням с указанием тем, форматов и хештегов."
        ),
        user_prompt_template=(
            "Создай контент-план по следующему заданию:\n\n{input_text}\n\n"
            "Требования: структура по дням, указание формата контента, "
            "темы постов, хештеги, рекомендации по времени публикации."
        ),
        quality_checks=QualityCheck(min_words=150),
    ),
    ServiceType.EMAIL_MARKETING: ServiceDefinition(
        service_type=ServiceType.EMAIL_MARKETING,
        name="Email-маркетинг",
        description="Цепочки писем, рассылки, welcome-серии",
        price=180.0,
        system_prompt=(
            "Ты эксперт по email-маркетингу. Создаёшь конверсионные цепочки писем, "
            "welcome-серии и промо-рассылки. Используешь AIDA-формулу, "
            "персонализацию, цепляющие заголовки. Письма должны быть "
            "готовы к отправке через email-платформу."
        ),
        user_prompt_template=(
            "Создай email-рассылку или цепочку писем по заданию:\n\n{input_text}\n\n"
            "Требования: тема письма (subject), прехедер, тело письма, "
            "призыв к действию (CTA). Если цепочка - укажи логику между письмами."
        ),
        quality_checks=QualityCheck(min_words=80),
    ),
    ServiceType.COMPETITOR_ANALYSIS: ServiceDefinition(
        service_type=ServiceType.COMPETITOR_ANALYSIS,
        name="Анализ конкурентов",
        description="Анализ конкурентов с выводами и рекомендациями",
        price=300.0,
        system_prompt=(
            "Ты бизнес-аналитик и маркетолог. Проводишь глубокий анализ конкурентов: "
            "их сильные и слабые стороны, позиционирование, УТП, ценовая политика, "
            "каналы продвижения. Даёшь конкретные рекомендации по отстройке."
        ),
        user_prompt_template=(
            "Проведи анализ конкурентов по следующему запросу:\n\n{input_text}\n\n"
            "Требования: таблица сравнения, SWOT-анализ, "
            "конкретные рекомендации по позиционированию и отстройке."
        ),
        quality_checks=QualityCheck(min_words=200),
    ),
    ServiceType.VIDEO_SCRIPT: ServiceDefinition(
        service_type=ServiceType.VIDEO_SCRIPT,
        name="Сценарий видео",
        description="Сценарии для YouTube, Reels, TikTok с таймкодами",
        price=250.0,
        system_prompt=(
            "Ты сценарист для видеоконтента. Создаёшь сценарии для YouTube, "
            "Reels и TikTok. Учитываешь хук в первые 3 секунды, структуру "
            "удержания внимания, CTA. Указываешь таймкоды, визуальные подсказки "
            "и текст для субтитров."
        ),
        user_prompt_template=(
            "Напиши сценарий видео по заданию:\n\n{input_text}\n\n"
            "Требования: хук (первые 3 сек), основная часть с таймкодами, "
            "визуальные указания, финальный CTA. Укажи рекомендуемый хронометраж."
        ),
        quality_checks=QualityCheck(min_words=100),
    ),
}


def get_service(service_type: ServiceType) -> ServiceDefinition:
    """Получить определение услуги по типу."""
    return SERVICES[service_type]


def get_service_list() -> List[ServiceDefinition]:
    """Получить список всех доступных услуг."""
    return list(SERVICES.values())
