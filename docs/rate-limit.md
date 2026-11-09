# Límites temporales — #7

RateLimiter limita por par inmediato de red y globalmente, ventana fija de 60 s.
Valores propuestos: SMISHING_RATE_LIMIT_PER_MINUTE=60 y
SMISHING_GLOBAL_RATE_LIMIT_PER_MINUTE=600. Se admite una ráfaga en los límites
de ventana; no es una protección volumétrica a nivel de red.
limited_contribution autentica, limita y luego valida el cuerpo. El rechazo es
429 con Retry-After entero en segundos, sin entrar al handler/dominio.
No se confía en X-Forwarded-For. Detrás de proxy todos comparten su cupo; la
integración debe preservar esta limitación o diseñar un proxy de confianza.

Solo memoria: HMAC de dirección con sal aleatoria por ventana. No se almacenan
direcciones en claro, no se escriben contadores en PostgreSQL ni en logs y se
eliminan mapa y sal automáticamente con un temporizador al vencer la ventana,
incluso sin tráfico. La memoria del mapa está acotada por la cuota global.
Los procesos deben llamar close al terminar. No hay identidad persistente.

Límite operativo: una instancia/proceso. Varios workers multiplican los cupos.
No desplegar con múltiples réplicas sin un contador global compartido con TTL y
la misma política de privacidad. No se simula Redis ni una cuota distribuida.
Las pruebas verifican concurrencia, expiración automática, privacidad de logs
y 429 antes del cuerpo. Integración en la ruta persistente pendiente de #1.
