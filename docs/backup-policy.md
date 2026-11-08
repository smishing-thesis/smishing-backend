# Política inicial y evidencia de respaldo — #17

Política técnica inicial propuesta a partir de la delegación del usuario el
8 de noviembre de 2026. No requiere escoger un proveedor distinto de Azure
ni crea recursos, tareas programadas o secretos de producción.

## Recomendación inicial

| Elemento | Política inicial | Estado |
| --- | --- | --- |
| Logs | Eventos permitidos sin SMS, IP o credenciales, 7 días | Código funcional en PR #33; falta verificar retención de consola |
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

Entorno Cloud, PostgreSQL 17, código funcional fijado a `1dc7862`, esquema
0005. Se crearon dos bases temporales nuevas con sufijo `_test`, sin usar la
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

Resultado: coincidieron 2 aportes, 3 etiquetas, 1 referencia de modelo y 1
revisión. También se restauraron metadatos de migración y la tabla de marcas,
vacía en este caso. El dump tuvo 17392 bytes. La ida/vuelta local pequeña tardó
0.96 segundos: **no mide el RTO de producción ni representa una prueba de carga**.

[Evidencia estructurada](evidence/backup-restore-2026-11-08.json), sin SMS,
credenciales, claves, nombres de bases temporales o datos del contribuyente.
Fue un ensayo efímero, no un respaldo de producción conservado en disco.

## Lo que aún impide cerrar #17

- Elegir y configurar almacén, programación diaria, retención y custodia de claves.
- Verificar permisos y una recuperación con la configuración que se desplegará.
- Comprobar retención de consola en la plataforma. El handler local existente
  rota cuando recibe eventos: seis históricos no prueban borrado estricto por
  edad si el servicio queda detenido. Definir/ensayar limpieza operativa o
  automatizar esa expiración antes de prometer una retención temporal estricta.

Este documento reduce incertidumbre con evidencia local, pero no declara
operaciones inexistentes ni cierra #17/#19/#20. No cambia código de ejecución.
