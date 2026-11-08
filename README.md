# smishing-backend

Base del servicio de corpus con FastAPI y Python 3.12.

La [arquitectura, datos, privacidad y estado operativo](docs/architecture-privacy.md)
es la referencia central del equipo. Distingue lo integrado en main de las
funciones implementadas en PR y de la infraestructura todavía pendiente.

## Desarrollo local

Instala [uv](https://docs.astral.sh/uv/) y ejecuta desde este directorio:

```bash
uv sync --locked --group dev
uv run --locked uvicorn smishing_backend.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

`GET http://127.0.0.1:8000/health` devuelve `{"status":"ok"}`.
Las pruebas se ejecutan con `uv run --locked pytest`.

## Configuración

`pydantic-settings` lee variables del proceso; no carga `.env` automáticamente.
El archivo `.env` queda excluido de Git.

| Variable | Predeterminado | Uso |
| --- | --- | --- |
| `SMISHING_DATABASE_URL` | `postgresql+psycopg://localhost/smishing` | Conexión PostgreSQL |
| `SMISHING_RATE_LIMIT_PER_MINUTE` | `60` | Límite futuro, entero positivo |
| `SMISHING_API_KEY` | Sin valor | Clave futura, protegida en representaciones |

Main incluye #3, #8 y #9: configuración, migraciones y repositorios. La ruta
de aportes, limitación y autenticación siguen en PR apilados. El endpoint de
salud no requiere clave ni consulta PostgreSQL.

## Capas

- `api`: rutas y modelos HTTP.
- `services`: casos de uso.
- `domain`: reglas puras del corpus, sin dependencias de FastAPI ni datos.
- `data/repositories`: persistencia PostgreSQL detrás de interfaces del dominio.

No se incluyen mensajes reales ni datos personales.

Migraciones y pruebas PostgreSQL: [docs/database.md](docs/database.md).
