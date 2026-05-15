"""Copywriter Agent - generates personalized outreach messages using LLM."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.config import Settings
    from core.llm import LLMClient
    from agents.reply_quality import ReplyQualityScorer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert B2B sales copywriter. You write concise, personalized cold emails that:
- Reference specific details about the recipient and their company
- Lead with value, not features
- Are conversational and human-sounding (not corporate or generic)
- Keep subject lines under 8 words and intriguing
- Keep email body under 150 words
- End with a low-friction CTA (not "book a 30 min call" but "worth exploring?")
- Never use buzzwords like "synergy", "leverage", "game-changer", "revolutionary"
- Never include fake compliments or generic flattery

You must return your response in EXACTLY this format:
SUBJECT: <subject line>
BODY: <email body>"""

INITIAL_TEMPLATE = """Write a personalized cold outreach email.

ABOUT THE SENDER:
- Name: {sender_name}
- Title: {sender_title}
- Company: {company_name}
- Value Proposition: {value_proposition}
- Tone: {tone_of_voice}

ABOUT THE RECIPIENT:
- Name: {first_name} {last_name}
- Title: {title}
- Company: {lead_company}

PERSONALIZATION DATA:
- Trigger Events: {trigger_events}
- Talking Points: {talking_points}
- Company News: {company_news}
- Recent Activity: {recent_activity}

Write an initial cold outreach email that opens with a reference to one of their trigger events or recent activity, connects it to the value proposition, and ends with a soft CTA. Be specific, not generic."""

FOLLOW_UP_1_TEMPLATE = """Write a first follow-up email (sent 3-4 days after no reply to initial outreach).

ABOUT THE SENDER:
- Name: {sender_name}
- Title: {sender_title}
- Company: {company_name}
- Value Proposition: {value_proposition}
- Tone: {tone_of_voice}

ABOUT THE RECIPIENT:
- Name: {first_name} {last_name}
- Title: {title}
- Company: {lead_company}

PERSONALIZATION DATA:
- Trigger Events: {trigger_events}
- Talking Points: {talking_points}
- Company News: {company_news}

Write a brief follow-up that:
- Does NOT say "just following up" or "bumping this"
- Adds a NEW piece of value (an insight, stat, or resource)
- References a different talking point than the initial email
- Keeps it to 2-3 sentences max
- Feels like a helpful nudge, not a chase"""

FOLLOW_UP_2_TEMPLATE = """Write a second follow-up email (sent 5-7 days after first follow-up, no reply).

ABOUT THE SENDER:
- Name: {sender_name}
- Title: {sender_title}
- Company: {company_name}
- Value Proposition: {value_proposition}
- Tone: {tone_of_voice}

ABOUT THE RECIPIENT:
- Name: {first_name} {last_name}
- Title: {title}
- Company: {lead_company}

PERSONALIZATION DATA:
- Trigger Events: {trigger_events}
- Company News: {company_news}

Write a second follow-up that:
- Uses social proof (mention a similar company or result without being name-droppy)
- Is more direct about the ask
- Includes a specific, quantified result or case study reference
- Stays under 100 words
- Still feels personal and human"""

BREAKUP_TEMPLATE = """Write a breakup email (final email in the sequence, sent 7-10 days after second follow-up).

ABOUT THE SENDER:
- Name: {sender_name}
- Company: {company_name}
- Tone: {tone_of_voice}

ABOUT THE RECIPIENT:
- Name: {first_name}
- Company: {lead_company}

Write a final "breakup" email that:
- Is very short (3-4 sentences max)
- Has a casual, no-pressure tone
- Gives them permission to say no
- Creates subtle FOMO without being manipulative
- Subject line should be simple like "closing the loop" or just their first name
- Does NOT guilt trip or be passive-aggressive"""

STEP_TEMPLATES: dict[str, str] = {
    "initial": INITIAL_TEMPLATE,
    "follow_up_1": FOLLOW_UP_1_TEMPLATE,
    "follow_up_2": FOLLOW_UP_2_TEMPLATE,
    "breakup": BREAKUP_TEMPLATE,
}

SEQUENCE_STEPS = ["initial", "follow_up_1", "follow_up_2", "breakup"]


