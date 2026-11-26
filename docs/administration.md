# Administración de las entidades del corpus — #46

La aplicación local de #46 sigue disponible en el puerto 8445. La API principal
(`smishing_backend.main:app`) también incluye el listado, borrado individual y
revisión de aportes, en la etiqueta «Administración de aportes» de su mismo
Swagger. Android usa las rutas de recepción de su contrato versionado.
Las rutas de gestión exigen HTTPS y Bearer de administración, distinto de todas
las claves Android y de revisión. Sin administradores configurados responden 401.

| Método | Ruta de la API principal | Uso |
| --- | --- | --- |
| GET | `/api/v1/admin/contributions` | Listar y filtrar |
| DELETE | `/api/v1/admin/contributions/{contribution_id}` | Borrado individual con cascada |
| PATCH | `/api/v1/admin/contributions/{contribution_id}/review` | Registrar una revisión terminal |

El prefijo administrativo conserva exactamente la ruta y el OpenAPI móvil,
incluyendo el envío por lote. La respuesta de gestión lleva
`Cache-Control: no-store`. Las cuotas por proceso de gestión autorizada (30/min)
y fallida (20/min) son independientes entre sí y de la ingesta.
Ajustes: `SMISHING_ADMIN_REQUESTS_PER_MINUTE` y
`SMISHING_ADMIN_FAILED_REQUESTS_PER_MINUTE`. Tras agotar cuota se devuelve 429 con
`Retry-After`. No se guardan credenciales, identificadores de red ni URLs en el
limitador. Detrás de Azure las solicitudes fallidas comparten una cuota global.

Filtros combinables: `status`, `received_from`, `received_to`, `reviewed_from`,
`reviewed_to`, `category`, `source`, `model_version`, `reason`, `has_risk`.
Las fechas son ISO 8601 con zona horaria y los límites son inclusivos.
`category` y `source` corresponden a la etiqueta vigente (manual más reciente
si existe, o automática). `model_version` proviene de la etiqueta automática
de origen, incluso si la etiqueta vigente es manual. `has_risk=true` selecciona
alertas aún sin revisar. `order=desc` por defecto, `asc` para invertir.
El orden usa recepción y UUID en la misma dirección. `limit=50` admite 1–100
y `offset=0` admite hasta 1 000 000. Filtros no admitidos, incluidos los de
texto, producen un 422 genérico. Un filtro sin coincidencias devuelve [].

En PATCH envía `decision`, `reason`, `label` y, si corresponde,
`acknowledge_flags: true`. Ejemplo: `{"decision":"accepted","reason":"quality_checked","label":"smishing"}`.
El actor se deriva del Bearer. Solo se modifica un aporte pendiente y se conserva
su etiqueta automática. Repetir la revisión, o intentar decidir con alertas
pendientes sin confirmarlas, devuelve 409. Borrar usa las mismas relaciones y
restricciones de #46. No hay borrado masivo.

Para grabar en local, usar PostgreSQL de prueba con migraciones y la versión
`1.0.0` registrada, y configurar `SMISHING_ADMIN_CREDENTIALS` como objeto JSON
que mapea un ID de operador a un secreto local de prueba. En el runner público
`python -m smishing_backend.server`, definir `TLS_CERT_PATH` y `TLS_KEY_PATH`,
usar el certificado local de confianza y abrir `https://127.0.0.1:8443/docs`.
Crear aportes sintéticos con la API key de prueba, autorizar Bearer de gestión,
filtrar por pendientes, revisar uno, repetir para mostrar 409 y borrar otro por ID.
No mostrar los valores de credenciales en la grabación.

La [ejecución de QA en GitHub Actions](https://github.com/smishing-thesis/smishing-backend/actions/runs/45766473712) levantó Uvicorn HTTPS con PostgreSQL 17 sintético y abrió Swagger en Chromium. Comprobó 401 sin Bearer, listado y revisión 200 y borrado 204. Las peticiones del flujo se hicieron con un cliente HTTPS que validó el certificado local. Queda verificar la publicación en Azure.

## Métodos de la aplicación local de #46

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
explícita; no deshace archivos exportados o respaldos previos. Proteger las credenciales y limitar la red del runner local. Las rutas de la API principal usan el Bearer documentado arriba.
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

## Revisar aportes en Excel — #55

En «Excel de revisión» del Swagger principal, usa
`GET /api/v1/admin/exports/contributions.xlsx` para descargar una página con
los mismos filtros y orden del listado. `limit` permite hasta 500 filas y
`offset` permite continuar. Usa `POST /api/v1/admin/exports/reviews.xlsx`
con un único archivo multipart en el campo `file` para aplicar las revisiones.

La hoja «Aportes» contiene UUID, fecha de recepción, estado, texto, huella,
etiqueta automática, versión del modelo y señales vigentes. Edita solo
`decision`, `label`, `reason` y `acknowledge_flags`. En la hoja
«Instrucciones» están los valores válidos. Una fila con alertas requiere
`true`. El importador no escribe el texto del archivo. Verifica UUID, huella
y versión bajo el bloqueo de la transacción de revisión. Una fila sin
decisión o con una revisión previa es `skipped`; otra inválida es `rejected`.
Las válidas son `applied`; la respuesta contiene solo número de fila y motivo
genérico. Reimportar una hoja aplicada conserva las revisiones originales.

Límites iniciales: 500 filas, 512 KiB por archivo, 528 KiB en multipart,
128 entradas ZIP y 8 MiB de tamaño descomprimido. Si la exportación excede
el tamaño del archivo, reduce `limit`. No se procesan formatos con macros,
vínculos externos ni celdas de fórmula como datos. Las cadenas que empiezan con
`=`, `+`, `-` o `@` se exportan como texto literal. La carga y descarga se
mantienen en memoria y usan los mismos controles HTTPS, Bearer y no-store.

Para el video, crea aportes sintéticos pendientes, descarga con
`status=pending`, rellena una fila con `accepted`, `smishing` y
`quality_checked`, y súbela por Swagger. Repite la carga para mostrar
`skipped`. No grabes el valor del Bearer. El build de Azure debe instalar el
`requirements.txt` actualizado antes de publicar estas rutas.

[Ensayo HTTPS e interfaz Swagger en Chromium](https://github.com/smishing-thesis/smishing-backend/actions/runs/45766506491): exportación 200, dos filas aplicadas y dos omitidas al reimportar. Datos sintéticos en PostgreSQL 17. Verificación Azure pendiente.
