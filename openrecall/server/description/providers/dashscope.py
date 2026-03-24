"""DashScope description provider."""
import json
import logging
import time
from pathlib import Path
from typing import Any

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
    DescriptionProviderConfigError,
    DescriptionProviderUnavailableError,
)

logger = logging.getLogger(__name__)


class DashScopeDescriptionProvider(DescriptionProvider):
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise DescriptionProviderConfigError("api_key is required")
        if not model_name:
            raise DescriptionProviderConfigError("model_name is required")
        try:
            import dashscope  # type: ignore
        except ImportError as e:
            raise DescriptionProviderUnavailableError(
                "dashscope is not installed. Install with: pip install dashscope"
            ) from e
        self._dashscope = dashscope
        self._dashscope.api_key = api_key
        self.model_name = model_name

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"image": f"file://{path.as_posix()}"},
                    {
                        "text": (
                            f"Analyze this screenshot. App context: {ctx_str}.\n"
                            'Output a strictly valid JSON: '
                            '{"narrative": "detailed description (max 512 chars)", "entities": ["..."], '
                            '"intent": "user intent phrase", "summary": "one sentence (max 200 chars)"}'
                        ),
                    },
                ],
            }
        ]

        try:
            start_time = time.time()
            response = self._dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
            )
            elapsed = time.time() - start_time
        except Exception as e:
            raise DescriptionProviderRequestError(f"DashScope request failed: {e}") from e

        raw_text = ""
        try:
            data = response
            if hasattr(response, "to_dict"):
                data = response.to_dict()
            if isinstance(data, dict):
                output = data.get("output") or {}
                choices = output.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    if isinstance(content, str):
                        raw_text = content.strip()
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                raw_text = str(item["text"]).strip()
                text = output.get("text")
                if isinstance(text, str) and text.strip():
                    raw_text = text.strip()
        except Exception as e:
            raise DescriptionProviderRequestError(f"DashScope response parse failed: {e}") from e

        if not raw_text:
            raise DescriptionProviderRequestError("Empty response from DashScope")

        try:
            clean = raw_text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                original_narrative = parsed.get("narrative", "")
                original_summary = parsed.get("summary", "")
                narrative = original_narrative[:512]  # Truncate to max length
                summary = original_summary[:200]  # Truncate to max length

                # Log truncation warnings
                if len(original_narrative) > 512:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 512 chars")
                if len(original_summary) > 200:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 200 chars")

                logger.info(f"Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(parsed.get('entities', []))} entities")
                return FrameDescription(
                    narrative=narrative,
                    entities=parsed.get("entities", []),
                    intent=parsed.get("intent", ""),
                    summary=summary,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from DashScope. Raw: {raw_text[:100]}...")
        # Truncate raw text for fallback
        fallback_narrative = raw_text[:512]
        fallback_summary = raw_text[:200]
        if len(raw_text) > 512:
            logger.warning(f"Fallback narrative truncated from {len(raw_text)} to 512 chars")
        logger.info(f"Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            entities=[],
            intent="",
            summary=fallback_summary,
        )
