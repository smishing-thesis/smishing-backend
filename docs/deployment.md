# Despliegue en Azure App Service — #19 y #20

Estado al 23 de noviembre de 2026: el backend está desplegado a mano en un App Service
(`smishy-backend`, Brasil Sur, Linux, Python 3.12, publicación Code, plan Free F1) con
HTTPS solo y TLS mínimo 1.2 configurados en el portal. **No hay base de datos en
Azure:** por ahora la base es un PostgreSQL gratuito de Render, con acceso externo
(ver [Riesgos](#riesgos-conocidos-con-el-plan-free-f1)). El despliegue no está
automatizado; el procedimiento de abajo es el que se ejecutó y funcionó. Lo que sigue
sin comprobar está marcado en la lista de verificación.

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
| SMISHING_DATABASE_URL | `postgresql+psycopg://usuario:clave@host:5432/base?sslmode=require`; ajuste de la app o Key Vault, nunca el repositorio. Con Render se usa la **External** Database URL (la Internal solo funciona dentro de Render) cambiando el inicio `postgresql://` por `postgresql+psycopg://` y agregando `?sslmode=require`, que hace fallar la conexión en vez de bajar a texto plano |
| SMISHING_API_KEY | clave de la app; para rotar con solapamiento, SMISHING_API_KEYS con una lista JSON |
| SMISHING_LOG_DIR | un directorio bajo /home, p. ej. /home/smishing-logs |
| PYTHONPATH | `src` (relativo; ver la nota de abajo) |
| SCM_DO_BUILD_DURING_DEPLOYMENT | true |
| WEBSITES_PORT | 8000 |

Comando de inicio: `python -m smishing_backend.server`.

**`PYTHONPATH` debe ser `src`, no `/home/site/wwwroot/src`.** Oryx comprime el
resultado del build y lo extrae al arrancar en una carpeta temporal
(`/tmp/<hash>`); en `/home/site/wwwroot` solo queda `output.tar.zst`. Con la ruta
absoluta, el contenedor se cae con `No module named 'smishing_backend'`. La ruta
relativa funciona porque la app arranca desde la carpeta temporal (comprobado el
23-11-2026; se desconoce si Oryx cambiaría ese comportamiento en otra versión).

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

## Procedimiento (ejecutado a mano el 23-11-2026)

Requiere la CLI de Azure con la sesión iniciada (`az login`) en la suscripción
correcta. Apuntar siempre a `smishy-backend` en el grupo `smishy-rg`: la suscripción
puede tener otras apps.

1. Zip solo con archivos versionados, sin pruebas, claves ni archivos sin versionar:

   ```sh
   git archive --format=zip -o app.zip HEAD src migrations alembic.ini requirements.txt
   ```

2. Desplegar:

   ```sh
   az webapp deploy --resource-group smishy-rg --name smishy-backend --src-path app.zip --type zip
   ```

   El build de Oryx tardó unos 106 s (instala los 56 paquetes, incluido spaCy). Si el
   contenedor no arranca, la CLI espera hasta 10 minutos, da el despliegue por fallido
   y **deja la app detenida**; el motivo está en los registros de arranque
   (`az webapp log download`). Guardar un ajuste de la app la reinicia.
3. Aplicar las migraciones y registrar el modelo **desde un equipo con el entorno del
   proyecto instalado**, con `SMISHING_DATABASE_URL` puesta solo en esa terminal (sin
   escribirla en un comando, para que no quede en el historial):

   ```sh
   alembic upgrade head
   alembic current          # debe decir 0006 (head)
   python -m smishing_backend.catalog --release v1.0.0
   ```

   El registro del modelo lee la publicación con `gh`, que debe tener sesión iniciada.
   Esto funciona porque la base de Render admite conexiones externas. Con una base
   privada habría que aplicarlas desde la consola SSH de la app (`cd
   /home/site/wwwroot` y los mismos comandos); **ese camino no se ha probado**.
4. Comprobar `GET /health`, `/docs` y `/openapi.json` por HTTPS, y enviar un aporte
   sintético con la clave de la app: debe responder 201 con `status: pending`.
   La primera respuesta tras un periodo de inactividad tardó unos 78 s.

## Riesgos conocidos con el plan Free (F1)

- **Sin red privada.** El portal muestra "Virtual network integration: Not supported" y
  "Private endpoint connections: Not supported". No se puede cumplir el criterio de #19
  "la base de datos no es accesible desde internet" con este plan. Lo más cercano sería
  una base con acceso público limitado por firewall, y eso no equivale a lo pedido.
- **Sin Always On:** la app se duerme tras inactividad y la primera solicitud es lenta,
  más con la carga del modelo de spaCy al arrancar: **unos 78 s** en la primera
  solicitud tras el despliegue (una sola medición; no se midió un segundo arranque en
  frío). El cliente móvil debe usar tiempos de espera generosos y reintentar. El
  límite de Azure para arrancar es de unos 230 s por defecto y no se superó.
- **1 GB de memoria y cuota diaria de CPU:** el modelo de spaCy cabió y la app
  respondió, pero no se ha medido el consumo ni cuánto dura la cuota con tráfico real.
- **La base de datos es pública.** Está en Render, accesible desde internet y
  protegida solo por contraseña y TLS (`sslmode=require`). Las bases gratuitas de
  Render pueden caducar: revisar la fecha en su panel. Cambiar de base solo exige
  cambiar `SMISHING_DATABASE_URL`, repetir las migraciones y registrar el modelo; los
  datos no se mueven solos.
- La suscripción puede no permitir F1 en algunas regiones (ocurrió en East US).

## Lista de verificación (a registrar en #19 y #20)

- [x] HTTPS responde y HTTP redirige con 301 (comprobado desde fuera el 23-11-2026
  sobre el App Service vacío).
- [x] TLS mínimo 1.2 configurado (informado por el equipo; no verificado aquí).
- [x] El backend desplegado responde `/health`, `/docs` y `/openapi.json` con 200
  (23-11-2026).
- [x] Un aporte sintético individual con clave responde 201 `pending` por HTTPS: la
  clave, la conexión Azure → Render y `X-Forwarded-Proto` funcionan juntos.
- [x] Sin clave, `POST /api/v1/contributions` responde 401.
- [ ] Un lote sintético (`/batch`) en el entorno real: no probado.
- [ ] Un aporte sin `X-Forwarded-Proto: https` se rechaza en el entorno real: no se ha
  podido comprobar, porque el proxy de App Service siempre lo agrega.
- [x] Migraciones (0006) y registro del modelo `v1.0.0` aplicados, desde un equipo
  externo y contra la base de Render, no desde la consola de la app.
- [x] `SMISHING_DATABASE_URL` y `SMISHING_API_KEY` están como ajustes de la app, fuera
  del repositorio (comprobado el formato de la URL sin mostrar el valor).
- [ ] Rotar la clave sin cambiar código (`SMISHING_API_KEYS`): no probado.
- [ ] Secretos fuera de los logs.
- [ ] Registros de la plataforma revisados.
- [ ] Base de datos sin acceso desde internet (**no alcanzable con el plan Free**).
- [ ] Revisión (8444) y administración (8445) no expuestas: no desplegar esos runners.
