# Ficha del corpus de aportes del backend

Estado: corpus de recepción y revisión, sin publicación de datos ni despliegue
declarado. No se documentan recuentos de mensajes reales porque no se han medido.
La API recibe aportes voluntarios ya anonimizados; Android conserva consentimiento
e inferencia local. El backend no verifica identidad de contribuyentes ni conserva
un identificador para relacionar sus aportes.

## Datos y procedencia

Cada aporte contiene texto anonimizado y etiqueta automática declarada por la
app (`safe` o `smishing`), vinculada con su versión de modelo. La etiqueta no se
presenta como verdad verificada. Se guarda fecha de recepción del servidor y un
hash SHA-256 del contenido normalizado. No se reciben teléfonos, remitentes,
contactos, fechas originales del SMS, IDs de instalación ni metadatos de red.

El texto se normaliza a NFC, se sustituyen controles por espacios y se colapsan
espacios antes de calcular el hash. El límite actual es 2048 puntos Unicode
normalizados y 16384 bytes de cuerpo JSON UTF-8. Diferencias solo de espacios
o representación canónica no crean ejemplos distintos.

## Verificación residual y sus límites

Reglas `sms-anonymizer` **1.3.0**, fuente
`6f44563b9bdb791f00a616c9850a19e494f84e81`, con procedencia y huella del archivo
fuente en `domain/resources/anonymization-1.3.0.json`. Nombres: spaCy
`es_core_news_lg` **3.8.0**, entidades PER. No es el clasificador de smishing.

Se rechazan enlaces/dominios visibles, correos, móviles peruanos, DNI/RUC con
palabra indicadora y nombres detectados. Los placeholders canónicos son <URL>,
<EMAIL_ADDRESS>, <PHONE_NUMBER>, <ID_NUMBER> y <NAMED_ENTITY>. El rechazo no guarda
el SMS recibido ni sus fragmentos y devuelve un error genérico.

No se garantiza anonimización perfecta: pueden escapar teléfonos no peruanos,
documentos sin palabra indicadora, obfuscaciones y nombres omitidos por NER;
también hay falsos positivos. No se usan listas de nombres de propietarios del
corpus ni se intenta identificar a quien contribuye. Un cambio de reglas/modelo
de nombres exige actualizar esta ficha y repetir las pruebas.

## Calidad y uso

Todo aporte nace pendiente. Solo los aceptados mediante revisión registrada
pueden seleccionarse para entrenamiento; los pendientes o rechazados no se
consideran datos de entrenamiento aprobados. La cuarentena y revisión no son
una prueba de que todos los mensajes estén libres de errores o sesgos.

API key compartida, cuotas y deduplicación reducen algunas formas de abuso;
no acreditan procedencia oficial ni impiden todos los intentos de envenenamiento.
No se afirma cobertura estadística, representatividad, balance o rendimiento
del modelo a partir de esta recepción. Los ensayos del backend usan únicamente
textos sintéticos y no aportan recuentos de un corpus de investigación real.

No se adjuntan archivos de mensajes, exportaciones o corpus al repositorio. La
exportación, procedencia de etiquetas manuales y señales adicionales tienen
sus propias historias; deben actualizar esta ficha cuando se integren. Su código
en otros PR no se presenta aquí como capacidad ya publicada en main.

Uso previsto: investigación/reentrenamiento después de revisión y controles de
acceso. No usar aportes sin verificar para evaluar rendimiento del modelo ni
mezclar entrenamiento con la evaluación reservada. Toda distribución requiere
revisión del equipo y de las condiciones aplicables al corpus.

Verificación #11: pruebas sintéticas de enlaces, correo, teléfono, documentos,
nombres, placeholders y fallo del detector; pruebas HTTP con PostgreSQL que
comprueban rechazo sin filas y sin eco de contenido. Véase
[anonimización](anonymization.md) para comandos, límites y dependencias.
