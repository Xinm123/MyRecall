import os
import logging
import math
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class OCRPostProcessor:
    """
    Robust OCR post-processing utility class.
    Converts raw RapidOCR outputs into a clean, structured list of strings,
    solving issues with line splitting and text gluing.
    Supports Grid Layouts (Column Detection) and Language-Aware Spacing.
    """

    @staticmethod
    def _is_cjk(char):
        """
        Check if a character is CJK (Chinese, Japanese, Korean).
        Range: 0x4E00 - 0x9FFF (Common CJK Unified Ideographs)
        """
        return 0x4E00 <= ord(char) <= 0x9FFF

    @staticmethod
    def _smart_join_line(line_items):
        """
        Join a list of items in a single line with smart spacing and column detection.

        Args:
            line_items: List of dicts, each containing 'text', 'x_start', 'x_end', 'height'.
                        Must be sorted by x_start.
        """
        if not line_items:
            return ""

        # Start with the first item
        result = [line_items[0]["text"]]

        for i in range(1, len(line_items)):
            prev_item = line_items[i - 1]
            curr_item = line_items[i]

            prev_text = prev_item["text"]
            curr_text = curr_item["text"]

            if not prev_text or not curr_text:
                result.append(curr_text)
                continue

            # Calculate Gap
            # Gap = current start - previous end
            gap = curr_item["x_start"] - prev_item["x_end"]

            # Column Break Threshold: > 2.0 * previous_height
            # If gap is huge, insert a TAB or wide separator
            if gap > (2.0 * prev_item["height"]):
                result.append("\t" + curr_text)
                continue

            # No Column Break -> Smart Spacing (Language Aware)
            last_char = prev_text[-1]
            first_char = curr_text[0]

            is_last_cjk = OCRPostProcessor._is_cjk(last_char)
            is_first_cjk = OCRPostProcessor._is_cjk(first_char)

            # If both are non-CJK (e.g. English words), add space
            if not is_last_cjk and not is_first_cjk:
                result.append(" " + curr_text)
            else:
                # If one is CJK, join tightly
                result.append(curr_text)

        return "".join(result)

    def process(self, dt_boxes, rec_res):
        """
        Process raw OCR results into merged lines.

        Args:
            dt_boxes: List of 4-point coordinates [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            rec_res: List of tuples (text_str, confidence_float)

        Returns:
            List[str]: A list of merged strings.
        """
        if not dt_boxes or not rec_res or len(dt_boxes) != len(rec_res):
            return []

        # Step 1: Data Standardization
        items = []
        for i, box in enumerate(dt_boxes):
            # box is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]

            y_center = sum(ys) / 4
            height = max(ys) - min(ys)
            x_start = min(xs)
            x_end = max(xs)

            items.append(
                {
                    "text": rec_res[i][0],
                    "y_center": y_center,
                    "height": height,
                    "x_start": x_start,
                    "x_end": x_end,
                    "box": box,
                }
            )

        # Step 2: Dynamic Row Clustering (Running Mean Algorithm)
        # Sort by y_center initially to process top-to-bottom
        items.sort(key=lambda x: x["y_center"])

        lines = []
        if not items:
            return []

        # Initialize first line
        current_line_items = [items[0]]
        current_line_mean_y = items[0]["y_center"]
        current_line_mean_height = items[0]["height"]

        for i in range(1, len(items)):
            item = items[i]

            # Threshold: 0.5 * current_line_mean_height
            threshold = 0.5 * current_line_mean_height

            if abs(item["y_center"] - current_line_mean_y) < threshold:
                # Add to current line
                current_line_items.append(item)

                # Update running means
                n = len(current_line_items)
                current_line_mean_y = (
                    current_line_mean_y * (n - 1) + item["y_center"]
                ) / n
                current_line_mean_height = (
                    current_line_mean_height * (n - 1) + item["height"]
                ) / n
            else:
                # Start new line
                lines.append(current_line_items)
                current_line_items = [item]
                current_line_mean_y = item["y_center"]
                current_line_mean_height = item["height"]

        # Add the last line
        if current_line_items:
            lines.append(current_line_items)

        # Step 3: Column Detection & Smart Joining
        final_lines = []
        for line_items in lines:
            # Sort by x_start (left-to-right)
            line_items.sort(key=lambda x: x["x_start"])

            # Apply Smart Join logic
            merged_text = self._smart_join_line(line_items)
            final_lines.append(merged_text)

        return final_lines


