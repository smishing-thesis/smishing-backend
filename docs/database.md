# PostgreSQL y migraciones — #8

PostgreSQL 17 de prueba real, sin corpus ni credenciales reales.
Estado físico: pending / accepted / rejected (pendiente / aceptado / rechazado).
Tablas: contributions, labels y model_versions. La versión en la etiqueta es
opcional para permitir otras fuentes futuras; la API v1 exige versión de modelo.
El hash es SHA-256 hexadecimal único. No hay tablas de personas o dispositivos.
Las fechas son de recepción del servidor, nunca fechas del SMS.

Configurar SMISHING_DATABASE_URL desde el entorno. No registrar su valor.
Ejecutar `uv run alembic upgrade head` y `uv run alembic downgrade base`.
Downgrade elimina el corpus: se ensaya exclusivamente en una base vacía de prueba.
Las migraciones no ejecutan create_all sobre metadatos mutables.

Pruebas locales, en una instancia dedicada con nombre terminado en _test:

```sh
export SMISHING_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55432/smishing_test
uv run pytest -q
```

El fixture crea un esquema aleatorio por prueba y solo elimina ese esquema.
Nunca usar la base de producción. Sin la variable se omiten explícitamente las
pruebas PostgreSQL; esa ejecución no verifica integración.

Verificado en Cloud el 2 de noviembre de 2026 (Lima), PostgreSQL 17 Docker
efímero: upgrade → downgrade → upgrade, comparación Alembic/metadatos sin diff,
unicidad, claves foráneas, versión opcional, estado, texto y formato de hash.
11 pruebas pasaron (8 de PostgreSQL y 3 de base FastAPI). Ruff correcto.
La retención/revisión pertenece a historias posteriores, no se simula aquí.
