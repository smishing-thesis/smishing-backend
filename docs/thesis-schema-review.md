# Contraste con la Memoria: modelo físico PostgreSQL

Revisión del 8 de noviembre de 2026 (Lima), a partir del Word proporcionado por
el equipo: **Memoria_Díaz_Valenzuela_ISW.docx**, sección «Diagrama físico»,
**Figura 6: Modelo físico de base de datos PostgreSQL**, y su explicación.
También se contrastaron las entidades del subsistema backend y RF-13/RF-14.
Los otros tres documentos se inspeccionaron para localizar ese modelo; la
especificación física concreta está en la Memoria. No se incorporan los Word,
sus imágenes, corpus ni ejemplos de SMS al repositorio.

## Diferencias encontradas y correcciones

Las relaciones esenciales y el hash único ya existían. Los identificadores
físicos, algunos tipos y la obligatoriedad de los metadatos no coincidían.
La migración **0005**, posterior a 0004, alinea el esquema sin recrear las tablas.

| Figura 6 | Antes de 0005 | Desde 0005 |
| --- | --- | --- |
| contributed_message | contributions | contributed_message |
| content_hash CHAR(64), único | VARCHAR(64), único | CHAR(64), único y hexadecimal |
| review_status VARCHAR(20) | status VARCHAR(16) | review_status VARCHAR(20) |
| message_label | labels | message_label |
| message_id, FK | contribution_id | message_id, FK a contributed_message |
| category VARCHAR(20) | value VARCHAR(16) | category VARCHAR(20) |
| source VARCHAR(20) | origin VARCHAR(16) | source VARCHAR(20) |
| model_version | model_versions | model_version |
| version_tag VARCHAR(20), único | version VARCHAR(64) | version_tag VARCHAR(20), único |
| generated_at TIMESTAMPTZ | trained_at, nullable | generated_at, obligatorio |
| training_set VARCHAR(100) | corpus_version VARCHAR(128), nullable | training_set VARCHAR(100), obligatorio |
| hyperparameters TEXT | JSONB, nullable | TEXT con JSON serializado, obligatorio |
| accuracy, precision_score, recall, f1_score NUMERIC(5,4) | dentro de metrics JSONB, nullable | columnas NUMERIC(5,4) obligatorias |

Se conservan UUID, texto, hash, fechas, etiquetas y claves foráneas. `received_at`,
`created_at` y `generated_at` usan zona horaria, como el diagrama. La versión de
modelo es obligatoria para la etiqueta automática y nula para la manual;
ambas pueden coexistir para el mismo aporte. El modelo no conoce al dispositivo.

Los nombres de objetos Python y las respuestas públicas pueden conservar
`contribution_id`, `status` u `origin`: son contratos internos/API, no nombres
físicos. SQLAlchemy los mapea a las columnas del Word. No hay vistas o tablas
duplicadas para aparentar correspondencia. Se conservan nombres antiguos de
restricciones e índices para mantener la traducción estable de duplicados.

## Extensiones necesarias y explícitas

La Figura 6 describe tres tablas de corpus. Se mantiene además `reviews`,
auditoría exigida por #13, y `alembic_version`, control técnico de migraciones.
`reviewed_at` y `review_reason` implementan la revisión registrada de #12.
El catálogo conserva huellas, URL, fecha de publicación y métricas agregadas
JSONB como procedencia adicional de #15; las cuatro métricas de la figura se
materializan a cuatro decimales desde esos agregados. No se recalculan métricas
ni se ejecuta inferencia. El JSON agregado conserva su precisión original.

Estas extensiones están documentadas; no se afirma que aparezcan en la Figura 6.
Las señales de #14 pertenecen a una migración adicional 0006, en PR #41,
separada de la corrección física 0005. risk_flags es otra extensión explícita,
sin campos de persona/dispositivo.

## Catálogo completo antes de recibir aportes

El Word no permite fichas de modelo sin fecha o métricas. La API deja de crear
referencias incompletas a partir de una versión declarada por Android. Primero
un operador registra la publicación real:

```sh
uv run --locked alembic upgrade head
uv run --locked python -m smishing_backend.catalog --release v1.0.0
```

Después puede recibir aportes para `1.0.0`. Versión no registrada: 422 genérico,
sin texto ni versión en el error y sin filas parciales. No se consulta GitHub
al recibir cada aporte. La publicación v1.0.0 es pre-release; registrarla no
certifica su calidad. Solo se importan metadatos agregados de la publicación.

El contrato público conserva `text`, `label`, `model_version`; el límite de
`model_version` pasa explícitamente de 64 a **20 caracteres** para coincidir con
`version_tag`. El snapshot OpenAPI se actualiza y compara en pruebas. Este cambio
necesita reflejarse en el cliente móvil. #4 registra la revisión estática de sus
datos y arquitectura y la adopción bajo autorización del responsable; no se
afirma una prueba Android ni un acuerdo individual realizado por terceros.

## Actualización de una base existente

Realizar backup verificado y detener ambos servicios antes de una actualización
operativa. La versión nueva del repositorio no puede atender tráfico con el
esquema antiguo, ni la versión antigua con el nuevo. No hay despliegue automático.

Si existen versiones incompletas, **0005 aborta antes de renombrar tablas**. No
rellena fechas, métricas o conjunto de entrenamiento con valores ficticios ni
recorta etiquetas de versión. Para una base anterior a 0005:

```sh
uv run --locked alembic upgrade 0004
uv run --locked python -m smishing_backend.catalog --release v1.0.0 --prepare-schema-0005
# Repetir para cada versión existente que tenga publicación real verificable.
uv run --locked alembic upgrade head
uv run --locked alembic check
```

El modo de preparación solo admite esquema 0004, conserva el UUID y es
idempotente. Si hay versiones sin publicación, datos demasiado largos o métricas
incompatibles, el operador debe resolver su procedencia; no se eliminan aportes
automáticamente. Nunca usar datos inventados para superar la migración.

La reversión `alembic downgrade 0004` restaura identificadores y JSONB anteriores;
se ensaya en bases aisladas. Un downgrade hasta base sí elimina tablas. Verificar
siempre un respaldo y la compatibilidad del código antes de revertir en operación.

## Evidencia

**162 pruebas y dos subtests**, PostgreSQL 17 real, Python 3.12. Ruff, formato y
mypy correctos. `tests/test_thesis_schema.py` verifica nombres físicos, tipos,
NOT NULL, PK, FK, unicidad, conservación de datos existentes en ambos sentidos,
trigger de estados terminales después de cada cambio, rechazo seguro de catálogo
incompleto y preparación explícita sin cambiar UUID. Alembic no detecta drift.

También se ejecutó un flujo con dos servidores Uvicorn HTTPS y certificado
verificado: registro previo de metadatos reales v1.0.0, cuatro SMS sintéticos,
revisión privada, dos aceptados exportados, lector real del modelo y segunda
exportación idéntica. Se ensayó upgrade/downgrade/upgrade sobre un esquema
temporal eliminado al terminar. [Resultado](evidence/thesis-schema-flow-2026-11-08.json).
No se usó corpus real, no se reentrenó y no se desplegó.
