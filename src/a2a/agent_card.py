"""Build the A2A agent card advertised at /.well-known/agent.json.

The card describes Ed-Copilot as a single A2A agent whose *skills* are the
registered districts. Each district contributes one skill; its supported
intents are exposed as tags so a caller can decide whether to route a
question here.

Card shape follows the Google A2A agent-card convention
(https://google.github.io/A2A/), kept minimal and dependency-free.
"""
from __future__ import annotations

from typing import Optional

from src.district_registry import DistrictRegistry

# Example prompts per intent — helps callers understand each skill.
_INTENT_EXAMPLES = {
    "math_curriculum": "What topics are covered in NC Math 1?",
    "admin_policy": "When is spring break?",
    "college_guidance": "What math should I take to prepare for engineering?",
    "course_catalog": "What math courses does the district offer for 9th graders?",
}

_INTENT_LABELS = {
    "math_curriculum": "Math Curriculum",
    "admin_policy": "District Policy",
    "college_guidance": "College & Course Planning",
    "course_catalog": "Course Catalog",
}


def build_agent_card(registry: DistrictRegistry, base_url: str) -> dict:
    """Return the A2A agent card as a JSON-serialisable dict.

    Args:
        registry:  loaded DistrictRegistry.
        base_url:  public base URL this service is reachable at
                   (e.g. "http://localhost:8100"), used for the `url` field.
    """
    names = registry.display_names()
    configs = registry.all_configs()

    skills = []
    for district_id in registry.all_district_ids():
        cfg = configs.get(district_id, {})
        intents = registry.supported_intents(district_id)
        state = cfg.get("state", "")
        name = names.get(district_id, district_id)

        skills.append({
            "id": district_id,
            "name": name,
            "description": (
                f"Answer questions about {name}"
                + (f" ({state})" if state else "")
                + ", grounded strictly in official district content. "
                + "Handles intents: " + ", ".join(intents) + "."
            ),
            "tags": [state.lower()] * bool(state) + list(intents),
            "examples": [
                _INTENT_EXAMPLES[i] for i in intents if i in _INTENT_EXAMPLES
            ],
            # Non-standard but useful extension so callers can drive /run:
            "intents": intents,
            "intent_labels": {i: _INTENT_LABELS.get(i, i) for i in intents},
        })

    return {
        "name": "Ed-Copilot",
        "description": (
            "Multi-district K-12 family assistant. Answers curriculum, district-policy, "
            "and course-planning questions grounded in official district content."
        ),
        "url": base_url.rstrip("/"),
        "version": "0.1.0",
        "provider": {"organization": "Ed-Copilot"},
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": skills,
    }
