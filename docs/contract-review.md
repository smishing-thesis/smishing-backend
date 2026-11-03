# Propuesta del contrato v1 — #4

Estado: pendiente de acuerdo con el equipo móvil; no cierra #4.
El archivo openapi-v1.json se genera desde FastAPI con contract_app().
La propuesta se mantiene separada para detectar cambios del contrato. Desde #1,
la ruta real usa esos modelos y metadatos y una prueba compara su OpenAPI.
No se simula persistencia con respuestas 201. #1 añade 503 genérico por fallos
de infraestructura/detector; el snapshot refleja esta ampliación explícita.

Revisión estática realizada el 2 de noviembre de 2026 (Lima): main de
smishing-mobile-app e69abbc15eaea2659bc1d9de6d269b000344d55f, README,
.claude/architecture.md y .claude/model-contract.md. No existe cliente Kotlin.
Su arquitectura exige consentimiento local, anonimización previa, HTTPS y
compartición independiente de inferencia. La propuesta respeta esas fronteras.
Esta inspección no constituye aceptación por el equipo móvil.

Propuesta concreta para confirmar: POST /api/v1/contributions con text, label
(safe o smishing) y model_version (versión numérica de tres componentes y
prerelease opcional; máximo 64 caracteres). La app mapea seguro/sospechoso a
esas etiquetas; no envía puntajes, remitentes, fechas del SMS, IDs o metadatos.
Texto: 1–2048 puntos Unicode después de NFC, eliminación de controles y
colapso de espacios; cuerpo: máximo 16384 bytes, application/json UTF-8.
El límite del corpus es independiente de la longitud de entrada del modelo.

201 devuelve UUID del aporte y pending. 400: JSON/tipo/codificación inválidos;
401: credencial; 409: contenido duplicado, sin estado de revisión; 413: cuerpo;
422: campos o texto inválidos; 429: cuota, con Retry-After en segundos.
Errores: {"error":{"code":"código estable","message":"mensaje genérico"}}.
Nunca contienen el texto ni los valores rechazados. La clave X-API-Key es una
propuesta rotable, no una garantía de procedencia de la app oficial (#6).

Pendiente: confirmar nombres de campos, etiquetas, límites, autenticación y
semántica de reintentos con el equipo móvil. No se han enviado mensajes al equipo.