class CopywriterAgent:
    """Generates personalized outreach emails using LLM."""

    def __init__(
        self,
        llm_client: LLMClient,
        settings: Settings,
        quality_scorer: ReplyQualityScorer | None = None,
    ) -> None:
        self._llm = llm_client
        self._settings = settings
        self._quality_scorer = quality_scorer

    async def write_message(
        self,
        lead: dict[str, Any],
        campaign_context: dict[str, Any],
        step_type: str = "initial",
        quality_check: bool = True,
        jurisdiction: str | None = None,
    ) -> dict[str, str]:
        """Generate a single outreach message for a lead.

        Args:
            lead: Enriched lead dict with enrichment_data.
            campaign_context: Dict with keys: tone_of_voice, value_proposition,
                company_name, sender_name, sender_title.
            step_type: One of "initial", "follow_up_1", "follow_up_2", "breakup".
            quality_check: If True and quality_scorer is set, score and potentially
                regenerate the message if quality is below threshold.
            jurisdiction: Optional jurisdiction string (e.g., "GDPR", "CAN-SPAM")
                to add compliance guidance to the system prompt.

        Returns:
            Dict with subject, body, step_type, and optionally quality_score.
        """
        template = STEP_TEMPLATES.get(step_type)
        if template is None:
            raise ValueError(
                f"Invalid step_type: {step_type}. Must be one of: {list(STEP_TEMPLATES.keys())}"
            )

        enrichment = lead.get("enrichment_data", {})

        format_vars = {
            "sender_name": campaign_context.get("sender_name", ""),
            "sender_title": campaign_context.get("sender_title", ""),
            "company_name": campaign_context.get("company_name", ""),
            "value_proposition": campaign_context.get("value_proposition", ""),
            "tone_of_voice": campaign_context.get("tone_of_voice", "professional and friendly"),
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "title": lead.get("title", ""),
            "lead_company": lead.get("company", ""),
            "trigger_events": self._format_list(enrichment.get("trigger_events", [])),
            "talking_points": self._format_list(enrichment.get("talking_points", [])),
            "company_news": self._format_list(enrichment.get("company_news", [])),
            "recent_activity": enrichment.get("recent_activity", "None available"),
        }

        user_prompt = template.format(**format_vars)
        system_content = SYSTEM_PROMPT

        # Add jurisdiction-specific compliance guidance
        if jurisdiction:
            compliance_note = (
                f"\n\nCOMPLIANCE NOTE: This email is for a {jurisdiction} recipient. "
                "Ensure subject line is not misleading. Do not make false claims."
            )
            if jurisdiction == "GDPR":
                compliance_note += (
                    " Include a note that this outreach is based on "
                    "legitimate business interest."
                )
            elif jurisdiction == "CASL":
                compliance_note += (
                    " Clearly identify yourself and your organization. "
                    "Include purpose of the message."
                )
            system_content = system_content + compliance_note

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._llm.generate(
                messages=messages, temperature=0.8, max_tokens=512
            )
            subject, body = self._parse_response(response)
        except Exception as exc:
            logger.error(
                "Message generation failed for %s (%s): %s",
                lead.get("email", "unknown"),
                step_type,
                exc,
            )
            subject = ""
            body = ""

        result = {
            "subject": subject,
            "body": body,
            "step_type": step_type,
        }

        # Quality check: score and regenerate if below threshold
        if quality_check and self._quality_scorer is not None and body:
            from agents.reply_quality import QUALITY_THRESHOLD

            best_result = result
            best_score = 0

            # Score the initial attempt
            prospect_msg = f"Outreach to {lead.get('first_name', '')} at {lead.get('company', '')}"
            quality = await self._quality_scorer.score_response(
                response_text=body,
                prospect_message=prospect_msg,
                campaign_context=campaign_context,
            )
            best_score = quality.overall_score
            best_result = {**result, "quality_score": quality.overall_score}

            # Regenerate up to 3 times if quality is below threshold
            if quality.overall_score < QUALITY_THRESHOLD:
                for _attempt in range(3):
                    try:
                        new_response = await self._llm.generate(
                            messages=messages, temperature=0.8, max_tokens=512
                        )
                        new_subject, new_body = self._parse_response(new_response)
                    except Exception:
                        break

                    if not new_body:
                        continue

                    new_quality = await self._quality_scorer.score_response(
                        response_text=new_body,
                        prospect_message=prospect_msg,
                        campaign_context=campaign_context,
                    )

                    if new_quality.overall_score > best_score:
                        best_score = new_quality.overall_score
                        best_result = {
                            "subject": new_subject,
                            "body": new_body,
                            "step_type": step_type,
                            "quality_score": new_quality.overall_score,
                        }

                    if new_quality.overall_score >= QUALITY_THRESHOLD:
                        break

            return best_result

        return result

    async def write_sequence(
        self,
        lead: dict[str, Any],
        campaign_context: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Generate a full email sequence for a lead.

        Args:
            lead: Enriched lead dict with enrichment_data.
            campaign_context: Campaign configuration dict.

        Returns:
            List of message dicts (one per sequence step).
        """
        messages: list[dict[str, str]] = []
        for step in SEQUENCE_STEPS:
            message = await self.write_message(lead, campaign_context, step)
            messages.append(message)
        return messages

    def _parse_response(self, response: str) -> tuple[str, str]:
        """Parse LLM response into subject and body."""
        subject = ""
        body = ""

        lines = response.strip().split("\n")
        body_started = False
        body_lines: list[str] = []

        for line in lines:
            if line.upper().startswith("SUBJECT:"):
                subject = line[len("SUBJECT:"):].strip()
            elif line.upper().startswith("BODY:"):
                body_started = True
                remainder = line[len("BODY:"):].strip()
                if remainder:
                    body_lines.append(remainder)
            elif body_started:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()

        # Fallback if format was not followed
        if not subject and not body:
            parts = response.split("\n", 1)
            subject = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else ""

        return subject, body

    def _format_list(self, items: list[str]) -> str:
        """Format a list of items as a bullet-point string."""
        if not items:
            return "None available"
        return "\n".join(f"- {item}" for item in items)
