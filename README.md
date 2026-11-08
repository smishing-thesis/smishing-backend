# smishing-backend

API optativa de aportes SMS ya anonimizados, Python 3.12 y FastAPI. La inferencia
Char-CNN/LiteRT permanece en Android; este servicio no clasifica mensajes.
La base y el flujo de aportes se integran por historias verificadas. Consulta
[arquitectura, privacidad y estado real](docs/architecture-privacy.md) para
distinguir main de las funciones internas que siguen en PR.

## Desarrollo y verificación

```sh
uv sync --locked --group dev
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked mypy
```

PostgreSQL 17 local efímero, solo para pruebas sintéticas:

```sh
docker run --rm --name smishing-test-pg -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smishing_test -p 127.0.0.1:55432:5432 -d postgres:17
export SMISHING_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55432/smishing_test
uv run --locked pytest -q
```

Sin esa variable se omiten explícitamente las pruebas PostgreSQL; no equivale a
verificación completa. El fixture rechaza nombres sin sufijo `_test` y crea un
esquema aleatorio por prueba. El ensayo HTTPS usa certificado efímero verificado,
OpenSSL y Uvicorn local; no despliega servicios. No usar corpus real en pruebas.

Para migraciones, configurar SMISHING_DATABASE_URL en la base correspondiente y
correr `uv run --locked alembic upgrade head`. En una base vacía dedicada se prueba
`alembic downgrade base` seguido de `alembic upgrade head`.

## Servidor local TLS

Configurar claves con el gestor de secretos/variables del proceso, sin valores
reales en Git. `pydantic-settings` no carga `.env` automáticamente.

```sh
export TLS_CERT_PATH=/ruta/externa/cert.pem
export TLS_KEY_PATH=/ruta/externa/key.pem
uv run --locked python -m smishing_backend.server
```

`GET /health` devuelve `{"status":"ok"}`. `POST /api/v1/contributions` exige
HTTPS y X-API-Key; valida y reexamina anonimización antes de guardar el aporte
pendiente junto a su etiqueta. `/docs` presenta OpenAPI. El contrato móvil sigue
pendiente de acuerdo: [revisión](docs/contract-review.md).

| Variable | Predeterminado | Uso |
| --- | --- | --- |
| SMISHING_DATABASE_URL | postgresql+psycopg://localhost/smishing | Conexión PostgreSQL |
| SMISHING_API_KEYS | lista vacía | Lista JSON de claves activas, rotable |
| SMISHING_API_KEY | sin valor | Compatibilidad; también es una clave activa |
| SMISHING_RATE_LIMIT_PER_MINUTE | 60 | Cuota del par de red inmediato por proceso |
| SMISHING_GLOBAL_RATE_LIMIT_PER_MINUTE | 600 | Cuota global por proceso |
| SMISHING_LOG_DIR | var/log/smishing-backend | Eventos sin texto/direcciones; rotación diaria |
| SMISHING_PORT | 8443 | Puerto local TLS |

El runner usa un proceso, desactiva encabezados de proxy y access logs. Una
clave Android extraíble no demuestra procedencia oficial. El modelo spaCy de
nombres se instala desde dependencia bloqueada; requiere memoria y no se descarga
al arrancar. No hay endpoints públicos de revisión, exportación ni entrenamiento.

## Diseño y operación

API y servicios componen casos de uso; dominio define reglas/puertos sin FastAPI
ni SQLAlchemy; datos implementa PostgreSQL detrás de interfaces. Solo se guardan
texto anonimizado, etiqueta, versión y revisión, sin campos de persona/dispositivo.

- [Contrato OpenAPI](docs/openapi-v1.json) y [validación](docs/validation.md).
- [PostgreSQL/migraciones](docs/database.md) y [repositorios](docs/repositories.md).
- [Autenticación](docs/authentication.md), [cuotas](docs/rate-limit.md) y [API](docs/contribution-api.md).
- [Duplicados](docs/deduplication.md), [anonimización y límites](docs/anonymization.md) y [cuarentena](docs/quarantine.md).
- [Logs y respaldos](docs/privacy-operations.md) y [CI](docs/ci.md).

Antes de recepción pública faltan el acuerdo móvil, decisiones operativas de
credenciales y revisión de respaldos/retención en la infraestructura elegida.
No se ha hecho despliegue ni se garantiza anonimización perfecta.

[Ramas, commits, PRs, resultados y pendientes de la sesión Cloud](docs/development-status.md).
