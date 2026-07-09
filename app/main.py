import io
import os

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from litofania import generar_stl

# --- Límites de seguridad (es un servicio público y gratuito) ---
MAX_ARCHIVO_MB = 15
MAX_RESOLUCION = 400          # px del lado más largo
MAX_ANCHO_MM = 300
MIN_ANCHO_MM = 20
MAX_GROSOR_MM = 10
MIN_GROSOR_MM = 0.1
RATE_LIMIT = os.getenv("RATE_LIMIT", "10/minute")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Litofanía API", version="1.0.0")
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
    if imagen.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Formato no soportado. Usa JPG, PNG o WEBP.")

    contenido = await imagen.read()
    if len(contenido) > MAX_ARCHIVO_MB * 1024 * 1024:
        raise HTTPException(413, f"La imagen supera el límite de {MAX_ARCHIVO_MB} MB.")

    # Validación / saneamiento de parámetros
    resolucion = max(30, min(resolucion, MAX_RESOLUCION))
    ancho_mm = max(MIN_ANCHO_MM, min(ancho_mm, MAX_ANCHO_MM))
    if alto_mm is not None:
        alto_mm = max(MIN_ANCHO_MM, min(alto_mm, MAX_ANCHO_MM))
    grosor_min = max(MIN_GROSOR_MM, min(grosor_min, MAX_GROSOR_MM))
    grosor_max = max(MIN_GROSOR_MM, min(grosor_max, MAX_GROSOR_MM))
    grosor_base = max(0.0, min(grosor_base, MAX_GROSOR_MM))
    if grosor_max <= grosor_min:
        raise HTTPException(400, "grosor_max debe ser mayor que grosor_min.")

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
    return StreamingResponse(
        io.BytesIO(stl_bytes),
        media_type="model/stl",
        headers={"Content-Disposition": f'attachment; filename="{nombre_salida}"'},
    )


# Sirve el frontend estático (index.html, css, js) en la raíz "/"
app.mount("/", StaticFiles(directory="static", html=True), name="static")
