# Contrato v1 y revisión entre repositorios — #4

Estado: contrato adoptado bajo la autorización del responsable del proyecto
para completar las tareas y su indicación de seguir la Memoria. Esta revisión
la realizó el agente sobre el documento y el código disponible; no se atribuye
una reunión o aprobación individual a otros integrantes. La implementación del
cliente de envío Android es trabajo separado: no se presenta como terminada.

## Qué exige la Memoria y qué se concreta técnicamente

Fuente: Memoria_Díaz_Valenzuela_ISW.docx, entidades del subsistema backend,
relaciones, compartición optativa y Figura 6 del modelo físico PostgreSQL.

| Fuente del requisito | Decisión del contrato |
| --- | --- |
| Aporte voluntario y previamente anonimizado | Android comprueba consentimiento y anonimiza antes de enviar text |
| Mensaje aportado y etiqueta automática asociada a una versión | text, label y model_version obligatorios |
| No identificar al contribuyente/dispositivo | Sin remitente, teléfono, ID, cuenta, IP, fecha original o telemetría en el cuerpo |
| Inferencia local independiente de la compartición | El backend no clasifica; recibe la etiqueta ya producida por Android |
| version_tag VARCHAR(20), Figura 6 | model_version tiene máximo 20 caracteres |
| TEXT y categoría sin especificación HTTP detallada en el Word | Se eligen 1–2048 puntos Unicode para text y safe/smishing para label |
| Recepción segura y control de abuso | Se concretan HTTPS, ruta /api/v1/contributions, JSON UTF-8 y máximo 16384 bytes |

El Word no prescribe literalmente el límite 2048, los nombres del JSON, la
ruta HTTP ni el mecanismo API key. Son decisiones técnicas del backend, tomadas
en el alcance delegado y documentadas como tales. La elección de API key
compartida y rotable ya se registró en #6, con sus limitaciones conocidas.
Los códigos de respuesta y el versionado corresponden también a los criterios
de #4; no se atribuyen como citas del Word.

## Revisión con el código de smishing-mobile-app

Revisión estática del main
`08af26a775357b96a74ab36dedef05e03b3b7517`:

- `.claude/architecture.md`: la compartición comprueba consentimiento, anonimiza
  y usa el servicio de corpus por HTTPS; no interrumpe la inferencia local.
- `domain/classification/ClassificationResult.kt`: el resultado Classified
  contiene isSmishing: Boolean y modelVersion: String, además de score y
  preprocessingVersion, que no se incorporan al cuerpo de aportes.
- `domain/classification/ModelInfo.kt`: conserva version y decide localmente
  con el umbral del modelo. El backend no recalcula esa decisión.

Mapeo definido para el futuro cliente: texto anonimizado → text;
isSmishing=true → label=smishing, false → label=safe; modelVersion →
model_version. NotClassified no debe convertirse artificialmente en una etiqueta
safe: no aporta una clasificación válida para este contrato.

No se encontró un cliente de aportes HTTP en el código Kotlin revisado. Eso
impide afirmar una prueba Android extremo a extremo, pero no impide definir y
revisar su contrato. Esta inspección técnica entre repositorios, el contraste
con el Word y la adopción por el responsable del proyecto constituyen la revisión
registrada de #4. La prueba de integración móvil se ejecutará al implementar el
cliente, sin mantener esta definición de contrato bloqueada por ese desarrollo.

## Solicitud, respuestas y reintentos

POST /api/v1/contributions, HTTPS, X-API-Key y application/json UTF-8.
Solo text, label y model_version; campos extra y valores de tipo incorrecto se
rechazan. Normalización NFC, controles y espacios antes de validar y calcular
el hash. Texto 1–2048 puntos Unicode; versión semántica hasta 20 caracteres;
cuerpo máximo 16384 bytes. No confundir este límite con la entrada del modelo.

Antes de admitir una versión, el operador registra sus metadatos publicados en
el catálogo. Una versión desconocida da 422 sin crear referencias incompletas.
Esto respeta la obligatoriedad del catálogo de la Figura 6.

- 201: UUID del aporte y pending; recepción completada.
- 400: tipo de contenido, JSON, UTF-8 o transporte inválido; corregir petición.
- 401: credencial ausente/inválida; no reintentar indefinidamente con la misma.
- 409: duplicado; no insistir ni inferir el estado de revisión del existente.
- 413: cuerpo demasiado grande; reducirlo antes de reintentar.
- 422: campos/texto/versión inválidos; corregir antes de reintentar.
- 429: respetar Retry-After en segundos.
- 503: indisponibilidad temporal; el cliente debe usar reintentos limitados con
  espera y no afectar la clasificación local.

