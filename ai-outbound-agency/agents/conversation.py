"""Conversation Agent - classifies replies and generates contextual responses."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.llm import LLMClient
from core.models import (
    Campaign,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from integrations.calendar import CalendarIntegration
from integrations.notifications import notify_human
from agents.approval_queue import ApprovalQueue
from agents.reply_quality import ReplyQualityScorer, QUALITY_THRESHOLD

logger = logging.getLogger(__name__)

# Confidence threshold below which automated responses are suppressed
_CONFIDENCE_THRESHOLD = 0.3

CLASSIFICATION_SYSTEM_PROMPT = """\
You are an AI assistant that classifies the intent of email replies in a B2B outreach context.

Classify the reply into exactly one of the following categories:
- positive: The prospect is interested, wants to learn more, or is open to a meeting.
- objection: The prospect raises a specific concern or objection about the product/service.
- question: The prospect asks a question about the product/service/company.
- not_now: The prospect indicates they are not interested right now but may be in the future.
- unsubscribe: The prospect explicitly asks to be removed from the mailing list or to stop receiving emails.
- negative: The prospect is clearly not interested and does not want further contact, but does not explicitly unsubscribe.
- out_of_office: An automated out-of-office or vacation reply.

Return your response as a JSON object with these fields:
- classification: one of the categories above
- confidence: a float between 0.0 and 1.0 indicating your confidence
- details: a brief explanation of why you chose this classification

Only return the JSON object, no other text.
"""

RESPONSE_SYSTEM_PROMPT = """\
You are an AI sales assistant generating a reply to a prospect's email.
Your goal is to be helpful, professional, and advance the conversation toward a meeting or sale.

Context about the campaign:
- Company: {company_name}
- Value Proposition: {value_proposition}
- Sender Name: {sender_name}
- Sender Title: {sender_title}

The prospect's reply was classified as: {classification}

Generate an appropriate response based on the classification:
- If positive: Be enthusiastic and suggest scheduling a meeting. Include the booking link: {booking_link}
- If objection: Address their specific concern using the value proposition. Be empathetic.
- If question: Answer their question based on the campaign context. Be helpful and informative.
- If not_now: Acknowledge their timing, mention you will follow up in 30-60 days.
- If unsubscribe: Confirm their removal from the list. Be professional and gracious.
- If out_of_office: Acknowledge their absence and indicate you will follow up after they return.
- If negative: Close gracefully with no hard feelings. Leave the door open.

Return your response as a JSON object with these fields:
- subject: The email subject line for the reply
- body: The full email body text
- action: One of "send_reply", "schedule_followup", "close", "book_meeting"
- follow_up_days: Number of days to follow up (null if not applicable)

