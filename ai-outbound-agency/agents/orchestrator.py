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
    """Send messages via AsyncEmailSender with tracking.

    Expects campaign_config to contain 'email_sender' (AsyncEmailSender instance)
    and 'tracker' (EmailTracker instance) for sending emails with open/click tracking.
    """
    logger.info("Send node: sending %d message sequences", len(state["messages"]))
    config = state["campaign_config"]
    email_sender = config.get("email_sender")
    tracker = config.get("tracker")

    updated_messages: list[dict[str, Any]] = []
    for msg in state["messages"]:
        if not email_sender:
            # No email sender configured - mark as sent without actually sending
            updated_messages.append({**msg, "status": "sent"})
            continue

        lead_email = msg.get("lead_email", "")
        sequence = msg.get("sequence", [])

        # Send the first message in the sequence
        if sequence:
            first_step = sequence[0] if isinstance(sequence, list) else sequence
            subject = first_step.get("subject", "") if isinstance(first_step, dict) else ""
            body = first_step.get("body", "") if isinstance(first_step, dict) else ""
            message_id = msg.get("message_id", str(__import__("uuid").uuid4()))

            # Generate tracking URLs if tracker is available
            tracking_pixel_url = None
            if tracker:
                tracking_pixel_url = tracker.generate_tracking_pixel_url(message_id)

            try:
                result = await email_sender.send_email(
                    to=lead_email,
                    subject=subject,
                    html_body=body,
                    message_id=message_id,
                    tracking_pixel_url=tracking_pixel_url,
                    tracked_links=None,
                )
                status = "sent" if result.get("success") else "failed"
            except Exception as exc:
                logger.error("Failed to send email to %s: %s", lead_email, exc)
                status = "failed"

            updated_messages.append({**msg, "status": status, "message_id": message_id})
        else:
            updated_messages.append({**msg, "status": "sent"})

    return {"messages": updated_messages, "current_step": "send"}


async def wait_node(state: PipelineState) -> dict[str, Any]:
    """Wait for replies (placeholder - simulates wait period)."""
    logger.info("Wait node: waiting for replies")
    return {"current_step": "wait"}


async def handle_reply_node(state: PipelineState) -> dict[str, Any]:
    """Classify reply sentiment using ConversationAgent and update messages.

    Expects campaign_config to contain 'conversation_agent' (ConversationAgent instance).
    Classifies replies and sets reply_sentiment on messages so _reply_router can route.
    """
    logger.info("Handle reply node: processing replies")
    config = state["campaign_config"]
    conversation_agent = config.get("conversation_agent")

    if not conversation_agent:
        # No conversation agent configured - cannot classify replies
        logger.warning("No conversation_agent in campaign_config, skipping classification")
        return {"current_step": "handle_reply"}

    updated_messages: list[dict[str, Any]] = []
    for msg in state.get("messages", []):
        # Check if there is a reply to process
        reply_content = msg.get("reply_content")
        if not reply_content:
            updated_messages.append(msg)
            continue

        # Classify the reply using ConversationAgent
        campaign_context = {
            "company_name": config.get("company_name", ""),
            "value_proposition": config.get("value_proposition", ""),
            "sender_name": config.get("sender_name", ""),
            "sender_title": config.get("sender_title", ""),
        }

        try:
            classification = await conversation_agent.classify_reply(
                message_content=reply_content,
                campaign_context=campaign_context,
            )
            intent = classification.get("classification", "")

            # Map classification to reply_sentiment for _reply_router
            if intent == "positive":
                reply_sentiment = "positive"
            elif intent in ("negative", "unsubscribe"):
                reply_sentiment = "negative"
            else:
                reply_sentiment = None  # Will trigger follow-up via _reply_router

            updated_messages.append({
                **msg,
                "reply_sentiment": reply_sentiment,
                "classification": classification,
            })
        except Exception as exc:
            logger.error("Failed to classify reply for message: %s", exc)
            updated_messages.append(msg)

    return {"messages": updated_messages, "current_step": "handle_reply"}


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
