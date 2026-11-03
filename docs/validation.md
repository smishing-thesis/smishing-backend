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
