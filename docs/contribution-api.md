# API de aportes optativos — #1

La app comprueba consentimiento y anonimiza antes de enviar. Android clasifica
con Char-CNN/LiteRT local; el backend recibe la etiqueta y no tiene inferencia,
modelo ni acceso al SMS original. No se comunica con dispositivos por iniciativa propia.

POST /api/v1/contributions exige HTTPS y X-API-Key, limita solicitudes, valida
UTF-8/esquema, normaliza y guarda aporte y etiqueta transaccionalmente en estado
pending. /health no abre conexión a PostgreSQL y no requiere autenticación.
Aplicar migraciones antes de servir tráfico. No hay rutas de revisión/exportación.

Prueba real: Uvicorn TLS local con certificado efímero de prueba, httpx con
verificación de certificado activa y PostgreSQL 17. Se verifica 201 y registro
pendiente; pruebas adicionales de 401, 422 y rechazo HTTP sin persistir.
No equivale a despliegue ni a verificación de infraestructura HTTPS pública.

Servidor local TLS (certificados propios fuera del repo):

```sh
uv run alembic upgrade head
uv run uvicorn smishing_backend.main:app --host 127.0.0.1 --port 8443 --ssl-certfile "$TLS_CERT_PATH" --ssl-keyfile "$TLS_KEY_PATH" --no-access-log --no-proxy-headers
```

No confiar en encabezados de proxy sin una topología explícita. La prueba TLS
desactiva proxy_headers. El comando evita access logs con IP/ruta; #17 completa
política y retención. Errores SQL se traducen a 503 genérico sin parámetros.

Pendiente: acuerdo de contrato móvil #4, reanonimización #11 y cuarentena #12;
no desplegar recepción pública hasta completar esas capas. Duplicados/409 en
#10. Un fallo de base no confirma recepción; la app necesita política de reintento.

Ramas: integration/1-prerequisites reúne únicamente ramas de trabajo de #7 y #9
con autorización explícita; no se ha integrado ningún PR en main.
El PR de #1 apunta a esa base para mostrar solo integración. Tras integrar las
dependencias en main, retarget a main y comprobar que el diff contiene solo #1.
