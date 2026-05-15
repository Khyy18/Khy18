"""Оркестратор агентов на базе LangGraph StateGraph."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from ai_office.agents.alice import alice_config
from ai_office.agents.sam import sam_config
from ai_office.core.config import settings


class AgentState(TypedDict):
    """Состояние графа агентов."""

    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    task_context: dict
    chat_history: list[dict]


def _get_llm() -> ChatOpenAI:
    """Получить экземпляр LLM."""
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
    )


def router_node(state: AgentState) -> AgentState:
    """Маршрутизатор: определяет какому агенту адресовано сообщение."""
    messages = state["messages"]
    if not messages:
        return {**state, "current_agent": "alice"}

    last_message = messages[-1]
    content = ""
    if isinstance(last_message, HumanMessage):
        content = last_message.content.lower()

    # Ключевые слова для маршрутизации
    sam_keywords = [
        "код", "code", "баг", "bug", "архитектур", "рефактор",
        "функци", "класс", "api", "тест", "деплой", "deploy",
        "sam", "сэм", "разработ", "программ", "ошибк",
    ]

    alice_keywords = [
        "задач", "task", "план", "приоритет", "статус",
        "alice", "алис", "проект", "управлени", "команд",
    ]

    # Определяем агента по ключевым словам
    sam_score = sum(1 for kw in sam_keywords if kw in content)
    alice_score = sum(1 for kw in alice_keywords if kw in content)

    if sam_score > alice_score:
        target_agent = "sam"
    else:
        # По умолчанию - Alice (как точка входа)
        target_agent = "alice"

    return {**state, "current_agent": target_agent}


def alice_node(state: AgentState) -> AgentState:
    """Нода агента Alice - персональный ассистент."""
    llm = _get_llm()
    llm_with_tools = llm.bind_tools(alice_config.tools)

    # Формируем сообщения с системным промптом
    messages = [SystemMessage(content=alice_config.system_prompt)] + state["messages"]

    response = llm_with_tools.invoke(messages)
    return {**state, "messages": [response], "current_agent": "alice"}


def sam_node(state: AgentState) -> AgentState:
    """Нода агента Sam - разработчик."""
    llm = _get_llm()
    llm_with_tools = llm.bind_tools(sam_config.tools)

    # Формируем сообщения с системным промптом
    messages = [SystemMessage(content=sam_config.system_prompt)] + state["messages"]

    response = llm_with_tools.invoke(messages)
    return {**state, "messages": [response], "current_agent": "sam"}


def tool_node(state: AgentState) -> AgentState:
    """Нода выполнения инструментов."""
    messages = state["messages"]
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state

    # Собираем все доступные инструменты
    all_tools = {t.name: t for t in alice_config.tools + sam_config.tools}

    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if tool_name in all_tools:
            result = all_tools[tool_name].invoke(tool_args)
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"],
                )
            )
        else:
            tool_messages.append(
                ToolMessage(
                    content=f"Инструмент '{tool_name}' не найден.",
                    tool_call_id=tool_call["id"],
                )
            )

    return {**state, "messages": tool_messages}


def _route_after_router(state: AgentState) -> Literal["alice_node", "sam_node"]:
    """Условное ребро: после роутера направляем к нужному агенту."""
    if state.get("current_agent") == "sam":
        return "sam_node"
    return "alice_node"


def _route_after_agent(state: AgentState) -> Literal["tool_node", "__end__"]:
    """Условное ребро: после агента проверяем нужны ли вызовы инструментов."""
    messages = state["messages"]
    if not messages:
        return "__end__"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool_node"
    return "__end__"


def _route_after_tools(state: AgentState) -> Literal["alice_node", "sam_node"]:
    """Условное ребро: после выполнения инструментов возвращаемся к агенту."""
    if state.get("current_agent") == "sam":
        return "sam_node"
    return "alice_node"


def build_graph() -> StateGraph:
    """Собрать и скомпилировать граф агентов."""
    graph = StateGraph(AgentState)

    # Добавляем ноды
    graph.add_node("router", router_node)
    graph.add_node("alice_node", alice_node)
    graph.add_node("sam_node", sam_node)
    graph.add_node("tool_node", tool_node)

    # Точка входа
    graph.set_entry_point("router")

    # Условные ребра после роутера
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {"alice_node": "alice_node", "sam_node": "sam_node"},
    )

    # Условные ребра после агентов (инструменты или завершение)
    graph.add_conditional_edges(
        "alice_node",
        _route_after_agent,
        {"tool_node": "tool_node", "__end__": END},
    )
    graph.add_conditional_edges(
        "sam_node",
        _route_after_agent,
        {"tool_node": "tool_node", "__end__": END},
    )

    # После выполнения инструментов возвращаемся к агенту
    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {"alice_node": "alice_node", "sam_node": "sam_node"},
    )

    # Компилируем граф
    compiled = graph.compile()
    return compiled
