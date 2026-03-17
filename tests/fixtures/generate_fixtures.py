"""Generate test fixture images for P1-S3 OCR testing.

Creates three test images:
1. sample_jpeg.jpg - Image with text for normal OCR scenario
2. corrupted_image.jpg - Invalid/corrupted image for OCR failure scenario
3. empty_text_image.jpg - Solid color image for OCR empty text scenario
"""

from PIL import Image, ImageDraw, ImageFont
import os

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))


def create_sample_jpeg():
    """Create a JPEG image with sample text for OCR testing."""
    # Create a white image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)

    # Draw some text - use default font
    try:
        # Try to use a basic font
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except (OSError, IOError):
        # Fall back to default
        font = ImageFont.load_default()

    draw.text((20, 30), "Test OCR Sample", fill='black', font=font)
    draw.text((20, 70), "Line 2: More Text", fill='black', font=font)
    draw.text((20, 110), "Line 3: Final Line", fill='black', font=font)

    path = os.path.join(FIXTURES_DIR, 'images', 'sample_jpeg.jpg')
    img.save(path, 'JPEG', quality=85)
    print(f"Created: {path}")
    return path


def create_corrupted_image():
    """Create a corrupted JPEG file for OCR failure testing."""
    path = os.path.join(FIXTURES_DIR, 'images', 'corrupted_image.jpg')
    # Write invalid JPEG data
    with open(path, 'wb') as f:
        # Write JPEG header but with corrupted data
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF')  # JPEG header
        f.write(b'\x00' * 100)  # Invalid data
        f.write(b'CORRUPTED DATA NOT A REAL IMAGE')
    print(f"Created: {path}")
    return path


def create_empty_text_image():
    """Create a solid color JPEG with no text for OCR empty text scenario."""
    # Create a solid color image with no text
    img = Image.new('RGB', (400, 200), color='#336699')

    path = os.path.join(FIXTURES_DIR, 'images', 'empty_text_image.jpg')
    img.save(path, 'JPEG', quality=85)
    print(f"Created: {path}")
    return path


if __name__ == '__main__':
    os.makedirs(os.path.join(FIXTURES_DIR, 'images'), exist_ok=True)
    create_sample_jpeg()
    create_corrupted_image()
    create_empty_text_image()
    print("\nAll test fixtures created successfully!")
