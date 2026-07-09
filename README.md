# Litofanías — foto a STL 🕯️

Convierte cualquier foto en un modelo 3D imprimible (**STL**) de una **litofanía**: un relieve delgado que, al iluminarlo por detrás, revela la imagen original en luces y sombras.

Servicio **100% gratuito, sin registro y de código abierto**, pensado para la comunidad de impresión 3D. No se almacenan las imágenes subidas: se procesan en memoria y se descartan apenas se genera el STL.

## Cómo funciona

1. Subís una imagen (JPG, PNG o WEBP) desde el navegador.
2. El backend la convierte a escala de grises y genera un mapa de alturas: zonas claras → espesor delgado, zonas oscuras → espesor grueso.
3. Se construye una malla 3D (superficie superior variable + base plana + paredes laterales).
4. Descargás el `.stl`, listo para laminar (Cura, PrusaSlicer, etc.) e imprimir con filamento translúcido (PLA blanco o natural funciona muy bien).

## Estructura del proyecto

```
litofania/
├── app/
│   ├── main.py           # API FastAPI (endpoints /litofania y /health)
│   ├── litofania.py       # Lógica de generación de la malla STL
│   └── requirements.txt
├── static/
│   └── index.html         # Frontend (sube la imagen, ajusta parámetros y descarga)
├── Dockerfile
└── docker-compose.yml
```

## Requisitos

- Docker y Docker Compose. No hace falta GPU: todo corre sobre CPU.

## Despliegue

```bash
git clone https://github.com/davidzeus/litofanias.git
cd litofanias
docker compose up -d --build
```

La app queda disponible en `http://localhost:8000` (o el puerto/dominio que configures).

## Parámetros de generación

| Parámetro     | Descripción                                   | Rango permitido |
|---------------|------------------------------------------------|------------------|
| `ancho_mm`    | Ancho físico final de la pieza                 | 20 – 300 mm      |
| `alto_mm`     | Alto físico (opcional, se calcula por proporción si no se envía) | 20 – 300 mm |
| `grosor_min`  | Espesor en las zonas más claras                | 0.1 – 10 mm      |
| `grosor_max`  | Espesor en las zonas más oscuras               | 0.1 – 10 mm      |
| `grosor_base` | Base rígida uniforme añadida debajo de toda la pieza | 0 – 10 mm  |
| `resolucion`  | Nivel de detalle (px del lado más largo)        | 30 – 400 px      |
| `invertir`    | Invierte el criterio claro/oscuro               | true / false     |

## API

```
POST /litofania          → recibe la imagen (multipart/form-data) + parámetros, devuelve el .stl
GET  /health              → chequeo de estado del servicio
```

Por ser un servicio público, tiene límites de uso: tamaño máx. de imagen 15 MB y un *rate limit* configurable (por defecto 10 peticiones/minuto por IP, variable de entorno `RATE_LIMIT`).

## Contribuir

Los *pull requests* son bienvenidos: mejoras de rendimiento, soporte para más formatos, opciones de marco/borde, traducciones, lo que se te ocurra.

## Apoyar el proyecto

Este servicio se mantiene y aloja de forma gratuita para la comunidad. Si te resultó útil y querés colaborar con los costos del servidor:

- **Transferencia (ARS):** `agnuxArg`
- **PayPal:** [paypal.me/agnux](https://paypal.me/agnux)

No es obligatorio, ¡pero se agradece! 🙌

## Licencia

MIT — usalo, modificalo y compartilo libremente.
