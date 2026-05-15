"""Edge Case Detector - handles uncommon conversation scenarios."""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class EdgeCaseType:
    """Edge case type constants."""

    LANGUAGE_SWITCH = "language_switch"
    FORWARDED_REPLY = "forwarded_reply"
    DELAYED_REPLY = "delayed_reply"
    PHONE_REQUEST = "phone_request"
    WRONG_PERSON = "wrong_person"
    AUTO_REPLY_LOOP = "auto_reply_loop"
    MULTIPLE_RAPID_REPLIES = "multiple_rapid_replies"
    CC_DETECTED = "cc_detected"


# Common non-English words indicating a language switch
_NON_ENGLISH_WORDS = (
    "bonjour",
    "hola",
    "danke",
    "gracias",
    "merci",
    "bitte",
    "guten",
    "buenos",
    "salut",
    "ciao",
    "obrigado",
    "spasibo",
    "privet",
    "nihao",
    "konnichiwa",
    "annyeong",
    "shukran",
    "dziekuje",
    "bedankt",
)

# Patterns for phone request detection
_PHONE_PATTERNS = re.compile(
    r"(call me|give me a call|phone number|let'?s hop on a call|my number is|"
    r"schedule a call|ring me|dial me|phone call)",
    re.IGNORECASE,
)

# Patterns for wrong person detection
_WRONG_PERSON_PATTERNS = re.compile(
    r"(wrong person|not the right person|you should talk to|forward this to|"
    r"i'?m not|not me|i don'?t handle|not my area|try reaching out to|"
    r"contact .+ instead)",
    re.IGNORECASE,
)

# Auto-reply signatures
_AUTO_REPLY_PATTERNS = re.compile(
    r"(auto-reply|automatic reply|out of office|noreply@|no-reply@|"
    r"auto.?response|automated message|away from the office|"
    r"currently unavailable|will be out)",
    re.IGNORECASE,
)

# Forwarded message patterns
_FORWARDED_PATTERNS = re.compile(
    r"(^FW:|^Fwd:|---------- Forwarded message|"
    r"Begin forwarded message|Original Message)",
    re.IGNORECASE | re.MULTILINE,
)


