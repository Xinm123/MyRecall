from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

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
    MultimodalEmbeddingProvider,
    OCRProvider,
    RerankerProvider,
)
from openrecall.server.ai_engine import AIEngine
from openrecall.server.nlp import get_nlp_engine
from openrecall.server.ocr import extract_text_from_image
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

    def analyze_image(self, image_path: str) -> str:
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
                        "text": (
                            "Analyze the screenshot. Return JSON only (no markdown, no extra text). "
                            "Schema: {\"app\":string,\"window_title\":string,\"scene\":string,"
                            "\"actions\":[string],\"entities\":[string],\"description\":string}. "
                            "Use concise Chinese if possible. scene=what screen is about; "
                            "actions=what the user is doing (verbs); entities=important nouns."
                        ),
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
        return output_text.strip()


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

    def analyze_image(self, image_path: str) -> str:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")

        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"file://{path.as_posix()}"},
                    {
                        "text": (
                            "Analyze the screenshot. Return JSON only (no markdown, no extra text). "
                            "Schema: {\"app\":string,\"window_title\":string,\"scene\":string,"
                            "\"actions\":[string],\"entities\":[string],\"description\":string}. "
                            "Use concise Chinese if possible. scene=what screen is about; "
                            "actions=what the user is doing (verbs); entities=important nouns."
                        )
                    },
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
                            return " ".join(texts).strip()
                text = output.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
            raise KeyError("unexpected response shape")
        except Exception as e:
            raise AIProviderRequestError(f"DashScope response parse failed: {e}") from e


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

    def analyze_image(self, image_path: str) -> str:
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
                            "text": (
                                "Analyze the screenshot. Return JSON only (no markdown, no extra text). "
                                "Schema: {\"app\":string,\"window_title\":string,\"scene\":string,"
                                "\"actions\":[string],\"entities\":[string],\"description\":string}. "
                                "Use concise Chinese if possible. scene=what screen is about; "
                                "actions=what the user is doing (verbs); entities=important nouns."
                            ),
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
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
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
            raise AIProviderRequestError(f"OpenAI response parse failed: {e}") from e


class LocalOCRProvider(OCRProvider):
    def extract_text(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")
        image = Image.open(path)
        image_array = np.array(image)
        return extract_text_from_image(image_array)


class PaddleOCRProvider(OCRProvider):
    def __init__(self, lang: str = "ch") -> None:
        self._lang = (lang or "ch").strip()
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as e:
            raise AIProviderUnavailableError(
                "paddleocr is not installed. Install with: pip install paddleocr paddlepaddle"
            ) from e
        try:
            try:
                self._engine = PaddleOCR(use_angle_cls=True, lang=self._lang, show_log=False)
            except Exception as e:
                msg = str(e)
                if "show_log" in msg or "Unknown argument" in msg:
                    self._engine = PaddleOCR(use_angle_cls=True, lang=self._lang)
                else:
                    raise
        except Exception as e:
            raise AIProviderUnavailableError(f"PaddleOCR init failed: {e}") from e
        return self._engine

    def extract_text(self, image_path: str) -> str:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")
        engine = self._get_engine()
        try:
            try:
                result = engine.ocr(str(path), cls=True)
            except Exception as e:
                msg = str(e)
                if "cls" in msg and ("unexpected keyword" in msg or "Unknown argument" in msg):
                    result = engine.ocr(str(path))
                else:
                    raise
        except Exception as e:
            raise AIProviderRequestError(f"PaddleOCR request failed: {e}") from e
        lines: list[str] = []
        if isinstance(result, list):
            for item in result:
                if not isinstance(item, list):
                    continue
                for box_and_text in item:
                    if (
                        isinstance(box_and_text, (list, tuple))
                        and len(box_and_text) >= 2
                        and isinstance(box_and_text[1], (list, tuple))
                        and box_and_text[1]
                    ):
                        text = box_and_text[1][0]
                        if isinstance(text, str) and text.strip():
                            lines.append(text.strip())
        return "\n".join(lines).strip()


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
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
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
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
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


class LocalMMEmbeddingProvider(MultimodalEmbeddingProvider):
    def __init__(self, model_name: str) -> None:
        model_name = (model_name or "").strip()
        if not model_name:
            raise AIProviderConfigError("Local multimodal embedding model_name is required")
        self.model_id = model_name

        if settings.device == "cpu":
            torch_dtype = torch.float32
        else:
            torch_dtype = torch.bfloat16

        logger.info(f"Loading LocalMMEmbeddingProvider model: {self.model_id}")
        logger.info(f"Using device: {settings.device}")

        try:
            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                self.model_id,
                trust_remote_code=True,
                dtype=torch_dtype,
                device_map=settings.device,
            )
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                trust_remote_code=True,
                min_pixels=4096,
                max_pixels=1843200,
            )
        except Exception as e:
            raise AIProviderUnavailableError(f"Local multimodal embedding init failed: {e}") from e

        self.query_instruction = "Retrieve images or text relevant to the user's query."
        self.doc_instruction = "Represent the content for retrieval."

    def _embed_messages(self, messages: list[dict]) -> np.ndarray:
        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
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
            out = self.model(**inputs, output_hidden_states=True, return_dict=True)
        hidden = None
        if getattr(out, "hidden_states", None):
            hidden = out.hidden_states[-1]
        elif getattr(out, "last_hidden_state", None) is not None:
            hidden = out.last_hidden_state
        if hidden is None:
            raise AIProviderRequestError("Local multimodal embedding forward produced no hidden states")

        attn = getattr(inputs, "attention_mask", None)
        if attn is None:
            idx = hidden.shape[1] - 1
        else:
            idx = int(attn[0].sum().item()) - 1
            if idx < 0:
                idx = hidden.shape[1] - 1
        vec = hidden[0, idx, :].detach().float().cpu().numpy()
        vec = _fit_embedding_dim(vec)
        return _l2_normalize(vec)

    def embed_text(self, text: str) -> np.ndarray:
        if not text or text.isspace():
            return np.zeros(int(settings.embedding_dim), dtype=np.float32)
        prompt = f"{self.query_instruction}\n\n{text.strip()}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        return self._embed_messages(messages)

    def embed_image(self, image_path: str) -> np.ndarray:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")
        image = Image.open(path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": self.doc_instruction},
                ],
            }
        ]
        return self._embed_messages(messages)


