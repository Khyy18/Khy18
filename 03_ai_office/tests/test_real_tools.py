"""Тесты реальных инструментов (code execution, web search, github)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# === Тесты execute_python_code ===


@pytest.mark.asyncio
async def test_execute_python_code_simple():
    """Тест: execute_python_code выполняет простой код."""
    from ai_office.tools.code_tools import execute_python_code

    with patch("ai_office.tools.code_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await execute_python_code.ainvoke({"code": "print(2+2)"})
        assert "4" in result


@pytest.mark.asyncio
async def test_execute_python_code_timeout():
    """Тест: execute_python_code обрабатывает таймаут."""
    from ai_office.tools.code_tools import execute_python_code

    with patch("ai_office.tools.code_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await execute_python_code.ainvoke({"code": "while True: pass"})
        assert "таймаут" in result or "время" in result


@pytest.mark.asyncio
async def test_execute_python_code_syntax_error():
    """Тест: execute_python_code обрабатывает синтаксические ошибки."""
    from ai_office.tools.code_tools import execute_python_code

    with patch("ai_office.tools.code_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await execute_python_code.ainvoke({"code": "def foo(:"})
        assert "Ошибка" in result or "SyntaxError" in result


# === Тесты web_search ===


@pytest.mark.asyncio
async def test_web_search_success():
    """Тест: web_search возвращает результаты из DuckDuckGo API."""
    from ai_office.tools.search_tools import web_search

    mock_response_data = {
        "AbstractText": "Python is a programming language.",
        "Results": [{"Text": "Python.org - Official site"}],
        "RelatedTopics": [
            {"Text": "Python tutorial - Learn Python basics"},
            {"Text": "Python documentation - Official docs"},
        ],
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("ai_office.tools.search_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_result_db = MagicMock()
        mock_result_db.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result_db)

        with patch("ai_office.tools.search_tools.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await web_search.ainvoke({"query": "Python programming"})
            assert "Python" in result
            assert "programming language" in result


@pytest.mark.asyncio
async def test_web_search_no_results():
    """Тест: web_search обрабатывает пустой ответ."""
    from ai_office.tools.search_tools import web_search

    mock_response_data = {
        "AbstractText": "",
        "Results": [],
        "RelatedTopics": [],
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("ai_office.tools.search_tools.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_result_db = MagicMock()
        mock_result_db.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result_db)

        with patch("ai_office.tools.search_tools.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await web_search.ainvoke({"query": "xyznonexistent"})
            assert "ничего не найдено" in result


# === Тесты github_tools ===


@pytest.mark.asyncio
async def test_create_github_issue_no_token():
    """Тест: create_github_issue возвращает ошибку без токена."""
    from ai_office.tools.github_tools import create_github_issue

    with patch("ai_office.tools.github_tools.settings") as mock_settings:
        mock_settings.github_token = ""

        result = await create_github_issue.ainvoke({
            "repo": "owner/repo",
            "title": "Test issue",
            "body": "Test body",
        })
        assert "GITHUB_TOKEN не настроен" in result


@pytest.mark.asyncio
async def test_list_github_issues_no_token():
    """Тест: list_github_issues возвращает ошибку без токена."""
    from ai_office.tools.github_tools import list_github_issues

    with patch("ai_office.tools.github_tools.settings") as mock_settings:
        mock_settings.github_token = ""

        result = await list_github_issues.ainvoke({"repo": "owner/repo"})
        assert "GITHUB_TOKEN не настроен" in result


@pytest.mark.asyncio
async def test_create_pull_request_comment_no_token():
    """Тест: create_pull_request_comment возвращает ошибку без токена."""
    from ai_office.tools.github_tools import create_pull_request_comment

    with patch("ai_office.tools.github_tools.settings") as mock_settings:
        mock_settings.github_token = ""

        result = await create_pull_request_comment.ainvoke({
            "repo": "owner/repo",
            "pr_number": 1,
            "body": "Test comment",
        })
        assert "GITHUB_TOKEN не настроен" in result


@pytest.mark.asyncio
async def test_create_github_issue_success():
    """Тест: create_github_issue успешно создает issue."""
    from ai_office.tools.github_tools import create_github_issue

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "number": 42,
        "title": "Test issue",
        "html_url": "https://github.com/owner/repo/issues/42",
    }

    with patch("ai_office.tools.github_tools.settings") as mock_settings:
        mock_settings.github_token = "test-token-123"

        with patch("ai_office.tools.github_tools.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result_db = MagicMock()
            mock_result_db.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result_db)

            with patch("ai_office.tools.github_tools.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await create_github_issue.ainvoke({
                    "repo": "owner/repo",
                    "title": "Test issue",
                    "body": "Test body",
                })
                assert "#42" in result
                assert "Test issue" in result


@pytest.mark.asyncio
async def test_list_github_issues_success():
    """Тест: list_github_issues успешно получает список issues."""
    from ai_office.tools.github_tools import list_github_issues

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"number": 1, "title": "First issue", "state": "open"},
        {"number": 2, "title": "Second issue", "state": "open"},
    ]

    with patch("ai_office.tools.github_tools.settings") as mock_settings:
        mock_settings.github_token = "test-token-123"

        with patch("ai_office.tools.github_tools.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_result_db = MagicMock()
            mock_result_db.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result_db)

            with patch("ai_office.tools.github_tools.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await list_github_issues.ainvoke({"repo": "owner/repo"})
                assert "#1" in result
                assert "First issue" in result
                assert "#2" in result
