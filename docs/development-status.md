# Estado verificable de las ramas

Sesión Cloud del 2 de noviembre de 2026, Lima. No se ha integrado ningún PR
en main ni se ha desplegado. main permanece en 1438bbc56ec979c99e7b71f49167bddf4700714a.
El entorno incluye backend, app móvil, modelo y anonimizador. Solo se modificó
smishing-backend. Se recuperó #3 sin rehacer su commit: SHA exacto 9fa087a,
árbol y blobs verificados contra GitHub. Inicialmente el ejecutor no tenía acceso
de red habilitado; con la capacidad de red normal funcionan Git y la API por
conector. El 403 actual corresponde exclusivamente a permisos administrativos
de protección de ramas; el tablero Project devuelve 404. Se leyeron los textos
completos de las trece historias mediante la API.

## Trazabilidad

| Historia | Rama | Commit del bloque | PR | Base del PR | Pruebas al terminar el bloque |
| --- | --- | --- | --- | --- | --- |
| #3 | feat/3-fastapi-foundation | 9fa087a | [22](https://github.com/smishing-thesis/smishing-backend/pull/22) | main | 3 |
| #4 | feat/4-contribution-contract | adbb03d | [23](https://github.com/smishing-thesis/smishing-backend/pull/23) | feat/3-fastapi-foundation | 4 |
| #5 | feat/5-contribution-validation | cecbd8d | [24](https://github.com/smishing-thesis/smishing-backend/pull/24) | feat/4-contribution-contract | 38 |
| #8 | feat/8-postgres-migrations | e9654da | [25](https://github.com/smishing-thesis/smishing-backend/pull/25) | feat/3-fastapi-foundation | 11 en esta rama |
| #9 | feat/9-postgres-repositories | eb14a36 | [26](https://github.com/smishing-thesis/smishing-backend/pull/26) | feat/8-postgres-migrations | 15 en esta rama |
| #6 | feat/6-app-authentication | d3f77a5 | [27](https://github.com/smishing-thesis/smishing-backend/pull/27) | feat/5-contribution-validation | 45 |
| #7 | feat/7-contribution-rate-limit | 43086c1 | [28](https://github.com/smishing-thesis/smishing-backend/pull/28) | feat/6-app-authentication | 49 |
| #1 | feat/1-contribution-api | 7722b38 | [29](https://github.com/smishing-thesis/smishing-backend/pull/29) | integration/1-prerequisites | 65 |
| #10 | feat/10-content-deduplication | 19875df | [30](https://github.com/smishing-thesis/smishing-backend/pull/30) | feat/1-contribution-api | 75 |
| #11 | feat/11-anonymization-verification | af47e04 | [31](https://github.com/smishing-thesis/smishing-backend/pull/31) | feat/10-content-deduplication | 94 suite; 20 específicas tras caso adicional |
| #12 | feat/12-contribution-quarantine | b4daccc | [32](https://github.com/smishing-thesis/smishing-backend/pull/32) | feat/11-anonymization-verification | 104 |
| #17 | feat/17-private-logging | 44c62ef | [33](https://github.com/smishing-thesis/smishing-backend/pull/33) | feat/12-contribution-quarantine | 106 |
| #18 | feat/18-backend-ci | 4ace4ca y 0c9c619; documentación posterior | [34](https://github.com/smishing-thesis/smishing-backend/pull/34) | feat/17-private-logging | 106, tipos y formato |

integration/1-prerequisites (8ca11d6) combina únicamente las ramas de trabajo de
#7 y #9 con autorización explícita del usuario. El primer intento fue rechazado
por auto-review debido a la prohibición de merge; no se ejecutó hasta recibir
esa autorización. No modifica main. Esta base permite que #1 muestre solo su
integración; los demás PR muestran exclusivamente su historia. Cuando el equipo
integre las bases, retarget a main y verificar que no aparezcan cambios ajenos.
No limpiar por force-push ni duplicar commits mientras haya revisión en curso.

## Validación final local

Con SMISHING_TEST_DATABASE_URL apuntando a PostgreSQL 17 efímero:

```sh
uv sync --locked --group dev
uv run --locked pytest -q
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked mypy
```

Resultados: 106 pruebas pasaron, cero omitidas; Ruff y formato correctos;
mypy sin errores en 25 archivos. Una advertencia de deprecación Starlette/httpx
permanece; no es fallo de prueba. Se ejecutó además upgrade → check → downgrade
→ upgrade por CLI sobre base dedicada, sin diferencias de metadatos. El wheel
construido incluye el recurso JSON de reglas versionadas. Prueba TLS real local
con verificación de certificado, no solo simulación de scheme HTTPS.
Las pruebas cubren restricciones, rollback, concurrencia de hashes/versiones y
revisiones, rechazo sin persistencia, privacidad de errores/logs y expiración.
No se usó corpus real ni se agregaron secretos reales.

## Pendientes que impiden declarar todo terminado

- #4: acuerdo con el equipo móvil sobre campos, etiquetas, límites y autenticación.
  Se revisaron documentos de la app en e69abbc, no se afirma revisión humana.
- #6: acuerdo operativo de distribución y rotación; una clave compartida Android
  es extraíble y no prueba procedencia oficial. No hay atestación implementada.
- #1: revisión conjunta del flujo y dependencias antes de recepción pública.
- #7: cuota por proceso; múltiples workers requieren contador compartido con TTL.
- #17: inspección de respaldos reales y retención de consola en infraestructura.
- #18: exigir backend-verify en protección/ruleset de main; lectura denegada 403.
- Todos los PR siguen abiertos para revisión. Las cláusulas Closes solo se usaron
  en historias con criterios técnicos probados; no se cerraron issues manualmente.

Las funciones públicas de revisión, exportación y despliegue no se implementaron
ni se simularon. El puerto interno de #12 solo aporta las reglas de cuarentena.
Las ejecuciones reales de Actions y sus resultados están en [ci.md](ci.md).
