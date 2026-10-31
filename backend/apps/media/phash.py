"""Perceptual image hashing (DCT-based pHash).

Two photos of the same object — resized, re-compressed, slightly cropped —
land within a handful of bits of each other, while unrelated images do not.
That is what makes stolen-photo and duplicate-listing detection possible
without storing or comparing pixels (Phase 17 consumes this; Phase 14
stores the hash with every upload and exposes the distance helper).

Implementation: 32x32 grayscale thumbnail -> orthonormal 2-D DCT-II -> the
top-left 8x8 low-frequency block (64 coefficients) -> one bit per
coefficient against the block's median. Small, dependency-light (numpy),
and deterministic across platforms.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

_SIZE = 32
_LOW = 8
#: Bits that may differ before two images stop looking like the same photo.
#: 8/64 tolerates re-encoding, resizing and light cropping; unrelated images
#: typically land around 28-32.
SIMILAR_DISTANCE = 8


def _dct_matrix(n: int) -> np.ndarray:
    """The orthonormal DCT-II matrix: ``C[k, x]``."""
    x = np.arange(n, dtype=np.float64).reshape(1, -1)
    k = np.arange(n, dtype=np.float64).reshape(-1, 1)
    matrix = np.cos(np.pi * (2 * x + 1) * k / (2 * n))
    matrix *= np.sqrt(2.0 / n)
    matrix[0, :] *= np.sqrt(1.0 / 2.0)
    return matrix


_DCT = _dct_matrix(_SIZE)


def phash(image: Image.Image) -> str:
    """64-bit perceptual hash as 16 lowercase hex characters."""
    gray = image.convert("L").resize((_SIZE, _SIZE), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float64)
    coefficients = _DCT @ pixels @ _DCT.T
    low = coefficients[:_LOW, :_LOW].flatten()
    threshold = float(np.median(low))
    value = 0
    for coefficient in low:
        value = (value << 1) | int(coefficient > threshold)
    return f"{value:016x}"


def hamming(left: str, right: str) -> int:
    """Bits that differ between two pHashes (0 = identical, 64 = opposite)."""
    if not left or not right:
        raise ValueError("Both hashes are required.")
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def is_probable_match(left: str, right: str, *, max_distance: int = SIMILAR_DISTANCE) -> bool:
    """Whether two hashes are close enough to be the same photograph."""
    try:
        return hamming(left, right) <= max_distance
    except ValueError:
        return False
