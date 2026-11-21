# Validación #5

validate_contribution es una dependencia HTTP reutilizable para la integración
de #1; todavía no se monta una ruta de aportes sin persistencia.
Se limita el flujo real a 16384 bytes incluso sin Content-Length. No se confía
en ese encabezado. Se rechazan compresión, codificaciones distintas de UTF-8,
JSON ambiguo por claves repetidas y valores no estándar NaN/Infinity.
Los límites de caracteres se aplican después de normalizar a NFC, reemplazar
controles Cc/Cf por espacios y colapsar espacios Unicode. Se rechazan sustitutos
Unicode no codificables. SHA-256 se calcula sobre UTF-8 normalizado.
Esto no cambia el preprocesamiento de la inferencia Android.

Pruebas con mensajes sintéticos exclusivamente; el harness HTTP devuelve solo
un hash y no representa recepción ni almacenamiento. Todos los errores de
validación tienen código/mensaje genéricos, sin input, contexto ni excepciones.
La integración debe registrar contribution_error_handler y usar esta dependencia.
Los límites siguen siendo la propuesta del contrato #4 pendiente de acuerdo móvil.

## Lote — #48

El lote usa el mismo transporte que el aporte único (JSON UTF-8 estricto, sin
compresión ni claves repetidas) con un límite de 327680 bytes de cuerpo, es decir
20 × 16384. El sobre debe ser exactamente {"contributions": [...]} con 1 a 20
elementos; si no, 422 para todo el lote. Cada elemento se valida por separado
con las reglas del aporte único (NFC, límites, sustitutos, campos extra); uno
inválido no afecta a los demás y se informa como rejected/invalid_contribution.
