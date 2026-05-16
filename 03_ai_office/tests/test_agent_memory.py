"""Тесты персистентной векторной памяти агентов (ChromaDB)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from ai_office.core.memory import AgentMemory


@pytest.fixture
def ephemeral_memory():
    """Фикстура AgentMemory с EphemeralClient (без файлов на диске)."""
    if not CHROMADB_AVAILABLE:
        pytest.skip("chromadb не установлен")
    client = chromadb.EphemeralClient()
    # Удаляем все коллекции для чистого состояния
    for col in client.list_collections():
        client.delete_collection(col if isinstance(col, str) else col.name)
    memory = AgentMemory(client=client)
    return memory


class TestAgentMemoryStore:
    """Тесты метода store."""

    def test_store_returns_id(self, ephemeral_memory):
        """store возвращает непустой ID."""
        memory_id = ephemeral_memory.store("alice", "Пользователь предпочитает Python")
        assert memory_id
        assert isinstance(memory_id, str)
        assert len(memory_id) == 32  # uuid4().hex

    def test_store_with_metadata(self, ephemeral_memory):
        """store сохраняет данные с метаданными."""
        memory_id = ephemeral_memory.store(
            "sam", "Архитектура на FastAPI", metadata={"type": "decision"}
        )
        assert memory_id

    def test_store_creates_collection_per_agent(self, ephemeral_memory):
        """Каждый агент получает свою коллекцию."""
        ephemeral_memory.store("alice", "Факт для Alice")
        ephemeral_memory.store("sam", "Факт для Sam")

        # У каждого агента своя коллекция
        alice_results = ephemeral_memory.recall("alice", "Alice")
        sam_results = ephemeral_memory.recall("sam", "Sam")

        assert len(alice_results) == 1
        assert len(sam_results) == 1
        assert alice_results[0]["text"] == "Факт для Alice"
        assert sam_results[0]["text"] == "Факт для Sam"

    def test_store_without_chromadb_returns_empty(self):
        """Без ChromaDB store возвращает пустую строку."""
        memory = AgentMemory(client=None)
        memory_id = memory.store("alice", "test")
        assert memory_id == ""


class TestAgentMemoryRecall:
    """Тесты метода recall."""

    def test_recall_returns_relevant_results(self, ephemeral_memory):
        """recall находит семантически похожие записи."""
        ephemeral_memory.store("alice", "Проект использует FastAPI для API")
        ephemeral_memory.store("alice", "База данных PostgreSQL")
        ephemeral_memory.store("alice", "Фронтенд на React")

        results = ephemeral_memory.recall("alice", "веб-фреймворк для API")
        assert len(results) > 0
        # Результаты содержат необходимые поля
        assert "id" in results[0]
        assert "text" in results[0]
        assert "metadata" in results[0]

    def test_recall_respects_k_parameter(self, ephemeral_memory):
        """recall возвращает не более k результатов."""
        for i in range(10):
            ephemeral_memory.store("alice", f"Факт номер {i}")

        results = ephemeral_memory.recall("alice", "факт", k=3)
        assert len(results) <= 3

    def test_recall_empty_collection(self, ephemeral_memory):
        """recall из пустой коллекции возвращает пустой список."""
        results = ephemeral_memory.recall("alice", "что-нибудь")
        assert results == []

    def test_recall_without_chromadb_returns_empty(self):
        """Без ChromaDB recall возвращает пустой список."""
        memory = AgentMemory(client=None)
        results = memory.recall("alice", "query")
        assert results == []

    def test_recall_different_agents_isolated(self, ephemeral_memory):
        """Память разных агентов изолирована."""
        ephemeral_memory.store("alice", "Секрет Alice")
        ephemeral_memory.store("sam", "Секрет Sam")

        alice_results = ephemeral_memory.recall("alice", "секрет")
        sam_results = ephemeral_memory.recall("sam", "секрет")

        assert len(alice_results) == 1
        assert alice_results[0]["text"] == "Секрет Alice"
        assert len(sam_results) == 1
        assert sam_results[0]["text"] == "Секрет Sam"


class TestAgentMemoryForget:
    """Тесты метода forget."""

    def test_forget_removes_memory(self, ephemeral_memory):
        """forget удаляет запись по ID."""
        memory_id = ephemeral_memory.store("alice", "Временный факт")
        assert memory_id

        result = ephemeral_memory.forget("alice", memory_id)
        assert result is True

        # После удаления recall не должен находить запись
        results = ephemeral_memory.recall("alice", "Временный факт")
        assert len(results) == 0

    def test_forget_without_chromadb_returns_false(self):
        """Без ChromaDB forget возвращает False."""
        memory = AgentMemory(client=None)
        result = memory.forget("alice", "some_id")
        assert result is False


class TestMemoryTools:
    """Тесты инструментов памяти."""

    @pytest.mark.asyncio
    async def test_remember_tool_stores_fact(self):
        """remember сохраняет факт и возвращает подтверждение."""
        from ai_office.tools.memory_tools import remember, set_current_agent

        set_current_agent("alice")

        with patch("ai_office.tools.memory_tools.agent_memory") as mock_memory:
            mock_memory.store.return_value = "abc123"
            with patch("ai_office.tools.memory_tools._log_activity", new_callable=AsyncMock):
                result = await remember.ainvoke({"fact": "Python 3.11 используется"})

            assert "Запомнено" in result
            assert "abc123" in result
            mock_memory.store.assert_called_once_with(
                agent_name="alice",
                text="Python 3.11 используется",
                metadata={"type": "manual", "agent": "alice"},
            )

    @pytest.mark.asyncio
    async def test_remember_tool_handles_failure(self):
        """remember обрабатывает ошибку сохранения."""
        from ai_office.tools.memory_tools import remember, set_current_agent

        set_current_agent("sam")

        with patch("ai_office.tools.memory_tools.agent_memory") as mock_memory:
            mock_memory.store.return_value = ""
            with patch("ai_office.tools.memory_tools._log_activity", new_callable=AsyncMock):
                result = await remember.ainvoke({"fact": "test"})

            assert "Не удалось" in result

    @pytest.mark.asyncio
    async def test_recall_memory_tool_returns_results(self):
        """recall_memory возвращает найденные воспоминания."""
        from ai_office.tools.memory_tools import recall_memory, set_current_agent

        set_current_agent("alice")

        with patch("ai_office.tools.memory_tools.agent_memory") as mock_memory:
            mock_memory.recall.return_value = [
                {"id": "id1", "text": "FastAPI используется", "metadata": {}},
                {"id": "id2", "text": "React на фронте", "metadata": {}},
            ]
            with patch("ai_office.tools.memory_tools._log_activity", new_callable=AsyncMock):
                result = await recall_memory.ainvoke({"query": "технологии"})

            assert "FastAPI используется" in result
            assert "React на фронте" in result
            mock_memory.recall.assert_called_once_with(
                agent_name="alice", query="технологии", k=5
            )

    @pytest.mark.asyncio
    async def test_recall_memory_tool_no_results(self):
        """recall_memory при отсутствии результатов возвращает соответствующее сообщение."""
        from ai_office.tools.memory_tools import recall_memory, set_current_agent

        set_current_agent("alice")

        with patch("ai_office.tools.memory_tools.agent_memory") as mock_memory:
            mock_memory.recall.return_value = []
            with patch("ai_office.tools.memory_tools._log_activity", new_callable=AsyncMock):
                result = await recall_memory.ainvoke({"query": "несуществующее"})

            assert "ничего не найдено" in result
