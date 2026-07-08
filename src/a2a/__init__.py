"""A2A (Agent-to-Agent) protocol surface for Ed-Copilot.

Exposes the district agents behind a small HTTP service so other systems
(e.g. flower16/copilot-for-families) can delegate district/curriculum
questions to Ed-Copilot without importing its code.

See MULTI_DISTRICT_PLAN.md section 4.3.
"""