class OpenAIMMEmbeddingProvider(MultimodalEmbeddingProvider):
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
        logger.info(f"OpenAIMMEmbeddingProvider configured: base={self.api_base} model={self.model_name}")

    def _post_embeddings(self, payload: dict) -> np.ndarray:
        url = f"{self.api_base}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI multimodal embeddings request failed: {e}") from e
        if not resp.ok:
            raise AIProviderRequestError(
                f"OpenAI multimodal embeddings request failed: url={url} status={resp.status_code} body={resp.text[:1000]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise AIProviderRequestError(f"OpenAI multimodal embeddings response is not JSON: {e}") from e
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
            raise AIProviderRequestError(f"OpenAI multimodal embeddings response parse failed: {e}") from e

    def embed_text(self, text: str) -> np.ndarray:
        if not text or text.isspace():
            return np.zeros(int(settings.embedding_dim), dtype=np.float32)
        payload = {"model": self.model_name, "input": text, "encoding_format": "float"}
        return self._post_embeddings(payload)

    def embed_image(self, image_path: str) -> np.ndarray:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise AIProviderRequestError(f"Image not found: {image_path}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {
            "model": self.model_name,
            "input": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                }
            ],
            "encoding_format": "float",
        }
        return self._post_embeddings(payload)


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


class LocalRerankerProvider(RerankerProvider):
    def __init__(self, model_name: str) -> None:
        model_name = (model_name or "").strip()
        if not model_name:
            raise AIProviderConfigError("Local reranker model_name is required")
        raise AIProviderUnavailableError("Local reranker provider is not available")

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        return candidates


