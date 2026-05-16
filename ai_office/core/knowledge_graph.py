"""Граф знаний для хранения и запроса фактов."""

import re
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import KnowledgeFact


class KnowledgeGraph:
    """Граф знаний на основе троек (субъект-предикат-объект)."""

    async def add_fact(
        self,
        session: AsyncSession,
        subject: str,
        predicate: str,
        object_value: str,
        source_agent: str,
        confidence: float = 0.8,
        workspace_id: Optional[int] = None,
    ) -> KnowledgeFact:
        """Добавить факт в граф знаний."""
        fact = KnowledgeFact(
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            source_agent=source_agent,
            confidence=confidence,
            workspace_id=workspace_id,
        )
        session.add(fact)
        await session.commit()
        await session.refresh(fact)
        return fact

    async def query(
        self,
        session: AsyncSession,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object_value: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> list[KnowledgeFact]:
        """Запросить факты по параметрам."""
        query = select(KnowledgeFact)
        conditions = []

        if subject:
            conditions.append(KnowledgeFact.subject.contains(subject))
        if predicate:
            conditions.append(KnowledgeFact.predicate.contains(predicate))
        if object_value:
            conditions.append(KnowledgeFact.object_value.contains(object_value))
        if workspace_id is not None:
            conditions.append(KnowledgeFact.workspace_id == workspace_id)

        if conditions:
            query = query.where(*conditions)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_related(
        self,
        session: AsyncSession,
        entity: str,
        depth: int = 2,
        workspace_id: Optional[int] = None,
    ) -> list[KnowledgeFact]:
        """Получить связанные факты (entity как субъект или объект)."""
        visited_ids: set[int] = set()
        entities_to_check = [entity]
        all_facts: list[KnowledgeFact] = []

        for _ in range(depth):
            if not entities_to_check:
                break
            next_entities = []
            for ent in entities_to_check:
                query = select(KnowledgeFact).where(
                    or_(
                        KnowledgeFact.subject == ent,
                        KnowledgeFact.object_value == ent,
                    )
                )
                if workspace_id is not None:
                    query = query.where(KnowledgeFact.workspace_id == workspace_id)

                result = await session.execute(query)
                facts = result.scalars().all()
                for fact in facts:
                    if fact.id not in visited_ids:
                        visited_ids.add(fact.id)
                        all_facts.append(fact)
                        next_entities.append(fact.subject)
                        next_entities.append(fact.object_value)

            entities_to_check = list(set(next_entities) - {entity})

        return all_facts

    async def forget(self, session: AsyncSession, fact_id: int) -> bool:
        """Удалить факт по ID."""
        result = await session.execute(
            select(KnowledgeFact).where(KnowledgeFact.id == fact_id)
        )
        fact = result.scalar_one_or_none()
        if fact is None:
            return False
        await session.delete(fact)
        await session.commit()
        return True


# Module-level instance
knowledge_graph = KnowledgeGraph()


def extract_facts(text: str, agent_name: str) -> list[dict]:
    """Извлечение фактов из русского текста на основе шаблонов.

    Patterns:
    - "X использует Y"
    - "X предпочитает Y"
    - "X решил Y"
    - "клиент X хочет Y"
    """
    facts = []
    patterns = [
        (r"(\w+)\s+использует\s+(.+?)(?:\.|$)", "использует"),
        (r"(\w+)\s+предпочитает\s+(.+?)(?:\.|$)", "предпочитает"),
        (r"(\w+)\s+решил\s+(.+?)(?:\.|$)", "решил"),
        (r"клиент\s+(\w+)\s+хочет\s+(.+?)(?:\.|$)", "хочет"),
    ]

    for pattern, predicate in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            facts.append({
                "subject": match.group(1).strip(),
                "predicate": predicate,
                "object_value": match.group(2).strip(),
                "source_agent": agent_name,
                "confidence": 0.7,
            })

    return facts
