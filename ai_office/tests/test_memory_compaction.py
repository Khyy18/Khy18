"""Тесты Memory TTL и компактификации."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from ai_office.core.memory import AgentMemory, MEMORY_TTL_DAYS


@pytest.fixture
def ephemeral_memory():
    """Фикстура AgentMemory с EphemeralClient."""
    if not CHROMADB_AVAILABLE:
        pytest.skip("chromadb не установлен")
    client = chromadb.EphemeralClient()
    for col in client.list_collections():
        client.delete_collection(col if isinstance(col, str) else col.name)
    memory = AgentMemory(client=client)
    return memory


class TestMemoryTTL:
    """Тесты TTL metadata в store."""

    def test_store_adds_expires_at_metadata(self, ephemeral_memory):
        """store всегда добавляет expires_at в метаданные."""
        memory_id = ephemeral_memory.store("alice", "Тестовый факт")
        assert memory_id

        # Recall to check metadata
        results = ephemeral_memory.recall("alice", "Тестовый факт", k=1)
        assert len(results) == 1
        assert "expires_at" in results[0]["metadata"]

        # Validate it's a parseable ISO date approximately 30 days from now
        expires_at = datetime.fromisoformat(results[0]["metadata"]["expires_at"])
        expected = datetime.now(timezone.utc) + timedelta(days=MEMORY_TTL_DAYS)
        # Allow 1 minute tolerance
        assert abs((expires_at - expected).total_seconds()) < 60

    def test_store_preserves_custom_metadata(self, ephemeral_memory):
        """store сохраняет пользовательские метаданные наряду с expires_at."""
        memory_id = ephemeral_memory.store(
            "alice", "Факт", metadata={"type": "decision", "priority": "high"}
        )
        assert memory_id

        results = ephemeral_memory.recall("alice", "Факт", k=1)
        assert len(results) == 1
        meta = results[0]["metadata"]
        assert meta["type"] == "decision"
        assert meta["priority"] == "high"
        assert "expires_at" in meta

    def test_store_without_client_returns_empty(self):
        """Без ChromaDB store возвращает пустую строку."""
        memory = AgentMemory(client=None)
        result = memory.store("alice", "test")
        assert result == ""


class TestGetExpired:
    """Тесты метода get_expired."""

    def test_get_expired_returns_expired_entries(self, ephemeral_memory):
        """get_expired возвращает записи с истекшим TTL."""
        # Store an entry with expired TTL (in the past)
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        collection = ephemeral_memory._get_collection("alice")
        collection.add(
            ids=["expired1", "expired2"],
            documents=["Старый факт 1", "Старый факт 2"],
            metadatas=[
                {"expires_at": past_date},
                {"expires_at": past_date},
            ],
        )

        # Store a fresh entry (not expired)
        ephemeral_memory.store("alice", "Свежий факт")

        # Get expired entries - use current time as cutoff
        now_iso = datetime.now(timezone.utc).isoformat()
        expired = ephemeral_memory.get_expired("alice", before_date=now_iso)

        assert len(expired) == 2
        expired_ids = {e["id"] for e in expired}
        assert "expired1" in expired_ids
        assert "expired2" in expired_ids

    def test_get_expired_returns_empty_when_none_expired(self, ephemeral_memory):
        """get_expired возвращает пустой список если нет просроченных."""
        ephemeral_memory.store("alice", "Свежий факт")

        now_iso = datetime.now(timezone.utc).isoformat()
        expired = ephemeral_memory.get_expired("alice", before_date=now_iso)
        assert expired == []

    def test_get_expired_without_client(self):
        """Без ChromaDB get_expired возвращает пустой список."""
        memory = AgentMemory(client=None)
        result = memory.get_expired("alice", "2025-01-01T00:00:00+00:00")
        assert result == []


class TestDeleteBatch:
    """Тесты метода delete_batch."""

    def test_delete_batch_removes_entries(self, ephemeral_memory):
        """delete_batch удаляет указанные записи."""
        id1 = ephemeral_memory.store("alice", "Факт 1")
        id2 = ephemeral_memory.store("alice", "Факт 2")
        id3 = ephemeral_memory.store("alice", "Факт 3")

        result = ephemeral_memory.delete_batch("alice", [id1, id2])
        assert result is True

        # Only id3 should remain
        all_entries = ephemeral_memory.get_all_for_agent("alice")
        remaining_ids = {e["id"] for e in all_entries}
        assert id3 in remaining_ids
        assert id1 not in remaining_ids
        assert id2 not in remaining_ids

    def test_delete_batch_empty_list(self, ephemeral_memory):
        """delete_batch с пустым списком возвращает True."""
        result = ephemeral_memory.delete_batch("alice", [])
        assert result is True

    def test_delete_batch_without_client(self):
        """Без ChromaDB delete_batch возвращает False."""
        memory = AgentMemory(client=None)
        result = memory.delete_batch("alice", ["id1"])
        assert result is False


class TestGetStats:
    """Тесты метода get_stats."""

    def test_get_stats_returns_counts(self, ephemeral_memory):
        """get_stats возвращает количество записей по агентам."""
        ephemeral_memory.store("alice", "Факт 1")
        ephemeral_memory.store("alice", "Факт 2")
        ephemeral_memory.store("sam", "Факт Sam")

        stats = ephemeral_memory.get_stats()
        assert stats["entries_per_agent"]["alice"] == 2
        assert stats["entries_per_agent"]["sam"] == 1
        assert stats["total_entries"] == 3

    def test_get_stats_empty(self, ephemeral_memory):
        """get_stats без записей возвращает пустую статистику."""
        stats = ephemeral_memory.get_stats()
        assert stats["entries_per_agent"] == {}
        assert stats["total_entries"] == 0

    def test_get_stats_without_client(self):
        """Без ChromaDB get_stats возвращает пустой результат."""
        memory = AgentMemory(client=None)
        stats = memory.get_stats()
        assert stats == {"entries_per_agent": {}, "total_entries": 0}


class TestGetAllForAgent:
    """Тесты метода get_all_for_agent."""

    def test_get_all_for_agent_returns_entries(self, ephemeral_memory):
        """get_all_for_agent возвращает все записи агента."""
        ephemeral_memory.store("alice", "Факт 1")
        ephemeral_memory.store("alice", "Факт 2")
        ephemeral_memory.store("alice", "Факт 3")

        entries = ephemeral_memory.get_all_for_agent("alice")
        assert len(entries) == 3
        for entry in entries:
            assert "id" in entry
            assert "text" in entry
            assert "metadata" in entry

    def test_get_all_for_agent_respects_limit(self, ephemeral_memory):
        """get_all_for_agent соблюдает лимит."""
        for i in range(20):
            ephemeral_memory.store("alice", f"Факт {i}")

        entries = ephemeral_memory.get_all_for_agent("alice", limit=5)
        assert len(entries) == 5

    def test_get_all_for_agent_empty(self, ephemeral_memory):
        """get_all_for_agent для пустой коллекции возвращает пустой список."""
        entries = ephemeral_memory.get_all_for_agent("alice")
        assert entries == []

    def test_get_all_for_agent_without_client(self):
        """Без ChromaDB get_all_for_agent возвращает пустой список."""
        memory = AgentMemory(client=None)
        entries = memory.get_all_for_agent("alice")
        assert entries == []


class TestCompactAgentMemory:
    """Тесты функции compact_agent_memory."""

    @pytest.mark.asyncio
    async def test_compact_summarizes_expired_entries(self, ephemeral_memory):
        """compact_agent_memory суммирует просроченные записи и заменяет оригиналы."""
        from ai_office.core.memory_compaction import compact_agent_memory

        # Add expired entries directly
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        collection = ephemeral_memory._get_collection("alice")
        collection.add(
            ids=["e1", "e2", "e3"],
            documents=["Факт 1", "Факт 2", "Факт 3"],
            metadatas=[
                {"expires_at": past_date},
                {"expires_at": past_date},
                {"expires_at": past_date},
            ],
        )

        # Mock LLM provider
        mock_response = MagicMock()
        mock_response.content = "Сводка: три факта о проекте"

        with patch("ai_office.core.memory_compaction.agent_memory", ephemeral_memory):
            with patch("ai_office.core.memory_compaction.llm_provider") as mock_llm:
                mock_llm.ainvoke_with_retry = AsyncMock(return_value=mock_response)

                compacted = await compact_agent_memory("alice")

        assert compacted == 3

        # Originals should be deleted, summary stored
        all_entries = ephemeral_memory.get_all_for_agent("alice")
        assert len(all_entries) == 1
        assert all_entries[0]["text"] == "Сводка: три факта о проекте"
        assert all_entries[0]["metadata"]["type"] == "compressed_memory"
        assert "expires_at" in all_entries[0]["metadata"]

    @pytest.mark.asyncio
    async def test_compact_no_expired_entries(self, ephemeral_memory):
        """compact_agent_memory с нет просроченных записей возвращает 0."""
        from ai_office.core.memory_compaction import compact_agent_memory

        # Store fresh entry
        ephemeral_memory.store("alice", "Свежий факт")

        with patch("ai_office.core.memory_compaction.agent_memory", ephemeral_memory):
            compacted = await compact_agent_memory("alice")

        assert compacted == 0

    @pytest.mark.asyncio
    async def test_compact_llm_failure_skips_batch(self, ephemeral_memory):
        """При ошибке LLM пакет пропускается, оригиналы не удаляются."""
        from ai_office.core.memory_compaction import compact_agent_memory

        # Add expired entries
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        collection = ephemeral_memory._get_collection("alice")
        collection.add(
            ids=["e1", "e2"],
            documents=["Факт 1", "Факт 2"],
            metadatas=[
                {"expires_at": past_date},
                {"expires_at": past_date},
            ],
        )

        with patch("ai_office.core.memory_compaction.agent_memory", ephemeral_memory):
            with patch("ai_office.core.memory_compaction.llm_provider") as mock_llm:
                mock_llm.ainvoke_with_retry = AsyncMock(
                    side_effect=RuntimeError("LLM unavailable")
                )

                compacted = await compact_agent_memory("alice")

        # Nothing should be compacted
        assert compacted == 0

        # Originals should still be there
        all_entries = ephemeral_memory.get_all_for_agent("alice")
        assert len(all_entries) == 2


class TestRunMemoryCompaction:
    """Тесты функции run_memory_compaction."""

    @pytest.mark.asyncio
    async def test_run_memory_compaction_iterates_agents(self):
        """run_memory_compaction вызывает compact_agent_memory для каждого агента."""
        from ai_office.core.memory_compaction import run_memory_compaction

        with patch("ai_office.core.memory_compaction.registry") as mock_registry:
            mock_registry.get_names.return_value = ["alice", "sam", "eva"]

            with patch(
                "ai_office.core.memory_compaction.compact_agent_memory",
                new_callable=AsyncMock,
            ) as mock_compact:
                mock_compact.return_value = 5

                results = await run_memory_compaction()

        assert results == {"alice": 5, "sam": 5, "eva": 5}
        assert mock_compact.call_count == 3

    @pytest.mark.asyncio
    async def test_run_memory_compaction_no_agents(self):
        """run_memory_compaction без агентов возвращает пустой словарь."""
        from ai_office.core.memory_compaction import run_memory_compaction

        with patch("ai_office.core.memory_compaction.registry") as mock_registry:
            mock_registry.get_names.return_value = []

            results = await run_memory_compaction()

        assert results == {}

    @pytest.mark.asyncio
    async def test_run_memory_compaction_handles_agent_error(self):
        """run_memory_compaction обрабатывает ошибку для одного агента."""
        from ai_office.core.memory_compaction import run_memory_compaction

        with patch("ai_office.core.memory_compaction.registry") as mock_registry:
            mock_registry.get_names.return_value = ["alice", "sam"]

            with patch(
                "ai_office.core.memory_compaction.compact_agent_memory",
                new_callable=AsyncMock,
            ) as mock_compact:
                mock_compact.side_effect = [
                    5,
                    RuntimeError("Failed"),
                ]

                results = await run_memory_compaction()

        assert results == {"alice": 5, "sam": 0}


class TestMemoryMetrics:
    """Тесты memory_stats в /api/metrics."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint_includes_memory_stats(self, ephemeral_memory):
        """Эндпоинт /api/metrics включает ai_office_memory_entries."""
        from httpx import AsyncClient, ASGITransport
        from ai_office.api.main import app

        with patch("ai_office.api.routes.metrics.agent_memory", ephemeral_memory):
            ephemeral_memory.store("alice", "Факт 1")
            ephemeral_memory.store("alice", "Факт 2")
            ephemeral_memory.store("sam", "Факт Sam")

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/metrics")

            assert response.status_code == 200
            content = response.text
            assert "ai_office_memory_entries" in content
