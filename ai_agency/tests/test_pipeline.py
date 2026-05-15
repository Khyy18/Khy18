"""Integration tests for pipeline module with mocked LLM."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from models import ServiceType


@pytest.mark.asyncio
class TestPipeline:
    """Integration tests with mocked LLM APIs."""

    @pytest.fixture(autouse=True)
    def reset_pipeline_singletons(self):
        """Reset pipeline singleton clients before each test."""
        import pipeline
        pipeline._openai_client = None
        pipeline._groq_client = None
        yield

    async def test_process_order_simple_service(self, initialized_db):
        """process_order returns result for simple service (REWRITE)."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = " ".join(["word"] * 60)

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("pipeline._get_openai_client", return_value=mock_openai):
            with patch("pipeline._openai_circuit", None):
                with patch("pipeline.retry_with_backoff", None):
                    import pipeline
                    # Override _call_openai to skip retry wrapper
                    original_call = pipeline._call_openai

                    async def mock_call_openai(messages, temperature=0.7, max_tokens=4000):
                        client = mock_openai
                        response = await client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        return response.choices[0].message.content.strip()

                    with patch("pipeline._call_openai", mock_call_openai):
                        result, variant_id = await pipeline.process_order(
                            ServiceType.REWRITE, "Hello world text to rewrite"
                        )

        assert result is not None
        assert "word" in result

    async def test_process_order_full_pipeline(self, initialized_db):
        """process_order returns result for full pipeline service (COPYWRITING)."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = " ".join(["content"] * 120)

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("pipeline._get_openai_client", return_value=mock_openai):
            with patch("pipeline._openai_circuit", None):
                import pipeline

                async def mock_call_openai(messages, temperature=0.7, max_tokens=4000):
                    client = mock_openai
                    response = await client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].message.content.strip()

                with patch("pipeline._call_openai", mock_call_openai):
                    result, variant_id = await pipeline.process_order(
                        ServiceType.COPYWRITING, "Write me a sales text"
                    )

        assert result is not None
        assert "content" in result

    async def test_process_order_openai_fails_groq_fallback(self, initialized_db):
        """process_order handles OpenAI failure with Groq fallback."""
        groq_response = MagicMock()
        groq_response.choices = [MagicMock()]
        groq_response.choices[0].message.content = " ".join(["groq_word"] * 60)

        mock_groq = AsyncMock()
        mock_groq.chat.completions.create = AsyncMock(return_value=groq_response)

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=Exception("OpenAI API error")
        )

        with patch("pipeline._get_openai_client", return_value=mock_openai):
            with patch("pipeline._get_groq_client", return_value=mock_groq):
                with patch("pipeline._openai_circuit", None):
                    import pipeline

                    async def failing_openai(messages, temperature=0.7, max_tokens=4000):
                        raise Exception("OpenAI API error")

                    with patch("pipeline._call_openai", failing_openai):
                        result, variant_id = await pipeline.process_order(
                            ServiceType.REWRITE, "Some text to rewrite"
                        )

        assert result is not None
        assert "groq_word" in result

    async def test_process_order_both_apis_fail(self, initialized_db):
        """process_order returns None when both APIs fail."""
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=Exception("OpenAI error")
        )

        mock_groq = AsyncMock()
        mock_groq.chat.completions.create = AsyncMock(
            side_effect=Exception("Groq error")
        )

        with patch("pipeline._get_openai_client", return_value=mock_openai):
            with patch("pipeline._get_groq_client", return_value=mock_groq):
                with patch("pipeline._openai_circuit", None):
                    import pipeline

                    async def failing_openai(messages, temperature=0.7, max_tokens=4000):
                        raise Exception("OpenAI error")

                    with patch("pipeline._call_openai", failing_openai):
                        result, variant_id = await pipeline.process_order(
                            ServiceType.REWRITE, "Some text"
                        )

        assert result is None

    async def test_ab_variant_selected_when_exists(self, initialized_db):
        """A/B variant is selected when variants exist."""
        import ab_testing

        await ab_testing.add_variant("rewrite", "test_v1", "Custom test prompt")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = " ".join(["ab_word"] * 60)

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("pipeline._get_openai_client", return_value=mock_openai):
            with patch("pipeline._openai_circuit", None):
                import pipeline

                async def mock_call_openai(messages, temperature=0.7, max_tokens=4000):
                    client = mock_openai
                    response = await client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].message.content.strip()

                with patch("pipeline._call_openai", mock_call_openai):
                    result, variant_id = await pipeline.process_order(
                        ServiceType.REWRITE, "Text for AB test"
                    )

        assert result is not None
        assert variant_id is not None
