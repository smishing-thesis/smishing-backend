# Despliegue en Azure App Service — #19 y #20

Estado al 23 de noviembre de 2026: existe un App Service vacío (`smishy-backend`,
Brasil Sur, Linux, Python 3.12, publicación Code, plan Free F1) con HTTPS solo y TLS
mínimo 1.2 configurados a mano en el portal. **El backend no está desplegado en él**
y no hay base de datos en Azure. Este documento describe lo que el código ya soporta
y el procedimiento previsto; nada de lo que sigue se ha ejecutado en Azure.

## Qué cambia en el código

App Service termina TLS en su entrada y reenvía HTTP al contenedor. Para eso existe
el modo `SMISHING_BEHIND_TLS_PROXY=true`, apagado por defecto:

- El runner (`python -m smishing_backend.server`) escucha en `SMISHING_HOST`
  (por defecto 0.0.0.0) y en el puerto de `PORT`, `WEBSITES_PORT` o `SMISHING_PORT`
  (por defecto 8000, el que espera App Service para Python). No usa TLS propio ni
  exige `TLS_CERT_PATH`. Sigue sin access logs ni proxy headers de uvicorn.
- Un middleware marca la solicitud como HTTPS solo si llega **exactamente un**
  `X-Forwarded-Proto: https`. Sin él, con `http` o repetido, el esquema sigue siendo
  `http` y las rutas de aportes responden 400 sin guardar nada.
- No se lee `X-Forwarded-For` ni la dirección del cliente. Por eso la cuota por par de
  red pasa a ser la global (todo llega del proxy): la protección real es la cuota
  global, y un cliente abusivo puede agotarla para todos. Es una limitación conocida;
  limitar por cliente exigiría leer su dirección, lo que el proyecto evita.
- Supone que el puerto de la aplicación solo es alcanzable a través del proxy. Un
  cliente que llegara directo podría falsear el encabezado. En App Service el
  contenedor no se expone por otra vía, pero **no se ha comprobado**.

## Variables y ajustes de la aplicación

| Ajuste | Valor |
| --- | --- |
| SMISHING_BEHIND_TLS_PROXY | true |
| SMISHING_DATABASE_URL | `postgresql+psycopg://usuario:clave@host/base`; Key Vault o ajuste de la app, nunca el repositorio |
| SMISHING_API_KEY | clave de la app; para rotar con solapamiento, SMISHING_API_KEYS con una lista JSON |
| SMISHING_LOG_DIR | un directorio bajo /home, p. ej. /home/smishing-logs |
| PYTHONPATH | /home/site/wwwroot/src |
| SCM_DO_BUILD_DURING_DEPLOYMENT | true |
| WEBSITES_PORT | 8000 |

Comando de inicio: `python -m smishing_backend.server`.

Configuración del recurso (#20): solo HTTPS activado, TLS mínimo 1.2, **lista de
orígenes CORS vacía** (la app móvil no la necesita y el código no emite
encabezados CORS), Application Insights apagado (es telemetría), registros de la
plataforma (aplicación, servidor web, solicitudes detalladas) apagados o revisados
para que no queden URL, IP ni cuerpos, FTP desactivado.

## Dependencias

App Service construye con `requirements.txt`, no con `uv.lock`. El archivo se genera
desde el lock y una prueba (`tests/test_proxy_mode.py`) comprueba que coincide en
versiones y que no incluye herramientas de desarrollo. Tras cambiar dependencias:

```sh
uv export --locked --no-dev --no-emit-project --format requirements-txt -o requirements.txt
```

Incluye el modelo de spaCy `es_core_news_lg` como enlace directo a GitHub.

## Procedimiento previsto

1. Zip con `src/`, `migrations/`, `alembic.ini` y `requirements.txt`, sin pruebas,
   documentos ni `.venv`.
2. `az webapp deploy --resource-group smishy-rg --name smishy-backend --src-path app.zip --type zip`.
3. En la consola SSH de la app: `cd /home/site/wwwroot`, `python -m alembic upgrade head` y
   `python -m smishing_backend.catalog --release v1.0.0`. La base de datos solo debe ser
   alcanzable desde la app, así que las migraciones se aplican desde ahí.
4. Comprobar `GET /health` por HTTPS.

## Riesgos conocidos con el plan Free (F1)

- **Sin red privada.** El portal muestra "Virtual network integration: Not supported" y
  "Private endpoint connections: Not supported". No se puede cumplir el criterio de #19
  "la base de datos no es accesible desde internet" con este plan. Lo más cercano sería
  una base con acceso público limitado por firewall, y eso no equivale a lo pedido.
- **Sin Always On:** la app se duerme tras inactividad y la primera solicitud es lenta,
  más con la carga del modelo de spaCy al arrancar. El cliente móvil debe usar tiempos
  de espera generosos y reintentar. Si el arranque supera el límite de Azure
  (unos 230 s por defecto), hay que subirlo.
- **1 GB de memoria y cuota diaria de CPU:** no se ha medido si el modelo de spaCy cabe,
  ni cuánto dura la cuota con tráfico real.
- La suscripción puede no permitir F1 en algunas regiones (ocurrió en East US).

## Lista de verificación (a registrar en #19 y #20)

- [x] HTTPS responde y HTTP redirige con 301 (comprobado desde fuera el 23-11-2026
  sobre el App Service vacío).
- [x] TLS mínimo 1.2 configurado (informado por el equipo; no verificado aquí).
- [ ] El backend desplegado responde `/health` y acepta un lote sintético.
- [ ] Un aporte sin `X-Forwarded-Proto: https` se rechaza en el entorno real.
- [ ] Migraciones y registro del modelo aplicados con el procedimiento anterior.
- [ ] Secretos fuera del repositorio y de los logs; rotar la clave sin cambiar código.
- [ ] Registros de la plataforma revisados.
- [ ] Base de datos sin acceso desde internet (**no alcanzable con el plan Free**).
- [ ] Revisión (8444) y administración (8445) no expuestas: no desplegar esos runners.
