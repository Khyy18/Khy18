"""Persona Adapter Agent - detects lead persona and adapts communication style."""

from __future__ import annotations

import enum
import json
import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PersonaType(str, enum.Enum):
    C_LEVEL = "c_level"
    VP = "vp"
    DIRECTOR = "director"
    MANAGER = "manager"
    TECHNICAL = "technical"
    STARTUP_FOUNDER = "startup_founder"
    SMB_OWNER = "smb_owner"


class PersonaProfile(BaseModel):
    """Profile describing a lead's persona and communication preferences."""

    persona_type: PersonaType
    formality_level: int  # 1-5
    technical_depth: int  # 1-5
    urgency_preference: str  # low, medium, high
    value_framing: str  # what to emphasize
    communication_style: str
    recommended_tone: str


# Title keyword mappings for rule-based persona detection
TITLE_KEYWORDS: dict[PersonaType, list[str]] = {
    PersonaType.C_LEVEL: ["ceo", "cto", "cfo", "cmo", "coo", "chief", "founder", "co-founder", "president"],
    PersonaType.VP: ["vp", "vice president", "svp", "evp"],
    PersonaType.DIRECTOR: ["director"],
    PersonaType.MANAGER: ["manager", "head of", "team lead"],
    PersonaType.TECHNICAL: ["engineer", "developer", "architect", "devops", "sre", "programmer"],
    PersonaType.STARTUP_FOUNDER: ["founder", "co-founder"],
    PersonaType.SMB_OWNER: ["owner", "proprietor"],
}

# Default persona profiles by type
PERSONA_DEFAULTS: dict[PersonaType, dict[str, Any]] = {
    PersonaType.C_LEVEL: {
        "formality_level": 4,
        "technical_depth": 2,
        "urgency_preference": "high",
        "value_framing": "ROI, strategic impact, competitive advantage",
        "communication_style": "Concise, executive-focused, data-driven",
        "recommended_tone": "Professional and confident",
    },
    PersonaType.VP: {
        "formality_level": 4,
        "technical_depth": 3,
        "urgency_preference": "medium",
        "value_framing": "Team efficiency, scalability, measurable outcomes",
        "communication_style": "Strategic with tactical details",
        "recommended_tone": "Collaborative and authoritative",
    },
    PersonaType.DIRECTOR: {
        "formality_level": 3,
        "technical_depth": 3,
        "urgency_preference": "medium",
        "value_framing": "Process improvement, team productivity, risk reduction",
        "communication_style": "Balanced strategic and operational",
        "recommended_tone": "Professional and solution-oriented",
    },
    PersonaType.MANAGER: {
        "formality_level": 3,
        "technical_depth": 3,
        "urgency_preference": "medium",
        "value_framing": "Ease of use, time savings, team adoption",
        "communication_style": "Practical and outcome-focused",
        "recommended_tone": "Friendly and supportive",
    },
    PersonaType.TECHNICAL: {
        "formality_level": 2,
        "technical_depth": 5,
        "urgency_preference": "low",
        "value_framing": "Technical capabilities, integrations, developer experience",
        "communication_style": "Technical and detailed",
        "recommended_tone": "Direct and technically precise",
    },
    PersonaType.STARTUP_FOUNDER: {
        "formality_level": 2,
        "technical_depth": 3,
        "urgency_preference": "high",
        "value_framing": "Speed to market, cost efficiency, growth enablement",
        "communication_style": "Fast-paced, visionary, action-oriented",
        "recommended_tone": "Energetic and entrepreneurial",
    },
    PersonaType.SMB_OWNER: {
        "formality_level": 2,
        "technical_depth": 2,
        "urgency_preference": "medium",
        "value_framing": "Cost savings, simplicity, immediate results",
        "communication_style": "Simple, practical, results-focused",
        "recommended_tone": "Warm and straightforward",
    },
}

DETECT_PERSONA_PROMPT = """\
Analyze the following lead data and determine their persona type.

Lead data:
- Title: {title}
- Company: {company}
- Industry: {industry}
- Company size: {company_size}

Persona types available:
- c_level: C-suite executives (CEO, CTO, CFO, etc.)
- vp: Vice Presidents and SVPs
- director: Directors
- manager: Managers and team leads
- technical: Engineers, developers, architects
- startup_founder: Startup founders
- smb_owner: Small business owners

Return a JSON object with:
- persona_type: one of the types above
- reasoning: brief explanation

Only return the JSON object, no other text.
"""

ADAPT_MESSAGE_PROMPT = """\
Rewrite the following message to match the persona's communication preferences.

Persona profile:
- Type: {persona_type}
- Formality level: {formality_level}/5
- Technical depth: {technical_depth}/5
- Urgency: {urgency_preference}
- Value framing: {value_framing}
- Communication style: {communication_style}
- Recommended tone: {recommended_tone}

Original message:
{base_message}

Rewrite the message to match the persona's preferences. Keep the core message but adjust tone, formality, technical depth, and emphasis.

Return only the rewritten message text, no other text or JSON.
"""


