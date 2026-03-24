"""Description providers."""
from openrecall.server.description.providers.base import DescriptionProvider, DescriptionProviderError
from openrecall.server.description.providers.local import LocalDescriptionProvider
from openrecall.server.description.providers.openai import OpenAIDescriptionProvider
from openrecall.server.description.providers.dashscope import DashScopeDescriptionProvider

__all__ = [
    "DescriptionProvider",
    "DescriptionProviderError",
    "LocalDescriptionProvider",
    "OpenAIDescriptionProvider",
    "DashScopeDescriptionProvider",
]
