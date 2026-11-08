# Hito #15: origen de etiquetas y catálogo del modelo

Un aporte conserva sus etiquetas automáticas (`origin=device`) y manuales
(`origin=manual`) por separado. PostgreSQL exige versión de modelo para las
automáticas y prohíbe esa referencia en las manuales. La API pública sigue
recibiendo únicamente texto, etiqueta y versión: no acepta origen ni identidad
del revisor. Esta historia no añade una ruta pública de revisión.

`PostgresLabelRepository.verified(id)` consulta solo etiquetas manuales.
La consulta interna de entrenamiento devuelve una fila por aporte aceptado,
priorizando la última etiqueta manual y, si no existe, la automática. Fecha e
ID desempatan de forma estable. Se conservan las etiquetas anteriores. La
autorización y registro del revisor se implementan separadamente en #13.

## Catálogo desde la publicación real

El operador usa el CLI de GitHub (`gh`) con acceso de lectura al repositorio
del modelo. Las credenciales se configuran fuera del código. Ejecutar:

```sh
uv run --locked alembic upgrade head
uv run --locked python -m smishing_backend.catalog --release v1.0.0
```

El comando consulta únicamente `smishing-thesis/charcnn-smishing-model` y los
assets `training_metadata.json` y `evaluation.json` de esa publicación. No
descarga modelos, corpus, vectores de mensajes ni ejecuta inferencia. Importa:

- versión, fecha de entrenamiento y fecha de publicación;
- versión y huella SHA-256 del conjunto de datos;
- los catorce hiperparámetros de la receta publicada;
- métricas agregadas de validación/evaluación y umbral;
- etiqueta y URL de publicación, con una huella del contenido importado.

No persiste `dataset_path`, historial de entrenamiento ni `robustness_suite`,
que puede contener mensajes; tampoco almacena campos desconocidos. Las fechas
requieren zona horaria y los metadatos deben coincidir en versión y huella del
modelo. Valores ausentes, inconsistentes o no finitos se rechazan sin imprimir
el contenido de los archivos ni errores del cliente con credenciales.

La publicación actual `v1.0.0` está marcada como **pre-release** en GitHub;
registrarla no significa aprobar su uso ni validar la calidad del modelo.
Los datos son los declarados por la publicación, no métricas recalculadas aquí.

Registrar dos veces los mismos hechos reutiliza la misma fila. Si ya se
registraron hechos distintos para esa versión, se rechaza el reemplazo.
La operación es transaccional y está protegida bajo concurrencia.

Para mantener compatibilidad, una versión enviada por Android puede crear
solo una referencia (`metadata_sha256 IS NULL`). No se presenta como publicación
verificada: el comando del operador completa los metadatos desde GitHub sobre
el mismo UUID. Recibir un aporte nunca descarga información de GitHub.

## Migración y verificación

0003 conserva las etiquetas anteriores con versión como automáticas. Si hay
etiquetas antiguas sin versión, aborta y revierte la migración: el equipo debe
aclarar su origen. No se inventan etiquetas manuales ni revisiones. Downgrade
retira la información añadida; ensayarlo solo en una base dedicada de prueba.

Verificado el 8 de noviembre de 2026 en Cloud, PostgreSQL 17 real:

```sh
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked mypy
# SMISHING_TEST_DATABASE_URL apunta a una base aislada terminada en _test
uv run --locked pytest -q
```

Resultado: **130 pruebas pasaron**, sin omisiones; Ruff y tipos correctos.
Incluye coexistencia de etiquetas, restricciones de origen/versión, selección
de manuales, preferencia para entrenamiento, migración con datos legados,
registro concurrente/idempotente y rechazo de metadatos inconsistentes.
Las pruebas usan exclusivamente datos sintéticos. El CLI además se ejecutó
dos veces contra los assets reales publicados de v1.0.0, sin copiar SMS ni
archivos de publicación al repositorio, sobre una base de prueba; ambos
registros fueron correctos y `alembic check` no encontró diferencias.

Revalidado sobre main después de integrar #34: 130 pruebas y dos subtests,
con importación real de v1.0.0 repetida sobre un esquema temporal nuevo.
[Resultado de la importación](evidence/catalog-2026-11-08.json).
El PR #38 tiene base main y contiene solo #15. No se ha desplegado.
