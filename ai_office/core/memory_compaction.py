"""Memory compaction: summarize expired memories via LLM and replace originals."""

import logging
from datetime import datetime, timezone

from ai_office.agents.registry import registry
from ai_office.core.llm_provider import llm_provider
from ai_office.core.memory import agent_memory, MEMORY_TTL_DAYS

logger = logging.getLogger(__name__)

# Batch size for compaction (number of entries to summarize at once)
COMPACTION_BATCH_SIZE = 10


async def compact_agent_memory(agent_name: str) -> int:
    """Compact expired memories for a single agent.

    Retrieves expired entries, groups into batches of COMPACTION_BATCH_SIZE,
    calls LLM to summarize each batch, deletes originals, stores summary
    with fresh TTL.

    Args:
        agent_name: Name of the agent whose memory to compact.

    Returns:
        Number of entries compacted (deleted and replaced with summaries).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    expired_entries = agent_memory.get_expired(agent_name, before_date=now_iso)

    if not expired_entries:
        logger.debug("No expired memories for agent '%s'", agent_name)
        return 0

    total_compacted = 0

    # Group into batches of COMPACTION_BATCH_SIZE
    for i in range(0, len(expired_entries), COMPACTION_BATCH_SIZE):
        batch = expired_entries[i:i + COMPACTION_BATCH_SIZE]

        # Build prompt for LLM summarization
        texts = [entry["text"] for entry in batch]
        combined = "\n---\n".join(texts)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a memory compaction assistant. "
                    "Summarize the following memory entries into a single concise summary "
                    "that preserves all important facts, decisions, and context. "
                    "Write in the same language as the input."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize these {len(batch)} memory entries:\n\n{combined}",
            },
        ]

        try:
            response = await llm_provider.ainvoke_with_retry(
                messages=messages,
                agent_name=agent_name,
            )
            summary_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(
                "LLM summarization failed for agent '%s' batch %d: %s. Skipping batch.",
                agent_name,
                i // COMPACTION_BATCH_SIZE,
                str(e),
            )
            # Don't delete originals if summarization failed
            continue

        # Delete original entries
        batch_ids = [entry["id"] for entry in batch]
        deleted = agent_memory.delete_batch(agent_name, batch_ids)

        if not deleted:
            logger.error(
                "Failed to delete batch for agent '%s'. Summary not stored.",
                agent_name,
            )
            continue

        # Store compressed summary with fresh TTL
        agent_memory.store(
            agent_name=agent_name,
            text=summary_text,
            metadata={"type": "compressed_memory", "original_count": str(len(batch))},
        )

        total_compacted += len(batch)

    logger.info(
        "Memory compaction for agent '%s': %d entries compacted",
        agent_name,
        total_compacted,
    )
    return total_compacted


async def run_memory_compaction() -> dict[str, int]:
    """Run memory compaction for all registered agents.

    Returns:
        Dict mapping agent_name -> number of entries compacted.
    """
    results = {}

    agent_names = registry.get_names()
    if not agent_names:
        logger.info("No agents registered, skipping memory compaction")
        return results

    for agent_name in agent_names:
        try:
            compacted = await compact_agent_memory(agent_name)
            results[agent_name] = compacted
        except Exception as e:
            logger.error(
                "Memory compaction failed for agent '%s': %s",
                agent_name,
                str(e),
            )
            results[agent_name] = 0

    total = sum(results.values())
    logger.info("Memory compaction complete: %d total entries compacted", total)
    return results
