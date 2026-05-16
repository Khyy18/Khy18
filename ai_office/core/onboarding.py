"""Onboarding state machine для новых рабочих пространств."""

import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import Workspace

logger = logging.getLogger(__name__)


ONBOARDING_STEPS = [
    {
        "step": 1,
        "question": "Чем занимается ваша команда?",
        "options": ["Development", "Marketing", "Design", "Mixed"],
        "key": "team_type",
    },
    {
        "step": 2,
        "question": "Сколько человек в команде?",
        "options": ["1-3", "4-10", "10+"],
        "key": "team_size",
    },
    {
        "step": 3,
        "question": "Какие задачи хотите автоматизировать?",
        "options": ["Task management", "Code review", "Content", "Analytics"],
        "key": "automation_goals",
    },
]


class OnboardingManager:
    """State machine для онбординга новых рабочих пространств."""

    async def start_onboarding(
        self, session: AsyncSession, workspace_id: int
    ) -> dict:
        """Start onboarding for a workspace.

        Returns the first question with options.
        """
        result = await session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Initialize onboarding state
        settings = json.loads(workspace.settings_json) if workspace.settings_json else {}
        settings["onboarding"] = {
            "current_step": 1,
            "answers": {},
            "completed": False,
        }
        workspace.settings_json = json.dumps(settings, ensure_ascii=False)
        await session.commit()

        step = ONBOARDING_STEPS[0]
        return {
            "step": step["step"],
            "question": step["question"],
            "options": step["options"],
        }

    async def handle_onboarding_response(
        self, session: AsyncSession, workspace_id: int, step: int, answer: str
    ) -> Optional[dict]:
        """Handle an onboarding answer and return next question or None if done.

        Returns:
            dict with next question, or None if onboarding is complete.
        """
        result = await session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")

        settings = json.loads(workspace.settings_json) if workspace.settings_json else {}
        onboarding = settings.get("onboarding", {})

        # Validate step
        if step < 1 or step > len(ONBOARDING_STEPS):
            raise ValueError(f"Invalid step: {step}")

        step_config = ONBOARDING_STEPS[step - 1]

        # Store answer
        answers = onboarding.get("answers", {})
        answers[step_config["key"]] = answer
        onboarding["answers"] = answers

        # Move to next step
        next_step = step + 1
        if next_step > len(ONBOARDING_STEPS):
            # Onboarding complete
            onboarding["current_step"] = step
            onboarding["completed"] = True
            settings["onboarding"] = onboarding
            workspace.settings_json = json.dumps(settings, ensure_ascii=False)
            await session.commit()

            # Finalize onboarding
            await self.finalize_onboarding(session, workspace_id, answers)
            return None
        else:
            onboarding["current_step"] = next_step
            settings["onboarding"] = onboarding
            workspace.settings_json = json.dumps(settings, ensure_ascii=False)
            await session.commit()

            next_step_config = ONBOARDING_STEPS[next_step - 1]
            return {
                "step": next_step_config["step"],
                "question": next_step_config["question"],
                "options": next_step_config["options"],
            }

    async def finalize_onboarding(
        self, session: AsyncSession, workspace_id: int, answers: dict
    ) -> dict:
        """Configure workspace settings based on onboarding answers.

        Args:
            session: Database session
            workspace_id: Workspace ID
            answers: Dict of onboarding answers (team_type, team_size, automation_goals)

        Returns:
            dict with final workspace configuration
        """
        result = await session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")

        settings = json.loads(workspace.settings_json) if workspace.settings_json else {}

        # Configure enabled agents based on team type
        team_type = answers.get("team_type", "Mixed")
        agent_configs = {
            "Development": ["alice", "sam", "leo", "nova"],
            "Marketing": ["alice", "iris", "eva", "max"],
            "Design": ["alice", "max", "eva", "iris"],
            "Mixed": ["alice", "sam", "max", "eva", "leo", "nova", "iris", "oscar"],
        }
        enabled_agents = agent_configs.get(team_type, agent_configs["Mixed"])

        # Configure team size settings
        team_size = answers.get("team_size", "4-10")
        max_concurrent_tasks = {"1-3": 3, "4-10": 8, "10+": 15}.get(team_size, 8)

        # Configure automation preferences
        automation_goals = answers.get("automation_goals", "Task management")
        automation_config = {
            "Task management": {"auto_assign": True, "daily_standup": True},
            "Code review": {"code_review_enabled": True, "pr_notifications": True},
            "Content": {"content_calendar": True, "social_posting": True},
            "Analytics": {"weekly_reports": True, "metrics_tracking": True},
        }
        automation = automation_config.get(
            automation_goals, automation_config["Task management"]
        )

        # Build final configuration
        config = {
            "enabled_agents": enabled_agents,
            "max_concurrent_tasks": max_concurrent_tasks,
            "automation": automation,
            "onboarding": settings.get("onboarding", {}),
        }

        workspace.settings_json = json.dumps(config, ensure_ascii=False)
        await session.commit()

        logger.info(
            "Workspace %d onboarding finalized: team=%s, size=%s, goals=%s",
            workspace_id,
            team_type,
            team_size,
            automation_goals,
        )

        return config


# Module-level instance
onboarding_manager = OnboardingManager()
