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
    'Output a strictly valid JSON object:\n'
    '{"narrative": "detailed description (max 2048 chars)", '
    '"summary": "one sentence (max 256 chars)", '
    '"tags": ["keyword1", "keyword2", ...]}  // 3-8 lowercase keywords'
)

# Add example output
_EXAMPLE_OUTPUT = '''
Example output:
{
  "narrative": "User is browsing GitHub repository page showing README content with project description and installation instructions.",
  "summary": "Browsing GitHub repository README",
  "tags": ["github", "repository", "readme", "browsing", "documentation"]
}
'''


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

        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        url = f"{self.api_base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        prompt_content = (
            f"Analyze this screenshot. App context: {ctx_str}.\n"
            f"{_PROMPT_TEXT}\n"
            f"{_EXAMPLE_OUTPUT}\n"
            "IMPORTANT: Output only valid JSON. No markdown, no explanation."
        )

        payload = {
            "model": self.model_name,
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

                narrative = original_narrative[:1024]
                summary = original_summary[:256]

                if len(original_narrative) > 1024:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 1024 chars")
                if len(original_summary) > 256:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 256 chars")

                # Normalize tags
                if isinstance(tags, list):
                    tags = [str(t).lower().strip() for t in tags if t]
                    tags = [t for t in tags if t]  # Filter out empty strings after strip
                    tags = tags[:10]  # Max 10 tags
                else:
                    tags = []

                logger.info(f"Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(tags)} tags")
                return FrameDescription(
                    narrative=narrative,
                    summary=summary,
                    tags=tags,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from OpenAIDescriptionProvider. Raw: {raw[:100]}...")
        fallback_narrative = raw[:1024]
        fallback_summary = raw[:256]
        if len(raw) > 1024:
            logger.warning(f"Fallback narrative truncated from {len(raw)} to 1024 chars")
        logger.info(f"Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            summary=fallback_summary,
            tags=[],
        )
