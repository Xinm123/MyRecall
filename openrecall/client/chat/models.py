"""
Model constants for Pi agent integration.

Pi is the authoritative source for all built-in model metadata
(context windows, cost, capabilities). MyRecall only needs the
default provider/model constants — no model metadata dictionary
is maintained here.
"""

DEFAULT_PROVIDER = "qianfan"
"""Default LLM provider. Configured via ~/.pi/agent/models.json."""

DEFAULT_MODEL = "deepseek-r1-250528"
"""Default model ID for qianfan provider (DeepSeek R1)."""