class PersonaAdapter:
    """Detects lead persona and adapts communication style accordingly."""

    def __init__(self, llm_client: Any, settings: Any) -> None:
        self._llm = llm_client
        self._settings = settings

    def _rule_based_detect(self, title: str, company_size: int | None = None) -> PersonaType | None:
        """Attempt rule-based persona detection from title keywords."""
        title_lower = title.lower() if title else ""
        # Split into words for more precise matching
        title_words = title_lower.split()

        # Check for startup founder (must check before C_LEVEL since "founder" is in both)
        if company_size is not None and company_size <= 50:
            for kw in TITLE_KEYWORDS[PersonaType.STARTUP_FOUNDER]:
                if kw in title_words or kw in title_lower.replace("-", " ").split():
                    return PersonaType.STARTUP_FOUNDER

        # Check for SMB owner
        if company_size is not None and company_size <= 100:
            for kw in TITLE_KEYWORDS[PersonaType.SMB_OWNER]:
                if kw in title_words:
                    return PersonaType.SMB_OWNER

        # Check C-level (use word matching for short abbreviations)
        for kw in TITLE_KEYWORDS[PersonaType.C_LEVEL]:
            if kw in title_words or kw in title_lower.replace("-", " ").split():
                return PersonaType.C_LEVEL

        # Check VP
        for kw in TITLE_KEYWORDS[PersonaType.VP]:
            if kw in title_words or kw in title_lower:
                return PersonaType.VP

        # Check Director
        for kw in TITLE_KEYWORDS[PersonaType.DIRECTOR]:
            if kw in title_words or kw in title_lower:
                return PersonaType.DIRECTOR

        # Check Manager (use substring for multi-word like "head of")
        for kw in TITLE_KEYWORDS[PersonaType.MANAGER]:
            if kw in title_words or kw in title_lower:
                return PersonaType.MANAGER

        # Check Technical
        for kw in TITLE_KEYWORDS[PersonaType.TECHNICAL]:
            if kw in title_words or kw in title_lower:
                return PersonaType.TECHNICAL

        return None

    async def detect_persona(self, lead_data: dict) -> PersonaProfile:
        """Detect persona type from lead data.

        Uses rule-based detection first, with LLM fallback for ambiguous cases.
        """
        title = lead_data.get("title", "")
        company_size = lead_data.get("company_size")
        if isinstance(company_size, str):
            try:
                company_size = int(company_size)
            except (ValueError, TypeError):
                company_size = None

        # Try rule-based detection
        persona_type = self._rule_based_detect(title, company_size)

        if persona_type is None:
            # LLM fallback
            prompt = DETECT_PERSONA_PROMPT.format(
                title=title,
                company=lead_data.get("company", "Unknown"),
                industry=lead_data.get("industry", "Unknown"),
                company_size=company_size or "Unknown",
            )
            try:
                response = await self._llm.generate(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=256,
                )
                data = json.loads(response)
                persona_type = PersonaType(data.get("persona_type", "manager"))
            except (json.JSONDecodeError, ValueError, TypeError):
                persona_type = PersonaType.MANAGER  # safe default

        # Build profile from defaults
        defaults = PERSONA_DEFAULTS[persona_type]
        return PersonaProfile(
            persona_type=persona_type,
            formality_level=defaults["formality_level"],
            technical_depth=defaults["technical_depth"],
            urgency_preference=defaults["urgency_preference"],
            value_framing=defaults["value_framing"],
            communication_style=defaults["communication_style"],
            recommended_tone=defaults["recommended_tone"],
        )

    async def adapt_message(self, persona: PersonaProfile, base_message: str) -> str:
        """Use LLM to rewrite message matching persona style."""
        prompt = ADAPT_MESSAGE_PROMPT.format(
            persona_type=persona.persona_type.value,
            formality_level=persona.formality_level,
            technical_depth=persona.technical_depth,
            urgency_preference=persona.urgency_preference,
            value_framing=persona.value_framing,
            communication_style=persona.communication_style,
            recommended_tone=persona.recommended_tone,
            base_message=base_message,
        )

        try:
            response = await self._llm.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=1024,
            )
            return response.strip()
        except Exception as exc:
            logger.error("Failed to adapt message: %s", exc)
            return base_message

    def get_voice_adjustments(self, persona: PersonaProfile) -> dict:
        """Return voice-specific adjustments for voice_conversation agent."""
        pace_map = {
            PersonaType.C_LEVEL: "moderate",
            PersonaType.VP: "moderate",
            PersonaType.DIRECTOR: "moderate",
            PersonaType.MANAGER: "moderate",
            PersonaType.TECHNICAL: "slow",
            PersonaType.STARTUP_FOUNDER: "fast",
            PersonaType.SMB_OWNER: "moderate",
        }

        tone_map = {
            PersonaType.C_LEVEL: "authoritative",
            PersonaType.VP: "collaborative",
            PersonaType.DIRECTOR: "professional",
            PersonaType.MANAGER: "friendly",
            PersonaType.TECHNICAL: "precise",
            PersonaType.STARTUP_FOUNDER: "energetic",
            PersonaType.SMB_OWNER: "warm",
        }

        vocab_map = {
            PersonaType.C_LEVEL: 4,
            PersonaType.VP: 4,
            PersonaType.DIRECTOR: 3,
            PersonaType.MANAGER: 3,
            PersonaType.TECHNICAL: 5,
            PersonaType.STARTUP_FOUNDER: 3,
            PersonaType.SMB_OWNER: 2,
        }

        return {
            "pace": pace_map.get(persona.persona_type, "moderate"),
            "tone": tone_map.get(persona.persona_type, "professional"),
            "vocabulary_level": vocab_map.get(persona.persona_type, 3),
            "formality": persona.formality_level,
            "technical_depth": persona.technical_depth,
        }
