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

    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": None},
                {
                    "type": "text",
                    "text": f"Analyze this screenshot. App context: {app_context or 'unknown'}. "
                    f"Output a strictly valid JSON object:\n"
                    f'{{"narrative": "detailed description (max 512 chars)", "entities": ["..."], '
                    f'"intent": "user intent phrase", "summary": "one sentence (max 200 chars)"}}',
                },
            ],
        }
    ]


class LocalDescriptionProvider(DescriptionProvider):
    """Qwen3 VL-based description provider running locally."""

    MAX_IMAGE_SIZE = 1024

    def __init__(self, model_name: str = "") -> None:
        self.model_id = model_name or AIEngine.MODEL_ID
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
                narrative = original_narrative[:512]
                summary = original_summary[:200]

                if len(original_narrative) > 512:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 512 chars")
                if len(original_summary) > 200:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 200 chars")

                logger.info(f"Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(data.get('entities', []))} entities")
                return FrameDescription(
                    narrative=narrative,
                    entities=data.get("entities", []),
                    intent=data.get("intent", ""),
                    summary=summary,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from LocalDescriptionProvider. Raw: {raw[:100]}...")
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
