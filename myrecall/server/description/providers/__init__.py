"""Description providers."""
from myrecall.server.description.providers.base import DescriptionProvider, DescriptionProviderError
from myrecall.server.description.providers.local import LocalDescriptionProvider
from myrecall.server.description.providers.openai import OpenAIDescriptionProvider
from myrecall.server.description.providers.dashscope import DashScopeDescriptionProvider

__all__ = [
    "DescriptionProvider",
    "DescriptionProviderError",
    "LocalDescriptionProvider",
    "OpenAIDescriptionProvider",
    "DashScopeDescriptionProvider",
]