class OpenAIRerankerProvider(RerankerProvider):
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
        logger.info(f"OpenAIRerankerProvider configured: base={self.api_base} model={self.model_name}")

    def _parse_scores(self, content: str) -> dict[int, float]:
        text = (content or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                return {}
            try:
                data = json.loads(m.group(0))
            except Exception:
                return {}
        items = None
        if isinstance(data, dict) and isinstance(data.get("scores"), list):
            items = data.get("scores")
        elif isinstance(data, list):
            items = data
        if not isinstance(items, list):
            return {}
        out: dict[int, float] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            if "id" not in it or "score" not in it:
                continue
            try:
                out[int(it["id"])] = float(it["score"])
            except Exception:
                continue
        return out

    def _parse_single_score(self, content: str) -> float:
        text = (content or "").strip()
        if not text:
            return 0.0
        try:
            data = json.loads(text)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                return 0.0
            try:
                data = json.loads(m.group(0))
            except Exception:
                return 0.0
        if isinstance(data, dict):
            if "score" in data:
                try:
                    return float(data["score"])
                except Exception:
                    return 0.0
            if "rerank_score" in data:
                try:
                    return float(data["rerank_score"])
                except Exception:
                    return 0.0
        return 0.0

    def _rerank_per_candidate(self, query: str, compact: list[dict]) -> dict[int, float]:
        url = f"{self.api_base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        prompt = (
            "You are a reranker. Score the candidate for relevance to the query. "
            "Use evidence fields (scene/actions/entities/keywords/time/ui_text) when present. "
            "Return JSON only: {\"score\":<0..1>}."
        )
        out: dict[int, float] = {}
        for c in compact:
            if "id" not in c:
                continue
            cid = int(c["id"])
            payload_candidate = dict(c)
            image_url = payload_candidate.pop("image_url", None)
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": (
                            [
                                {
                                    "type": "text",
                                    "text": json.dumps(
                                        {"query": query, "candidate": payload_candidate}, ensure_ascii=False
                                    ),
                                },
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ]
                            if isinstance(image_url, str) and image_url
                            else json.dumps({"query": query, "candidate": payload_candidate}, ensure_ascii=False)
                        ),
                    },
                ],
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if not resp.ok:
                raise AIProviderRequestError(
                    f"OpenAI rerank request failed: url={url} status={resp.status_code} body={resp.text[:1000]}"
                )
            try:
                data = resp.json()
            except Exception as e:
                raise AIProviderRequestError(f"OpenAI rerank response is not JSON: {e}") from e
            try:
                choices = data.get("choices") or []
                if not choices:
                    raise KeyError("choices missing")
                message = choices[0].get("message") or {}
                content = message.get("content")
                if not isinstance(content, str):
                    raise TypeError("message.content is not a string")
                out[cid] = self._parse_single_score(content)
            except Exception as e:
                raise AIProviderRequestError(f"OpenAI rerank response parse failed: {e}") from e
        return out

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        q = (query or "").strip()
        if not q or not candidates:
            return candidates

        compact = []
        for c in candidates:
            if not isinstance(c, dict) or "id" not in c:
                continue
            compact.append(
                {
                    "id": c.get("id"),
                    "timestamp": c.get("timestamp"),
                    "time_bucket": c.get("time_bucket") or "",
                    "app": c.get("app") or "",
                    "title": c.get("title") or "",
                    "scene": c.get("scene") or "",
                    "actions": c.get("actions") or [],
                    "entities": c.get("entities") or [],
                    "keywords": c.get("keywords") or [],
                    "ui_text": c.get("ui_text") or [],
                    "text": c.get("text") or "",
                    "description_text": c.get("description_text") or "",
                    "description": c.get("description") or "",
                    "image_url": c.get("image_url") or "",
                }
            )
        if not compact:
            return candidates

        has_image = any(isinstance(x.get("image_url"), str) and x.get("image_url") for x in compact)
        if has_image:
            scores = self._rerank_per_candidate(q, compact)
        else:
            url = f"{self.api_base}/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            prompt = (
                "You are a reranker. Score each candidate for relevance to the query. "
                "Use evidence fields (scene/actions/entities/keywords/time/ui_text) when present. "
                "Return JSON only. Format: {\"scores\":[{\"id\":<id>,\"score\":<0..1>},...]}"
            )
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps({"query": q, "candidates": compact}, ensure_ascii=False)},
                ],
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
            except Exception as e:
                raise AIProviderRequestError(f"OpenAI rerank request failed: {e}") from e
            if not resp.ok:
                raise AIProviderRequestError(
                    f"OpenAI rerank request failed: url={url} status={resp.status_code} body={resp.text[:1000]}"
                )
            try:
                data = resp.json()
            except Exception as e:
                raise AIProviderRequestError(f"OpenAI rerank response is not JSON: {e}") from e
            try:
                choices = data.get("choices") or []
                if not choices:
                    raise KeyError("choices missing")
                message = choices[0].get("message") or {}
                content = message.get("content")
                if not isinstance(content, str):
                    raise TypeError("message.content is not a string")
                scores = self._parse_scores(content)
            except Exception as e:
                raise AIProviderRequestError(f"OpenAI rerank response parse failed: {e}") from e

        out = []
        for c in candidates:
            if not isinstance(c, dict) or "id" not in c:
                continue
            cid = int(c["id"])
            updated = dict(c)
            updated["rerank_score"] = scores.get(cid, 0.0)
            out.append(updated)
        out.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)
        return out
