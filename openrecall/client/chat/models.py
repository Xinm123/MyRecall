"""
Model constants for Pi agent integration.

Pi is the authoritative source for all built-in model metadata
(context windows, cost, capabilities). MyRecall only needs the
default provider/model constants — no model metadata dictionary
is maintained here.
"""

DEFAULT_PROVIDER = "minimax-cn"
"""Default LLM provider. Pi provides built-in minimax-cn + kimi-coding providers."""

DEFAULT_MODEL = "MiniMax-M2.7"
"""Default model ID for minimax-cn provider."""
