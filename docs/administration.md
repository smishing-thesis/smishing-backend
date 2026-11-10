# Administración de las entidades del corpus — #46

Las tres entidades de Figura 6 tienen CRUD real en una aplicación interna
separada: `smishing_backend.admin:app`. Requiere credenciales administrativas
propias, distintas de Android y de revisión. No ofrece acceso anónimo al corpus.
La API pública de Android conserva POST /api/v1/contributions; GET y los cambios
se usan en el Swagger administrativo, no con la API key compartida de Android.

## Métodos

| Recurso | Colección | Elemento |
| --- | --- | --- |
| contributed_message | GET /api/v1/contributions, POST /api/v1/contributions | GET, PUT, PATCH, DELETE /api/v1/contributions/{identity} |
| message_label | GET /api/v1/message-labels, POST /api/v1/message-labels | GET, PUT, PATCH, DELETE /api/v1/message-labels/{identity} |
| model_version | GET /api/v1/model-versions, POST /api/v1/model-versions | GET, PUT, PATCH, DELETE /api/v1/model-versions/{identity} |

GET admite limit (1–100) y offset (>=0), orden estable por UUID. Sin resultados
responde lista vacía. UUID inexistente devuelve 404; conflictos de unicidad,
referencias y reglas de revisión devuelven 409; entrada inválida 422; límite
16384 bytes 413; falta de credencial 401 antes de leer el cuerpo. HTTPS obligatorio.
Los errores no incluyen SMS, credenciales ni valores rechazados.

POST de aporte recibe text, label y model_version, como la recepción pública:
normaliza, comprueba anonimización/hash, exige modelo registrado y aplica señales.
Se guarda aporte y etiqueta en una transacción. PUT/PATCH de aporte acepta text;
los demás campos del recurso son relaciones o datos asignados por servidor.
El texto solo cambia en pending y vuelve a pasar los detectores de anonimización
y señales. PUT sustituye los campos editables completos; PATCH solo cambia los
campos enviados (para el aporte, el único editable es text).

POST/PUT de etiqueta recibe message_id, category (safe/smishing), source
(device/manual), model_version_id. PATCH admite category y model_version_id.
El origen y mensaje no se cambian silenciosamente. Manual exige versión nula;
automática exige una versión existente y solo hay una automática administrable
por aporte. Las modificaciones de categoría/modelo quedan marcadas para revisión.
Solo se administran etiquetas de pendientes; las revisiones terminales y su
atribución se preservan. No se borra la etiqueta automática ni la última etiqueta.
El control de estado continúa en la API de revisión, sin atajos de estado en CRUD.

POST/PUT/PATCH de versión recibe `{"release_tag":"v1.0.0"}`. Importa metadatos
agregados auténticos de la publicación de charcnn-smishing-model usando gh;
el servidor necesita acceso de lectura a ese repositorio y el CLI instalado.
No permite escribir métricas ficticias ni ejecuta inferencia. POST reutiliza
el registro idéntico de forma idempotente; sustituir otra publicación mediante
PUT/PATCH solo es posible si no hay etiquetas que usen el registro. DELETE de
una versión referenciada devuelve 409 y revierte la operación.

DELETE de aporte elimina físicamente ese aporte y sus relaciones en una
transacción, incluyendo revisión/marcas. Es una operación administrativa
explícita; no deshace archivos exportados o respaldos previos. Proteger las
credenciales y limitar la red de este servicio; no publicarlo como API Android.
No se crea una auditoría nueva de borrados ni se afirma que exista un historial
de modificaciones: la auditoría de revisión sigue en reviews y risk_flags.

## Base reutilizable

- domain/entity.py: Entity comparte UUID en SavedContribution y RegisteredReview.
- data/entity.py: EntityBase comparte PK y construcción de timestamps de las
  tablas sin añadir una tabla base ni duplicar columnas físicas.
- admin.py: EntityResponse comparte el UUID de las respuestas de las tres entidades.

received_at es recepción del servidor; created_at es creación de etiqueta;
generated_at procede de la publicación del modelo. No se sustituyen por un
mismo instante ni se permite que el cliente elija UUID/tiempos de auditoría.
El refactor no requiere migración: Alembic sigue sin drift respecto a 0006.

## Arranque local en Windows

Actualizar primero a la versión que contiene #46; feat/18-backend-ci antigua
no tiene este módulo. Configurar la misma base PostgreSQL y certificados que
el backend, con migraciones aplicadas según [la preparación existente](thesis-schema-review.md).
No saltarse la preparación del catálogo si la base estaba en 0002/0004.

En una terminal PowerShell nueva, definir también SMISHING_DATABASE_URL,
TLS_CERT_PATH y TLS_KEY_PATH con los valores locales ya usados. Luego, solo
para una demostración sintética (sustituir para operación):

```powershell
$env:SMISHING_ADMIN_CREDENTIALS = '{"admin-local":"clave-admin-solo-pruebas"}'
uv run --locked python -m smishing_backend.admin_server
```

Swagger: https://127.0.0.1:8445/docs. En Authorize introducir la credencial
administrativa (sin prefijar Bearer; Swagger lo añade). Las credenciales de
Android/revisión no habilitan este servicio. No cerrar la terminal mientras se usa.
El runner escucha solo en loopback, desactiva access logs/proxy headers y usa
logs privados con retención en un directorio separado.

## Verificación

Pruebas de CRUD positivo y negativo de los tres recursos con PostgreSQL 17 real:
credenciales antes del cuerpo en todos los métodos, HTTPS, límites, conflictos,
campos inmutables, referencias, cascadas y rollback. Se compara el esquema
físico y se ejecuta el contrato público anterior sin cambios. Un ensayo con
Uvicorn y certificado efímero verificado ejecuta POST/GET/PATCH/DELETE sobre HTTPS.
Los metadatos externos se sustituyen por fixtures sintéticos en CI para no
necesitar credenciales GitHub ni descargar corpus. El lector de publicaciones
real se mantiene como el ya probado por el catálogo.
