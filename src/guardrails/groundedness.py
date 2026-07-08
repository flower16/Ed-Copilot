"""Groundedness + safety guardrails.

Ported and adapted from flower16/copilot-for-families/backend/app/guardrails/groundedness.py

POC uses lightweight lexical-overlap groundedness (no extra API cost).
Production path: replace score() with an NLI/LLM-as-judge entailment check.
"""
from __future__ import annotations

import re

_STOP = set(
    "the a an of to in for and or is are was were on at by with as that this it "
    "what which who when where how does do can may might will should i you your".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower())
            if t not in _STOP and len(t) > 2}


def score(answer: str, context: str) -> float:
    """Return fraction of answer content-tokens that appear in the retrieved context.

    Range: 0.0 (answer shares nothing with context) → 1.0 (fully grounded).
    Threshold 0.35 is appropriate for a POC; raise to 0.5+ for production.
    """
    a, c = _tokens(answer), _tokens(context)
    if not a:
        return 0.0
    return round(len(a & c) / len(a), 4)


_PII_PATTERNS = [
    "ssn", "social security", "home address", "phone number",
    "another student", "other students", "someone's address",
    "personal information of",
]


def input_is_safe(message: str) -> tuple[bool, str]:
    """Block obvious PII-elicitation / student-privacy probes.

    Returns (is_safe, refusal_message).
    Prod: replace with a real moderation model + prompt-injection classifier.
    """
    lowered = message.lower()
    if any(p in lowered for p in _PII_PATTERNS):
        return False, (
            "For privacy, I can't help retrieve or share personal contact or "
            "identifying information about students or individuals."
        )
    return True, ""
