"""Оркестратор агентов на базе LangGraph StateGraph."""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from ai_office.agents.registry import registry
from ai_office.core.config import settings


class AgentState(TypedDict):
    """Состояние графа агентов."""

    messages: Annotated[list[BaseMessage], add_messages]
    current_agent: str
    task_context: dict
    chat_history: list[dict]


class RouterDecision(BaseModel):
    """Структурированный ответ роутера."""

    target_agent: str = Field(
        description="Имя агента для маршрутизации"
    )


ROUTER_SYSTEM_PROMPT = """Ты - маршрутизатор запросов в AI Office. Определи какому агенту адресовать сообщение пользователя.

Доступные агенты:
- alice: Персональный ассистент и продакт-менеджер. Занимается задачами, планированием, приоритетами, управлением проектами, общими вопросами.
- sam: Senior Developer. Занимается кодом, архитектурой, багами, техническими вопросами, ревью, деплоем.
- max: UI/UX дизайнер. Занимается дизайном интерфейсов, вайрфреймами, UX-аудитом, юзабилити, визуальной частью.
- eva: Бизнес-аналитик. Занимается требованиями, user stories, аналитическими отчётами, метриками, исследованием рынка.
- leo: QA инженер. Занимается тестированием, тест-планами, баг-репортами, верификацией исправлений, качеством продукта.
- nova: DevOps/SRE инженер. Занимается деплоями, мониторингом, CI/CD, инфраструктурой, производительностью.

Верни имя агента, которому лучше всего подходит запрос. Если не уверен - выбери alice."""


def _get_llm() -> ChatOpenAI:
    """Получить экземпляр LLM."""
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
    )


async def router_node(state: AgentState) -> AgentState:
    """Маршрутизатор: определяет какому агенту адресовано сообщение через LLM."""
    messages = state["messages"]
    if not messages:
        return {**state, "current_agent": "alice"}

    last_message = messages[-1]
    if not isinstance(last_message, HumanMessage):
        return {**state, "current_agent": "alice"}

    try:
        router_llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
            temperature=0,
        )
        structured_llm = router_llm.with_structured_output(RouterDecision)

        # Формируем контекст для роутера
        router_messages = [SystemMessage(content=ROUTER_SYSTEM_PROMPT)]

        # Добавляем историю чата для контекста
        chat_history = state.get("chat_history", [])
        for msg in chat_history[-5:]:
            if msg["role"] == "human":
                router_messages.append(HumanMessage(content=msg["content"]))
            else:
                router_messages.append(AIMessage(content=msg["content"]))

        router_messages.append(HumanMessage(content=last_message.content))

        decision = await structured_llm.ainvoke(router_messages)

        target_agent = decision.target_agent.lower()
        if target_agent not in registry.get_names():
            target_agent = "alice"

    except Exception:
        target_agent = "alice"

    return {**state, "current_agent": target_agent}


def make_agent_node(config):
    """Фабрика нод агентов: создаёт async-функцию ноды для заданного агента."""

    async def agent_node(state: AgentState) -> AgentState:
        llm = _get_llm()
        llm_with_tools = llm.bind_tools(config.tools)

        # Формируем сообщения с системным промптом
        messages = [SystemMessage(content=config.system_prompt)] + state["messages"]

        response = await llm_with_tools.ainvoke(messages)
        return {**state, "messages": [response], "current_agent": config.name}

    agent_node.__name__ = f"{config.name}_node"
    agent_node.__doc__ = f"Нода агента {config.name} - {config.role}."
    return agent_node


async def tool_node(state: AgentState) -> AgentState:
    """Нода выполнения инструментов (async)."""
    messages = state["messages"]
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state

    # Собираем все доступные инструменты из реестра
    all_tools = {}
    for config in registry.get_all():
        for t in config.tools:
            all_tools[t.name] = t

    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if tool_name in all_tools:
            result = await all_tools[tool_name].ainvoke(tool_args)
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


def _route_after_router(state: AgentState) -> str:
    """Условное ребро: после роутера направляем к нужному агенту."""
    agent_name = state.get("current_agent", "alice")
    return f"{agent_name}_node"


def _route_after_agent(state: AgentState) -> str:
    """Условное ребро: после агента проверяем нужны ли вызовы инструментов."""
    messages = state["messages"]
    if not messages:
        return "__end__"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool_node"
    return "__end__"


def _route_after_tools(state: AgentState) -> str:
    """Условное ребро: после выполнения инструментов возвращаемся к агенту."""
    agent_name = state.get("current_agent", "alice")
    return f"{agent_name}_node"


def build_graph() -> StateGraph:
    """Собрать и скомпилировать граф агентов."""
    graph = StateGraph(AgentState)

    # Добавляем ноды
    graph.add_node("router", router_node)
    graph.add_node("tool_node", tool_node)

    # Динамически добавляем ноды агентов из реестра
    agent_nodes = {}
    for config in registry.get_all():
        node_name = f"{config.name}_node"
        agent_nodes[config.name] = node_name
        graph.add_node(node_name, make_agent_node(config))

    # Точка входа
    graph.set_entry_point("router")

    # Условные ребра после роутера -> к агенту
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {node_name: node_name for node_name in agent_nodes.values()},
    )

    # Условные ребра после каждого агента (инструменты или завершение)
    for node_name in agent_nodes.values():
        graph.add_conditional_edges(
            node_name,
            _route_after_agent,
            {"tool_node": "tool_node", "__end__": END},
        )

    # После выполнения инструментов возвращаемся к агенту
    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {node_name: node_name for node_name in agent_nodes.values()},
    )

    # Компилируем граф
    compiled = graph.compile()
    return compiled
