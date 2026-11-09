# Logs y respaldos — #17

Ejecutar el servidor soportado con `uv run python -m smishing_backend.server`,
TLS_CERT_PATH y TLS_KEY_PATH fuera del repositorio. SMISHING_LOG_DIR configura
el directorio (por defecto var/log/smishing-backend). El runner desactiva access
logs y encabezados de proxy y aplica PrivateFormatter al archivo. No añade
handler de consola; cada servicio debe usar su propio directorio de logs. No registrar cuerpos/headers, direcciones, IDs, hashes o versiones por
solicitud. Solo tiempo y evento fijo. Mensajes arbitrarios de dependencias,
args, extras y tracebacks se descartan sin interpolar. No usar logging externo
de peticiones ni SQL echo, ni captura automática de errores con request bodies.

Retención configurada: siete días calendario UTC, seis históricos y un activo.
RetainedEventHandler rota y elimina históricos vencidos al arrancar, antes de
escribir y cada 60 segundos aunque no haya solicitudes. Solo elimina archivos
con su nombre y sufijo de fecha; no limpia otros archivos ni sigue enlaces.
El cierre del handler detiene el mantenimiento. Si el proceso está apagado no
puede ejecutar tareas: la limpieza se realiza al siguiente arranque; el despliegue
debe añadir limpieza externa si requiere vencimiento también durante apagados.
No se promete una purga física desde un proceso que no está ejecutándose.
Usar un proceso por directorio y permisos 0750. Un fallo de escritura produce
un error fijo; no usa el error handler estándar de logging que podría imprimir
el mensaje y argumentos originales. No reenviar logs a colectores sin revisar
su configuración. Los access logs de Azure/proxy y su política se verifican al
implementar #19/#20, no se presentan como configurados aquí.

Respaldos: base dedicada con contributed_message, message_label, model_version,
auditoría reviews, risk_flags y metadatos de migración; nunca el entorno, credenciales, directorios de logs,
archivos del dispositivo o corpus originales. El esquema almacena únicamente
texto aportado anonimizado, etiqueta, versiones y revisión acotada; no hay
campos de dispositivo, remitente o red. El hash y UUID son del aporte, no del
contribuyente. Usar pg_dump de base dedicada, cifrar el respaldo y controlar
acceso; política propuesta de siete días. El servicio no crea respaldos por su
cuenta ni publica exportaciones. Auditar una restauración aislada antes de
adoptar backups. La anonimización tiene los límites de docs/anonymization.md.

Pruebas: solicitudes aceptada y rechazada reales sobre PostgreSQL sintético,
búsqueda de texto, dirección de prueba y metadatos en archivo; excepción con
texto no se imprime. Configuración de retención y mensajes de access log probados.
Revisión de respaldo y restauración sobre el esquema 0006: [política y evidencia](backup-policy.md).
176 pruebas y dos subtests con PostgreSQL real; Ruff, formato y mypy correctos.
Se prueba limpieza al arranque y sin eventos, cierre del hilo y error de disco
sin imprimir el registro original. La revisión del backend no certifica Azure.
