# Repositorios — #9

El dominio define ContributionRepository, entidades inmutables y el caso de uso
receive_contribution. No importa FastAPI ni SQLAlchemy. La capa de datos
implementa el puerto con PostgresContributionRepository y una conexión
configurable mediante create_database_engine(Settings().database_url).
No se abre conexión al importar módulos.

Una transacción guarda aporte, versiones nuevas y todas las etiquetas.
La versión se reutiliza con ON CONFLICT DO NOTHING y consulta posterior,
también con aportes concurrentes. El contexto begin revierte todo si falla
una etiqueta. Los parámetros SQL quedan ocultos y echo está desactivado.
La traducción del conflicto de hash a error de dominio/409 corresponde a #10.

Verificación: PostgreSQL 17 real, persistencia y referencias, versión opcional,
reutilización de versión concurrente y rollback del aporte/etiquetas/versiones
cuando la segunda etiqueta viola la restricción. Prueba de frontera de imports.
Comando: SMISHING_TEST_DATABASE_URL configurada, `uv run pytest -q`.
