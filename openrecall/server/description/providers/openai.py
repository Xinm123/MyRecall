"""OpenAI-compatible description provider."""
import base64
import json
import logging
import time
from pathlib import Path

import requests

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.prompts import build_description_prompt, PROMPT_VERSION
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
    DescriptionProviderConfigError,
)
from openrecall.server.ai.providers import _normalize_api_base
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class OpenAIDescriptionProvider(DescriptionProvider):
    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not model_name:
            raise DescriptionProviderConfigError("model_name is required")
        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        prompt_content = build_description_prompt()

        payload = {
            "model": self.model_name,
            "temperature": 0.2,
            "max_tokens": 512,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_content},
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
                tags = parsed.get("tags", [])

                narrative = original_narrative[:2048]
                summary = original_summary[:256]

                if len(original_narrative) > 2048:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 2048 chars")
                if len(original_summary) > 256:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 256 chars")

                # Normalize tags
                if isinstance(tags, list):
                    tags = [str(t).lower().strip() for t in tags if t]
                    tags = [t for t in tags if t]  # Filter out empty strings after strip
                    tags = tags[:10]  # Max 10 tags
                else:
                    tags = []

                logger.info(f"[PromptVersion:{PROMPT_VERSION}] Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(tags)} tags")
                return FrameDescription(
                    narrative=narrative,
                    summary=summary,
                    tags=tags,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from OpenAIDescriptionProvider. Raw: {raw[:100]}...")
        fallback_narrative = raw[:2048]
        fallback_summary = raw[:256]
        if len(raw) > 2048:
            logger.warning(f"Fallback narrative truncated from {len(raw)} to 2048 chars")
        logger.info(f"[PromptVersion:{PROMPT_VERSION}] Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            summary=fallback_summary,
            tags=[],
        )
