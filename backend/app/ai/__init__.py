"""AI layer: pluggable engines (recommendation, forecasting, copilot, scoring...).

Every engine sits behind a protocol/ABC so providers (deterministic rules,
LLM) can be swapped without touching the service layer.
"""
