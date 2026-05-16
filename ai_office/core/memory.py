"""Персистентная векторная память агентов на базе ChromaDB."""

import logging
import uuid

logger = logging.getLogger(__name__)

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("chromadb не установлен. Память агентов будет недоступна.")


_UNSET = object()


class AgentMemory:
    """Хранилище долгосрочной памяти агентов с семантическим поиском."""

    def __init__(self, client=_UNSET):
        """Инициализация памяти.

        Args:
            client: ChromaDB клиент. По умолчанию создается PersistentClient.
                    Передайте None для отключения памяти.
        """
        self._collections: dict = {}

        if client is _UNSET:
            # Создать клиент по умолчанию
            if CHROMADB_AVAILABLE:
                try:
                    self._client = chromadb.PersistentClient(path="./ai_office_memory")
                except Exception as e:
                    logger.error(f"Не удалось инициализировать ChromaDB: {e}")
                    self._client = None
            else:
                self._client = None
        else:
            self._client = client

    def _get_collection(self, agent_name: str):
        """Получить или создать коллекцию для агента."""
        collection_name = f"agent_{agent_name}"
        if collection_name not in self._collections:
            if self._client is None:
                return None
            try:
                self._collections[collection_name] = self._client.get_or_create_collection(
                    name=collection_name
                )
            except Exception as e:
                logger.error(f"Ошибка при получении коллекции '{collection_name}': {e}")
                return None
        return self._collections[collection_name]

    def store(self, agent_name: str, text: str, metadata: dict | None = None) -> str:
        """Сохранить текст в память агента.

        Args:
            agent_name: Имя агента.
            text: Текст для сохранения.
            metadata: Дополнительные метаданные.

        Returns:
            ID сохраненной записи или пустая строка при ошибке.
        """
        if not CHROMADB_AVAILABLE or self._client is None:
            return ""

        collection = self._get_collection(agent_name)
        if collection is None:
            return ""

        memory_id = uuid.uuid4().hex
        try:
            add_kwargs = {
                "ids": [memory_id],
                "documents": [text],
            }
            if metadata:
                add_kwargs["metadatas"] = [metadata]
            collection.add(**add_kwargs)
            return memory_id
        except Exception as e:
            logger.error(f"Ошибка при сохранении в память: {e}")
            return ""

    def recall(self, agent_name: str, query: str, k: int = 5) -> list[dict]:
        """Найти релевантные воспоминания по запросу.

        Args:
            agent_name: Имя агента.
            query: Поисковый запрос.
            k: Количество результатов.

        Returns:
            Список словарей с ключами id, text, metadata.
        """
        if not CHROMADB_AVAILABLE or self._client is None:
            return []

        collection = self._get_collection(agent_name)
        if collection is None:
            return []

        try:
            # Не запрашивать больше, чем есть документов
            count = collection.count()
            if count == 0:
                return []
            n_results = min(k, count)

            results = collection.query(
                query_texts=[query],
                n_results=n_results,
            )

            memories = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    memories.append({
                        "id": doc_id,
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    })
            return memories
        except Exception as e:
            logger.error(f"Ошибка при поиске в памяти: {e}")
            return []

    def forget(self, agent_name: str, memory_id: str) -> bool:
        """Удалить запись из памяти агента.

        Args:
            agent_name: Имя агента.
            memory_id: ID записи для удаления.

        Returns:
            True если удалено успешно, False при ошибке.
        """
        if not CHROMADB_AVAILABLE or self._client is None:
            return False

        collection = self._get_collection(agent_name)
        if collection is None:
            return False

        try:
            collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении из памяти: {e}")
            return False


# Singleton экземпляр для использования по всему приложению
agent_memory = AgentMemory()
