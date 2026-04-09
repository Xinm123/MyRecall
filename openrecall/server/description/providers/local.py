"""Local description provider using Qwen3 VL."""
import json
import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image
from qwen_vl_utils import process_vision_info
import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
)
from openrecall.server.ai_engine import AIEngine
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_MAX_NEW_TOKENS = 256


def _build_messages(context: FrameContext) -> list[dict[str, Any]]:
    """Build messages for the vision model with context injection."""
    app_context = ""
    if context.app_name:
        app_context = f"App: {context.app_name}"
    if context.window_name:
        app_context += f" | Window: {context.window_name}"
    if context.browser_url:
        app_context += f" | URL: {context.browser_url}"

    prompt_text = (
        f"Analyze this screenshot. App context: {app_context or 'unknown'}. "
        f"Output a strictly valid JSON object:\n"
        f'{{"narrative": "detailed description (max 2048 chars)", '
        f'"summary": "one sentence (max 256 chars)", '
        f'"tags": ["keyword1", "keyword2", ...]}}  // 3-8 lowercase keywords\n\n'
        f'Example output:\n'
        f'{{\n'
        f'  "narrative": "User is browsing GitHub repository page showing README content.",\n'
        f'  "summary": "Browsing GitHub repository README",\n'
        f'  "tags": ["github", "repository", "readme", "browsing", "documentation"]\n'
        f'}}\n\n'
        f'IMPORTANT: Output only valid JSON. No markdown, no explanation.'
    )

    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": None},
                {"type": "text", "text": prompt_text},
            ],
        }
    ]


class LocalDescriptionProvider(DescriptionProvider):
    """Qwen3 VL-based description provider running locally."""

    MAX_IMAGE_SIZE = 1024

    def __init__(self, model_name: str = "") -> None:
        self.model_id = model_name or AIEngine.MODEL_ID
        if not self.model_id:
            raise ValueError(
                "LocalDescriptionProvider requires model_name to be configured. "
                "Set [description] model = '/path/to/local/model' in server.toml, "
                "or use provider = 'openai' with api_base pointing to a vLLM server."
            )
        if settings.device == "cpu":
            torch_dtype = torch.float32
        else:
            torch_dtype = torch.bfloat16
        logger.info(f"Loading LocalDescriptionProvider: {self.model_id}")
        logger.info(f"Using device: {settings.device}")
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            dtype=torch_dtype,
            device_map=settings.device,
        )
        self.processor = AutoProcessor.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            min_pixels=256 * 28 * 28,
            max_pixels=1024 * 28 * 28,
        )

    def _resize_if_needed(self, image: Image.Image) -> Image.Image:
        w, h = image.size
        if w <= self.MAX_IMAGE_SIZE and h <= self.MAX_IMAGE_SIZE:
            return image
        if w > h:
            new_w, new_h = self.MAX_IMAGE_SIZE, int(h * (self.MAX_IMAGE_SIZE / w))
        else:
            new_h, new_w = self.MAX_IMAGE_SIZE, int(w * (self.MAX_IMAGE_SIZE / h))
        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path)
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        image = Image.open(path)
        if settings.device == "cpu":
            image = self._resize_if_needed(image)

        messages = _build_messages(context)
        messages[0]["content"][0]["image"] = image

        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=text,
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(self.model.device) if hasattr(v, 'to') else v for k, v in inputs.items()}

        with torch.no_grad():
            start_time = time.time()
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS,
            )
            elapsed = time.time() - start_time

        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        raw = output_text.strip()
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            if isinstance(data, dict):
                original_narrative = data.get("narrative", "")
                original_summary = data.get("summary", "")
                tags = data.get("tags", [])

                narrative = original_narrative[:1024]
                summary = original_summary[:256]

                if len(original_narrative) > 1024:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 1024 chars")
                if len(original_summary) > 256:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 256 chars")

                # Normalize tags
                if isinstance(tags, list):
                    tags = [str(t).lower().strip() for t in tags if t]
                    tags = [t for t in tags if t]  # Filter empty strings
                    tags = tags[:10]
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

        logger.warning(f"Failed to parse JSON from LocalDescriptionProvider. Raw: {raw[:100]}...")
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
