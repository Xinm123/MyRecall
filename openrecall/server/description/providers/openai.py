"""OpenAI-compatible description provider."""
import base64
import json
import logging
import time
from pathlib import Path

import requests

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
    DescriptionProviderConfigError,
)
from openrecall.server.ai.providers import _normalize_api_base
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


_PROMPT_TEXT = (
    "Analyze this screenshot. Output a strictly valid JSON object:\n"
    '{"narrative": "detailed description (max 512 chars)", "entities": ["entity1"], '
    '"intent": "user intent phrase", "summary": "one sentence (max 200 chars)"}'
)


class OpenAIDescriptionProvider(DescriptionProvider):
    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not model_name:
            raise DescriptionProviderConfigError("model_name is required")
        # api_key can be empty for local vLLM without auth
        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Analyze this screenshot. App context: {ctx_str}.\n{_PROMPT_TEXT}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        }

        try:
            start_time = time.time()
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)
            elapsed = time.time() - start_time
        except Exception as e:
            raise DescriptionProviderRequestError(f"OpenAI request failed: {e}") from e

        if not resp.ok:
            raise DescriptionProviderRequestError(
                f"OpenAI request failed: status={resp.status_code} body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise DescriptionProviderRequestError("choices missing in response")
            message = choices[0].get("message") or {}
            content = message.get("content", "")
        except Exception as e:
            raise DescriptionProviderRequestError(f"Parse failed: {e}") from e

        raw = content.strip()
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
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

        logger.warning(f"Failed to parse JSON from OpenAIDescriptionProvider. Raw: {raw[:100]}...")
        # Truncate raw text for fallback
        fallback_narrative = raw[:512]
        fallback_summary = raw[:200]
        if len(raw) > 512:
            logger.warning(f"Fallback narrative truncated from {len(raw)} to 512 chars")
        logger.info(f"Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            entities=[],
            intent="",
            summary=fallback_summary,
        )
