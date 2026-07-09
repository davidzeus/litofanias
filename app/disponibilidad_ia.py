"""
disponibilidad_ia.py
Controla la ventana horaria en la que la mejora con IA está habilitada.
Pensado para no saturar el Ollama local: solo disponible fuera del horario
de uso "normal" del dueño de la GPU.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_HORARIA = os.getenv("IA_ZONA_HORARIA", "America/Argentina/Buenos_Aires")
HORA_INICIO = int(os.getenv("IA_HORA_INICIO", "15"))  # 15 = 15:00
HORA_FIN = int(os.getenv("IA_HORA_FIN", "5"))          # 5 = 05:00 del día siguiente

_tz = ZoneInfo(ZONA_HORARIA)


def ia_disponible_ahora() -> bool:
    """True si la hora actual (en ZONA_HORARIA) cae dentro de la ventana
    configurada. Soporta ventanas que cruzan la medianoche (ej. 15 -> 5).
    """
    hora_actual = datetime.now(_tz).hour

    if HORA_INICIO <= HORA_FIN:
        return HORA_INICIO <= hora_actual < HORA_FIN
    # Ventana que cruza medianoche, ej. 15:00 -> 05:00
    return hora_actual >= HORA_INICIO or hora_actual < HORA_FIN


def proxima_ventana_info() -> str:
    """Texto legible para mostrarle al usuario cuándo está disponible."""
    return f"Disponible de {HORA_INICIO:02d}:00 a {HORA_FIN:02d}:00 (hora Argentina)."