class EdgeCaseDetector:
    """Detects and handles uncommon conversation edge cases."""

    def __init__(self, llm_client: Any = None) -> None:
        """Initialize EdgeCaseDetector.

        Args:
            llm_client: Optional LLM client for generating responses.
        """
        self._llm = llm_client

    def detect_edge_case(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        conversation_history: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str | None:
        """Check message for edge cases and return first match or None.

        Args:
            message_content: The text content of the reply.
            lead_data: Information about the lead.
            conversation_history: Previous messages for this lead.
            headers: Email headers (cc, bcc, etc).

        Returns:
            Edge case type string or None if no edge case detected.
        """
        # Check language switch
        if self._is_language_switch(message_content):
            return EdgeCaseType.LANGUAGE_SWITCH

        # Check forwarded reply
        if self._is_forwarded_reply(message_content):
            return EdgeCaseType.FORWARDED_REPLY

        # Check delayed reply
        if self._is_delayed_reply(conversation_history):
            return EdgeCaseType.DELAYED_REPLY

        # Check phone request
        if self._is_phone_request(message_content):
            return EdgeCaseType.PHONE_REQUEST

        # Check wrong person
        if self._is_wrong_person(message_content):
            return EdgeCaseType.WRONG_PERSON

        # Check auto-reply loop
        if self._is_auto_reply_loop(message_content, conversation_history):
            return EdgeCaseType.AUTO_REPLY_LOOP

        # Check multiple rapid replies
        if self._is_multiple_rapid_replies(conversation_history):
            return EdgeCaseType.MULTIPLE_RAPID_REPLIES

        # Check CC detected
        if self._is_cc_detected(headers):
            return EdgeCaseType.CC_DETECTED

        return None

    def _is_language_switch(self, message_content: str) -> bool:
        """Detect if message is in a non-English language."""
        content_lower = message_content.lower()

        # Check for common non-English words
        for word in _NON_ENGLISH_WORDS:
            if word in content_lower:
                return True

        # Check non-ASCII character ratio
        if len(message_content) > 0:
            non_ascii_count = sum(1 for c in message_content if ord(c) > 127)
            ratio = non_ascii_count / len(message_content)
            if ratio > 0.3:
                return True

        return False

    def _is_forwarded_reply(self, message_content: str) -> bool:
        """Detect forwarded messages."""
        return bool(_FORWARDED_PATTERNS.search(message_content))

    def _is_delayed_reply(
        self, conversation_history: list[dict[str, Any]] | None
    ) -> bool:
        """Detect if last message was more than 30 days ago."""
        if not conversation_history:
            return False

        # Find the most recent message in history
        last_msg = conversation_history[-1]
        last_date = last_msg.get("sent_at")

        if last_date is None:
            return False

        if isinstance(last_date, str):
            try:
                last_date = datetime.fromisoformat(last_date)
            except (ValueError, TypeError):
                return False

        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return (now - last_date) > timedelta(days=30)

    def _is_phone_request(self, message_content: str) -> bool:
        """Detect phone/call requests."""
        return bool(_PHONE_PATTERNS.search(message_content))

    def _is_wrong_person(self, message_content: str) -> bool:
        """Detect wrong person / referral patterns."""
        return bool(_WRONG_PERSON_PATTERNS.search(message_content))

    def _is_auto_reply_loop(
        self,
        message_content: str,
        conversation_history: list[dict[str, Any]] | None,
    ) -> bool:
        """Detect auto-reply loop (bot signature + consecutive auto-replies)."""
        # Check if current message is an auto-reply
        is_auto = bool(_AUTO_REPLY_PATTERNS.search(message_content))

        if not is_auto:
            return False

        # Check conversation history for consecutive auto-replies
        if conversation_history:
            auto_reply_count = 0
            for msg in reversed(conversation_history):
                content = msg.get("content", "")
                if _AUTO_REPLY_PATTERNS.search(content):
                    auto_reply_count += 1
                else:
                    break
            # 2+ prior auto-replies plus current one = loop
            if auto_reply_count >= 2:
                return True

        # Even a single auto-reply message is detected as an edge case
        return True

    def _is_multiple_rapid_replies(
        self, conversation_history: list[dict[str, Any]] | None
    ) -> bool:
        """Detect 3+ inbound messages within 5 minutes."""
        if not conversation_history or len(conversation_history) < 3:
            return False

        # Get inbound messages with timestamps
        inbound_times: list[datetime] = []
        for msg in conversation_history:
            if msg.get("direction") == "inbound":
                sent_at = msg.get("sent_at")
                if sent_at:
                    if isinstance(sent_at, str):
                        try:
                            sent_at = datetime.fromisoformat(sent_at)
                        except (ValueError, TypeError):
                            continue
                    if sent_at.tzinfo is None:
                        sent_at = sent_at.replace(tzinfo=timezone.utc)
                    inbound_times.append(sent_at)

        if len(inbound_times) < 3:
            return False

        # Sort and check for 3 messages within 5 minutes
        inbound_times.sort()
        for i in range(len(inbound_times) - 2):
            window = inbound_times[i + 2] - inbound_times[i]
            if window <= timedelta(minutes=5):
                return True

        return False

    def _is_cc_detected(self, headers: dict[str, str] | None) -> bool:
        """Detect if CC or BCC headers are present."""
        if not headers:
            return False
        return bool(headers.get("cc") or headers.get("bcc"))

    async def handle_edge_case(
        self,
        edge_case_type: str,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle detected edge case and return appropriate response.

        Args:
            edge_case_type: The detected edge case type.
            message_content: The text content of the reply.
            lead_data: Information about the lead.
            campaign_context: Campaign context information.

        Returns:
            Dict with action, response_body, response_subject, notes,
            create_new_lead, new_lead_info.
        """
        campaign_context = campaign_context or {}

        handler_map = {
            EdgeCaseType.LANGUAGE_SWITCH: self._handle_language_switch,
            EdgeCaseType.FORWARDED_REPLY: self._handle_forwarded_reply,
            EdgeCaseType.DELAYED_REPLY: self._handle_delayed_reply,
            EdgeCaseType.PHONE_REQUEST: self._handle_phone_request,
            EdgeCaseType.WRONG_PERSON: self._handle_wrong_person,
            EdgeCaseType.AUTO_REPLY_LOOP: self._handle_auto_reply_loop,
            EdgeCaseType.MULTIPLE_RAPID_REPLIES: self._handle_multiple_rapid_replies,
            EdgeCaseType.CC_DETECTED: self._handle_cc_detected,
        }

        handler = handler_map.get(edge_case_type)
        if handler is None:
            return {
                "action": "unknown",
                "response_body": "",
                "response_subject": "",
                "notes": f"Unknown edge case type: {edge_case_type}",
                "create_new_lead": False,
                "new_lead_info": None,
            }

        return await handler(message_content, lead_data, campaign_context)

    async def _handle_language_switch(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle non-English language reply."""
        first_name = lead_data.get("first_name", "")
        body = (
            f"Hi {first_name},\n\n"
            "Thank you for your reply. I noticed you may prefer communicating "
            "in a different language. I want to make sure we can have a productive "
            "conversation - would you prefer I respond in your language?\n\n"
            "Best regards"
        )
        return {
            "action": "respond_in_language",
            "response_body": body,
            "response_subject": "Re: Following up",
            "notes": "Language switch detected, acknowledging preference",
            "create_new_lead": False,
            "new_lead_info": None,
        }

    async def _handle_forwarded_reply(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle forwarded message reply."""
        # Try to extract original sender info from forwarded content
        sender_match = re.search(
            r"From:\s*(.+?)(?:\n|$)", message_content, re.IGNORECASE
        )
        sender_info = sender_match.group(1).strip() if sender_match else None

        first_name = lead_data.get("first_name", "")
        body = (
            f"Hi {first_name},\n\n"
            "Thank you for forwarding this. I appreciate you connecting me "
            "with the right person. I will follow up with them directly.\n\n"
            "Best regards"
        )
        return {
            "action": "match_forward",
            "response_body": body,
            "response_subject": "Re: Following up",
            "notes": f"Forwarded reply detected. Original sender: {sender_info or 'unknown'}",
            "create_new_lead": False,
            "new_lead_info": None,
        }

    async def _handle_delayed_reply(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle reply that came after a long delay (>30 days)."""
        first_name = lead_data.get("first_name", "")
        company_name = campaign_context.get("company_name", "our team")
        body = (
            f"Hi {first_name},\n\n"
            f"It's been a while since we connected! Great to hear back from you. "
            f"I wanted to quickly recap what {company_name} can help with and "
            "see if there's still an opportunity to work together.\n\n"
            "Would you have time for a brief chat this week?\n\n"
            "Best regards"
        )
        return {
            "action": "context_refresh",
            "response_body": body,
            "response_subject": "Re: Great to reconnect",
            "notes": "Delayed reply detected (>30 days), providing context refresh",
            "create_new_lead": False,
            "new_lead_info": None,
        }

    async def _handle_phone_request(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle request for phone call."""
        first_name = lead_data.get("first_name", "")
        calendly_link = campaign_context.get("booking_link", "")
        phone = campaign_context.get("phone", "")

        body = f"Hi {first_name},\n\n" "Absolutely, I would be happy to connect by phone!\n\n"

        if calendly_link:
            body += f"You can book a time that works best for you here: {calendly_link}\n\n"
        if phone:
            body += f"Or feel free to reach me directly at: {phone}\n\n"
        if not calendly_link and not phone:
            body += "Let me know what time works best for you and I will give you a call.\n\n"

        body += "Looking forward to speaking with you!\n\nBest regards"

        return {
            "action": "provide_phone",
            "response_body": body,
            "response_subject": "Re: Let's connect",
            "notes": "Phone request detected, providing contact info",
            "create_new_lead": False,
            "new_lead_info": None,
        }

    async def _handle_wrong_person(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle wrong person / referral."""
        # Try to extract referred person name
        name_match = re.search(
            r"(?:talk to|contact|reach out to|forward.+to|speak with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            message_content,
        )
        referred_name = name_match.group(1) if name_match else None

        first_name = lead_data.get("first_name", "")
        body = (
            f"Hi {first_name},\n\n"
            "Thank you for letting me know and for pointing me in the right direction. "
        )
        if referred_name:
            body += f"I will reach out to {referred_name} directly. "
        body += (
            "I appreciate your time!\n\n"
            "Best regards"
        )

        new_lead_info = None
        if referred_name:
            new_lead_info = {
                "name": referred_name,
                "referred_by": lead_data.get("email", ""),
                "company": lead_data.get("company", ""),
            }

        return {
            "action": "create_referral",
            "response_body": body,
            "response_subject": "Re: Thank you",
            "notes": f"Wrong person, referred to: {referred_name or 'unknown'}",
            "create_new_lead": referred_name is not None,
            "new_lead_info": new_lead_info,
        }

    async def _handle_auto_reply_loop(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle auto-reply loop detection."""
        return {
            "action": "stop_sequence",
            "response_body": "",
            "response_subject": "",
            "notes": "Auto-reply loop detected, stopping outreach",
            "create_new_lead": False,
            "new_lead_info": None,
        }

    async def _handle_multiple_rapid_replies(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle multiple rapid-fire replies."""
        first_name = lead_data.get("first_name", "")
        body = (
            f"Hi {first_name},\n\n"
            "Thank you for all your messages! I have reviewed everything you sent. "
            "Let me address your points together to keep things organized.\n\n"
            "Best regards"
        )
        return {
            "action": "batch_response",
            "response_body": body,
            "response_subject": "Re: Following up on your messages",
            "notes": "Multiple rapid replies detected, batching response",
            "create_new_lead": False,
            "new_lead_info": None,
        }

    async def _handle_cc_detected(
        self,
        message_content: str,
        lead_data: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle reply with CC/BCC recipients."""
        first_name = lead_data.get("first_name", "")
        body = (
            f"Hi {first_name},\n\n"
            "Thank you for your reply. I appreciate you including your team "
            "in this conversation. I would be happy to provide any additional "
            "information that would be helpful for everyone.\n\n"
            "Best regards"
        )
        return {
            "action": "adjust_tone",
            "response_body": body,
            "response_subject": "Re: Following up",
            "notes": "Others CC'd, using formal tone",
            "create_new_lead": False,
            "new_lead_info": None,
        }
