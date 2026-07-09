"""
ollama_client.py
Cliente para pedirle al modelo de visión en Ollama (local, LAN) que analice
una foto y recomiende ajustes para mejorarla antes de convertirla en litofanía.
"""

import base64
import os

import httpx
from pydantic import BaseModel, Field, ValidationError

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://10.10.0.48:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ministral-es:latest")
OLLAMA_TIMEOUT_SEGUNDOS = float(os.getenv("OLLAMA_TIMEOUT_SEGUNDOS", "25"))

PROMPT_ANALISIS = """Sos un asistente que analiza fotos para convertirlas en litofanías \
(relieves 3D que se iluminan por detrás). Mirá la imagen y devolvé SOLO un JSON \
con esta forma exacta, sin texto adicional ni explicaciones fuera del JSON:

{"contraste": <float entre 0.7 y 1.6>, "brillo": <float entre 0.7 y 1.4>, \
"gamma": <float entre 0.6 y 1.4>, "invertir": <true o false>, \
"motivo": "<explicación breve en español, máximo 20 palabras>"}

Reglas:
- Si la imagen tiene poco contraste o se ve plana, subí "contraste".
- Si está muy oscura, subí "brillo" y bajá "gamma"; si está muy clara, al revés.
- "invertir" casi siempre debe ser false; poné true solo si es un negativo fotográfico \
o una radiografía.
- Los valores 1.0 significan "sin cambios"."""


class AjustesIA(BaseModel):
    contraste: float = Field(ge=0.5, le=2.0, default=1.0)
    brillo: float = Field(ge=0.5, le=2.0, default=1.0)
    gamma: float = Field(ge=0.4, le=2.0, default=1.0)
    invertir: bool = False
    motivo: str = ""


class OllamaNoDisponibleError(Exception):
    """Se lanza si Ollama no responde, tarda demasiado o devuelve algo inválido."""


async def analizar_imagen(imagen_bytes: bytes) -> AjustesIA:
    b64 = base64.b64encode(imagen_bytes).decode("ascii")
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": PROMPT_ANALISIS, "images": [b64]},
        ],
        "format": "json",
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SEGUNDOS) as client:
            resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise OllamaNoDisponibleError(f"No se pudo contactar a Ollama: {exc}") from exc

    contenido = (data.get("message") or {}).get("content", "")
    try:
        return AjustesIA.model_validate_json(contenido)
    except (ValidationError, ValueError) as exc:
        raise OllamaNoDisponibleError(f"Respuesta de la IA inválida: {exc}") from exc
