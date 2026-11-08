# smishing-backend

Base del servicio de corpus con FastAPI y Python 3.12.

## Desarrollo local

Instala [uv](https://docs.astral.sh/uv/) y ejecuta desde este directorio:

```bash
uv sync --locked --group dev
uv run --locked uvicorn smishing_backend.main:app --host 127.0.0.1 --port 8000
```

`GET http://127.0.0.1:8000/health` devuelve `{"status":"ok"}`.
Las pruebas se ejecutan con `uv run --locked pytest`.

## Configuración

`pydantic-settings` lee variables del proceso; no carga `.env` automáticamente.
El archivo `.env` queda excluido de Git.

| Variable | Predeterminado | Uso |
| --- | --- | --- |
| `SMISHING_DATABASE_URL` | `sqlite:///./data/smishing.db` | Conexión futura |
| `SMISHING_RATE_LIMIT_PER_MINUTE` | `60` | Límite futuro, entero positivo |
| `SMISHING_API_KEY` | Sin valor | Clave futura, protegida en representaciones |

La historia #3 configura estas opciones; aún no implementa persistencia,
limitación ni autenticación. El endpoint de salud no requiere clave.

## Capas

- `api`: rutas y modelos HTTP.
- `services`: casos de uso.
- `domain`: reglas puras del corpus, sin dependencias de FastAPI ni datos.
- `data/repositories`: persistencia cuando se defina su contrato.

No se incluyen mensajes reales ni datos personales.
