"""AI Engine for image analysis using Qwen3-VL-2B-Instruct."""

import logging
from typing import Optional

import torch
from PIL import Image
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class AIEngine:
    """Vision-Language model engine for screenshot analysis.
    
    Uses Qwen3-VL-2B-Instruct for generating semantic descriptions
    of screenshots, including UI understanding and activity detection.
    """
    
    MODEL_ID = "/Users/tiiny/models/Qwen3-VL-2B-Instruct"
    MAX_IMAGE_SIZE = 1024  # Max dimension for CPU optimization
    
    def __init__(self) -> None:
        """Initialize the AI engine with Qwen3-VL model.
        
        Loads the model and processor with appropriate settings for
        the configured device (CPU/CUDA/MPS).
        """
        logger.info(f"Loading AI engine with model: {self.MODEL_ID}")
        logger.info(f"Using device: {settings.device}")
        
        # Determine dtype based on device
        if settings.device == "cpu":
            torch_dtype = torch.float32
        else:
            torch_dtype = torch.bfloat16
        
        # Load model with trust_remote_code for Qwen3 architecture
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            self.MODEL_ID,
            trust_remote_code=True,
            dtype=torch_dtype,
            device_map=settings.device,
        )
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(
            self.MODEL_ID,
            trust_remote_code=True,
            min_pixels=256 * 28 * 28,
            max_pixels=1024 * 28 * 28,
        )
        
        logger.info("AI engine loaded successfully")
    
    def _resize_for_cpu(self, image: Image.Image) -> Image.Image:
        """Resize image if too large for efficient CPU inference.
        
        VL models slice high-res images into many tokens. On CPU,
        large images cause massive latency. Resizing is the most
        effective optimization.
        
        Args:
            image: PIL Image to potentially resize.
            
        Returns:
            Resized image if original was too large, otherwise original.
        """
        width, height = image.size
        
        if width <= self.MAX_IMAGE_SIZE and height <= self.MAX_IMAGE_SIZE:
            return image
        
        # Calculate new size maintaining aspect ratio
        if width > height:
            new_width = self.MAX_IMAGE_SIZE
            new_height = int(height * (self.MAX_IMAGE_SIZE / width))
        else:
            new_height = self.MAX_IMAGE_SIZE
            new_width = int(width * (self.MAX_IMAGE_SIZE / height))
        
        logger.debug(f"Resizing image from {width}x{height} to {new_width}x{new_height}")
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def analyze_image(self, image: Image.Image) -> str:
        """Generate a semantic description of a screenshot.
        
        Args:
            image: PIL Image of the screenshot to analyze.
            
        Returns:
            A concise description of the active application, visible
            text, and user activity in the screenshot.
        """
        # Step 1: CPU Optimization - resize if needed
        if settings.device == "cpu":
            image = self._resize_for_cpu(image)
        
        # Step 2: Construct messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": "In one sentence: What app is this and what is the user doing?"
                    }
                ]
            }
        ]
        
        # Step 3: Preprocessing
        text = self.processor.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=text,
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        inputs = inputs.to(self.model.device)
        
        # Step 4: Inference
        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=128
            )
        
        # Step 5: Decode - only get newly generated tokens (exclude input)
        generated_ids_trimmed = [
            out_ids[len(in_ids):] 
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0]
        
        result = output_text.strip()
        logger.debug(f"VL model output: {result}")
        return result


# Lazy-loaded singleton instance
_engine: Optional[AIEngine] = None


def get_ai_engine() -> AIEngine:
    """Get or create the singleton AIEngine instance.
    
    Returns:
        The global AIEngine instance.
    """
    global _engine
    if _engine is None:
        _engine = AIEngine()
    return _engine
