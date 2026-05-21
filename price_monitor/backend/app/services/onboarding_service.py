"""Сервис онбординга для новых пользователей."""

from dataclasses import dataclass


@dataclass
class OnboardingStep:
    step_id: int
    title: str
    description: str
    action: str  # что пользователь должен сделать
    completed: bool = False


ONBOARDING_STEPS = [
    OnboardingStep(1, "Добро пожаловать", "Мы находим лучшие скидки на WB и Ozon", "start"),
    OnboardingStep(2, "Выберите категории", "Какие товары вас интересуют?", "select_categories"),
    OnboardingStep(3, "Настройте алерт", "Создайте первое уведомление о снижении цены", "create_alert"),
    OnboardingStep(4, "Пригласите друга", "Получите неделю VIP бесплатно за приглашение", "invite_friend"),
    OnboardingStep(5, "Готово!", "Вы настроили всё. Скидки уже ищутся!", "complete"),
]


class OnboardingService:
    """Управление прогрессом онбординга."""

    @staticmethod
    def get_steps(completed_step_ids: list[int]) -> list[dict]:
        """Получить все шаги с отметками выполнения."""
        result = []
        for step in ONBOARDING_STEPS:
            result.append({
                "step_id": step.step_id,
                "title": step.title,
                "description": step.description,
                "action": step.action,
                "completed": step.step_id in completed_step_ids,
            })
        return result

    @staticmethod
    def get_current_step(completed_step_ids: list[int]) -> dict | None:
        """Получить текущий (первый невыполненный) шаг."""
        for step in ONBOARDING_STEPS:
            if step.step_id not in completed_step_ids:
                return {
                    "step_id": step.step_id,
                    "title": step.title,
                    "description": step.description,
                    "action": step.action,
                }
        return None

    @staticmethod
    def is_completed(completed_step_ids: list[int]) -> bool:
        """Проверить, завершён ли онбординг."""
        return len(completed_step_ids) >= len(ONBOARDING_STEPS)


onboarding_service = OnboardingService()
