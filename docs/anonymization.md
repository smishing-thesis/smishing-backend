# Verificación residual — #11

Reglas sms-anonymizer 1.3.0, commit 6f44563b9bdb791f00a616c9850a19e494f84e81.
Se conserva una exportación de su especificación, con procedencia y SHA-256 del
archivo fuente en domain/resources/anonymization-1.3.0.json. No incluye corpus,
listas de nombres de propietarios ni remitentes. Actualizar la especificación
requiere revisión explícita y nuevas pruebas; nunca se lee una rama flotante.

Se reutilizan sus expresiones de enlaces (incluido dominio sin esquema), correo,
teléfono móvil peruano y DNI/RUC con palabra indicadora, y el mismo detector de
nombres: spaCy es_core_news_lg 3.8.0, entidad PER. Dependencia fijada a wheel
oficial de la versión 3.8.0 y hash en uv.lock. No es el modelo de smishing.
El modelo de nombres se carga al arrancar: si falta o difiere la versión, no
se sirve recepción. Fallos de inferencia residual dan 503, nunca se acepta sin
verificar. Se serializa el acceso al detector para evitar estado compartido inseguro.

Se verifica el texto normalizado antes de llamar al repositorio. Los placeholders
canónicos son <URL>, <EMAIL_ADDRESS>, <PHONE_NUMBER>, <ID_NUMBER> y <NAMED_ENTITY>.
Un hallazgo produce 422 genérico, sin persistencia, spans, texto ni tipo de dato.
No se corrige silenciosamente el SMS: la app debe anonimizar antes de enviar.

Límites heredados: teléfonos no peruanos, documentos sin palabra indicadora,
obfuscaciones y nombres omitidos por NER pueden escapar; NER también puede dar
falsos positivos. No se garantiza anonimato perfecto. No se usa la lista privada
de nombres de propietarios del corpus porque identificar contribuyentes sería
incompatible con el servicio. La cuarentena y revisión siguen siendo necesarias.
El detector pesado requiere memoria para vectores y arranque; un proceso por
instancia según #7, sin copiar el modelo a Git. No hay descargas al arrancar.

Pruebas de reglas y NER real con identificadores ficticios y dominios .invalid,
además de rechazo HTTP sin filas y sin texto en logs. La ficha del corpus debe
referenciar esta versión y estos límites al implementar exportación, sin simularla.
