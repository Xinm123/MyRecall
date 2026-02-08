"""Shared image utility functions for OpenRecall.

Provides MSSIM computation used by both:
- Client-side screenshot deduplication (recorder.py)
- Server-side video frame deduplication (frame_extractor.py)
"""

import numpy as np
from PIL import Image


def mean_structured_similarity_index(
    img1: np.ndarray, img2: np.ndarray, L: int = 255
) -> float:
    """Calculates the Mean Structural Similarity Index (MSSIM) between two images.

    Args:
        img1: The first image as a NumPy array (RGB).
        img2: The second image as a NumPy array (RGB).
        L: The dynamic range of the pixel values (default is 255).

    Returns:
        The MSSIM value between the two images (float between -1 and 1).
    """
    K1, K2 = 0.01, 0.03
    C1, C2 = (K1 * L) ** 2, (K2 * L) ** 2

    def rgb2gray(img: np.ndarray) -> np.ndarray:
        return 0.2989 * img[..., 0] + 0.5870 * img[..., 1] + 0.1140 * img[..., 2]

    img1_gray = rgb2gray(img1)
    img2_gray = rgb2gray(img2)
    mu1 = np.mean(img1_gray)
    mu2 = np.mean(img2_gray)
    sigma1_sq = np.var(img1_gray)
    sigma2_sq = np.var(img2_gray)
    sigma12 = np.mean((img1_gray - mu1) * (img2_gray - mu2))
    ssim_index = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return float(ssim_index)


def resize_image(image: np.ndarray, max_dim: int = 800) -> np.ndarray:
    """Resizes an image to fit within a maximum dimension while maintaining aspect ratio.

    Args:
        image: The input image as a NumPy array (RGB).
        max_dim: The maximum dimension for resizing.

    Returns:
        The resized image as a NumPy array (RGB).
    """
    pil_image = Image.fromarray(image)
    pil_image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    return np.array(pil_image)


def compute_similarity(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute MSSIM similarity between two images after resizing.

    Args:
        img1: First image as NumPy array (RGB).
        img2: Second image as NumPy array (RGB).

    Returns:
        MSSIM similarity score (0.0 to 1.0).
    """
    compress_img1 = resize_image(img1)
    compress_img2 = resize_image(img2)
    return mean_structured_similarity_index(compress_img1, compress_img2)