Only return the JSON object, no other text.
"""


class ConversationAgent:
    """Classifies inbound replies and generates contextual responses."""

    def __init__(
        self,
        llm_client: LLMClient,
        settings: Settings,
        calendar: CalendarIntegration,
        session_factory: async_sessionmaker[AsyncSession],
        email_sender: Any | None = None,
    ) -> None:
        self._llm = llm_client
        self._settings = settings
        self._calendar = calendar
        self._session_factory = session_factory
        self._email_sender = email_sender

    async def classify_reply(
        self,
        message_content: str,
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Classify the intent of an inbound reply using the LLM.

        Args:
            message_content: The text content of the reply.
            campaign_context: Context about the campaign for better classification.

        Returns:
            Dict with classification, confidence, and details.
        """
        user_prompt = (
            f"Campaign context:\n"
            f"- Company: {campaign_context.get('company_name', 'N/A')}\n"
            f"- Value Proposition: {campaign_context.get('value_proposition', 'N/A')}\n\n"
            f"Reply to classify:\n{message_content}"
        )

        messages = [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._llm.generate(
                messages=messages,
                temperature=0.1,
                max_tokens=256,
            )
            result = json.loads(response)
            return {
                "classification": result.get("classification", "needs_review"),
                "confidence": float(result.get("confidence", 0.5)),
                "details": result.get("details", ""),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse classification response: %s", exc)
            return {
                "classification": "needs_review",
                "confidence": 0.0,
                "details": "Failed to classify - requires manual review",
            }

    async def generate_response(
        self,
        classification: dict[str, Any],
        original_message: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate an appropriate response based on classification.

        Args:
            classification: Result from classify_reply().
            original_message: The original inbound message text.
            lead_data: Information about the lead.
            campaign_context: Campaign details for context.

        Returns:
            Dict with subject, body, action, and follow_up_days.
        """
        # Generate booking link for positive responses
        booking_link = ""
        if classification.get("classification") == "positive":
            booking_link = await self._calendar.generate_booking_link(
                lead_data=lead_data,
                meeting_duration=30,
            )

        system_prompt = RESPONSE_SYSTEM_PROMPT.format(
            company_name=campaign_context.get("company_name", ""),
            value_proposition=campaign_context.get("value_proposition", ""),
            sender_name=campaign_context.get("sender_name", ""),
            sender_title=campaign_context.get("sender_title", ""),
            classification=classification.get("classification", "needs_review"),
            booking_link=booking_link or "N/A",
        )

        user_prompt = (
            f"Prospect name: {lead_data.get('first_name', '')} {lead_data.get('last_name', '')}\n"
            f"Prospect company: {lead_data.get('company', '')}\n"
            f"Prospect title: {lead_data.get('title', '')}\n\n"
            f"Their reply:\n{original_message}\n\n"
            f"Classification details: {classification.get('details', '')}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._llm.generate(
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            result = json.loads(response)
            return {
                "subject": result.get("subject", "Re: Follow up"),
                "body": result.get("body", ""),
                "action": result.get("action", "send_reply"),
                "follow_up_days": result.get("follow_up_days"),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse response generation: %s", exc)
            return {
                "subject": "Re: Follow up",
                "body": "",
                "action": "needs_review",
                "follow_up_days": None,
            }

    async def handle_reply(self, message_id: str) -> dict[str, Any]:
        """Main entry point for processing an inbound reply.

        Loads message context, classifies the reply, generates a response,
        and updates lead status accordingly. Sends the generated response
        if classification confidence is above threshold and action warrants it.

        Args:
            message_id: UUID string of the inbound message to process.

        Returns:
            Action summary dict with classification, response, and status updates.
        """
        async with self._session_factory() as session:
            # Load the inbound message
            msg_uuid = uuid.UUID(message_id)
            stmt = select(Message).where(Message.id == msg_uuid)
            result = await session.execute(stmt)
            inbound_message = result.scalar_one_or_none()

            if inbound_message is None:
                logger.error("Message %s not found", message_id)
                return {"error": "Message not found"}

            # Load the lead
            lead_stmt = select(Lead).where(Lead.id == inbound_message.lead_id)
            lead_result = await session.execute(lead_stmt)
            lead = lead_result.scalar_one_or_none()

            if lead is None:
                logger.error("Lead not found for message %s", message_id)
                return {"error": "Lead not found"}

            # Load campaign context
            campaign_stmt = select(Campaign).where(
                Campaign.id == inbound_message.campaign_id
            )
            campaign_result = await session.execute(campaign_stmt)
            campaign = campaign_result.scalar_one_or_none()

            campaign_context: dict[str, Any] = {}
            if campaign and campaign.icp_filter:
                campaign_context = {
                    "company_name": campaign.icp_filter.get("company_name", ""),
                    "value_proposition": campaign.icp_filter.get("value_proposition", ""),
                    "sender_name": campaign.icp_filter.get("sender_name", ""),
                    "sender_title": campaign.icp_filter.get("sender_title", ""),
                }

            # Classify the reply
            classification = await self.classify_reply(
                message_content=inbound_message.content,
                campaign_context=campaign_context,
            )

            # Check confidence threshold - if below threshold, skip auto-response
            confidence = classification.get("confidence", 0.0)
            if confidence < _CONFIDENCE_THRESHOLD:
                logger.warning(
                    "Classification confidence %.2f below threshold %.2f for message %s, "
                    "skipping automated response",
                    confidence,
                    _CONFIDENCE_THRESHOLD,
                    message_id,
                )
                classification["classification"] = "needs_review"
                await session.commit()
                return {
                    "message_id": message_id,
                    "classification": classification,
                    "response": None,
                    "lead_status": lead.status.value if lead.status else None,
                    "skipped": "confidence_below_threshold",
                }

            # Build lead data dict
            lead_data: dict[str, Any] = {
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "company": lead.company,
                "title": lead.title,
            }

            # Generate response
            response = await self.generate_response(
                classification=classification,
                original_message=inbound_message.content,
                lead_data=lead_data,
                campaign_context=campaign_context,
            )

            # Quality scoring for auto-send responses
            quality_score_value = None
            action = response.get("action", "")
            if action in ("send_reply", "book_meeting"):
                quality_scorer = ReplyQualityScorer(self._llm)
                quality_result = await quality_scorer.score_response(
                    response_text=response.get("body", ""),
                    prospect_message=inbound_message.content,
                    campaign_context=campaign_context,
                )
                quality_score_value = quality_result.overall_score

                if quality_result.overall_score < QUALITY_THRESHOLD:
                    # Route to approval queue with quality notes
                    response["quality_score"] = quality_result.overall_score
                    response["quality_notes"] = quality_result.improvement_suggestions

                    async with self._session_factory() as approval_session:
                        await ApprovalQueue.create_approval(
                            session=approval_session,
                            lead_id=lead.id,
                            message_id=inbound_message.id,
                            proposed_response=response,
                        )
                        await approval_session.commit()

                    await notify_human(
                        lead_data=lead_data,
                        classification=classification.get("classification", ""),
                        proposed_response=response,
                        settings=self._settings,
                    )

                    logger.info(
                        "Routed reply %s to approval queue (quality_score=%d < %d)",
                        message_id,
                        quality_result.overall_score,
                        QUALITY_THRESHOLD,
                    )

                    return {
                        "message_id": message_id,
                        "classification": classification,
                        "response": response,
                        "lead_status": lead.status.value if lead.status else None,
                        "routed_to_approval": True,
                        "response_sent": False,
                        "quality_score": quality_score_value,
                    }

            # Update lead status based on classification
            intent = classification.get("classification", "")
            if intent == "positive":
                lead.status = LeadStatus.qualified
            elif intent in ("unsubscribe", "negative"):
                lead.status = LeadStatus.lost
            elif intent in ("objection", "question"):
                lead.status = LeadStatus.replied

            # Handle unsubscribe opt-out
            if intent == "unsubscribe":
                enrichment = lead.enrichment_data or {}
                enrichment["opted_out"] = True
                enrichment["opt_out_reason"] = "unsubscribe_reply"
                lead.enrichment_data = enrichment

            await session.commit()

            # Determine if this reply requires human approval
            requires_approval = self._requires_human_approval(
                classification=intent,
                lead=lead,
            )

            if requires_approval:
                # Route to approval queue instead of auto-sending
                async with self._session_factory() as approval_session:
                    await ApprovalQueue.create_approval(
                        session=approval_session,
                        lead_id=lead.id,
                        message_id=inbound_message.id,
                        proposed_response=response,
                    )
                    await approval_session.commit()

                # Notify human reviewers
                await notify_human(
                    lead_data=lead_data,
                    classification=intent,
                    proposed_response=response,
                    settings=self._settings,
                )

                logger.info(
                    "Routed reply %s to approval queue (classification=%s)",
                    message_id,
                    intent,
                )

                return {
                    "message_id": message_id,
                    "classification": classification,
                    "response": response,
                    "lead_status": lead.status.value if lead.status else None,
                    "routed_to_approval": True,
                    "response_sent": False,
                }

            # Send the generated response if action warrants it
            action = response.get("action", "")
            response_sent = False
            if (
                action in ("send_reply", "book_meeting")
                and response.get("body")
                and self._email_sender is not None
            ):
                try:
                    reply_msg_id = str(uuid.uuid4())
                    send_result = await self._email_sender.send_email(
                        to=lead.email,
                        subject=response["subject"],
                        html_body=f"<p>{response['body']}</p>",
                        message_id=reply_msg_id,
                        tracking_pixel_url=None,
                        tracked_links=None,
                    )
                    response_sent = send_result.get("success", False)
                    if response_sent:
                        logger.info(
                            "Sent automated reply to %s for message %s",
                            lead.email,
                            message_id,
                        )
                    else:
                        logger.warning(
                            "Failed to send automated reply to %s for message %s",
                            lead.email,
                            message_id,
                        )
                except Exception as exc:
                    logger.error(
                        "Error sending automated reply for message %s: %s",
                        message_id,
                        exc,
                    )

            logger.info(
                "Processed reply %s: classification=%s, action=%s, sent=%s",
                message_id,
                classification.get("classification"),
                response.get("action"),
                response_sent,
            )

            return {
                "message_id": message_id,
                "classification": classification,
                "response": response,
                "lead_status": lead.status.value if lead.status else None,
                "response_sent": response_sent,
                "quality_score": quality_score_value,
            }

    def _requires_human_approval(
        self,
        classification: str,
        lead: Lead,
    ) -> bool:
        """Determine if a reply requires human approval before responding.

        Approval is required if:
        - Classification is 'positive'
        - Lead's company has more employees than approval_required_company_size
        - Lead's title contains C-level keywords

        Args:
            classification: The reply classification string.
            lead: The Lead ORM instance.

        Returns:
            True if human approval is required.
        """
        # Positive replies always require approval
        if classification == "positive":
            return True

        # Check company size from enrichment data
        enrichment = lead.enrichment_data or {}
        company_data = enrichment.get("company_data", {})
        employee_count = company_data.get("employee_count", 0)
        if isinstance(employee_count, (int, float)) and employee_count > self._settings.approval_required_company_size:
            return True

        # Check for C-level titles
        c_level_keywords = ("ceo", "cto", "cfo", "coo", "cmo", "vp", "director")
        title = (lead.title or "").lower()
        for keyword in c_level_keywords:
            if keyword in title:
                return True

        return False
