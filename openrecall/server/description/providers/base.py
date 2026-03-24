"""Description provider protocol and errors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openrecall.server.description.models import FrameDescription, FrameContext


class DescriptionProviderError(Exception):
    """Base error for description providers."""
    pass


class DescriptionProviderConfigError(DescriptionProviderError):
    """Configuration error."""
    pass


class DescriptionProviderRequestError(DescriptionProviderError):
    """Request/execution error."""
    pass


class DescriptionProviderUnavailableError(DescriptionProviderError):
    """Provider unavailable (missing dependency, etc)."""
    pass


class DescriptionProvider(ABC):
    """Protocol for frame description generation providers."""

    @abstractmethod
    def generate(
        self,
        image_path: str,
        context: "FrameContext",
    ) -> "FrameDescription":
        """
        Generate a structured description for a frame.

        Args:
            image_path: Path to the JPEG snapshot file.
            context: Frame metadata for prompt injection.

        Returns:
            FrameDescription with narrative, entities, intent, summary.

        Raises:
            DescriptionProviderRequestError: On API/SDK error.
            DescriptionProviderUnavailableError: On missing dependencies.
        """
        raise NotImplementedError
