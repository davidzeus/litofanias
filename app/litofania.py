"""
litofania.py
Convierte una imagen en un modelo 3D (STL) de litofanía.

Una litofanía es un relieve delgado que, al ser iluminado por detrás,
revela la imagen original gracias a las variaciones de espesor:
- Zonas claras de la imagen  -> espesor delgado  (deja pasar más luz)
- Zonas oscuras de la imagen -> espesor grueso    (deja pasar menos luz)
"""

from __future__ import annotations

import io
import numpy as np
from PIL import Image, ImageOps
from stl import mesh as stl_mesh


def _cargar_heightmap(
    imagen_bytes: bytes,
    resolucion: int,
    invertir: bool,
) -> np.ndarray:
    """Carga la imagen, la convierte a escala de grises y la redimensiona.

    Devuelve un array 2D (h, w) con valores float en [0, 1], donde 1.0
    significa "debe quedar delgado" (zona clara) y 0.0 "debe quedar grueso"
    (zona oscura), salvo que `invertir=True`, que voltea ese criterio.
    """
    img = Image.open(io.BytesIO(imagen_bytes))
    img = ImageOps.exif_transpose(img)  # respeta orientación EXIF
    img = img.convert("L")  # escala de grises

    w, h = img.size
    escala = resolucion / max(w, h)
    nuevo_w = max(2, round(w * escala))
    nuevo_h = max(2, round(h * escala))
    img = img.resize((nuevo_w, nuevo_h), Image.LANCZOS)

    arr = np.asarray(img, dtype=np.float64) / 255.0  # (h, w) en [0,1]

    if invertir:
        arr = 1.0 - arr

    return arr


def _construir_malla(
    brillo: np.ndarray,
    ancho_mm: float,
    alto_mm: float,
    grosor_min: float,
    grosor_max: float,
    grosor_base: float,
) -> stl_mesh.Mesh:
    """Construye la malla triangular (superficie superior variable,
    superficie inferior plana y paredes laterales) a partir del heightmap.
    """
    h, w = brillo.shape

    # Espesor real en mm en cada punto: brillo alto -> delgado, brillo bajo -> grueso
    # brillo=1 (claro)  -> grosor_min
    # brillo=0 (oscuro) -> grosor_max
    espesor = grosor_max - (brillo * (grosor_max - grosor_min))
    z_top = grosor_base + espesor  # superficie superior (variable)
    z_bottom = np.zeros_like(z_top)  # superficie inferior (plana, z=0)

    paso_x = ancho_mm / (w - 1)
    paso_y = alto_mm / (h - 1)

    xs = np.arange(w) * paso_x
    ys = np.arange(h) * paso_y
    grid_x, grid_y = np.meshgrid(xs, ys)  # (h, w)

    # --- Vértices ---
    top_vertices = np.stack([grid_x, grid_y, z_top], axis=-1).reshape(-1, 3)
    bottom_vertices = np.stack([grid_x, grid_y, z_bottom], axis=-1).reshape(-1, 3)
    vertices = np.vstack([top_vertices, bottom_vertices])
    offset = h * w  # índice donde empiezan los vértices "de abajo"

    def idx(i, j):
        return i * w + j

    # --- Caras de la superficie superior (grid vectorizado) ---
    i, j = np.mgrid[0 : h - 1, 0 : w - 1]
    v0 = idx(i, j)
    v1 = idx(i, j + 1)
    v2 = idx(i + 1, j)
    v3 = idx(i + 1, j + 1)

    top_faces = np.concatenate(
        [
            np.stack([v0, v2, v1], axis=-1).reshape(-1, 3),
            np.stack([v1, v2, v3], axis=-1).reshape(-1, 3),
        ]
    )

    # --- Caras de la superficie inferior (mismo grid, offset e invertidas) ---
    v0b, v1b, v2b, v3b = v0 + offset, v1 + offset, v2 + offset, v3 + offset
    bottom_faces = np.concatenate(
        [
            np.stack([v0b, v1b, v2b], axis=-1).reshape(-1, 3),
            np.stack([v1b, v3b, v2b], axis=-1).reshape(-1, 3),
        ]
    )

    # --- Paredes laterales (los 4 bordes del rectángulo) ---
    def pared(top_ids_a, top_ids_b, bottom_ids_a, bottom_ids_b):
        """Genera dos triángulos por cada segmento del borde."""
        t1 = np.stack([top_ids_a, bottom_ids_a, top_ids_b], axis=-1)
        t2 = np.stack([top_ids_b, bottom_ids_a, bottom_ids_b], axis=-1)
        return np.concatenate([t1, t2])

    # borde superior (i=0), recorriendo j
    j_range = np.arange(w - 1)
    borde_top = pared(
        idx(0, j_range), idx(0, j_range + 1),
        idx(0, j_range) + offset, idx(0, j_range + 1) + offset,
    )
    # borde inferior (i=h-1), orden invertido para normal hacia afuera
    borde_bottom = pared(
        idx(h - 1, j_range + 1), idx(h - 1, j_range),
        idx(h - 1, j_range + 1) + offset, idx(h - 1, j_range) + offset,
    )
    # borde izquierdo (j=0), recorriendo i, orden invertido
    i_range = np.arange(h - 1)
    borde_left = pared(
        idx(i_range + 1, 0), idx(i_range, 0),
        idx(i_range + 1, 0) + offset, idx(i_range, 0) + offset,
    )
    # borde derecho (j=w-1)
    borde_right = pared(
        idx(i_range, w - 1), idx(i_range + 1, w - 1),
        idx(i_range, w - 1) + offset, idx(i_range + 1, w - 1) + offset,
    )

    faces = np.concatenate(
        [top_faces, bottom_faces, borde_top, borde_bottom, borde_left, borde_right]
    )

    data = np.zeros(faces.shape[0], dtype=stl_mesh.Mesh.dtype)
    modelo = stl_mesh.Mesh(data, remove_empty_areas=False)
    modelo.vectors[:] = vertices[faces]
    return modelo


def generar_stl(
    imagen_bytes: bytes,
    ancho_mm: float = 100.0,
    alto_mm: float | None = None,
    grosor_min: float = 0.8,
    grosor_max: float = 3.0,
    grosor_base: float = 0.6,
    resolucion: int = 250,
    invertir: bool = False,
) -> bytes:
    """Genera un STL de litofanía a partir de los bytes de una imagen.

    Args:
        imagen_bytes: contenido crudo del archivo de imagen.
        ancho_mm: ancho físico final en milímetros.
        alto_mm: alto físico final en milímetros (si es None, se calcula
            manteniendo la proporción original de la imagen).
        grosor_min: espesor mínimo (zonas más claras) en mm.
        grosor_max: espesor máximo (zonas más oscuras) en mm.
        grosor_base: espesor de una base sólida añadida debajo de toda la
            pieza, para darle rigidez (0 = sin base).
        resolucion: número máximo de píxeles en el lado más largo de la
            imagen (controla el nivel de detalle y el tamaño del STL).
        invertir: si es True, invierte el criterio claro/oscuro.

    Returns:
        Bytes del archivo STL binario resultante.
    """
    brillo = _cargar_heightmap(imagen_bytes, resolucion, invertir)
    h, w = brillo.shape

    if alto_mm is None:
        alto_mm = ancho_mm * (h / w)

    modelo = _construir_malla(
        brillo, ancho_mm, alto_mm, grosor_min, grosor_max, grosor_base
    )

    buffer = io.BytesIO()
    modelo.save("litofania.stl", fh=buffer, mode=stl_mesh.stl.Mode.BINARY)
    return buffer.getvalue()
