# smishing-backend

Contexto para trabajar en este repositorio. Proyecto de tesis (UPC): detector de
smishing en SMS en español que corre **dentro del teléfono Android**, sin internet,
para gama baja. La app (repo `smishing-mobile-app`) clasifica con un Char-CNN en
LiteRT. **Este repo es solo la API OPCIONAL de aportes al corpus**: no clasifica,
no entrena y no tiene el modelo. Python 3.12, FastAPI, PostgreSQL.

## Reglas que no se rompen

- Los aportes llegan ya anonimizados y con consentimiento verificado **en el
  teléfono**. El backend no guarda nada que identifique al contribuyente o al
  dispositivo: sin IP, ID, cuenta ni telemetría.
- Nunca poner texto de mensajes ni direcciones en logs, respaldos ni mensajes de
  error. Los errores públicos son genéricos y no repiten valores recibidos.
- Pruebas solo con mensajes sintéticos. Nunca corpus real, ni abrir los archivos
  de SMS reales de la carpeta de la tesis.
- Issues en español; una rama y un PR por historia (`feat/<n>-...`); nunca
  commits en `main`. No agregar a Claude como coautor.
- Explicar antes de aplicar cambios. No hacer commit ni push salvo que se pida.
- Registrar resultados con honestidad: si una prueba falla o no se pudo medir,
  decirlo. No declarar terminado lo que no se verificó.
- Un cambio de contrato se acuerda con la app antes de implementarlo y se refleja
  en el OpenAPI.

## Contrato (fuente de verdad compartida con la app)

[docs/openapi-v1.json](docs/openapi-v1.json) y [docs/contract-review.md](docs/contract-review.md).
Versión 1.1.0. HTTPS y `X-API-Key`.

- `POST /api/v1/contributions`: un aporte. Cuerpo `text` (1 a 2048), `label`
  (`safe`|`smishing`), `model_version` (máx. 20). Respuestas 201, 400, 401, 409
  duplicado, 413, 422, 429 con `Retry-After`, 503.
- `POST /api/v1/contributions/batch` (#48): 1 a 20 aportes, hasta 327680 bytes.
  200 con un resultado por aporte (`accepted`, `duplicate`, `rejected` con
  `reason`). Atomicidad por aporte; la cuota cuenta aportes, no solicitudes.
  No acepta `anonymization_version`.

`docs/openapi-v1.json` se genera con `contract_app()`; `tests/test_contract.py` lo
compara con el código. Si cambia el contrato, regenerarlo a propósito.

## Estructura

`src/smishing_backend/`: `api/` (rutas, validación, autenticación, cuota),
`domain/` (reglas, sin FastAPI ni SQLAlchemy), `data/` (PostgreSQL, repositorios),
más revisión interna, exportación y servidores TLS. Migraciones en `migrations/`
(0001–0006). Estado y límites reales: [docs/architecture-privacy.md](docs/architecture-privacy.md).
`docs/development-status.md` está desactualizado (2 de noviembre).

## Verificación

```sh
uv sync --locked --group dev
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked mypy
uv run --locked pytest -q
```

`pytest` necesita `SMISHING_TEST_DATABASE_URL` apuntando a una base PostgreSQL 17
cuyo nombre **termine en `_test`** (el fixture lo exige y crea un esquema por
prueba). Sin la variable, las pruebas de PostgreSQL se omiten y eso no es
verificación completa. Ver el README para Docker. No guardar claves en el repo.

## Notas de Windows

- Usar `PYTHONUTF8=1`; si no, `tests/test_contract.py` y otros lectores de archivos
  usan la codificación del sistema.
- `tests/test_corpus_export.py::test_real_unmodified_model_loader_reads_export`
  falla en Windows porque Git convierte a CRLF un archivo fijado por hash. Pasa en
  Linux/CI. No es un fallo de la lógica.
