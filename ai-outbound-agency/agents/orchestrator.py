"""Lead Pipeline Orchestrator - LangGraph StateGraph for outbound lead processing."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.copywriter import CopywriterAgent
from agents.enricher import EnricherAgent
from agents.researcher import ResearcherAgent

logger = logging.getLogger(__name__)


class PipelineState(TypedDict):
    """State schema for the lead pipeline graph."""

    leads: list[dict[str, Any]]
    enriched_leads: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    campaign_config: dict[str, Any]
    tenant_id: str
    current_step: str
    errors: list[str]


async def research_node(state: PipelineState) -> dict[str, Any]:
    """Find leads matching ICP criteria using ResearcherAgent.

    Expects campaign_config to contain 'icp_criteria' and 'apollo_client'
    and 'settings' keys for agent construction.
    """
    logger.info("Research node: starting lead search")
    config = state["campaign_config"]
    icp_criteria = config.get("icp_criteria", {})
    apollo_client = config.get("apollo_client")
    settings = config.get("settings")

    if not apollo_client or not settings:
        return {
            "leads": [],
            "current_step": "research",
            "errors": state["errors"] + ["Missing apollo_client or settings in campaign_config"],
        }

    researcher = ResearcherAgent(apollo_client=apollo_client, settings=settings)
    max_results = config.get("max_leads", 50)

    try:
        leads = await researcher.research(icp_criteria, max_results=max_results)
    except Exception as exc:
        logger.error("Research node failed: %s", exc)
        return {
            "leads": [],
            "current_step": "research",
            "errors": state["errors"] + [f"Research failed: {exc}"],
        }

    logger.info("Research node: found %d leads", len(leads))
    return {"leads": leads, "current_step": "research"}


async def enrich_node(state: PipelineState) -> dict[str, Any]:
    """Enrich leads with web search and LLM analysis using EnricherAgent."""
    logger.info("Enrich node: enriching %d leads", len(state["leads"]))
    config = state["campaign_config"]
    llm_client = config.get("llm_client")
    settings = config.get("settings")

    if not llm_client or not settings:
        return {
            "enriched_leads": state["leads"],
            "current_step": "enrich",
            "errors": state["errors"] + ["Missing llm_client or settings in campaign_config"],
        }

    enricher = EnricherAgent(llm_client=llm_client, settings=settings)

    try:
        enriched = await enricher.enrich_batch(state["leads"])
    except Exception as exc:
        logger.error("Enrich node failed: %s", exc)
        return {
            "enriched_leads": state["leads"],
            "current_step": "enrich",
            "errors": state["errors"] + [f"Enrichment failed: {exc}"],
        }

    logger.info("Enrich node: enriched %d leads", len(enriched))
    return {"enriched_leads": enriched, "current_step": "enrich"}


async def write_node(state: PipelineState) -> dict[str, Any]:
    """Generate personalized outreach messages using CopywriterAgent."""
    logger.info("Write node: generating messages for %d leads", len(state["enriched_leads"]))
    config = state["campaign_config"]
    llm_client = config.get("llm_client")
    settings = config.get("settings")

    if not llm_client or not settings:
        return {
            "messages": [],
            "current_step": "write",
            "errors": state["errors"] + ["Missing llm_client or settings in campaign_config"],
        }

    copywriter = CopywriterAgent(llm_client=llm_client, settings=settings)
    campaign_context = {
        "sender_name": config.get("sender_name", ""),
        "sender_title": config.get("sender_title", ""),
        "company_name": config.get("company_name", ""),
        "value_proposition": config.get("value_proposition", ""),
        "tone_of_voice": config.get("tone_of_voice", "professional and friendly"),
    }

    all_messages: list[dict[str, Any]] = []
    for lead in state["enriched_leads"]:
        try:
            sequence = await copywriter.write_sequence(lead, campaign_context)
            all_messages.append({
                "lead_email": lead.get("email", ""),
                "lead_name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}",
                "sequence": sequence,
                "status": "draft",
            })
        except Exception as exc:
            logger.warning(
                "Write failed for %s: %s",
                lead.get("email", "unknown"),
                exc,
            )

    logger.info("Write node: generated sequences for %d leads", len(all_messages))
    return {"messages": all_messages, "current_step": "write"}


async def send_node(state: PipelineState) -> dict[str, Any]:
    """Mark messages as sent (placeholder for email delivery)."""
    logger.info("Send node: sending %d message sequences", len(state["messages"]))
    updated_messages: list[dict[str, Any]] = []
    for msg in state["messages"]:
        updated_messages.append({**msg, "status": "sent"})
    return {"messages": updated_messages, "current_step": "send"}


async def wait_node(state: PipelineState) -> dict[str, Any]:
    """Wait for replies (placeholder - simulates wait period)."""
    logger.info("Wait node: waiting for replies")
    return {"current_step": "wait"}


async def handle_reply_node(state: PipelineState) -> dict[str, Any]:
    """Classify reply sentiment and determine next action (placeholder)."""
    logger.info("Handle reply node: processing replies")
    # In production, this would check inbox for replies and classify sentiment
    # For now, return state unchanged - the conditional edge will route accordingly
    return {"current_step": "handle_reply"}


async def book_node(state: PipelineState) -> dict[str, Any]:
    """Book a meeting (placeholder for calendar integration)."""
    logger.info("Book node: attempting to book meeting")
    return {"current_step": "book"}


def _reply_router(state: PipelineState) -> str:
    """Route based on reply classification.

    Returns:
        'book' if positive reply detected,
        'end' if negative reply or unsubscribe,
        'write' if no reply (trigger follow-up).
    """
    # In production, this checks reply sentiment from handle_reply_node
    # Default: no reply -> follow up
    current_messages = state.get("messages", [])

    for msg in current_messages:
        reply_sentiment = msg.get("reply_sentiment")
        if reply_sentiment == "positive":
            return "book"
        elif reply_sentiment == "negative":
            return "end"

    # No replies detected - send follow-up
    return "write"


def build_pipeline() -> Any:
    """Construct and compile the lead pipeline StateGraph.

    Returns:
        Compiled LangGraph application ready for invocation.
    """
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("research", research_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("write", write_node)
    graph.add_node("send", send_node)
    graph.add_node("wait", wait_node)
    graph.add_node("handle_reply", handle_reply_node)
    graph.add_node("book", book_node)

    # Add edges - linear pipeline with conditional branch at handle_reply
    graph.add_edge(START, "research")
    graph.add_edge("research", "enrich")
    graph.add_edge("enrich", "write")
    graph.add_edge("write", "send")
    graph.add_edge("send", "wait")
    graph.add_edge("wait", "handle_reply")

    # Conditional edges from handle_reply
    graph.add_conditional_edges(
        "handle_reply",
        _reply_router,
        {
            "book": "book",
            "end": END,
            "write": "write",
        },
    )

    # Terminal edges
    graph.add_edge("book", END)

    # Compile and return
    compiled = graph.compile()
    return compiled