Formato: {"error":{"code":"código estable","message":"mensaje genérico"}}.
No contiene texto ni valores rechazados. La API key extraíble de Android no
prueba procedencia oficial ni identifica a un dispositivo; ver authentication.md.

## Verificación de la especificación

`docs/openapi-v1.json` se genera con contract_app(). Los modelos y metadatos se
usan en la ruta real; tests/test_contract.py compara todo el snapshot, campos
permitidos y códigos. test_runtime_schema_matches_contract compara además
OpenAPI de la aplicación funcional con el contrato, incluidos sus esquemas.

Revalidación local: ambas pruebas pasaron. No cambió el contrato ni el runtime
con este documento; se registra la revisión y se elimina un bloqueo de aprobación
adicional que no era exigido por la historia. La CI completa del repositorio
continúa comprobando contrato, validación y persistencia con SMS sintéticos.

## Lote de aportes — #48

Decisión técnica del backend, tomada tras leer docs/contrato-con-el-backend.md de
smishing-mobile-app (#72). La Memoria no fija la forma HTTP del envío ni dice
nada sobre lotes: describe un aporte por mensaje analizado, con autenticación,
validación, verificación de anonimización, deduplicación y cuarentena en el
backend. El lote conserva esa cadena de filtros aporte por aporte. No es una
cita del Word. Nadie consume todavía el contrato v1, por lo que el cambio es
aditivo; la versión del contrato pasa a 1.1.0.

POST /api/v1/contributions/batch, HTTPS, X-API-Key, application/json UTF-8:

    {"contributions": [{"text": "...", "label": "smishing", "model_version": "1.0.0"}]}

De 1 a 20 aportes (maxItems en el OpenAPI; la app debe leerlo de ahí) y 327680
bytes de cuerpo. Respuesta 200 con un resultado por aporte, en el mismo orden:

    {"results": [{"index": 0, "status": "accepted"},
                 {"index": 1, "status": "duplicate"},
                 {"index": 2, "status": "rejected", "reason": "not_anonymized"}]}

- accepted: guardado como pending. La respuesta no incluye ids.
- duplicate: ese contenido ya existe (o se repitió en el lote). No revela su
  estado de revisión; es lo mismo que el 409 del aporte único. La app lo saca de
  la cola. Reenviar un lote es seguro: lo ya guardado vuelve como duplicate.
- rejected con reason not_anonymized, unknown_model_version o
  invalid_contribution: la app lo descarta y no lo reintenta. El motivo nunca
  repite el texto ni el valor recibido.
- Atomicidad por aporte. Un fallo de almacenamiento da 503 para todo el lote y
  deja guardados los aportes anteriores; al reintentar vuelven como duplicate.
- Errores del lote entero, con el mismo formato genérico: 400 (transporte, JSON,
  UTF-8), 401, 413, 422 (sobre mal formado o fuera de 1 a 20), 429 con
  Retry-After y 503. No existe 409: el duplicado se informa por aporte.
- Cuota: cuenta aportes, no solicitudes (ver rate-limit.md). La app asumía que un
  lote contaba como una solicitud; con ese criterio un par de red podría enviar
  1200 aportes por minuto, el doble del límite global.

Decisiones sobre lo que pedía la app:

- anonymization_version no se acepta en v1. El backend reverifica cada aporte con
  sus propias reglas, la Memoria no define el campo y guardarlo exigiría una
  migración sin que ninguna lógica lo use. Con campos extra prohibidos, la app
  no debe enviarlo. Si más adelante hace falta, se añade acordándolo con la app.
- El máximo de 20 es fijo en v1, no configurable por entorno, para que el
  OpenAPI sea la única fuente que lee la app.
- Aportes safe: el backend sigue aceptando safe y smishing. Que la app solo envíe
  riesgo alto (siempre smishing) es decisión de la app y de la tesis. Un corpus
  solo con positivos que el modelo ya marcó no permite construir el conjunto de
  prueba confiable que la Memoria exige para distinguir etiquetas automáticas de
  verificadas; conviene decidirlo antes de implementar el cliente.
- 401: ya es inequívoco (código unauthorized). La app debe dejar de reintentar.
  Rotación: el backend admite varias claves a la vez; ver authentication.md. La
  distribución entre versiones de la app sigue pendiente de acuerdo operativo.

Verificación: tests/test_batch_validation.py (sin base de datos) y
tests/test_batch_api.py (PostgreSQL real) con mensajes sintéticos. El snapshot
docs/openapi-v1.json y el OpenAPI de la aplicación funcional se comparan en
ambas rutas. No hay prueba con el cliente Android, que aún no existe.
