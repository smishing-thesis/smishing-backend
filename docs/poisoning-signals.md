# Hito #14: señales de posible envenenamiento

El servicio público usa `RiskAwareContributionRepository`: analiza únicamente
contenido ya anonimizado, etiquetas y fechas de recepción del servidor. No usa
direcciones de red, tokens de app, remitentes ni IDs de dispositivo para estas
señales. No predice smishing: esa inferencia continúa en Android.

## Señales implementadas

- `similarity_burst`: al menos cinco textos casi iguales en cinco minutos,
  contando el nuevo. Jaccard de conjuntos de trigramas de caracteres, con NFC,
  espacios normalizados y casefold; umbral inicial 0.9 y longitud mínima 30.
- `label_conflict`: el mismo contenido normalizado vuelve con una etiqueta
  automática distinta. El envío duplicado sigue recibiendo 409; solo se marca
  el aporte existente. No se guarda otro SMS, ni se reemplaza una etiqueta.
- `class_shift`: cambio absoluto de al menos 0.4 en la proporción de smishing
  entre la ventana reciente y la anterior. Requiere al menos 20 aportes de base
  y 10 recientes, contando el nuevo. Sin muestra suficiente no se inventa una
  estimación. Cuenta etiquetas automáticas, no la identidad de quien aporta.
- `evaluation_similarity`: similitud de trigramas >= 0.9 con referencias
  configuradas por el operador. No se descargan mensajes de evaluación.

Estos valores iniciales buscan detectar copias muy cercanas, evitar comparar
textos triviales y exigir muestra mínima para cambios de clases. Son propuestas
heurísticas documentadas, no umbrales calibrados para tráfico real. Pueden
marcar campañas legítimas, correcciones de otro modelo o avisos con plantilla;
tampoco cubren todos los ataques. Una marca no demuestra intención maliciosa.

## Configuración por entorno

Todas las variables llevan prefijo `SMISHING_`:

| Sufijo | Valor inicial |
| --- | --- |
| POISON_WINDOW_SECONDS | 300 |
| POISON_HISTORY_LIMIT | 500 (máximo 2000) |
| POISON_SIMILARITY_THRESHOLD | 0.9 |
| POISON_SIMILAR_COUNT | 5 |
| POISON_MIN_TEXT_LENGTH | 30 |
| POISON_MIN_BASELINE | 20 |
| POISON_MIN_RECENT | 10 |
| POISON_CLASS_DELTA | 0.4 |
| POISON_EVALUATION_THRESHOLD | 0.9 |
| POISON_EVALUATION_FINGERPRINTS_PATH | sin archivo por defecto |

El archivo de referencias tiene `format=char-ngrams-v1`, `n=3` y `references`,
una lista de conjuntos de SHA-256 de trigramas generados por
`smishing_backend.domain.poisoning.fingerprint`. Se limita a 2 MiB, cien
referencias y 2048 huellas por referencia. Se rechaza configuración inválida
sin mostrar el contenido. Usar un archivo fuera de Git con permisos de operador,
generado exclusivamente a partir de referencias ya anonimizadas y autorizadas.
Las huellas de trigramas **no son una garantía de anonimización** y no justifican
usar SMS personales como referencias.

Si no se configura archivo, no hay comparación con evaluación: las otras tres
señales sí funcionan. Antes de afirmar cobertura de una evaluación concreta,
el equipo debe proporcionar, versionar operativamente y revisar esas referencias.
Los tests usan solo referencias sintéticas; no equivalen a esa configuración.

## Marcado, revisión y entrenamiento

0005 crea `risk_flags` con tipo de señal, fecha y revisión posterior atribuida.
No incluye el cuerpo del duplicado, datos del remitente ni del contribuyente.
Solo hay una alerta no resuelta por aporte/tipo; al resolverse conserva el
histórico y permite una nueva alerta futura. No se divulgan señales al cliente:
una recepción nueva sigue devolviendo 201/pending y un duplicado 409 genérico.

Un snapshot acotado con bloqueo transaccional compartido en PostgreSQL serializa
ingreso y revisión, para que envíos simultáneos no eludan la cuenta de ráfagas.
Texto/etiquetas nuevos y marcas se guardan en la misma transacción. Si falla la
marca, no queda un aporte aceptado sin ella. La contradicción conocida se marca
antes de rechazar el duplicado y sin perder el bloqueo del snapshot.

La API **interna** de #13 añade:

- `GET /reviews/flagged`: lista aportes con alertas no revisadas.
- En la decisión inicial, `acknowledge_flags=true` confirma que el revisor
  examinó las señales; sin esa confirmación, una decisión de un marcado da 409.
- Si un aporte ya aceptado recibe después una señal, se excluye de entrenamiento
  y exportación hasta `POST /reviews/{id}/flags/acknowledge` con `confirm=true`.
  Esta confirmación registra revisor y fecha sin reescribir la decisión terminal
  ni su etiqueta. Un pendiente debe pasar por la revisión completa, no por ese
  atajo. La clave de app no permite ninguna de estas acciones.

La consulta de entrenamiento/exportación exige accepted **y ninguna alerta
pendiente**, incluso si alguien usa un puerto interno antiguo para cambiar
estado. Marcar no publica ni entrena nada automáticamente.

El bloqueo es global para esta revisión de corpus, no una solución de cuotas
distribuidas de #7. El snapshot de hasta 500 filas limita trabajo y memoria;
si una ráfaga llena ese cupo, puede faltar base para el detector de clases.
Evaluar latencia y volumen antes de un despliegue; no se prometen capacidades
de producción a partir de los tests pequeños.

## Verificación real del hito

PostgreSQL 17, suite completa: **154 pruebas pasaron**, sin omisiones; Ruff,
formato y mypy correctos. Se probaron las cuatro señales, conflicto posterior
a aceptación, bloqueo de exportación, confirmación atribuida, reaparición de
una alerta, concurrencia y rollback forzado. No se usaron SMS reales.

Falsos marcados: **0/20 controles sintéticos diversos y balanceados** con base
previa balanceada. El valor se registra como propiedad JUnit; es el resultado
de esos controles, no una estimación del desempeño sobre mensajes reales.

```sh
# Base PostgreSQL aislada configurada con SMISHING_TEST_DATABASE_URL
uv run --locked pytest -q -o junit_family=xunit1 --junitxml=/tmp/smishing-tests.xml
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked mypy
```

Pendiente de revisión del equipo, calibración y referencias operativas antes de
recepción pública. El PR se apila sobre #16, #13 y #15. No se declara Done ni
se hace despliegue por disponer de implementación y tests.
