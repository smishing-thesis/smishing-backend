# Hitos del 8 de noviembre de 2026 (Lima)

## Estado contrastado

#3/#8/#9 se integraron inicialmente mediante #22/#25/#26; el lote funcional
posterior incorporó validación, autenticación, cuotas, recepción HTTPS,
duplicados, anonimización, cuarentena, logs privados y CI por PR independientes.
#21 consolidó documentación mediante #42. No se ha desplegado.

| Historia | PR y estado | Verificación registrada |
| --- | --- | --- |
| #15 etiquetas y catálogo | #38 integrado, historia cerrada | 130 pruebas; metadatos publicados reales, idempotencia, origen y restricciones |
| #13 revisión protegida | #39 integrado, historia cerrada | 145 pruebas; acceso separado, auditoría, rollback y HTTPS |
| #16 exportación | #40 integrado, historia cerrada | 152 pruebas; bytes reproducibles y lector real del modelo |
| #8 corrección de Figura 6 | #44 integrado, historia cerrada | 162 pruebas; modelo físico del Word, datos legados y reversión |
| #14 señales | #41 actualizado sobre main; esta versión incorpora migración 0006 | 173 pruebas; ráfagas, contradicciones, clases, referencias configuradas y revisión |

La migración 0005 es la alineación física con la Memoria. La migración de
señales se trasladó a 0006, sin reescribir migraciones ya integradas. La API
mantiene el catálogo registrado previamente y el límite de versión de veinte
caracteres del Word. No se duplican ramas ni se copian documentos/corpus reales.

Los valores iniciales de #14 se adoptan por criterio técnico delegado por el
usuario. Los controles legibles muestran 0/20 falsos marcados intercalados y
2/20 al agrupar clases; no se oculta este coste ni se afirma calibración real.
Una marca requiere revisión, no constituye rechazo ni atribución de intención.

## Pendientes que no se presentan como completados

- #4: el Word ya fue contrastado; falta registrar acuerdo con el cliente Android
  sobre el contrato actualizado y el registro previo de versiones.
- #17: PR #43 incorpora retención automática local, consola desactivada y revisión
  de respaldo 0006. El despliegue debe programar copias, custodiar claves y
  revisar logs externos; no equivale a infraestructura configurada.
- #18: CI existe, falta exigir su check en protección de main.
- #19/#20: infraestructura Azure, red privada, secretos y TLS del despliegue.
- Para operación de #14: referencias de evaluación anonimizadas autorizadas y
  calibración con tráfico permitido; los tests usan solo referencias sintéticas.

La autorización más reciente del usuario permite completar tareas e integrar
cambios verificados. Las restricciones iniciales limitadas de merge ya no son
el bloqueo vigente. Esto no proporciona credenciales Azure ni permisos GitHub
que el entorno no posea. No se ha entrenado ni desplegado por pasar tests locales.
