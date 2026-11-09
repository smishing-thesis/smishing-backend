# Repositorios — #9

El dominio define ContributionRepository, entidades inmutables y el caso de uso
receive_contribution. No importa FastAPI ni SQLAlchemy. La capa de datos
implementa el puerto con PostgresContributionRepository y una conexión
configurable mediante create_database_engine(Settings().database_url).
No se abre conexión al importar módulos.

Una transacción guarda el aporte y sus etiquetas, reutilizando una versión
previamente registrada por el operador desde la publicación real del modelo.
Una versión desconocida se traduce a 422 y revierte todo el aporte. El catálogo
se registra por separado de forma idempotente con ON CONFLICT DO NOTHING.
El contexto begin revierte todo si falla una etiqueta. Los parámetros SQL quedan
ocultos y echo está desactivado. El conflicto del hash único se traduce a 409.
[Correspondencia física con la Memoria](thesis-schema-review.md).

Verificación: PostgreSQL 17 real, persistencia y referencias, versión opcional,
reutilización de versión concurrente y rollback del aporte/etiquetas, conservando el catálogo previo
cuando la segunda etiqueta viola la restricción. Prueba de frontera de imports.
Comando: SMISHING_TEST_DATABASE_URL configurada, `uv run pytest -q`.
