from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import requests
import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

from openrecall.server.ai.base import (
    AIProvider,
    EmbeddingProvider,
    AIProviderConfigError,
    AIProviderRequestError,
    AIProviderUnavailableError,
    OCRProvider,
)
from openrecall.server.ai_engine import AIEngine
from openrecall.server.nlp import get_nlp_engine
# from openrecall.server.ocr import extract_text_from_image
from openrecall.server.ocr.rapid_backend import RapidOCRBackend
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _normalize_api_base(api_base: str) -> str:
    base = api_base.strip().strip("`\"' ")
    return base[:-1] if base.endswith("/") else base


def _fit_embedding_dim(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32, copy=False)
    if vec.ndim != 1:
        vec = vec.reshape(-1).astype(np.float32, copy=False)
    dim = int(getattr(settings, "embedding_dim", 0) or 0)
    if dim <= 0 or vec.shape[0] == dim:
        return vec
    if vec.shape[0] > dim:
        return vec[:dim]
    padded = np.zeros(dim, dtype=np.float32)
    padded[: vec.shape[0]] = vec
    return padded


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec.astype(np.float32, copy=False)
    return (vec / norm).astype(np.float32, copy=False)


class LocalProvider(AIProvider):
    MAX_IMAGE_SIZE = AIEngine.MAX_IMAGE_SIZE

    def __init__(self, model_name: str = "") -> None:
        self.model_id = model_name or AIEngine.MODEL_ID

        if settings.device == "cpu":
            torch_dtype = torch.float32
        else:
            torch_dtype = torch.bfloat16

        logger.info(f"Loading LocalProvider model: {self.model_id}")
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

    def _resize_for_cpu(self, image: Image.Image) -> Image.Image:
        width, height = image.size

        if width <= self.MAX_IMAGE_SIZE and height <= self.MAX_IMAGE_SIZE:
            return image

        if width > height:
            new_width = self.MAX_IMAGE_SIZE
            new_height = int(height * (self.MAX_IMAGE_SIZE / width))
        else:
            new_height = self.MAX_IMAGE_SIZE
            new_width = int(width * (self.MAX_IMAGE_SIZE / height))

        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def analyze_image(self, image_path: str) -> dict[str, Any]:
        path = Path(image_path)
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")

        image = Image.open(path)
        if settings.device == "cpu":
            image = self._resize_for_cpu(image)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": "Analyze this screenshot. Output a strictly valid JSON object with these keys:\n- 'caption': A detailed natural language description of the screen content and user intent.\n- 'scene': A single tag describing the scene (e.g., coding, browsing, meeting, chat).\n- 'action': A single tag describing the action (e.g., debugging, reading, typing).\nDo not include markdown formatting.",
                    },
                ],
            }
        ]

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
        inputs = inputs.to(self.model.device)

        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=128)

        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        
        raw_text = output_text.strip()
        try:
            # Attempt to clean potential markdown fences
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
            
        logger.warning(f"Failed to parse JSON from LocalProvider. Raw: {raw_text[:50]}...")
        return {"caption": raw_text, "scene": "", "action": ""}


class DashScopeProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise AIProviderConfigError("DashScope api_key is required")
        if not model_name:
            raise AIProviderConfigError("DashScope model_name is required")

        try:
            import dashscope  # type: ignore
        except ImportError as e:
            raise AIProviderUnavailableError(
                "dashscope is not installed. Install with: pip install dashscope"
            ) from e

        self._dashscope = dashscope
        self._dashscope.api_key = api_key
        self.model_name = model_name

    def analyze_image(self, image_path: str) -> dict[str, Any]:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")

        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"file://{path.as_posix()}"},
                    {"text": "Analyze this screenshot. Output a strictly valid JSON object with these keys:\n- 'caption': A detailed natural language description of the screen content and user intent.\n- 'scene': A single tag describing the scene (e.g., coding, browsing, meeting, chat).\n- 'action': A single tag describing the action (e.g., debugging, reading, typing).\nDo not include markdown formatting."},
                ],
            }
        ]

        try:
            response = self._dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
            )
        except Exception as e:
            raise AIProviderRequestError(f"DashScope request failed: {e}") from e

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
                        texts: list[str] = []
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                texts.append(str(item["text"]))
                        if texts:
                            raw_text = " ".join(texts).strip()
                else:
                    text = output.get("text")
                    if isinstance(text, str) and text.strip():
                        raw_text = text.strip()
        except Exception as e:
            raise AIProviderRequestError(f"DashScope response parse failed: {e}") from e
            
        if not raw_text:
             raise KeyError("unexpected response shape or empty text")

        try:
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
            
        logger.warning(f"Failed to parse JSON from DashScopeProvider. Raw: {raw_text[:50]}...")
        return {"caption": raw_text, "scene": "", "action": ""}


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str, api_base: str = "") -> None:
        api_key = api_key.strip().strip("`\"' ")
        model_name = model_name.strip().strip("`\"' ")
        if not api_key:
            raise AIProviderConfigError("OpenAI-compatible api_key is required")
        if not model_name:
            raise AIProviderConfigError("OpenAI-compatible model_name is required")

        self.api_key = api_key
        self.model_name = model_name
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")
        logger.info(f"OpenAIProvider configured: base={self.api_base} model={self.model_name}")

    def analyze_image(self, image_path: str) -> dict[str, Any]:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyze this screenshot. Output a strictly valid JSON object with these keys:\n- 'caption': A detailed natural language description of the screen content and user intent.\n- 'scene': A single tag describing the scene (e.g., coding, browsing, meeting, chat).\n- 'action': A single tag describing the action (e.g., debugging, reading, typing).\nDo not include markdown formatting.",
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
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI request failed: {e}") from e

        if not resp.ok:
            raise AIProviderRequestError(
                f"OpenAI request failed: url={url} status={resp.status_code} body={resp.text[:1000]}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI response is not JSON: {e}") from e

        raw_text = ""
        try:
            choices = data.get("choices") or []
            if not choices:
                raise KeyError("choices missing")
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                raw_text = content.strip()
            else:
                raise TypeError("message.content is not a string")
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI response parse failed: {e}") from e
            
        try:
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
            
        logger.warning(f"Failed to parse JSON from OpenAIProvider. Raw: {raw_text[:50]}...")
        return {"caption": raw_text, "scene": "", "action": ""}


class DoctrOCRProvider(OCRProvider):
    def extract_text(self, image_path: str) -> str:
        # Import Doctr backend lazily to avoid triggering model downloads
        # when this provider is not in use.
        try:
            from openrecall.server.ocr.doctr_backend import extract_text_from_image
        except ImportError as e:
            raise AIProviderUnavailableError(
                "Doctr dependencies are missing. Install with 'pip install python-doctr[torch]' or similar."
            ) from e
            
        path = Path(image_path)
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")
        image = Image.open(path)
        image_array = np.array(image)
        return extract_text_from_image(image_array)


class LocalOCRProvider(OCRProvider):
    def extract_text(self, image_path: str) -> str:
        # Backward compatibility: Use RapidOCR as the default local provider
        return RapidOCRBackend().extract_text(image_path)


class OpenAIOCRProvider(OCRProvider):
    def __init__(self, api_key: str, model_name: str, api_base: str = "") -> None:
        api_key = api_key.strip().strip("`\"' ")
        model_name = model_name.strip().strip("`\"' ")
        if not api_key:
            raise AIProviderConfigError("OpenAI-compatible api_key is required")
        if not model_name:
            raise AIProviderConfigError("OpenAI-compatible model_name is required")

        self.api_key = api_key
        self.model_name = model_name
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")
        logger.info(f"OpenAIOCRProvider configured: base={self.api_base} model={self.model_name}")

    def extract_text(self, image_path: str) -> str:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all visible text from the image. Return plain text only, preserve line breaks when possible.",
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
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI OCR request failed: {e}") from e

        if not resp.ok:
            raise AIProviderRequestError(
                f"OpenAI OCR request failed: url={url} status={resp.status_code} body={resp.text[:1000]}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI OCR response is not JSON: {e}") from e

        try:
            choices = data.get("choices") or []
            if not choices:
                raise KeyError("choices missing")
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            raise TypeError("message.content is not a string")
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI OCR response parse failed: {e}") from e


