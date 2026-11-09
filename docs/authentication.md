# Decisión de autenticación — #6

Propuesta implementada: X-API-Key compartida por la aplicación, sin IDs de
instalación, cuentas, huellas ni tokens individuales. Se verifica antes de leer
el cuerpo y antes del dominio. Sin claves configuradas, se rechaza todo con 401.
No se registra la credencial ni se guarda en PostgreSQL.

SMISHING_API_KEYS es una lista JSON de claves secretas en el entorno.
SMISHING_API_KEY conserva compatibilidad con la configuración inicial; también
cuenta como clave activa. No definirla si ya fue revocada. Configurar valores
aleatorios de alta entropía en el gestor de secretos, nunca en Git.
Rotación: agregar la nueva clave, reiniciar procesos, distribuir cliente nuevo,
retirar la anterior y reiniciar todos los procesos. Se permite solapamiento;
no hay recarga automática y se debe coordinar la retirada entre réplicas.

Límite explícito: una clave embebida en Android se puede extraer. Autoriza a
quien la conoce; no acredita que la petición proceda de la aplicación oficial
ni garantiza integridad de los aportes. No usarla como frontera única contra
envenenamiento. Cuotas, reanonimización y cuarentena son capas adicionales.
Si se filtra: revocar la clave afectada, rotar, limitar o suspender aportes y
revisar los aportes pendientes; la inferencia local sigue funcionando.
Los logs del proxy/servidor deben excluir encabezados y direcciones (#17).

Alternativa: atestación de aplicación verificada en servidor con desafío y
protección contra replay. Requiere decisiones de proveedor, disponibilidad,
política de tokens y evaluación de privacidad (no retener identidad de dispositivo).
No se implementa ni se afirma una atestación ficticia. Pendiente acuerdo móvil
del mecanismo y ciclo de distribución/rotación; #4 sigue abierto.

Pruebas sintéticas: ausente, inválida, repetida, válida, solapamiento,
revocación por entorno y configuración vacía; 401 antes de parseo y del handler.
La integración del endpoint persistente se hace en #1.