class RapidOCRBackend:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RapidOCRBackend, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        use_local = settings.ocr_rapid_use_local
        model_dir = settings.ocr_rapid_model_dir
        use_gpu = settings.ocr_rapid_use_gpu

        logger.info(
            f"Initializing RapidOCRBackend (use_local={use_local}, use_gpu={use_gpu})"
        )

        if use_local:
            if not model_dir:
                raise ValueError(
                    "OPENRECALL_OCR_RAPID_MODEL_DIR is required when USE_LOCAL is True"
                )

            # Use configured paths or fallback to default structure in model_dir
            det_path = settings.ocr_rapid_det_model or os.path.join(
                model_dir, "onnx/PP-OCRv5/det/ch_PP-OCRv5_server_det.onnx"
            )
            rec_path = settings.ocr_rapid_rec_model or os.path.join(
                model_dir, "onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_server_infer.onnx"
            )
            cls_path = settings.ocr_rapid_cls_model or os.path.join(
                model_dir, "onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_infer.onnx"
            )

            if not (
                os.path.exists(det_path)
                and os.path.exists(rec_path)
                and os.path.exists(cls_path)
            ):
                # Log detailed error about which file is missing
                missing = []
                if not os.path.exists(det_path):
                    missing.append(f"DET: {det_path}")
                if not os.path.exists(rec_path):
                    missing.append(f"REC: {rec_path}")
                if not os.path.exists(cls_path):
                    missing.append(f"CLS: {cls_path}")
                raise FileNotFoundError(
                    f"Missing required ONNX models: {', '.join(missing)}"
                )

            self.engine = RapidOCR(
                det_model_path=det_path,
                rec_model_path=rec_path,
                cls_model_path=cls_path,
                use_angle_cls=True,
                use_gpu=use_gpu,
            )
        else:
            self.engine = RapidOCR(use_angle_cls=True, use_gpu=use_gpu)

    def extract_text(self, image):
        """
        Extract text from image.
        Args:
            image: PIL.Image, numpy.ndarray, or bytes
        Returns:
            str: Extracted text joined by newlines
        """
        # Ensure engine is initialized (in case _initialize failed silently or wasn't called)
        if not hasattr(self, "engine"):
            # Try to re-initialize or fallback
            try:
                self._initialize()
            except Exception as e:
                logger.error(f"RapidOCR engine not initialized and re-init failed: {e}")
                return ""

        try:
            # Handle PIL Image -> Convert to BGR Numpy
            if isinstance(image, Image.Image):
                img_np = np.array(image)
                if img_np.ndim == 3 and img_np.shape[2] == 3:
                    # RGB to BGR
                    image = img_np[:, :, ::-1]
                else:
                    image = img_np

            result, _ = self.engine(image)
            if not result:
                return ""

            # result structure: [[box, text, score], ...]
            # Extract dt_boxes and rec_res for OCRPostProcessor
            dt_boxes = [item[0] for item in result]
            rec_res = [(item[1], item[2]) for item in result]

            # Use OCRPostProcessor to merge lines
            processor = OCRPostProcessor()
            lines = processor.process(dt_boxes, rec_res)

            if settings.debug:
                logger.debug(
                    f"RapidOCR: Extracted {len(lines)} merged lines from image"
                )

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"RapidOCR extraction failed: {e}")
            return ""


if __name__ == "__main__":
    # Mock Data for Test: Grid Layout Simulation
    # Simulating 3 columns:
    # Col 1: "GLM-4" (x: 10-50)
    # Col 2: "Minimind" (x: 200-250) -- BIG GAP
    # Col 3: "Qwen" (x: 400-450) -- BIG GAP
    dt_boxes = [
        [[10, 100], [50, 100], [50, 120], [10, 120]],  # Row 1 Col 1: GLM-4
        [[200, 100], [250, 100], [250, 120], [200, 120]],  # Row 1 Col 2: Minimind
        [[400, 102], [450, 102], [450, 122], [400, 122]],  # Row 1 Col 3: Qwen
        [[10, 150], [60, 150], [60, 170], [10, 170]],  # Row 2: "DeepSeek"
        [
            [65, 152],
            [90, 152],
            [90, 172],
            [65, 172],
        ],  # Row 2: "3B" (Close gap -> should merge with space)
        [[10, 200], [50, 200], [50, 220], [10, 220]],  # Row 3: "人工"
        [
            [50, 200],
            [90, 200],
            [90, 220],
            [50, 220],
        ],  # Row 3: "智能" (Zero gap -> should merge tightly)
    ]
    rec_res = [
        ("GLM-4", 0.99),
        ("Minimind", 0.95),
        ("Qwen", 0.98),
        ("DeepSeek", 0.99),
        ("3B", 0.96),
        ("人工", 0.99),
        ("智能", 0.99),
    ]

    print("Running OCRPostProcessor Grid Test...")
    processor = OCRPostProcessor()
    merged_lines = processor.process(dt_boxes, rec_res)

    print("\n[Result]:")
    for line in merged_lines:
        print(f"'{line}'")

    # Expected Output Validation
    # Row 1: "GLM-4\tMinimind\tQwen"
    # Row 2: "DeepSeek 3B"
    # Row 3: "人工智能"

    assert len(merged_lines) == 3, f"Expected 3 lines, got {len(merged_lines)}"

    # Check Row 1: Grid Layout with Tabs
    assert merged_lines[0] == "GLM-4\tMinimind\tQwen", (
        f"Row 1 Grid Mismatch: '{merged_lines[0]}'"
    )

    # Check Row 2: English Space
    assert merged_lines[1] == "DeepSeek 3B", (
        f"Row 2 English Space Mismatch: '{merged_lines[1]}'"
    )

    # Check Row 3: Chinese Tight Join
    assert merged_lines[2] == "人工智能", (
        f"Row 3 Chinese Join Mismatch: '{merged_lines[2]}'"
    )

    print("\n✅ Verification Passed! Grid Layout & Smart Spacing Working Correctly.")