class DashScopeOCRProvider(OCRProvider):
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise AIProviderConfigError("DashScope api_key is required")
        if not model_name:
            raise AIProviderConfigError("DashScope model_name is required")

        try:
            import dashscope  # type: ignore
        except ImportError as e:
            raise AIProviderUnavailableError(
                "dashscope is not installed. Install with: pip install dashscope"
            ) from e

        self._dashscope = dashscope
        self._dashscope.api_key = api_key
        self.model_name = model_name

    def extract_text(self, image_path: str) -> str:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")

        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"file://{path.as_posix()}"},
                    {"text": "Extract all visible text from the image. Return plain text only."},
                ],
            }
        ]

        try:
            response = self._dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
            )
        except Exception as e:
            raise AIProviderRequestError(f"DashScope OCR request failed: {e}") from e

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
                        return content.strip()
                    if isinstance(content, list):
                        texts: list[str] = []
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                texts.append(str(item["text"]))
                        if texts:
                            return "\n".join(texts).strip()
                text = output.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
            raise KeyError("unexpected response shape")
        except Exception as e:
            raise AIProviderRequestError(f"DashScope OCR response parse failed: {e}") from e


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self._engine = get_nlp_engine()

    def embed_text(self, text: str) -> np.ndarray:
        return self._engine.encode(text)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model_name: str, api_base: str = "") -> None:
        api_key = api_key.strip().strip("`\"' ")
        model_name = model_name.strip().strip("`\"' ")
        if not api_key:
            raise AIProviderConfigError("OpenAI-compatible api_key is required")
        if not model_name:
            raise AIProviderConfigError("OpenAI-compatible model_name is required")

        self.api_key = api_key
        self.model_name = model_name
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")
        logger.info(f"OpenAIEmbeddingProvider configured: base={self.api_base} model={self.model_name}")

    def embed_text(self, text: str) -> np.ndarray:
        if not text or text.isspace():
            return np.zeros(int(settings.embedding_dim), dtype=np.float32)

        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model_name, "input": text, "encoding_format": "float"}

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI embeddings request failed: {e}") from e

        if not resp.ok:
            raise AIProviderRequestError(
                f"OpenAI embeddings request failed: url={url} status={resp.status_code} body={resp.text[:1000]}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI embeddings response is not JSON: {e}") from e

        try:
            items = data.get("data") or []
            if not items:
                raise KeyError("data missing")
            emb = items[0].get("embedding")
            if not isinstance(emb, list):
                raise TypeError("embedding is not a list")
            vec = np.array(emb, dtype=np.float32)
            vec = _fit_embedding_dim(vec)
            return _l2_normalize(vec)
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI embeddings response parse failed: {e}") from e


class DashScopeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise AIProviderConfigError("DashScope api_key is required")
        if not model_name:
            raise AIProviderConfigError("DashScope model_name is required")

        try:
            import dashscope  # type: ignore
        except ImportError as e:
            raise AIProviderUnavailableError(
                "dashscope is not installed. Install with: pip install dashscope"
            ) from e

        self._dashscope = dashscope
        self._dashscope.api_key = api_key
        self.model_name = model_name

    def embed_text(self, text: str) -> np.ndarray:
        if not text or text.isspace():
            return np.zeros(int(settings.embedding_dim), dtype=np.float32)

        try:
            response = self._dashscope.TextEmbedding.call(model=self.model_name, input=text)
        except Exception as e:
            raise AIProviderRequestError(f"DashScope embeddings request failed: {e}") from e

        try:
            data = response
            if hasattr(response, "to_dict"):
                data = response.to_dict()
            if not isinstance(data, dict):
                raise TypeError("unexpected response type")
            output = data.get("output") or {}
            embeddings = output.get("embeddings") or []
            if embeddings and isinstance(embeddings, list) and isinstance(embeddings[0], dict):
                emb = embeddings[0].get("embedding")
                vec = np.array(emb, dtype=np.float32)
                vec = _fit_embedding_dim(vec)
                return _l2_normalize(vec)
            emb = output.get("embedding")
            if isinstance(emb, list):
                vec = np.array(emb, dtype=np.float32)
                vec = _fit_embedding_dim(vec)
                return _l2_normalize(vec)
            raise KeyError("embedding missing")
        except Exception as e:
            raise AIProviderRequestError(f"DashScope embeddings response parse failed: {e}") from e


class RapidOCRProvider(OCRProvider):
    def extract_text(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")
        # RapidOCRBackend supports path string directly
        return RapidOCRBackend().extract_text(str(path))
