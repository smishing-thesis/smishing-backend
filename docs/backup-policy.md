# Política inicial y evidencia de respaldo — #17

Política técnica inicial propuesta a partir de la delegación del usuario el
8 de noviembre de 2026. No requiere escoger un proveedor distinto de Azure
ni crea recursos, tareas programadas o secretos de producción.

## Recomendación inicial

| Elemento | Política inicial | Estado |
| --- | --- | --- |
| Logs | Eventos permitidos sin SMS, IP o credenciales, 7 días | Handler automático en PR #43; consola de aplicación desactivada |
| Copia de base | Diaria, cifrada y con acceso restringido | Sin programación ni almacenamiento configurados |
| Retención de copias | 7 días | Pendiente de configurar en el almacén elegido |
| Pérdida máxima objetivo (RPO) | 24 horas | Objetivo acorde a copia diaria, no garantía medida |
| Recuperación objetivo (RTO) | 24 horas | Objetivo inicial, requiere simulacro del entorno real |
| Restauración | Antes de despliegue, al cambiar procedimiento/esquema y revisión mensual | Un simulacro local sintético completado |

Respaldar la base dedicada del corpus, su esquema, migraciones y auditoría;
no respaldar variables del proceso, claves, archivos de dispositivos, corpus
originales o carpetas de logs. Mantener el respaldo fuera del repositorio y
la clave de descifrado separada del archivo, con acceso controlado y recuperación
verificada. No improvisar una clave fija de ejemplo ni enviarla por chat.

`pg_dump`/`pg_restore` deben ser compatibles con la versión del servidor.
No copiar volúmenes de PostgreSQL en funcionamiento como sustituto de un
procedimiento de respaldo coherente. Una copia sin restauración probada no
demuestra recuperación. La función de exportación #16 no sustituye al respaldo:
excluye pendientes, rechazados y metadatos necesarios para restaurar el servicio.

## Simulacro realizado

Entorno Cloud, PostgreSQL 17, código funcional fijado a `deca983`, esquema
0006, más cambios de logging de #43. Se crearon dos bases temporales nuevas con sufijo `_test`, sin usar la
base del usuario ni corpus reales. La fuente contenía exclusivamente dos
mensajes sintéticos anonimizados, sus etiquetas y una revisión ficticia.

Pasos efectivamente ejecutados:

1. Crear las bases fuente/destino, aplicar migraciones y sembrar los datos.
2. Generar dump custom con `pg_dump --format=custom --no-owner --no-acl`.
3. Cifrarlo en memoria mediante AES-256-GCM, clave y nonce aleatorios.
4. Alterar el ciphertext y comprobar rechazo por autenticidad.
5. Descifrar el original y restaurar con `pg_restore --exit-on-error`.
6. Comparar recuentos y huellas del contenido; comprobar el trigger de
   cuarentena y que PostgreSQL rechaza un estado no permitido.
7. Eliminar ambas bases y no conservar la clave o el dump en claro.

Resultado: coincidieron 2 aportes, 3 etiquetas, 1 versión de modelo con metadatos reales publicados y 1
revisión. También se restauraron metadatos de migración y la tabla de marcas,
vacía en este caso. El dump tuvo 18329 bytes. La ida/vuelta local pequeña tardó
0.984 segundos: **no mide el RTO de producción ni representa una prueba de carga**.

[Evidencia estructurada](evidence/backup-restore-2026-11-08.json), sin SMS,
credenciales, claves, nombres de bases temporales o datos del contribuyente.
Fue un ensayo efímero, no un respaldo de producción conservado en disco.

## Criterios de backend y condiciones del despliegue

#17 verifica logs sin contenido/red, retención definida/configurada y revisión
de respaldos. El backend usa ahora siete días calendario UTC, mantenimiento
cada 60 segundos sin tráfico y limpieza al arrancar; no duplica eventos en
consola. Se prueba la solicitud aceptada/rechazada, retención y fallo de disco
sin eco. La revisión de tablas y restauración real se realizó sobre 0006.

Esto no equivale a un servicio de backups de producción. Al desplegar #19/#20
se deben configurar almacén, programación diaria, retención de copias, custodia
y recuperación de claves, y desactivar/revisar access logs de Azure y proxies.
Si se exige eliminación durante apagados, debe existir limpieza externa:
un proceso detenido no puede ejecutar su hilo de retención. Estos controles
se registran como condiciones del despliegue; no se simulan como realizados.

RPO/RTO de 24h siguen siendo objetivos iniciales, no garantías operativas.
No se ha desplegado ni se ha conservado un dump real o clave de producción.
