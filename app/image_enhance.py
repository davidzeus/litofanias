"""
image_enhance.py
Aplica ajustes de contraste, brillo y gamma sobre una imagen (bytes -> bytes).
Los valores de ajuste suelen venir de ollama_client.analizar_imagen().
"""

import io

import numpy as np
from PIL import Image, ImageEnhance


def aplicar_ajustes(
    imagen_bytes: bytes,
    contraste: float = 1.0,
    brillo: float = 1.0,
    gamma: float = 1.0,
) -> bytes:
    img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")

    if contraste != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contraste)
    if brillo != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brillo)
    if gamma != 1.0:
        arr = np.asarray(img).astype(np.float64) / 255.0
        arr = np.clip(arr, 0, 1) ** gamma
        img = Image.fromarray((arr * 255.0).round().astype(np.uint8))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
