# Hito #13: revisión manual protegida

La revisión es una **segunda aplicación**, `smishing_backend.review:app`.
El runner local conserva sus rutas. La misma revisión terminal también está en
la API principal por `PATCH /api/v1/admin/contributions/{contribution_id}/review`,
con Bearer de administración y fuera del contrato del cliente Android. El servicio de revisión escucha solo en loopback
por defecto; una futura publicación necesita acceso privado y controles de red.
No se ha hecho despliegue ni se ha expuesto este servicio en Internet.

## Identidad y autorización

Configurar `SMISHING_REVIEW_CREDENTIALS` como objeto JSON de identificadores
internos de revisor a secretos distintos de las claves de Android. Usar IDs
estables y seudónimos, de 1 a 64 caracteres `a-z`, números, guion o guion bajo.
La relación con cada revisor se mantiene en la configuración operativa privada,
sin introducir nombres de contribuyentes o dispositivos en la base.

Cada revisor usa `Authorization: Bearer <su credencial>`. No se acepta
`X-API-Key` de la app. Tampoco se acepta su valor como Bearer. La configuración
rechaza claves compartidas entre app/revisión, IDs inválidos y claves de
revisor repetidas. Sin revisores configurados, todo acceso a `/reviews` da 401.
El ID registrado se deriva del secreto validado en servidor; el cuerpo no
puede elegir quién revisó. Las credenciales se comparan sin interpolarlas ni
registrarlas, y se exige HTTPS antes de leer el cuerpo o llamar al repositorio.

La revisión requiere acceso humano autorizado, no demuestra por sí sola que
una decisión sea correcta. Para rotar, actualizar el gestor de secretos y
reiniciar el proceso de revisión. No usar valores de las pruebas en producción.

## Arranque y uso local

Con base, credenciales y certificados configurados por entorno:

```sh
uv run --locked alembic upgrade head
uv run --locked python -m smishing_backend.review_server
```

TLS_CERT_PATH/TLS_KEY_PATH apuntan a archivos fuera de Git, igual que para el
servidor público. El puerto de revisión es 8444; SMISHING_REVIEW_PORT permite
cambiarlo. Swagger interno: https://127.0.0.1:8444/docs. En Authorize se introduce
la credencial de revisor, no la clave de Android. El contrato público original
permanece en el otro servicio/puerto.

- `GET /reviews/pending?limit=50`: lista hasta 100 pendientes, primero los más
  antiguos. Al revisarlos desaparecen de la lista, permitiendo procesar el lote
  siguiente sin saltar registros por desplazamiento.
- `POST /reviews/{id}`: decide `accepted` o `rejected`, un motivo permitido
  (`quality_checked`, `invalid_content`, `out_of_scope`) y etiqueta final
  (`safe`, `smishing`). Esto permite corregir la etiqueta de Android al revisar.

No se envía el texto del SMS ni el ID del revisor en el cuerpo. Campos extra se
rechazan con error genérico sin eco del valor. El cuerpo se limita a 2048 bytes,
incluidos envíos sin Content-Length. Las decisiones registradas son terminales
según #12: repetir o cambiar una decisión devuelve 409. No existe reapertura
ni edición silenciosa de un registro aceptado.

## Registro y transacción

La migración 0004 añade `reviews`: revisor, decisión, motivo, fecha y referencia
a la etiqueta manual del mismo aporte. Una clave foránea compuesta impide que
la revisión apunte a la etiqueta automática o a otra contribución.

En una sola transacción se cambia el estado pendiente, se añade la etiqueta
manual y se registra la revisión. Si falla el registro de auditoría, se revierten
las tres operaciones. Dos revisores concurrentes producen una sola revisión;
el otro recibe 409. La etiqueta automática permanece para trazabilidad.

Las filas terminales anteriores a #13 conservan su fecha/motivo de #12; no se
fabrican identidades históricas. Antes de atribuir revisiones anteriores, el
equipo debe reconciliarlas. Las nuevas decisiones hechas por esta API siempre
incluyen el ID autorizado. Los puertos internos antiguos no se publican.

## Verificación

PostgreSQL 17 real, suite local: **145 pruebas pasaron**, sin omisiones; Ruff,
formato y mypy correctos. Se verifica acceso con clave de app, revisor y sin
credencial; 401 aun con cuerpo inválido, separación del contrato público,
corrección/conservación de etiquetas, fecha/revisor, concurrencia, rollback
forzado al fallar auditoría y restricciones directas. Solo datos sintéticos.
Reproducir con los comandos del README y SMISHING_TEST_DATABASE_URL en una base
dedicada terminada en `_test`.

Revalidado con la base actualizada de #15 y main: 145 pruebas y dos subtests.
Además, un ensayo con dos servidores Uvicorn y certificados verificados comprobó
la recepción pública y la revisión privada contra PostgreSQL real: acceso de
app y sin credencial rechazado, dos aceptados, un rechazado y un pendiente.
La corrección de etiqueta mantuvo la automática y registró la manual junto
al revisor y la fecha. Solo SMS sintéticos; sin despliegue.
El PR #39 depende de #15; al integrarla se cambia su base a main.
