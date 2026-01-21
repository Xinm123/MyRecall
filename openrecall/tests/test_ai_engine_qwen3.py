"""Tests for Phase 6.2 - Qwen3-VL AI Engine.

This test requires the model to be downloaded and may use significant
RAM (~4-5GB for the 2B model).
"""

import os
import sys
from pathlib import Path

import pytest
from PIL import Image


pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(
        os.environ.get("CI") == "true" and os.environ.get("HAS_GPU") != "true",
        reason="Skipping AI engine tests in CI without GPU",
    ),
]


class TestAIEngine:
    """Tests for the AIEngine class."""
    
    @pytest.fixture(scope="class")
    def ai_engine(self):
        """Load AI engine once for all tests in this class."""
        from openrecall.server.ai_engine import AIEngine
        return AIEngine()
    
    @pytest.fixture
    def sample_screenshot(self) -> Image.Image:
        """Create a simple test image (or load a real screenshot)."""
        # Check if there's a real screenshot to use
        test_screenshot_path = Path(__file__).parent / "fixtures" / "screenshot.png"
        if test_screenshot_path.exists():
            return Image.open(test_screenshot_path)
        
        # Create a simple synthetic image for testing
        img = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
        return img
    
    def test_engine_initialization(self, ai_engine):
        """Test that the AI engine initializes correctly."""
        assert ai_engine is not None
        assert ai_engine.model is not None
        assert ai_engine.processor is not None
    
    def test_analyze_image_returns_string(self, ai_engine, sample_screenshot):
        """Test that analyze_image returns a non-empty string."""
        result = ai_engine.analyze_image(sample_screenshot)
        
        assert isinstance(result, str)
        assert len(result) > 0
        print(f"\n=== AI Analysis Result ===\n{result}\n")
    
    def test_resize_for_cpu_small_image(self, ai_engine):
        """Test that small images are not resized."""
        small_img = Image.new("RGB", (800, 600))
        result = ai_engine._resize_for_cpu(small_img)
        
        assert result.size == (800, 600)
    
    def test_resize_for_cpu_large_image(self, ai_engine):
        """Test that large images are resized appropriately."""
        large_img = Image.new("RGB", (3840, 2160))  # 4K
        result = ai_engine._resize_for_cpu(large_img)
        
        # Should be resized so longest edge is MAX_IMAGE_SIZE
        assert max(result.size) == ai_engine.MAX_IMAGE_SIZE
        # Aspect ratio should be maintained
        original_ratio = 3840 / 2160
        result_ratio = result.size[0] / result.size[1]
        assert abs(original_ratio - result_ratio) < 0.01


class TestAIEngineSingleton:
    """Tests for the singleton pattern."""
    
    def test_get_ai_engine_returns_same_instance(self):
        """Test that get_ai_engine returns the same instance."""
        from openrecall.server.ai_engine import get_ai_engine
        
        engine1 = get_ai_engine()
        engine2 = get_ai_engine()
        
        assert engine1 is engine2


if __name__ == "__main__":
    """Run as script to manually test with a real screenshot."""
    import resource
    
    print("=" * 60)
    print("Qwen3-VL AI Engine Manual Test")
    print("=" * 60)
    
    # Monitor memory before loading
    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
    print(f"Memory before loading: {mem_before:.1f} MB")
    
    # Load engine
    from openrecall.server.ai_engine import AIEngine
    engine = AIEngine()
    
    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
    print(f"Memory after loading: {mem_after:.1f} MB")
    print(f"Model memory usage: ~{mem_after - mem_before:.1f} MB")
    
    # Test with real screenshot if provided
    if len(sys.argv) > 1:
        screenshot_path = sys.argv[1]
        print(f"\nAnalyzing: {screenshot_path}")
        image = Image.open(screenshot_path)
        
        import time
        start = time.time()
        result = engine.analyze_image(image)
        elapsed = time.time() - start
        
        print(f"\n=== Result (took {elapsed:.2f}s) ===")
        print(result)
    else:
        print("\nUsage: python test_ai_engine_qwen3.py <path_to_screenshot>")
        print("Creating synthetic test image...")
        
        test_img = Image.new("RGB", (1920, 1080), color=(50, 50, 50))
        
        import time
        start = time.time()
        result = engine.analyze_image(test_img)
        elapsed = time.time() - start
        
        print(f"\n=== Result (took {elapsed:.2f}s) ===")
        print(result)
