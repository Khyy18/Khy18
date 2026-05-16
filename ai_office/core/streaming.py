"""Streaming callback for real-time agent response broadcasting via WebSocket."""

import uuid
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from ai_office.api.websocket import broadcast_event


class StreamingCallback(AsyncCallbackHandler):
    """Callback that broadcasts LLM tokens via WebSocket as they arrive."""

    def __init__(self, agent_name: str):
        super().__init__()
        self.agent_name = agent_name
        self.message_id = uuid.uuid4()
        self._buffer: list[str] = []

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Broadcast each new token chunk to connected clients."""
        self._buffer.append(token)
        await broadcast_event(
            "agent_typing_chunk",
            {
                "agent": self.agent_name,
                "chunk": token,
                "message_id": str(self.message_id),
            },
        )

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Broadcast the complete response when LLM finishes."""
        full_text = ""
        try:
            full_text = response.generations[0][0].text
        except (IndexError, AttributeError):
            full_text = "".join(self._buffer)

        await broadcast_event(
            "agent_response_complete",
            {
                "agent": self.agent_name,
                "message_id": str(self.message_id),
                "full_text": full_text,
            },
        )
