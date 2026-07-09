import io
import os
import urllib.parse

from dotenv import load_dotenv

load_dotenv()  # lee .env si existe (en Docker, docker-compose ya inyecta las vars)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from disponibilidad_ia import ia_disponible_ahora, proxima_ventana_info
from image_enhance import aplicar_ajustes
from litofania import generar_stl
from ollama_client import OllamaNoDisponibleError, analizar_imagen

# --- Límites de seguridad (es un servicio público y gratuito) ---
MAX_ARCHIVO_MB = 15
MAX_RESOLUCION = 400          # px del lado más largo
MAX_ANCHO_MM = 300
MIN_ANCHO_MM = 20
MAX_GROSOR_MM = 10
MIN_GROSOR_MM = 0.1
RATE_LIMIT = os.getenv("RATE_LIMIT", "10/minute")
RATE_LIMIT_IA = os.getenv("RATE_LIMIT_IA", "5/minute")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Litofanía API", version="1.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ia/estado")
def ia_estado():
    """El frontend consulta esto para saber si mostrar/habilitar el toggle de IA."""
    return {
        "disponible": ia_disponible_ahora(),
        "info": proxima_ventana_info(),
    }


def _leer_y_validar(imagen: UploadFile, contenido: bytes) -> None:
    if imagen.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Formato no soportado. Usa JPG, PNG o WEBP.")
    if len(contenido) > MAX_ARCHIVO_MB * 1024 * 1024:
        raise HTTPException(413, f"La imagen supera el límite de {MAX_ARCHIVO_MB} MB.")


def _sanear_parametros(
    resolucion: int,
    ancho_mm: float,
    alto_mm: float | None,
    grosor_min: float,
    grosor_max: float,
    grosor_base: float,
) -> tuple[int, float, float | None, float, float, float]:
    resolucion = max(30, min(resolucion, MAX_RESOLUCION))
    ancho_mm = max(MIN_ANCHO_MM, min(ancho_mm, MAX_ANCHO_MM))
    if alto_mm is not None:
        alto_mm = max(MIN_ANCHO_MM, min(alto_mm, MAX_ANCHO_MM))
    grosor_min = max(MIN_GROSOR_MM, min(grosor_min, MAX_GROSOR_MM))
    grosor_max = max(MIN_GROSOR_MM, min(grosor_max, MAX_GROSOR_MM))
    grosor_base = max(0.0, min(grosor_base, MAX_GROSOR_MM))
    if grosor_max <= grosor_min:
        raise HTTPException(400, "grosor_max debe ser mayor que grosor_min.")
    return resolucion, ancho_mm, alto_mm, grosor_min, grosor_max, grosor_base


def _respuesta_stl(stl_bytes: bytes, nombre_archivo: str, motivo_ia: str | None = None) -> StreamingResponse:
    headers = {"Content-Disposition": f'attachment; filename="{nombre_archivo}"'}
    if motivo_ia:
        # Los headers HTTP deben ser ASCII/latin-1: se codifica para permitir acentos.
        headers["X-IA-Motivo"] = urllib.parse.quote(motivo_ia)
    return StreamingResponse(io.BytesIO(stl_bytes), media_type="model/stl", headers=headers)


@app.post("/litofania")
@limiter.limit(RATE_LIMIT)
async def crear_litofania(
    request: Request,
    imagen: UploadFile = File(...),
    ancho_mm: float = Form(100.0),
    alto_mm: float | None = Form(None),
    grosor_min: float = Form(0.8),
    grosor_max: float = Form(3.0),
    grosor_base: float = Form(0.6),
    resolucion: int = Form(250),
    invertir: bool = Form(False),
):
    contenido = await imagen.read()
    _leer_y_validar(imagen, contenido)
    resolucion, ancho_mm, alto_mm, grosor_min, grosor_max, grosor_base = _sanear_parametros(
        resolucion, ancho_mm, alto_mm, grosor_min, grosor_max, grosor_base
    )

    try:
        stl_bytes = generar_stl(
            imagen_bytes=contenido,
            ancho_mm=ancho_mm,
            alto_mm=alto_mm,
            grosor_min=grosor_min,
            grosor_max=grosor_max,
            grosor_base=grosor_base,
            resolucion=resolucion,
            invertir=invertir,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"No se pudo procesar la imagen: {exc}") from exc

    nombre_salida = os.path.splitext(imagen.filename or "litofania")[0] + ".stl"
    return _respuesta_stl(stl_bytes, nombre_salida)


@app.post("/litofania/ia")
@limiter.limit(RATE_LIMIT_IA)
async def crear_litofania_con_ia(
    request: Request,
    imagen: UploadFile = File(...),
    ancho_mm: float = Form(100.0),
    alto_mm: float | None = Form(None),
    grosor_min: float = Form(0.8),
    grosor_max: float = Form(3.0),
    grosor_base: float = Form(0.6),
    resolucion: int = Form(250),
):
    """Igual que /litofania, pero primero le pide a la IA (Ollama local) que
    analice la foto y ajuste contraste/brillo/gamma/inversión automáticamente.
    Solo disponible fuera del horario de uso normal de la GPU.
    """
    if not ia_disponible_ahora():
        raise HTTPException(
            403,
            f"La mejora con IA no está disponible en este horario. {proxima_ventana_info()}",
        )

    contenido = await imagen.read()
    _leer_y_validar(imagen, contenido)
    resolucion, ancho_mm, alto_mm, grosor_min, grosor_max, grosor_base = _sanear_parametros(
        resolucion, ancho_mm, alto_mm, grosor_min, grosor_max, grosor_base
    )

    try:
        ajustes = await analizar_imagen(contenido)
    except OllamaNoDisponibleError as exc:
        raise HTTPException(503, f"La IA no está disponible ahora mismo: {exc}") from exc

    contenido_mejorado = aplicar_ajustes(
        contenido, contraste=ajustes.contraste, brillo=ajustes.brillo, gamma=ajustes.gamma
    )

    try:
        stl_bytes = generar_stl(
            imagen_bytes=contenido_mejorado,
            ancho_mm=ancho_mm,
            alto_mm=alto_mm,
            grosor_min=grosor_min,
            grosor_max=grosor_max,
            grosor_base=grosor_base,
            resolucion=resolucion,
            invertir=ajustes.invertir,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"No se pudo procesar la imagen: {exc}") from exc

    nombre_salida = os.path.splitext(imagen.filename or "litofania")[0] + "-ia.stl"
    return _respuesta_stl(stl_bytes, nombre_salida, motivo_ia=ajustes.motivo)


# Sirve el frontend estático (index.html, css, js) en la raíz "/"
app.mount("/", StaticFiles(directory="static", html=True), name="static")
